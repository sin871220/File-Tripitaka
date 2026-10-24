import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from library_items import (ARRANGEMENTS, SORT_LABELS, filter_items, item_metadata,
                           normalize_sort_order, scan_items, sort_items)


class LibraryItems(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, name, data=b'image bytes'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_recursive_walk_collects_only_archives_and_direct_image_folders(self):
        archive = self.write('book.ZIP')
        self.write('01.JPG')
        self.write('group/child/page.PNG')
        child = self.root / 'group/child'
        self.write('group/note.txt')
        empty = self.root / 'empty'
        empty.mkdir()
        paths, modified, metadata, kinds = scan_items(self.root)
        self.assertEqual(set(paths), {archive, self.root, child})
        self.assertEqual(kinds, {archive: 'archive', self.root: 'folder', child: 'folder'})
        self.assertEqual(set(modified), set(paths))
        self.assertEqual(metadata[child][0], len(b'image bytes'))
        self.assertNotIn(self.root / 'group', paths)

    def test_nonrecursive_includes_selected_folder_and_its_direct_archives(self):
        archive = self.write('a.cbz')
        self.write('page.png')
        self.write('child/other.cbz')
        self.write('child/page.png')
        paths, _, _, _ = scan_items(self.root, recursive=False)
        self.assertEqual(set(paths), {archive, self.root})

    def test_folder_metadata_counts_direct_images_only(self):
        self.write('book/page1.png', b'123')
        self.write('book/page2.jpg', b'4567')
        self.write('book/notes.txt', b'x' * 100)
        self.write('book/child/page.png', b'x' * 200)
        folder = self.root / 'book'
        kind, modified, metadata = item_metadata(folder)
        paths, times, values, _ = scan_items(self.root)
        self.assertIn(folder, paths)
        self.assertEqual(kind, 'folder')
        self.assertEqual(metadata[0], 7)
        self.assertEqual(values[folder], metadata)
        self.assertEqual(times[folder], modified)

    def test_folder_with_archive_suffix_keeps_its_kind(self):
        self.write('album.zip/001.png')
        self.write('album.zip/book.cbz')
        paths, _, _, kinds = scan_items(self.root)
        self.assertIn(self.root / 'album.zip', paths)
        self.assertEqual(kinds[self.root / 'album.zip'], 'folder')
        self.assertEqual(kinds[self.root / 'album.zip/book.cbz'], 'archive')

    def test_query_and_kind_filters_combine_and_old_archives_default_to_archive(self):
        folders = [self.root / 'Album.01', self.root / 'Other']
        archive = self.root / 'Album.zip'
        kinds = {path: 'folder' for path in folders}
        candidates = [*folders, archive]
        self.assertEqual(filter_items(candidates, 'album', '전체', kinds), [folders[0], archive])
        self.assertEqual(filter_items(candidates, 'ALBUM', '폴더', kinds), [folders[0]])
        self.assertEqual(filter_items(candidates, '', '압축파일', kinds), [archive])

    def test_directory_and_image_links_are_not_scanned(self):
        self.write('real/page.png')
        try:
            os.symlink(self.root / 'real', self.root / 'linked', target_is_directory=True)
            os.symlink(self.root / 'real/page.png', self.root / 'image.png')
        except OSError:
            self.skipTest('Symlink creation unavailable')
        paths, _, _, _ = scan_items(self.root)
        self.assertEqual(paths, [self.root / 'real'])

    def test_cancellation_does_not_keep_walking(self):
        self.write('a.png')
        self.assertEqual(scan_items(self.root, cancel=lambda: True), ([], {}, {}, {}))

    def test_all_sort_directions_keep_selected_groups_first(self):
        folder_a, folder_z = self.root / 'A2', self.root / 'Z9'
        file_a, file_z, legacy = (self.root / name for name in ('A1.zip', 'Z10.zip', 'Q4.zip'))
        paths = [folder_z, file_z, legacy, file_a, folder_a]
        kinds = {folder_a: 'folder', folder_z: 'folder', file_a: 'archive', file_z: 'archive'}
        # An item missing a kind is a legacy archive, including when grouping.
        modified = {folder_a: 20, folder_z: 10, file_a: 10, file_z: 30, legacy: 20}
        expected = {
            '이름 오름차순': ([file_a, folder_a, legacy, folder_z, file_z],
                        [folder_a, folder_z], [file_a, legacy, file_z]),
            '이름 내림차순': ([file_z, folder_z, legacy, folder_a, file_a],
                        [folder_z, folder_a], [file_z, legacy, file_a]),
            '수정한 날짜 오름차순': ([file_a, folder_z, folder_a, legacy, file_z],
                            [folder_z, folder_a], [file_a, legacy, file_z]),
            '수정한 날짜 내림차순': ([file_z, folder_a, legacy, file_a, folder_z],
                            [folder_a, folder_z], [file_z, legacy, file_a]),
        }
        self.assertEqual(ARRANGEMENTS, ('섞어서', '폴더 먼저', '파일 먼저'))
        before = paths.copy()
        for order, (mixed, folders, files) in expected.items():
            for arrangement, result in (('섞어서', mixed), ('폴더 먼저', folders + files),
                                        ('파일 먼저', files + folders)):
                with self.subTest(order=order, arrangement=arrangement):
                    self.assertEqual(sort_items(paths, order, modified, kinds, arrangement), result)
            self.assertEqual(sort_items(paths, order, modified, kinds), mixed)
        self.assertEqual(paths, before, 'Sorting must not mutate the scan snapshot')

    def test_group_sort_has_deterministic_same_name_and_time_ties(self):
        a, b, c, d = (self.root / parent / 'Same.zip' for parent in ('a2', 'a10', 'b2', 'b10'))
        paths = [d, b, c, a]
        kinds = {a: 'folder', d: 'folder', b: 'archive', c: 'archive'}
        modified = {path: 100 for path in paths}
        for source in (paths, list(reversed(paths))):
            for order in ('수정한 날짜 오름차순', '수정한 날짜 내림차순'):
                with self.subTest(order=order, source=source):
                    self.assertEqual(sort_items(source, order, modified, kinds, '섞어서'), [a, b, c, d])
                    self.assertEqual(sort_items(source, order, modified, kinds, '폴더 먼저'), [a, d, b, c])
                    self.assertEqual(sort_items(source, order, modified, kinds, '파일 먼저'), [b, c, a, d])

    def test_unknown_arrangement_preserves_mixed_sorting(self):
        folder, archive = self.root / 'Z folder', self.root / 'A.zip'
        kinds = {folder: 'folder', archive: 'archive'}
        self.assertEqual(sort_items([folder, archive], '이름 오름차순', {}, kinds, 'unknown'),
                         [archive, folder])

    def test_sort_labels_have_six_name_date_and_size_choices(self):
        self.assertEqual(SORT_LABELS,
                         {'이름 오름차순': '이름 ▲', '이름 내림차순': '이름 ▼',
                          '수정한 날짜 오름차순': '수정 날짜 ▲', '수정한 날짜 내림차순': '수정 날짜 ▼',
                          '용량 오름차순': '용량 ▲', '용량 내림차순': '용량 ▼'})

    def test_size_sort_keeps_group_modes_and_unknowns_last(self):
        folder_small, folder_large, folder_unknown = (self.root / name for name in
                                                     ('Folder2', 'Folder10', 'Folder20'))
        file_small, file_large, file_unknown = (self.root / name for name in
                                               ('File2.zip', 'File10.zip', 'File20.zip'))
        paths = [folder_unknown, file_large, folder_large, file_unknown, file_small, folder_small]
        kinds = {path: 'folder' for path in (folder_small, folder_large, folder_unknown)}
        metadata = {folder_small: (100, 0), folder_large: (900, 0),
                    file_small: (200, 0), file_large: (800, 0)}
        before = paths.copy()
        for direction, mixed, folders, files in (
                ('오름차순', [folder_small, file_small, file_large, folder_large, file_unknown, folder_unknown],
                 [folder_small, folder_large, folder_unknown], [file_small, file_large, file_unknown]),
                ('내림차순', [folder_large, file_large, file_small, folder_small, file_unknown, folder_unknown],
                 [folder_large, folder_small, folder_unknown], [file_large, file_small, file_unknown])):
            for arrangement, expected in (('섞어서', mixed), ('폴더 먼저', folders + files),
                                          ('파일 먼저', files + folders)):
                with self.subTest(direction=direction, arrangement=arrangement):
                    self.assertEqual(sort_items(paths, f'용량 {direction}', {}, kinds,
                                                arrangement, metadata=metadata), expected)
        self.assertEqual(paths, before)

    def test_size_sort_ties_are_natural_name_then_path_for_both_directions(self):
        a, b, c, d = (self.root / parent / name for parent, name in
                      (('a2', 'Same2.zip'), ('a10', 'Same2.zip'),
                       ('a1', 'Same10.zip'), ('a2', 'Same10.zip')))
        metadata = {path: (100, 0) for path in (a, b, c, d)}
        for paths in ([d, b, c, a], [a, c, b, d]):
            for direction in ('오름차순', '내림차순'):
                with self.subTest(paths=paths, direction=direction):
                    self.assertEqual(sort_items(paths, f'용량 {direction}', {}, {},
                                                metadata=metadata), [a, b, c, d])

    def test_known_zero_size_is_distinct_from_missing_or_invalid_metadata(self):
        zero, known, invalid, missing = (self.root / name for name in
                                          ('Z.zip', 'K.zip', 'I.zip', 'M.zip'))
        paths = [invalid, zero, missing, known]
        metadata = {zero: (0, 0), known: (100, 0), invalid: (True, 0)}
        self.assertEqual(sort_items(paths, '용량 오름차순', {}, {}, metadata=metadata),
                         [zero, known, invalid, missing])
        self.assertEqual(sort_items(paths, '용량 내림차순', {}, {}, metadata=metadata),
                         [known, zero, invalid, missing])

    def test_size_sort_uses_only_snapshot_maps_and_has_backwards_compatible_defaults(self):
        paths = [self.root / 'Never10.zip', self.root / 'Never2.zip']
        with patch.object(Path, 'stat', side_effect=AssertionError('Sorting must not stat candidates')):
            for direction in ('오름차순', '내림차순'):
                self.assertEqual(sort_items(paths, f'용량 {direction}', {}, {}), list(reversed(paths)))
            self.assertEqual(sort_items(paths, '용량 오름차순', {}, {},
                                        metadata={paths[0]: (1, 0), paths[1]: (2, 0)}), paths)

    def test_retired_page_sort_and_malformed_settings_restore_default_name_order(self):
        paths = [self.root / 'Book10.zip', self.root / 'Book2.zip']
        for order in SORT_LABELS:
            self.assertEqual(normalize_sort_order(order), order)
        for retired_or_bad in ('페이지 수 오름차순', '페이지 수 내림차순', 'Page count ▼',
                               None, [], {}, True, 1, '', 'unknown'):
            with self.subTest(order=retired_or_bad):
                self.assertEqual(normalize_sort_order(retired_or_bad), '이름 오름차순')
                with patch.object(Path, 'stat', side_effect=AssertionError('Migration must not read files')):
                    self.assertEqual(sort_items(paths, retired_or_bad, {}, {}), list(reversed(paths)))


if __name__ == '__main__':
    unittest.main()
