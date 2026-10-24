"""Folder previews use direct images and invalidate caches independently of dir mtime."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

import archive_core


class FolderCoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='file-tripitaka-folder-core-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.folder = self.root / '日本語 한글 images.zip'
        self.folder.mkdir()
        self.cache = self.root / 'cache'

    def page(self, name, color, size=(90, 180)):
        path = self.folder / name
        Image.new('RGB', size, color).save(path, 'PNG')
        return path

    def test_only_direct_regular_images_are_naturally_ordered(self):
        self.page('10.PNG', 'blue')
        self.page('2.png', 'green')
        self.page('1.png', 'red')
        (self.folder / 'not-image.txt').write_text('ignore')
        subfolder = self.folder / '0.png'
        subfolder.mkdir()
        Image.new('RGB', (20, 20), 'purple').save(subfolder / 'page.png')
        self.assertEqual([name for name, _ in archive_core.image_entries(str(self.folder))],
                         ['1.png', '2.png', '10.PNG'])
        self.assertEqual(archive_core.first_image(self.folder), (self.folder / '1.png').read_bytes())

    def test_empty_and_nested_image_only_folders_are_not_sources(self):
        with self.assertRaisesRegex(ValueError, '폴더'):
            archive_core.image_entries(self.folder)
        subfolder = self.folder / 'child'
        subfolder.mkdir()
        Image.new('RGB', (20, 20), 'red').save(subfolder / 'page.png')
        with self.assertRaisesRegex(ValueError, '폴더'):
            archive_core.cover(self.folder, self.cache)

    def test_single_pair_triple_sampling_order_and_fewer_pages(self):
        colors = ['red', 'green', 'blue', 'yellow', 'purple', 'orange']
        for index, color in enumerate(colors, 1):
            self.page(f'{index}.png', color)
        single = archive_core.cover(self.folder, self.cache)
        pair = archive_core.cover(self.folder, self.cache, 2)
        triple = archive_core.cover(self.folder, self.cache, 3)
        ratio = archive_core.cover(self.folder, self.cache, 3, '비율 보기')
        self.assertEqual(single.getpixel((0, 0)), (255, 0, 0))
        gap = max(2, round(180 * 6 / 340))
        xs = [45 + i * (90 + gap) for i in range(3)]
        self.assertEqual([pair.getpixel((x, 90))[:3] for x in xs[:2]],
                         [(0, 128, 0), (255, 0, 0)])
        self.assertEqual([triple.getpixel((x, 90))[:3] for x in xs],
                         [(0, 0, 255), (0, 128, 0), (255, 0, 0)])
        self.assertEqual([ratio.getpixel((x, 90))[:3] for x in xs],
                         [(128, 0, 128), (0, 0, 255), (255, 0, 0)])
        pair_ratio = archive_core.cover(self.folder, self.cache, 2, '비율 보기')
        self.assertEqual(pair_ratio.getpixel((45, 90))[:3], (255, 255, 0))
        for name in ('2.png', '3.png', '4.png', '5.png', '6.png'):
            (self.folder / name).unlink()
        self.assertEqual(archive_core.cover(self.folder, self.cache, 3).size, single.size)

    def test_automatic_and_edited_cache_notice_in_place_image_changes(self):
        page = self.page('1.png', 'red')
        self.page('2.png', 'green')
        directory_time = self.folder.stat()
        initial_signature = archive_core.source_signature(self.folder)
        original = archive_core.cover(self.folder, self.cache)
        recipe = {'0': {'entry': '1.png', 'box': [0, 0, 1, 1]}}
        original_edit = archive_core.render_edited_cover(self.folder, self.cache, recipe)
        self.assertEqual(original.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(original_edit.getpixel((0, 0)), (255, 0, 0))
        before = page.stat()
        self.page('1.png', 'blue')
        os.utime(page, ns=(before.st_atime_ns, before.st_mtime_ns + 2_000_000_000))
        os.utime(self.folder, ns=(directory_time.st_atime_ns, directory_time.st_mtime_ns))
        self.assertNotEqual(archive_core.source_signature(self.folder), initial_signature)
        self.assertEqual(archive_core.cover(self.folder, self.cache).getpixel((0, 0)), (0, 0, 255))
        self.assertEqual(archive_core.render_edited_cover(self.folder, self.cache, recipe).getpixel((0, 0)),
                         (0, 0, 255))

    def test_cached_folder_does_not_inherit_new_subfolder_or_non_image_changes(self):
        self.page('1.png', 'red')
        original = archive_core.source_signature(self.folder)
        archive_core.cover(self.folder, self.cache)
        (self.folder / 'notes.txt').write_text('notes')
        subfolder = self.folder / 'child'
        subfolder.mkdir()
        Image.new('RGB', (20, 20), 'blue').save(subfolder / 'page.png')
        self.assertEqual(archive_core.source_signature(self.folder), original)
        with patch.object(archive_core, 'decode_thumbnail', side_effect=AssertionError('cache not reused')):
            self.assertEqual(archive_core.cover(self.folder, self.cache).getpixel((0, 0)), (255, 0, 0))

    def test_add_remove_and_rename_pages_invalidate_order(self):
        self.page('2.png', 'green')
        original = archive_core.source_signature(self.folder)
        self.assertEqual(archive_core.cover(self.folder, self.cache).getpixel((0, 0)), (0, 128, 0))
        page = self.page('1.png', 'red')
        self.assertNotEqual(archive_core.source_signature(self.folder), original)
        self.assertEqual(archive_core.cover(self.folder, self.cache).getpixel((0, 0)), (255, 0, 0))
        page.rename(self.folder / '3.png')
        self.assertEqual(archive_core.cover(self.folder, self.cache).getpixel((0, 0)), (0, 128, 0))
        (self.folder / '2.png').unlink()
        self.assertEqual(archive_core.cover(self.folder, self.cache).getpixel((0, 0)), (255, 0, 0))

    def test_edited_selection_crops_original_and_keeps_sources_unchanged(self):
        image = Image.new('RGB', (200, 100), 'red')
        image.paste('blue', (100, 0, 200, 100))
        image.save(self.folder / '1.png')
        self.page('2.png', 'green')
        sources = {path.name: path.read_bytes() for path in self.folder.iterdir()}
        recipe = {'0': {'entry': '1.png', 'box': [0.5, 0, 1, 1]}}
        cropped = archive_core.render_edited_cover(self.folder, self.cache, recipe)
        self.assertEqual(cropped.size, (100, 100))
        self.assertEqual(cropped.getpixel((0, 0)), (0, 0, 255))
        self.assertEqual({path.name: path.read_bytes() for path in self.folder.iterdir()}, sources)
        # Missing saved page falls back to the automatic page for its slot.
        stale = {'0': {'entry': 'removed.png', 'box': [0, 0, 1, 1]}}
        self.assertEqual(archive_core.render_edited_cover(self.folder, self.cache, stale).getpixel((0, 0)),
                         (255, 0, 0))

    def test_archive_previews_still_work_beside_folder_previews(self):
        page = self.page('1.png', 'red')
        archive = self.root / 'example.cbz'
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.writestr('1.png', page.read_bytes())
        for source in (self.folder, archive):
            with self.subTest(source=source):
                self.assertEqual(archive_core.cover(source, self.cache).getpixel((0, 0)), (255, 0, 0))

    def test_traversal_and_unsupported_entries_never_open_a_file(self):
        self.page('1.png', 'red')
        names = ('../outside.png', 'child/image.png', r'child\image.png', '/tmp/outside.png',
                 r'C:\outside.png', 'C:outside.png', '.', '..', 'bad\0.png', 'notes.txt')
        with patch.object(archive_core.os, 'open', side_effect=AssertionError('unsafe open')):
            for name in names:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    archive_core.read_image_entry(self.folder, (name, 1))

    def test_symlinks_are_not_pages_and_cannot_be_read(self):
        self.page('1.png', 'red')
        outside = self.root / 'outside.png'
        Image.new('RGB', (20, 20), 'blue').save(outside)
        link = self.folder / '0.png'
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable to this user')
        self.assertEqual([name for name, _ in archive_core.image_entries(self.folder)], ['1.png'])
        with patch.object(archive_core.os, 'open', side_effect=AssertionError('symlink followed')):
            with self.assertRaises(ValueError):
                archive_core.read_image_entry(self.folder, ('0.png', outside.stat().st_size))

    def test_changed_or_oversized_page_is_rejected_before_unbounded_read(self):
        page = self.page('1.png', 'red')
        with patch.object(archive_core, 'MAX_IMAGE', 8):
            with self.assertRaisesRegex(ValueError, '64MB'):
                archive_core.read_image_entry(self.folder, ('1.png', 1))
        original = page.stat()
        # Replace the page after validation, before opening the descriptor.
        real_open = os.open
        def replace_then_open(path, flags):
            replacement = self.folder / 'replacement.tmp'
            replacement.write_bytes(b'replaced page data')
            replacement.replace(page)
            return real_open(path, flags)
        with patch.object(archive_core.os, 'open', side_effect=replace_then_open):
            with self.assertRaises(OSError):
                archive_core.read_image_entry(self.folder, ('1.png', original.st_size))


if __name__ == '__main__':
    unittest.main()
