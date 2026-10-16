from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import viewer


class ViewerPlatforms(unittest.TestCase):
    def test_actions_and_defaults_follow_the_platform(self):
        self.assertEqual(viewer.default_action('darwin'), '파일 위치 열기')
        self.assertEqual(viewer.default_action('win32'), '꿀뷰 열기')
        self.assertEqual(viewer.available_actions(platform='win32'), viewer.ACTIONS)
        mac = viewer.available_actions(platform='darwin')
        self.assertNotIn('꿀뷰 열기', mac)
        self.assertIn('기본 앱으로 열기', mac)
        self.assertNotIn('없음', mac)
        self.assertIn('없음', viewer.available_actions(keyboard=True, platform='darwin'))
        self.assertEqual(viewer.normalize_action('꿀뷰 열기', platform='darwin'), '파일 위치 열기')
        self.assertEqual(viewer.normalize_action('기본 앱으로 열기', platform='win32'), '꿀뷰 열기')

    def test_bundle_and_executable_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder) / 'Reader.app'
            app.mkdir()
            self.assertFalse(viewer.is_viewer(app, 'darwin'))
            (app / 'Contents').mkdir()
            (app / 'Contents' / 'Info.plist').write_text('<plist/>')
            self.assertTrue(viewer.is_viewer(app, 'darwin'))
            self.assertFalse(viewer.is_viewer(app, 'win32'))
            executable = Path(folder) / 'reader'
            executable.write_text('placeholder')
            with patch('viewer.os.access', return_value=False):
                self.assertFalse(viewer.is_viewer(executable, 'darwin'))
            self.assertTrue(viewer.is_viewer(executable, 'win32'))
            with patch('viewer.os.access', return_value=True):
                self.assertTrue(viewer.is_viewer(executable, 'darwin'))

    def test_bundle_launch_keeps_unicode_and_shell_metacharacters_in_single_arguments(self):
        with tempfile.TemporaryDirectory() as folder, patch('viewer.sys.platform', 'darwin'):
            app = Path(folder) / 'Reader $(unsafe) ; 사진.app'
            (app / 'Contents').mkdir(parents=True)
            (app / 'Contents' / 'Info.plist').write_text('<plist/>')
            archive = Path(folder) / '사진 ; 만화.zip'
            with patch('viewer.subprocess.Popen') as launch:
                viewer.launch_viewer(app, archive)
                launch.assert_called_once_with(['/usr/bin/open', '-a', str(app.resolve()), str(archive.resolve())])

    def test_executable_launch_and_invalid_viewer(self):
        with tempfile.TemporaryDirectory() as folder, patch('viewer.sys.platform', 'win32'):
            executable = Path(folder) / 'Reader.exe'
            executable.write_text('placeholder')
            archive = Path(folder) / 'archive.cbz'
            with patch('viewer.subprocess.Popen') as launch:
                viewer.launch_viewer(executable, archive)
                launch.assert_called_once_with([str(executable), str(archive.resolve())])
                with self.assertRaises(FileNotFoundError):
                    viewer.launch_viewer(Path(folder) / 'missing.exe', archive)
                self.assertEqual(launch.call_count, 1)

    def test_default_app_and_native_application_picker(self):
        with patch('viewer.sys.platform', 'darwin'), patch('viewer.subprocess.Popen') as launch:
            viewer.launch_default(Path('사진.zip'))
            launch.assert_called_once_with(['/usr/bin/open', str(Path('사진.zip').resolve())])
        with patch('viewer.sys.platform', 'darwin'), patch('viewer.filedialog.askopenfilename', return_value='/Applications/Reader.app') as picker:
            self.assertEqual(viewer.choose_viewer(), '/Applications/Reader.app')
            self.assertIn(('응용 프로그램', '*.app'), picker.call_args.kwargs['filetypes'])
            self.assertEqual(picker.call_args.kwargs['initialdir'], '/Applications')
        with patch('viewer.sys.platform', 'win32'), patch('viewer.filedialog.askopenfilename') as picker:
            viewer.choose_viewer()
            self.assertIn(('실행 파일', '*.exe'), picker.call_args.kwargs['filetypes'])
