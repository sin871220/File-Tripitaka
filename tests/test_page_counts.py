"""Total image counts travel with cached thumbnails without eager rescans."""
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image
from PIL.PngImagePlugin import PngInfo

import archive_core as core


class PageCounts(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.cache = self.root / 'cache'
        data = io.BytesIO()
        Image.new('RGB', (24, 36), '#3471ae').save(data, format='PNG')
        self.pixels = data.getvalue()
        self.archive = self.root / 'Library.cbz'
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for index in range(7):
                archive.writestr(f'pages/{index + 1}.png', self.pixels)
            archive.writestr('notes.txt', 'not a page')
            archive.writestr('__MACOSX/ignored.png', self.pixels)
        self.folder = self.root / 'Images'
        self.folder.mkdir()
        for index in range(5):
            (self.folder / f'{index + 1}.png').write_bytes(self.pixels)
        (self.folder / 'notes.txt').write_text('not a page')
        nested = self.folder / 'Nested'
        nested.mkdir()
        (nested / 'excluded.png').write_bytes(self.pixels)

    def overwrite_metadata(self, target, count=None):
        with Image.open(target) as cached:
            image = cached.copy()
        metadata = PngInfo()
        if count is not None:
            metadata.add_text('page_count', count)
        image.save(target, format='PNG', pnginfo=metadata)

    def test_total_is_not_preview_count_and_is_saved_in_png(self):
        original = self.archive.read_bytes()
        for count in (1, 2, 3):
            with self.subTest(count=count), patch.object(core, 'image_entries', wraps=core.image_entries) as listing:
                result = core.cover(self.archive, self.cache, count)
                self.assertEqual(result.info['page_count'], 7)
                self.assertIsInstance(result.info['page_count'], int)
                listing.assert_called_once_with(self.archive.resolve())
        for target in self.cache.glob('*.png'):
            with Image.open(target) as cached:
                self.assertEqual(cached.info['page_count'], '7')
        self.assertEqual(self.archive.read_bytes(), original)

    def test_valid_archive_cache_needs_no_listing_or_decode(self):
        first = core.cover(self.archive, self.cache)
        with patch.object(core, 'image_entries', side_effect=AssertionError('Unexpected rescan')), \
                patch.object(core, 'decode_thumbnail', side_effect=AssertionError('Unexpected decode')):
            cached = core.cover(self.archive, self.cache)
        self.assertEqual(cached.info['page_count'], 7)
        self.assertEqual(cached.tobytes(), first.tobytes())

    def test_legacy_and_malformed_cache_are_repaired_without_decoding(self):
        first = core.cover(self.archive, self.cache)
        target, = self.cache.glob('*.png')
        for value in (None, '', '-3', '0', 'abc', '99999999999', '２', '2147483648'):
            with self.subTest(value=value):
                self.overwrite_metadata(target, value)
                with patch.object(core, 'image_entries', wraps=core.image_entries) as listing, \
                        patch.object(core, 'decode_thumbnail', side_effect=AssertionError('Unexpected decode')):
                    cached = core.cover(self.archive, self.cache)
                listing.assert_called_once_with(self.archive.resolve())
                self.assertEqual(cached.info['page_count'], 7)
                self.assertEqual(cached.tobytes(), first.tobytes())
                with Image.open(target) as saved:
                    self.assertEqual(saved.info['page_count'], '7')

    def test_unwritable_legacy_cache_still_returns_image_and_count(self):
        core.cover(self.archive, self.cache)
        target, = self.cache.glob('*.png')
        self.overwrite_metadata(target)
        with patch.object(core, '_save_cover_cache', side_effect=PermissionError('read only')):
            cached = core.cover(self.archive, self.cache)
        self.assertEqual(cached.info['page_count'], 7)

    def test_folder_count_excludes_subfolders_and_updates_when_images_change(self):
        for count in (1, 3):
            with self.subTest(count=count):
                self.assertEqual(core.cover(self.folder, self.cache, count).info['page_count'], 5)
                self.assertEqual(core.cover(self.folder, self.cache, count).info['page_count'], 5)
        (self.folder / 'added.png').write_bytes(self.pixels)
        self.assertEqual(core.cover(self.folder, self.cache).info['page_count'], 6)
        (self.folder / 'added.png').unlink()
        (self.folder / '1.png').unlink()
        self.assertEqual(core.cover(self.folder, self.cache).info['page_count'], 4)

    def test_edited_covers_keep_total_across_samples_and_cache_repair(self):
        for source, expected, entry in ((self.archive, 7, 'pages/2.png'), (self.folder, 5, '2.png')):
            for count in (1, 2, 3):
                with self.subTest(source=source.name, count=count):
                    recipes = {'0': {'entry': entry, 'box': [0.1, 0.1, 0.9, 0.9]}}
                    image = core.render_edited_cover(source, self.cache, recipes, count)
                    self.assertEqual(image.info['page_count'], expected)
                    with patch.object(core, 'decode_preview', side_effect=AssertionError('Unexpected decode')):
                        cached = core.render_edited_cover(source, self.cache, recipes, count)
                    self.assertEqual(cached.info['page_count'], expected)
                    self.assertEqual(cached.tobytes(), image.tobytes())
        for target in self.cache.glob('*.png'):
            self.overwrite_metadata(target)
        with patch.object(core, 'decode_preview', side_effect=AssertionError('Unexpected decode')):
            cached = core.render_edited_cover(self.archive, self.cache,
                                             {'0': {'entry': 'pages/2.png', 'box': [0.1, 0.1, 0.9, 0.9]}}, 3)
        self.assertEqual(cached.info['page_count'], 7)

    def test_sevenzip_supported_entry_count_uses_existing_listing(self):
        path = self.root / 'Library.7z'
        path.write_bytes(b'synthetic fixture')
        listing = '\n\n'.join(f'Path = pages/{index}.png\nSize = {len(self.pixels)}\nFolder = -'
                              for index in range(1, 5))
        listing += '\n\nPath = notes.txt\nSize = 1\nFolder = -'
        with patch.object(core, 'sevenzip', return_value='synthetic-7z'), \
                patch.object(core, 'command', return_value=SimpleNamespace(stdout=listing.encode())) as command, \
                patch.object(core, 'read_image_entry', return_value=self.pixels):
            image = core.cover(path, self.cache, 2)
        self.assertEqual(image.info['page_count'], 4)
        command.assert_called_once()


if __name__ == '__main__':
    unittest.main()
