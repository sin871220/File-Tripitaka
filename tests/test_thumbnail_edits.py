from concurrent.futures import ThreadPoolExecutor
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

from thumbnail_edits import (QUICK_BYTES, ThumbnailEditDatabaseError,
                             ThumbnailEditStore, ThumbnailFileChangedError,
                             ThumbnailEditCancelledError)
import thumbnail_edits


class ThumbnailEdits(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.archive = self.folder / 'example.cbz'
        self.archive.write_bytes(b'original archive bytes')
        self.database = self.folder / 'data' / 'thumbnail_edits.json'
        self.store = ThumbnailEditStore(self.database)
        self.box = [0.1, 0.2, 0.9, 0.8]

    def save(self, slot=0, archive=None):
        self.store.set(archive or self.archive, slot, 'pages/001.png', self.box)

    def test_unavailable_database_is_deferred_until_worker_read(self):
        self.database.parent.mkdir(parents=True)
        self.database.write_bytes(b'preserve unavailable metadata')
        with patch.object(ThumbnailEditStore, '_refresh', side_effect=PermissionError('unavailable')) as refresh:
            store = ThumbnailEditStore(self.database)
            refresh.assert_not_called()
            with self.assertRaises(PermissionError):
                store.get(self.archive)
        self.assertEqual(self.database.read_bytes(), b'preserve unavailable metadata')

    def test_slots_deep_copies_and_archive_is_never_modified(self):
        original = self.archive.read_bytes()
        self.save()
        self.store.set(self.archive, 2, 'pages/日本語.png', (0, 0, 1, 1))
        recipes = self.store.get(self.archive)
        self.assertEqual(set(recipes), {'0', '2'})
        self.assertEqual(recipes['0'], {'entry': 'pages/001.png', 'box': self.box})
        recipes['0']['box'][0] = 0.5
        recipes['2']['entry'] = 'changed'
        self.box[0] = 0.3
        self.assertEqual(self.store.get(self.archive)['0']['box'][0], 0.1)
        self.assertEqual(self.archive.read_bytes(), original)

    def test_rename_move_restart_and_identical_copy_restore(self):
        self.save()
        renamed = self.archive.rename(self.folder / 'renamed.zip')
        self.store.relocate(self.archive, renamed)
        self.assertIsNotNone(self.store.get(renamed))
        destination = self.folder / 'other drive'
        destination.mkdir()
        moved = destination / 'new name.cbz'
        shutil.move(renamed, moved)
        restarted = ThumbnailEditStore(self.database)
        self.assertEqual(restarted.get(moved), self.store.get(moved))
        copied = self.folder / 'copy.zip'
        shutil.copyfile(moved, copied)
        self.assertEqual(restarted.get(copied), restarted.get(moved))
        payload = self.database.read_text()
        self.assertNotIn(str(self.folder), payload)
        self.assertNotIn('new name.cbz', payload)

    def test_missing_file_keeps_content_record(self):
        self.save()
        original_database = self.database.read_bytes()
        original = self.archive.read_bytes()
        self.archive.unlink()
        self.assertIsNone(self.store.get(self.archive))
        self.assertFalse(self.store.reset(self.archive))
        self.assertEqual(self.database.read_bytes(), original_database)
        self.archive.write_bytes(original)
        self.assertIsNotNone(self.store.get(self.archive))

    def test_unrelated_size_skips_all_fingerprinting(self):
        self.save()
        unrelated = self.folder / 'unrelated.zip'
        unrelated.write_bytes(b'different size')
        with patch('thumbnail_edits._quick_fingerprint') as quick, \
                patch('thumbnail_edits._full_digest') as full:
            self.assertIsNone(self.store.get(unrelated))
        quick.assert_not_called()
        full.assert_not_called()

    def test_same_size_quick_mismatch_does_not_read_full_archive(self):
        self.save()
        unrelated = self.folder / 'unrelated.zip'
        unrelated.write_bytes(b'x' * self.archive.stat().st_size)
        with patch('thumbnail_edits._full_digest') as full:
            self.assertIsNone(self.store.get(unrelated))
            self.assertIsNone(self.store.get(unrelated))
        full.assert_not_called()

    def test_same_quick_fingerprint_requires_full_content_match(self):
        # A different middle section has the same size, prefix and suffix.
        self.archive.write_bytes(b'a' * QUICK_BYTES + b'b' * QUICK_BYTES * 2 + b'c' * QUICK_BYTES)
        self.save()
        candidate = self.folder / 'candidate.zip'
        candidate.write_bytes(b'a' * QUICK_BYTES + b'd' * QUICK_BYTES * 2 + b'c' * QUICK_BYTES)
        with patch('thumbnail_edits._full_digest', wraps=thumbnail_edits._full_digest) as full:
            self.assertIsNone(self.store.get(candidate))
            self.assertIsNone(self.store.get(candidate))
        self.assertEqual(full.call_count, 1)

    def test_known_unchanged_path_does_not_hash_again(self):
        self.save()
        with patch('thumbnail_edits._full_digest') as full, \
                patch('thumbnail_edits._quick_fingerprint') as quick:
            self.assertIsNotNone(self.store.get(self.archive))
            self.store.set(self.archive, 1, '002.png', (0, 0, 1, 1))
            self.assertIsNotNone(self.store.get(self.archive))
        full.assert_not_called()
        quick.assert_not_called()

    def test_modified_file_and_replaced_same_size_are_not_false_matches(self):
        self.save()
        old_stat = self.archive.stat()
        replacement = self.folder / 'replacement.cbz'
        replacement.write_bytes(b'x' * old_stat.st_size)
        os.utime(replacement, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        replacement.replace(self.archive)
        self.assertIsNone(self.store.get(self.archive))
        self.archive.write_bytes(b'y' * old_stat.st_size)
        os.utime(self.archive, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        self.assertIsNone(self.store.get(self.archive))

    def test_negative_cache_is_invalidated_after_matching_content_is_edited(self):
        self.save()
        candidate = self.folder / 'candidate.cbz'
        candidate.write_bytes(b'different bytes')
        self.assertIsNone(self.store.get(candidate))
        identical = self.folder / 'identical.cbz'
        shutil.copyfile(candidate, identical)
        self.save(archive=identical)
        self.assertIsNotNone(self.store.get(candidate))

    def test_slot_and_whole_reset_apply_to_identical_copies(self):
        self.save()
        self.save(2)
        duplicate = self.folder / 'duplicate.zip'
        shutil.copyfile(self.archive, duplicate)
        self.assertTrue(self.store.reset(duplicate, 0))
        self.assertEqual(set(self.store.get(self.archive)), {'2'})
        self.assertFalse(self.store.reset(duplicate, 0))
        self.assertTrue(self.store.reset(self.archive))
        self.assertIsNone(self.store.get(duplicate))
        self.assertFalse(self.store.reset(self.archive))

    def test_invalid_recipes_never_write_database(self):
        cases = [('', [0, 0, 1, 1]), ('a\0b', [0, 0, 1, 1]),
                 ('001.png', [0, 0, 1]), ('001.png', [0, 0, 0, 1]),
                 ('001.png', [-0.1, 0, 1, 1]), ('001.png', [0, 0, 1.1, 1]),
                 ('001.png', [0, 0, float('nan'), 1]),
                 ('001.png', [0, 0, float('inf'), 1]),
                 ('001.png', [False, 0, 1, 1]), ('001.png', ['0', 0, 1, 1])]
        for entry, box in cases:
            with self.subTest(entry=entry, box=box), self.assertRaises(ValueError):
                self.store.set(self.archive, 0, entry, box)
        for slot in (-1, 3, True, '0', 1.0):
            with self.subTest(slot=slot):
                with self.assertRaises(ValueError):
                    self.store.set(self.archive, slot, '001.png', [0, 0, 1, 1])
                with self.assertRaises(ValueError):
                    self.store.reset(self.archive, slot)
        self.assertFalse(self.database.exists())

    def test_malformed_database_is_preserved_and_mutations_refused(self):
        self.database.parent.mkdir()
        valid_digest = 'a' * 64
        cases = [b'not json', b'\xff\xfe', b'{"version":2,"edits":{}}',
                 b'{"version":true,"edits":{}}', b'[]',
                 json.dumps({'version': 1, 'edits': {valid_digest:
                     {'size': 3, 'quick': 'b' * 64, 'slots':
                      {'0': {'entry': '001.png', 'box': [0, 0, float('nan'), 1]}}}}}).encode(),
                 json.dumps({'version': 1, 'edits': {valid_digest:
                     {'size': -1, 'quick': 'b' * 64, 'slots': {}}}}).encode()]
        for payload in cases:
            with self.subTest(payload=payload):
                self.database.write_bytes(payload)
                store = ThumbnailEditStore(self.database)
                self.assertIsNone(store.get(self.archive))
                with self.assertRaises(ThumbnailEditDatabaseError):
                    store.set(self.archive, 0, '001.png', [0, 0, 1, 1])
                with self.assertRaises(ThumbnailEditDatabaseError):
                    store.reset(self.archive)
                self.assertEqual(self.database.read_bytes(), payload)

    def test_actual_io_failures_propagate(self):
        with patch.object(Path, 'open', side_effect=PermissionError('read denied')):
            with self.assertRaises(PermissionError):
                self.save()
        with self.assertRaises(FileNotFoundError):
            self.store.set(self.folder / 'missing.zip', 0, '001.png', [0, 0, 1, 1])

    def test_atomic_replace_failure_preserves_old_database_and_memory(self):
        self.save()
        original = self.database.read_bytes()
        with patch('thumbnail_edits.os.replace', side_effect=PermissionError('write denied')):
            with self.assertRaises(PermissionError):
                self.save(1)
            with self.assertRaises(PermissionError):
                self.store.reset(self.archive)
        self.assertEqual(self.database.read_bytes(), original)
        self.assertEqual(set(self.store.get(self.archive)), {'0'})
        self.assertEqual(list(self.database.parent.glob('*.tmp')), [])
        self.assertEqual(set(ThumbnailEditStore(self.database).get(self.archive)), {'0'})

    def test_file_changes_during_fingerprint_are_rejected(self):
        signature = thumbnail_edits._file_signature(self.archive)
        self.archive.write_bytes(b'changed before read')
        with self.assertRaises(ThumbnailFileChangedError):
            thumbnail_edits._full_digest(self.archive, signature)
        signature = thumbnail_edits._file_signature(self.archive)
        real_signature = thumbnail_edits._file_signature
        calls = []

        def change_at_end(path):
            calls.append(path)
            if len(calls) == 2:
                path.write_bytes(b'changed after read')
            return real_signature(path)

        with patch('thumbnail_edits._file_signature', side_effect=change_at_end):
            with self.assertRaises(ThumbnailFileChangedError):
                thumbnail_edits._full_digest(self.archive, signature)

    def test_windows_path_handle_ctime_difference_allows_save_get_and_reset(self):
        # Windows stat(path) exposes birthtime as ctime, whereas fstat(fd) can
        # expose ChangeTime. Both describe the same unchanged read-only archive.
        self.archive.chmod(0o444)
        original = self.archive.read_bytes()
        real_fstat = os.fstat

        def windows_handle_stat(fd):
            info = real_fstat(fd)
            return SimpleNamespace(st_size=info.st_size, st_mtime_ns=info.st_mtime_ns,
                                   st_ctime_ns=info.st_ctime_ns + 100_000_000,
                                   st_dev=info.st_dev, st_ino=info.st_ino)

        with patch('thumbnail_edits.os.fstat', side_effect=windows_handle_stat):
            self.save()
            self.assertEqual(self.store.get(self.archive)['0']['box'], self.box)
            reopened = ThumbnailEditStore(self.database)
            self.assertEqual(reopened.get(self.archive)['0']['box'], self.box)
            self.assertTrue(reopened.reset(self.archive, 0))
            self.assertIsNone(self.store.get(self.archive))
            reopened.close()
        self.assertEqual(self.archive.read_bytes(), original)
        self.assertEqual(json.loads(self.database.read_text())['edits'], {})

    def test_changing_handle_ctime_during_read_is_still_rejected(self):
        info = self.archive.stat()
        signature = thumbnail_edits._signature(info)

        def handle_stat(change_time):
            return SimpleNamespace(st_size=info.st_size, st_mtime_ns=info.st_mtime_ns,
                                   st_ctime_ns=change_time, st_dev=info.st_dev,
                                   st_ino=info.st_ino)

        with patch('thumbnail_edits.os.fstat', side_effect=[
                handle_stat(info.st_ctime_ns + 100), handle_stat(info.st_ctime_ns + 200)]):
            with self.assertRaisesRegex(ThumbnailFileChangedError, 'while fingerprinting'):
                thumbnail_edits._full_digest(self.archive, signature)

    def test_cross_api_size_mtime_device_or_inode_mismatch_is_rejected(self):
        info = self.archive.stat()
        signature = thumbnail_edits._signature(info)
        for field in ('st_size', 'st_mtime_ns', 'st_dev', 'st_ino'):
            with self.subTest(field=field):
                fields = {name: getattr(info, name) for name in
                          ('st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_dev', 'st_ino')}
                fields['st_ctime_ns'] += 100
                fields[field] += 1
                with patch('thumbnail_edits.os.fstat', return_value=SimpleNamespace(**fields)):
                    with self.assertRaisesRegex(ThumbnailFileChangedError, 'before reading'):
                        thumbnail_edits._full_digest(self.archive, signature)

    def test_two_instances_concurrent_updates_do_not_lose_slots(self):
        other = ThumbnailEditStore(self.database)
        jobs = [(self.store, 0), (other, 1), (self.store, 2)]
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(store.set, self.archive, slot, f'{slot}.png', [0, 0, 1, 1])
                       for store, slot in jobs]
            for future in futures:
                future.result(timeout=10)
        recipes = self.store.get(self.archive)
        self.assertEqual(set(recipes), {'0', '1', '2'})
        self.assertEqual(other.get(self.archive), recipes)
        persisted = json.loads(self.database.read_text())
        self.assertEqual(set(persisted['edits']), {hashlib.sha256(self.archive.read_bytes()).hexdigest()})

    def test_slow_matching_archive_does_not_block_unrelated_lookup(self):
        self.save()
        candidate = self.folder / 'candidate.cbz'
        shutil.copyfile(self.archive, candidate)
        unrelated = self.folder / 'unrelated.cbz'
        unrelated.write_bytes(b'other size')
        started = threading.Event()
        finish = threading.Event()
        original_digest = thumbnail_edits._full_digest

        def slow_digest(path, signature, cancel=None):
            started.set()
            if not finish.wait(5):
                raise RuntimeError('Test fingerprint wait timed out')
            return original_digest(path, signature, cancel)

        with ThreadPoolExecutor(max_workers=2) as executor:
            with patch('thumbnail_edits._full_digest', side_effect=slow_digest):
                match = executor.submit(self.store.get, candidate)
                try:
                    self.assertTrue(started.wait(5))
                    no_match = executor.submit(self.store.get, unrelated)
                    self.assertIsNone(no_match.result(timeout=2))
                finally:
                    finish.set()
                self.assertIsNotNone(match.result(timeout=5))

    def test_close_cancels_pending_hash_and_future_operations(self):
        self.save()
        candidate = self.folder / 'candidate.cbz'
        shutil.copyfile(self.archive, candidate)
        started = threading.Event()
        finish = threading.Event()
        original_digest = thumbnail_edits._full_digest

        def paused_digest(path, signature, cancel=None):
            started.set()
            finish.wait(5)
            return original_digest(path, signature, cancel)

        with ThreadPoolExecutor(max_workers=1) as executor:
            with patch('thumbnail_edits._full_digest', side_effect=paused_digest):
                lookup = executor.submit(self.store.get, candidate)
                try:
                    self.assertTrue(started.wait(5))
                    self.store.close()
                finally:
                    finish.set()
                with self.assertRaises(ThumbnailEditCancelledError):
                    lookup.result(timeout=5)
        with self.assertRaises(ThumbnailEditCancelledError):
            self.store.get(self.archive)
        with self.assertRaises(ThumbnailEditCancelledError):
            self.save(1)
        with self.assertRaises(ThumbnailEditCancelledError):
            self.store.reset(self.archive)
        self.assertIsNotNone(ThumbnailEditStore(self.database).get(self.archive))

    def test_close_during_atomic_commit_finishes_valid_save(self):
        original_replace = thumbnail_edits.os.replace

        def close_then_commit(source, destination):
            self.store.close()
            original_replace(source, destination)

        with patch('thumbnail_edits.os.replace', side_effect=close_then_commit):
            self.save()
        self.assertEqual(ThumbnailEditStore(self.database).get(self.archive)['0']['box'], self.box)


if __name__ == '__main__':
    unittest.main()
