import errno
from pathlib import Path, PureWindowsPath
import tempfile
import unittest
from unittest.mock import patch

from file_operations import FileOperationError, rename_archive, trash_archive, _rename_no_replace


class FileOperations(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.archive = self.folder / '원본 日本語.ZIP'
        self.archive.write_bytes(b'archive content')

    def test_rename_preserves_content_extension_and_folder(self):
        renamed = rename_archive(self.archive, '수정한 日本語 이름')
        self.assertEqual(renamed, self.folder / '수정한 日本語 이름.ZIP')
        self.assertEqual(renamed.read_bytes(), b'archive content')
        self.assertFalse(self.archive.exists())

    def test_dotted_stem_and_unchanged_name(self):
        self.assertEqual(rename_archive(self.archive, self.archive.stem), self.archive)
        renamed = rename_archive(self.archive, 'chapter.01')
        self.assertEqual(renamed.name, 'chapter.01.ZIP')

    def test_invalid_names_never_change_source(self):
        names = ['', '  ', '.', '..', '../escape', 'sub/name', 'sub\\name', 'bad:name',
                 'bad*name', 'bad?name', 'bad"name', 'bad|name', 'bad<name', 'bad>name',
                 'bad\x00name', 'bad\nname', 'trailing.', 'trailing ', 'CON', 'con.data',
                 'NUL', 'COM1', 'com¹', 'LPT9', 'lpt³.txt', '\ud800']
        for name in names:
            with self.subTest(name=repr(name)):
                with self.assertRaises(FileOperationError) as caught:
                    rename_archive(self.archive, name)
                self.assertEqual(caught.exception.code, 'invalid_name')
                self.assertEqual(self.archive.read_bytes(), b'archive content')

    def test_existing_file_directory_and_dangling_link_are_never_replaced(self):
        targets = [self.folder / name for name in ('file.ZIP', 'folder.ZIP', 'link.ZIP')]
        targets[0].write_bytes(b'keep this')
        targets[1].mkdir()
        try:
            targets[2].symlink_to(self.folder / 'missing')
        except (OSError, NotImplementedError):
            targets.pop()
        for target in targets:
            with self.subTest(target=target.name):
                with self.assertRaises(FileOperationError) as caught:
                    rename_archive(self.archive, target.stem)
                self.assertEqual(caught.exception.code, 'exists')
                self.assertTrue(self.archive.is_file())
        self.assertEqual(targets[0].read_bytes(), b'keep this')
        self.assertTrue(targets[1].is_dir())
        if len(targets) == 3:
            self.assertTrue(targets[2].is_symlink())

    def test_case_only_rename_preserves_file(self):
        source = self.folder / 'example.cbz'
        source.write_bytes(b'pages')
        renamed = rename_archive(source, 'EXAMPLE')
        self.assertEqual(renamed.name, 'EXAMPLE.cbz')
        self.assertEqual(renamed.read_bytes(), b'pages')

    def test_windows_path_equality_does_not_skip_case_only_rename(self):
        # Exercise WindowsPath's case-insensitive equality on every test host.
        # A comparison of Path objects would incorrectly treat this as a no-op.
        source = PureWindowsPath('C:/archives/example.ZIP')
        expected = PureWindowsPath('C:/archives/EXAMPLE.ZIP')
        self.assertEqual(source, expected)
        with patch('file_operations._file_path', return_value=source), \
                patch('file_operations._rename_no_replace') as rename:
            renamed = rename_archive(source, 'EXAMPLE')
        rename.assert_called_once_with(source, expected)
        self.assertEqual(str(renamed), str(expected))
        self.assertEqual(renamed.suffix, '.ZIP')

    def test_missing_directory_and_symlink_are_rejected_for_both_operations(self):
        cases = [(self.folder / 'missing.zip', 'missing'), (self.folder, 'not_file')]
        link = self.folder / 'alias.zip'
        try:
            link.symlink_to(self.archive)
            cases.append((link, 'symlink'))
        except (OSError, NotImplementedError):
            pass
        with patch('file_operations._send2trash') as trash:
            for path, code in cases:
                for operation in (lambda p: rename_archive(p, 'new'), trash_archive):
                    with self.subTest(path=path.name, code=code):
                        with self.assertRaises(FileOperationError) as caught:
                            operation(path)
                        self.assertEqual(caught.exception.code, code)
            trash.assert_not_called()
        self.assertTrue(self.archive.exists())

    def test_native_collision_race_is_reported_without_replacement(self):
        def race(source, destination):
            destination.write_bytes(b'created concurrently')
            _rename_no_replace(source, destination)
        with patch('file_operations._rename_no_replace', side_effect=race):
            with self.assertRaises(FileOperationError) as caught:
                rename_archive(self.archive, 'raced')
        self.assertEqual(caught.exception.code, 'exists')
        self.assertEqual((self.folder / 'raced.ZIP').read_bytes(), b'created concurrently')
        self.assertTrue(self.archive.exists())

    def test_permission_and_native_support_failures_preserve_source(self):
        for error, code in [(PermissionError(errno.EACCES, 'locked'), 'permission'),
                            (OSError(errno.ENOSYS, 'unsupported'), 'unavailable'),
                            (OSError(errno.ENAMETOOLONG, 'long'), 'invalid_name'),
                            (OSError(errno.EIO, 'volume error'), 'rename_failed')]:
            with self.subTest(code=code), patch('file_operations._rename_no_replace', side_effect=error):
                with self.assertRaises(FileOperationError) as caught:
                    rename_archive(self.archive, 'new')
                self.assertEqual(caught.exception.code, code)
                self.assertTrue(self.archive.exists())

    def test_windows_rename_uses_non_replacing_os_rename(self):
        with patch('file_operations.sys.platform', 'win32'), patch('file_operations.os.rename') as rename:
            _rename_no_replace(self.archive, self.folder / 'new.zip')
        rename.assert_called_once_with(self.archive, self.folder / 'new.zip')

    def test_trash_uses_native_backend_with_absolute_path(self):
        # Do not touch the user's real Trash during tests.
        with patch('file_operations._send2trash') as trash:
            self.assertIsNone(trash_archive(self.archive))
        trash.assert_called_once_with(str(self.archive.absolute()))

    def test_trash_failure_never_falls_back_to_permanent_delete(self):
        for error, code in [(PermissionError(errno.EACCES, 'no trash permission'), 'permission'),
                            (OSError(errno.EIO, 'trash failed'), 'trash_failed'),
                            (RuntimeError('native COM setup failed'), 'trash_failed')]:
            with self.subTest(code=code), patch('file_operations._send2trash', side_effect=error):
                with self.assertRaises(FileOperationError) as caught:
                    trash_archive(self.archive)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(self.archive.read_bytes(), b'archive content')

    def test_missing_trash_dependency_preserves_file(self):
        with patch('file_operations._send2trash', None):
            with self.assertRaises(FileOperationError) as caught:
                trash_archive(self.archive)
        self.assertEqual(caught.exception.code, 'unavailable')
        self.assertEqual(self.archive.read_bytes(), b'archive content')


if __name__ == '__main__':
    unittest.main()
