import unittest
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import Mock, MagicMock, patch
from windows_shell import _select_item, logical_drive_roots, reveal_file


class ShellSelection(unittest.TestCase):
    def test_mac_reveal_uses_native_selection_without_a_shell(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '사진 ; $(example).zip'
            path.touch()
            with patch('windows_shell.sys.platform', 'darwin'), patch('windows_shell.subprocess.run') as run:
                self.assertTrue(reveal_file(path))
                run.assert_called_once_with(['/usr/bin/open', '-R', str(path.resolve())],
                                            check=True, capture_output=True, timeout=15)
            with patch('windows_shell.sys.platform', 'darwin'), patch('windows_shell.subprocess.run', side_effect=subprocess.TimeoutExpired('open', 15)):
                with self.assertRaises(OSError):
                    reveal_file(path)

    def test_mac_volume_roots_include_only_mounted_directories(self):
        def volume(name, mounted=True, resolved=None):
            result = MagicMock()
            result.name = name
            result.__str__.return_value = '/Volumes/' + name
            result.is_dir.return_value = True
            result.is_mount.return_value = mounted
            result.resolve.return_value = Path(resolved or '/Volumes/' + name)
            return result
        external = volume('External Disk')
        ordinary = volume('not mounted', mounted=False)
        internal = volume('Macintosh HD', resolved='/')
        directory = Mock()
        directory.iterdir.return_value = [ordinary, internal, external]
        path_type = Path
        with patch('windows_shell.sys.platform', 'darwin'), patch('windows_shell.Path', side_effect=lambda value: directory if value == '/Volumes' else path_type(value)):
            self.assertEqual(logical_drive_roots(), ['/', '/Volumes/External Disk'])
        external.is_mount.assert_called_once()

    def test_drive_letters_include_fixed_removable_and_mapped_letters(self):
        kernel = Mock()
        kernel.GetLogicalDrives.return_value = (1 << 2) | (1 << 3) | (1 << 25)
        self.assertEqual(logical_drive_roots(kernel), ['C:\\', 'D:\\', 'Z:\\'])
        kernel.GetLogicalDrives.return_value = 0
        self.assertEqual(logical_drive_roots(kernel), [])

    def libraries(self, parse=0, select=0, init=0):
        shell, ole = Mock(), Mock()
        ole.CoInitializeEx.return_value = init
        def parse_path(path, context, output, flags, attrs):
            if parse >= 0:
                output._obj.value = 1234
            return parse
        shell.SHParseDisplayName.side_effect = parse_path
        shell.SHOpenFolderAndSelectItems.return_value = select
        return shell, ole

    def test_unicode_path_and_cleanup(self):
        shell, ole = self.libraries()
        path = 'C:\\한글 폴더\\사진, 모음.zip'
        _select_item(path, shell, ole)
        self.assertEqual(shell.SHParseDisplayName.call_args.args[0], path)
        self.assertEqual(shell.SHOpenFolderAndSelectItems.call_args.args[1:], (0, None, 0))
        ole.CoTaskMemFree.assert_called_once()
        ole.CoUninitialize.assert_called_once()

    def test_selection_failure_still_releases_resources(self):
        shell, ole = self.libraries(select=-1)
        with self.assertRaises(OSError):
            _select_item('C:\\a.zip', shell, ole)
        ole.CoTaskMemFree.assert_called_once()
        ole.CoUninitialize.assert_called_once()

    def test_parse_failure_and_existing_com_apartment(self):
        shell, ole = self.libraries(parse=-1, init=-2147417850)
        with self.assertRaises(OSError):
            _select_item('C:\\a.zip', shell, ole)
        shell.SHOpenFolderAndSelectItems.assert_not_called()
        ole.CoTaskMemFree.assert_not_called()
        ole.CoUninitialize.assert_not_called()
