from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from preferences import Preferences, card_text, PALETTES


class PreferencesChecks(unittest.TestCase):
    def dummy(self, **settings):
        view = Preferences()
        view.settings = settings
        view.reveal = Mock()
        view.open_archive = Mock()
        view.open_settings = Mock()
        view.recursive = Mock()
        view.recursive.get.return_value = True
        view.current_folder = '/test'
        view.save = Mock()
        view.apply_theme = Mock()
        view.scan = Mock()
        return view

    def test_display_combinations_and_extension(self):
        import itertools
        for filename, extension, size, date in itertools.product((False, True), repeat=4):
            settings = dict(show_filename=filename, show_extension=extension, show_size=size, show_date=date)
            name, details = card_text(Path('사진.모음.zip'), (1048576, 1700000000), settings)
            self.assertEqual(name, ('사진.모음.zip' if extension else '사진.모음') if filename else '')
            self.assertEqual('MB' in details, size)
            self.assertEqual('2023-' in details, date)
            self.assertFalse(details.startswith(' · ') or details.endswith(' · '))

    def test_failed_preview_overrides_viewer_preference(self):
        path = Path('failed.zip')
        for action in ('꿀뷰 열기', '다른 뷰어 프로그램 열기', '파일 위치 열기'):
            view = self.dummy(double_click=action)
            view.preview_errors = {str(path)}
            view.double_click(path)
            view.reveal.assert_called_once_with(path)
            view.open_archive.assert_not_called()
            view.open_settings.assert_not_called()

    def test_font_size_validation_before_saving(self):
        for size in (7, 25, 'bad'):
            view = self.dummy()
            with self.assertRaises(ValueError):
                view.commit_preferences('라이트', '파일 위치 열기', '', '', True, typography=dict(family='', size=size))
            view.save.assert_not_called()

    def test_font_preferences_saved_and_applied(self):
        view = self.dummy()
        view.font_size = 10
        view.remember_position = Mock()
        view.views = {}
        view.update_region = Mock()
        view.refresh_visible = Mock()
        with patch('preferences.font.families', return_value=['Meiryo']), patch('preferences.configure_fonts', return_value='Meiryo') as configure:
            view.commit_preferences('다크', '파일 위치 열기', '', '', True, typography=dict(family='Meiryo', size=16))
        self.assertEqual(view.settings['font_family'], 'Meiryo')
        self.assertEqual(view.settings['font_size'], 16)
        configure.assert_called_once_with(view, 'Meiryo', 16)
        view.save.assert_called_once()

    def test_four_distinct_themes_are_supported(self):
        self.assertEqual(set(PALETTES), {'라이트', '다크', '네이비', '블루'})
        self.assertEqual(len({p['bg'] for p in PALETTES.values()}), 4)
        for mode in PALETTES:
            view = self.dummy()
            view.commit_preferences(mode, '파일 위치 열기', '', '', True)
            self.assertEqual(view.settings['theme'], mode)

    def test_keyboard_actions_are_independent_and_none_is_keyboard_only(self):
        view = self.dummy()
        view.commit_preferences('라이트', '꿀뷰 열기', '', '', True, key_actions=dict(enter='파일 위치 열기', space='없음'))
        self.assertEqual(view.settings['double_click'], '꿀뷰 열기')
        self.assertEqual(view.settings['enter_action'], '파일 위치 열기')
        self.assertEqual(view.settings['space_action'], '없음')
        view.execute_action(Path('test.zip'), '없음')
        view.reveal.assert_not_called()
        view.open_archive.assert_not_called()
        with self.assertRaises(ValueError):
            view.commit_preferences('라이트', '없음', '', '', True)
        with self.assertRaises(ValueError):
            view.commit_preferences('라이트', '꿀뷰 열기', '', '', True, key_actions=dict(enter='다른 뷰어 프로그램 열기', space='없음'))

    def test_keyboard_favorite_action_works_even_when_preview_failed(self):
        path = Path('failed.zip')
        view = self.dummy()
        view.toggle_favorite = Mock()
        view.preview_errors = {str(path)}
        view.commit_preferences('다크', '파일 위치 열기', '', '', True,
                                key_actions=dict(enter='즐겨찾기 추가/해제', space='즐겨찾기 추가/해제'))
        view.execute_action(path, view.settings['enter_action'])
        view.toggle_favorite.assert_called_once_with(path)
        view.reveal.assert_not_called()
        view.open_archive.assert_not_called()
        with self.assertRaises(ValueError):
            view.commit_preferences('다크', '즐겨찾기 추가/해제', '', '', True)

    def test_double_click_dispatch(self):
        path = Path('archive with spaces.zip')
        view = self.dummy(double_click='파일 위치 열기')
        view.double_click(path)
        view.reveal.assert_called_once_with(path)
        view.settings['double_click'] = '꿀뷰 열기'
        view.double_click(path)
        view.open_archive.assert_called_once_with(path)
        view.settings.update(double_click='다른 뷰어 프로그램 열기', custom_viewer=sys.executable)
        with patch('preferences.subprocess.Popen') as launch:
            view.double_click(path)
            launch.assert_called_once_with([sys.executable, str(path.resolve())])

    def test_apply_saves_theme_and_only_rescans_when_needed(self):
        view = self.dummy()
        view.commit_preferences('다크', '파일 위치 열기', '', '', True)
        self.assertEqual(view.settings['theme'], '다크')
        view.save.assert_called_once()
        view.apply_theme.assert_called_once()
        view.scan.assert_not_called()
        view.commit_preferences('라이트', '파일 위치 열기', '', '', False)
        view.scan.assert_called_once()

    def test_invalid_custom_viewer_does_not_save(self):
        view = self.dummy(theme='라이트')
        with self.assertRaises(ValueError):
            view.commit_preferences('다크', '다른 뷰어 프로그램 열기', '', '', True)
        view.save.assert_not_called()
        self.assertEqual(view.settings['theme'], '라이트')
