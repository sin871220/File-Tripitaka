"""Folder crops follow verified image contents without changing source folders."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from thumbnail_edits import (QUICK_BYTES, ThumbnailEditStore,
                             ThumbnailEditDatabaseError,
                             ThumbnailFileChangedError,
                             ThumbnailEditCancelledError)
import thumbnail_edits as edits


class FolderEdits(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.folder = self.root / 'Image collection'
        self.folder.mkdir()
        for name, content in (('page-10.png', b'tenth page'),
                              ('page-2.JPG', b'second page'),
                              ('page-1.png', b'first page')):
            (self.folder / name).write_bytes(content)
        self.database = self.root / 'settings' / 'thumbnail_edits.json'
        self.store = ThumbnailEditStore(self.database)
        self.box = [0.1, 0.2, 0.9, 0.8]

    def save(self, folder=None, slot=0, entry='page-1.png'):
        self.store.set(folder or self.folder, slot, entry, self.box)

    def source_bytes(self, folder=None):
        return {child.name: child.read_bytes() for child in (folder or self.folder).iterdir()
                if child.is_file()}

    @contextmanager
    def windows_cached_directory_stats(self):
        """Emulate Win32 enumeration metadata with no device/file identity."""
        real_scandir = os.scandir

        @contextmanager
        def cached_listing(path):
            with real_scandir(path) as listing:
                entries = []
                for child in listing:
                    info = child.stat(follow_symlinks=False)
                    cached = SimpleNamespace(st_mode=info.st_mode, st_size=info.st_size,
                        st_mtime_ns=info.st_mtime_ns, st_ctime_ns=info.st_ctime_ns,
                        st_dev=0, st_ino=0)
                    entries.append(SimpleNamespace(name=child.name,
                        stat=lambda *args, _cached=cached, **kwargs: _cached))
                yield iter(entries)

        with patch('thumbnail_edits.os.scandir', side_effect=cached_listing):
            yield

    def test_windows_directory_cached_ids_allow_save_restart_copy_and_reset(self):
        original = self.source_bytes()
        duplicate = self.root / 'Copied album'
        shutil.copytree(self.folder, duplicate)
        with self.windows_cached_directory_stats():
            self.save()
            self.assertEqual(self.store.get(self.folder)['0']['box'], self.box)
            restarted = ThumbnailEditStore(self.database)
            self.assertEqual(restarted.get(duplicate), restarted.get(self.folder))
            snapshot = dict(edits._folder_signature(self.folder)[2])
            for name, signature in snapshot.items():
                self.assertEqual(signature, edits._file_signature(self.folder / name))
            self.assertTrue(restarted.reset(duplicate, 0))
            self.assertIsNone(self.store.get(self.folder))
        self.assertEqual(self.source_bytes(), original)

    def test_windows_directory_cached_ids_do_not_hide_same_size_file_replacement(self):
        with self.windows_cached_directory_stats():
            self.save()
            signature = edits._folder_signature(self.folder)
            image = self.folder / 'page-1.png'
            info = image.stat()
            replacement = self.root / 'replacement.png'
            replacement.write_bytes(b'x' * info.st_size)
            os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
            replacement.replace(image)
            with self.assertRaises(ThumbnailFileChangedError):
                edits._folder_digest(self.folder, signature, full=True)
            self.assertIsNone(self.store.get(self.folder))
            self.assertIsNone(ThumbnailEditStore(self.database).get(self.folder))

    def test_three_slots_deep_copy_and_sources_are_never_changed(self):
        original = self.source_bytes()
        self.save()
        self.save(slot=1, entry='page-2.JPG')
        self.save(slot=2, entry='page-10.png')
        slots = self.store.get(self.folder)
        self.assertEqual(set(slots), {'0', '1', '2'})
        slots['0']['box'][0] = 0.4
        self.assertEqual(self.store.get(self.folder)['0']['box'], self.box)
        self.assertEqual(self.source_bytes(), original)
        records = json.loads(self.database.read_text())
        self.assertEqual(records['version'], 1)
        self.assertEqual(next(iter(records['edits'].values()))['kind'], 'folder')
        self.assertNotIn(str(self.folder), self.database.read_text())
        self.assertEqual([name for name, _ in edits._folder_signature(self.folder)[2]],
                         ['page-1.png', 'page-2.JPG', 'page-10.png'])

    def test_rename_move_restart_and_identical_copy_restore(self):
        self.save()
        renamed = self.folder.rename(self.root / 'Renamed album')
        self.store.relocate(self.folder, renamed)
        self.assertEqual(self.store.get(renamed)['0']['box'], self.box)
        destination = self.root / 'Other location'
        destination.mkdir()
        moved = Path(shutil.move(renamed, destination / 'Moved album'))
        restarted = ThumbnailEditStore(self.database)
        self.assertEqual(restarted.get(moved)['0']['box'], self.box)
        duplicate = self.root / 'Copied album'
        shutil.copytree(moved, duplicate)
        self.assertEqual(restarted.get(duplicate), restarted.get(moved))

    def test_image_addition_deletion_and_content_changes_invalidate_identity(self):
        self.save()
        original = (self.folder / 'page-1.png').read_bytes()
        extra = self.folder / 'page-3.png'
        extra.write_bytes(b'new image')
        self.assertIsNone(self.store.get(self.folder))
        extra.unlink()
        self.assertIsNotNone(self.store.get(self.folder))
        image = self.folder / 'page-1.png'
        image.unlink()
        self.assertIsNone(self.store.get(self.folder))
        image.write_bytes(original)
        self.assertIsNotNone(self.store.get(self.folder))
        image.write_bytes(b'x' * len(original))
        self.assertIsNone(self.store.get(self.folder))
        self.assertIsNone(ThumbnailEditStore(self.database).get(self.folder))

    def test_same_size_replacement_with_preserved_mtime_is_not_cached_identity(self):
        self.save()
        image = self.folder / 'page-1.png'
        before = image.stat()
        replacement = self.root / 'replacement.png'
        replacement.write_bytes(b'x' * before.st_size)
        os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
        replacement.replace(image)
        self.assertIsNone(self.store.get(self.folder))

    def test_subfolders_and_nonimage_changes_do_not_rehash_or_change_identity(self):
        self.save()
        nested = self.folder / 'Nested'
        nested.mkdir()
        (nested / 'page.png').write_bytes(b'nested image is separate')
        (self.folder / 'notes.txt').write_text('not an image')
        with patch('thumbnail_edits._folder_digest', side_effect=AssertionError('Unexpected hash')):
            self.assertIsNotNone(self.store.get(self.folder))
            self.save(slot=1)
        self.assertEqual(set(self.store.get(self.folder)), {'0', '1'})

    def test_linked_images_are_excluded_and_directory_links_are_rejected(self):
        self.save()
        outside = self.root / 'outside.png'
        outside.write_bytes(b'outside image')
        link = self.folder / 'page-0.png'
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f'Symbolic links unavailable: {error}')
        self.assertIsNotNone(self.store.get(self.folder))
        with self.assertRaises(ValueError):
            self.save(entry=link.name)
        directory_link = self.root / 'folder link'
        directory_link.symlink_to(self.folder, target_is_directory=True)
        with self.assertRaises(NotADirectoryError):
            self.store.get(directory_link)
        self.assertEqual(outside.read_bytes(), b'outside image')

    def test_invalid_folder_entry_names_cannot_be_saved(self):
        for entry in ('../outside.png', '/outside.png', 'Nested/page.png',
                      'Nested\\page.png', 'missing.png'):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                self.save(entry=entry)
        self.assertFalse(self.database.exists())

    def test_legacy_archive_records_survive_folder_save_and_reset(self):
        archive = self.root / 'archive.cbz'
        archive.write_bytes(b'unchanged archive bytes')
        self.store.set(archive, 0, 'nested/001.png', self.box)
        archive_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        old_record = json.loads(self.database.read_text())['edits'][archive_digest]
        self.assertNotIn('kind', old_record)
        self.save()
        records = json.loads(self.database.read_text())['edits']
        self.assertEqual(records[archive_digest], old_record)
        self.assertEqual(len(records), 2)
        self.assertTrue(self.store.reset(self.folder))
        self.assertEqual(json.loads(self.database.read_text())['edits'],
                         {archive_digest: old_record})
        self.assertEqual(ThumbnailEditStore(self.database).get(archive)['0']['box'], self.box)

    def test_missing_and_empty_folder_keep_saved_records(self):
        self.save()
        database = self.database.read_bytes()
        original = self.source_bytes()
        shutil.rmtree(self.folder)
        self.assertIsNone(self.store.get(self.folder))
        self.assertFalse(self.store.reset(self.folder))
        self.folder.mkdir()
        self.assertIsNone(self.store.get(self.folder))
        with self.assertRaisesRegex(ValueError, '이미지'):
            self.save()
        self.assertEqual(self.database.read_bytes(), database)
        for name, content in original.items():
            (self.folder / name).write_bytes(content)
        self.assertIsNotNone(self.store.get(self.folder))

    def test_unrelated_size_skips_hash_and_quick_mismatch_skips_full_read(self):
        self.save()
        unrelated = self.root / 'Other album'
        unrelated.mkdir()
        (unrelated / 'page.png').write_bytes(b'different length')
        with patch('thumbnail_edits._folder_digest') as digest:
            self.assertIsNone(self.store.get(unrelated))
            digest.assert_not_called()
        duplicate = self.root / 'Same size album'
        shutil.copytree(self.folder, duplicate)
        image = duplicate / 'page-1.png'
        image.write_bytes(b'x' * image.stat().st_size)
        with patch('thumbnail_edits._folder_digest', wraps=edits._folder_digest) as digest:
            self.assertIsNone(self.store.get(duplicate))
        self.assertEqual(digest.call_count, 1)
        self.assertFalse(digest.call_args.kwargs.get('full', digest.call_args.args[2]))

    def test_matching_quick_folder_hash_requires_full_image_content_match(self):
        image = self.folder / 'page-1.png'
        image.write_bytes(b'a' * QUICK_BYTES + b'b' * QUICK_BYTES * 2 + b'c' * QUICK_BYTES)
        self.save()
        duplicate = self.root / 'Same quick album'
        shutil.copytree(self.folder, duplicate)
        (duplicate / image.name).write_bytes(
            b'a' * QUICK_BYTES + b'd' * QUICK_BYTES * 2 + b'c' * QUICK_BYTES)
        with patch('thumbnail_edits._folder_digest', wraps=edits._folder_digest) as digest:
            self.assertIsNone(self.store.get(duplicate))
        self.assertEqual(digest.call_count, 2)
        self.assertEqual([call.args[2] for call in digest.call_args_list], [False, True])

    def test_quick_reads_at_most_two_images_and_full_match_checks_middle_images(self):
        self.save()
        signature = edits._folder_signature(self.folder)
        with patch('thumbnail_edits._digest', wraps=edits._digest) as image_digest:
            edits._folder_digest(self.folder, signature, full=False)
        self.assertEqual([call.args[0].name for call in image_digest.call_args_list],
                         ['page-1.png', 'page-10.png'])
        duplicate = self.root / 'Changed middle image'
        shutil.copytree(self.folder, duplicate)
        middle = duplicate / 'page-2.JPG'
        middle.write_bytes(b'x' * middle.stat().st_size)
        with patch('thumbnail_edits._folder_digest', wraps=edits._folder_digest) as digest:
            self.assertIsNone(self.store.get(duplicate))
        self.assertEqual([call.args[2] for call in digest.call_args_list], [False, True])

    def test_reset_one_slot_and_identical_copy_are_shared(self):
        self.save()
        self.save(slot=2, entry='page-10.png')
        duplicate = self.root / 'Duplicate'
        shutil.copytree(self.folder, duplicate)
        self.assertTrue(self.store.reset(duplicate, 0))
        self.assertEqual(set(self.store.get(self.folder)), {'2'})
        self.assertTrue(self.store.reset(self.folder))
        self.assertIsNone(self.store.get(duplicate))

    def test_corrupt_database_and_unknown_source_kind_are_preserved(self):
        self.save()
        records = json.loads(self.database.read_text())
        next(iter(records['edits'].values()))['kind'] = 'unsupported'
        payload = json.dumps(records).encode()
        self.database.write_bytes(payload)
        restarted = ThumbnailEditStore(self.database)
        self.assertIsNone(restarted.get(self.folder))
        with self.assertRaises(ThumbnailEditDatabaseError):
            restarted.set(self.folder, 0, 'page-1.png', self.box)
        with self.assertRaises(ThumbnailEditDatabaseError):
            restarted.reset(self.folder)
        self.assertEqual(self.database.read_bytes(), payload)

    def test_changes_during_hashing_are_rejected(self):
        signature = edits._folder_signature(self.folder)
        real_digest = edits._digest
        modified = False

        def change_listing(*args, **kwargs):
            nonlocal modified
            result = real_digest(*args, **kwargs)
            if not modified:
                modified = True
                (self.folder / 'page-3.png').write_bytes(b'new image during read')
            return result

        with patch('thumbnail_edits._digest', side_effect=change_listing):
            with self.assertRaises(ThumbnailFileChangedError):
                edits._folder_digest(self.folder, signature, full=True)
        self.assertFalse(self.database.exists())

    def test_concurrent_instances_save_without_losing_slots(self):
        other = ThumbnailEditStore(self.database)
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(store.set, self.folder, slot, 'page-1.png', self.box)
                       for store, slot in ((self.store, 0), (other, 1), (self.store, 2))]
            for future in futures:
                future.result(timeout=5)
        self.assertEqual(set(self.store.get(self.folder)), {'0', '1', '2'})

    def test_slow_folder_hash_does_not_block_unrelated_lookup_and_close_cancels(self):
        self.save()
        duplicate = self.root / 'Duplicate'
        shutil.copytree(self.folder, duplicate)
        unrelated = self.root / 'Unrelated'
        unrelated.mkdir()
        (unrelated / 'page.png').write_bytes(b'other size')
        started, finish = threading.Event(), threading.Event()
        real_digest = edits._folder_digest

        def pause_full(path, signature, full, cancel=None):
            if full:
                started.set()
                if not finish.wait(5):
                    raise TimeoutError('Test hash wait timed out')
            return real_digest(path, signature, full, cancel)

        with ThreadPoolExecutor(max_workers=2) as executor:
            with patch('thumbnail_edits._folder_digest', side_effect=pause_full):
                lookup = executor.submit(self.store.get, duplicate)
                try:
                    self.assertTrue(started.wait(5))
                    self.assertIsNone(executor.submit(self.store.get, unrelated).result(timeout=2))
                    self.store.close()
                finally:
                    finish.set()
                with self.assertRaises(ThumbnailEditCancelledError):
                    lookup.result(timeout=5)
        self.assertIsNotNone(ThumbnailEditStore(self.database).get(self.folder))


if __name__ == '__main__':
    unittest.main()
