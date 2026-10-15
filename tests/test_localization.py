import base64
import json
import os
import subprocess
import unittest
from unittest.mock import Mock, patch
import desktop_shortcuts
from localization import translate, set_language
from preferences import Preferences


class Languages(unittest.TestCase):
    def tearDown(self):
        set_language('ko')

    def test_names_options_and_dynamic_status_roundtrip(self):
        self.assertEqual(translate('파일만대장경', 'en'), 'File Tripitaka')
        self.assertEqual(translate('즐겨찾기 추가/해제', 'en'), 'Toggle favorite')
        status = '즐겨찾기 전체 7,444개 · 검색 결과 48개 · 더블클릭: 설정한 동작 · 우클릭: 파일 위치'
        english = translate(status, 'en')
        self.assertTrue(english.startswith('Favorites: 7,444 · Matches: 48'))
        self.assertEqual(translate(english, 'ko'), status)
        self.assertEqual(translate('▼  폴더 탐색', 'en'), '▼  Folders')

    def test_error_translation_and_paths_are_unchanged(self):
        self.assertEqual(translate('미리보기 불가\n압축파일에 지원하는 이미지가 없습니다.', 'en'),
                         'Preview unavailable\nNo supported images in this archive.')
        path = r'D:\설정\즐겨찾기 추가.zip'
        self.assertEqual(translate(path, 'en'), path)
        self.assertEqual(translate('폴더를 찾을 수 없습니다.\n' + path, 'en'), 'Folder not found.\n' + path)

    def test_invalid_language_does_not_save(self):
        view = Preferences()
        view.settings = {}
        view.save = Mock()
        with self.assertRaises(ValueError):
            view.commit_preferences('라이트', '꿀뷰 열기', '', '', True, language='invalid')
        view.save.assert_not_called()


class DesktopShortcutChecks(unittest.TestCase):
    def test_source_launch_does_not_rename_shortcuts(self):
        with patch('desktop_shortcuts.subprocess.run') as run:
            desktop_shortcuts.rename_desktop_shortcuts('en')
            run.assert_not_called()

    def test_windows_shortcut_request_uses_data_environment_and_unicode(self):
        result = Mock(returncode=0, stdout=json.dumps(dict(renamed=['File Tripitaka.lnk'], errors=[])))
        with patch.object(desktop_shortcuts.os, 'name', 'nt'), patch.object(desktop_shortcuts.sys, 'frozen', True, create=True), patch.object(desktop_shortcuts.subprocess, 'run', return_value=result) as run:
            renamed = desktop_shortcuts.rename_desktop_shortcuts('en')
        self.assertEqual(renamed['renamed'], ['File Tripitaka.lnk'])
        args, kwargs = run.call_args
        script = base64.b64decode(args[0][-1]).decode('utf-16le')
        self.assertIn('[String]::Equals($linkTarget, $target', script)
        self.assertIn('Test-Path -LiteralPath $newPath', script)
        self.assertIn('Rename-Item -LiteralPath', script)
        self.assertEqual(kwargs['env']['FILETRIPITAKA_SHORTCUT_NAME'], 'File Tripitaka')
        self.assertEqual(kwargs['env']['FILETRIPITAKA_SHORTCUT_TARGET'], os.path.abspath(desktop_shortcuts.sys.executable))
        self.assertEqual(kwargs['timeout'], 20)
        self.assertNotIn('shell', kwargs)

    def test_timeout_is_reported_without_crashing(self):
        with patch.object(desktop_shortcuts.os, 'name', 'nt'), patch.object(desktop_shortcuts.sys, 'frozen', True, create=True), patch.object(desktop_shortcuts.subprocess, 'run', side_effect=subprocess.TimeoutExpired('powershell', 20)):
            result = desktop_shortcuts.rename_desktop_shortcuts('ko')
        self.assertTrue(result['errors'])
