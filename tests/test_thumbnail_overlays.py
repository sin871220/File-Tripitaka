import unittest
from unittest.mock import Mock

from preferences import Preferences
from thumbnail_overlays import (DEFAULT_OVERLAYS, OVERLAY_ORDER,
                                normalize_overlay_settings, normalize_overlay_order)


class OverlaySettingsTests(unittest.TestCase):
    def test_old_settings_get_independent_defaults(self):
        first = normalize_overlay_settings()
        self.assertEqual(first, DEFAULT_OVERLAYS)
        first['favorite']['visible'] = False
        self.assertTrue(normalize_overlay_settings()['favorite']['visible'])

    def test_partial_and_invalid_saved_values_fall_back_per_field(self):
        values = normalize_overlay_settings({
            'favorite': {'visible': False, 'position': 'bottom_left'},
            'folder': {'visible': 'false', 'position': ['invalid']},
            'pages': None, 'unknown': {'visible': False},
        })
        self.assertEqual(values['favorite'], {'visible': False, 'position': 'bottom_left', 'size': 'large'})
        self.assertEqual(values['folder'], DEFAULT_OVERLAYS['folder'])
        self.assertEqual(values['pages'], DEFAULT_OVERLAYS['pages'])
        self.assertEqual(set(values), set(DEFAULT_OVERLAYS))
        self.assertEqual(normalize_overlay_settings([]), DEFAULT_OVERLAYS)

    def test_sizes_are_independent_and_legacy_or_invalid_values_use_current_large(self):
        values = normalize_overlay_settings({'favorite': {'size': 'medium'},
                                             'folder': {'size': 'small'},
                                             'pages': {'size': 'small'}})
        self.assertEqual(values['favorite']['size'], 'medium')
        self.assertEqual(values['folder']['size'], 'small')
        self.assertEqual(values['pages']['font_size'], 5)
        self.assertNotIn('size', values['pages'])
        invalid = normalize_overlay_settings({'favorite': {'size': []}, 'folder': {'size': 'unknown'}})
        self.assertEqual(invalid['favorite']['size'], 'large')
        self.assertEqual(invalid['folder']['size'], 'large')

    def test_page_colors_and_alpha_validate_independently(self):
        values = normalize_overlay_settings({'pages': {'size': 'medium', 'text_color': '#1a2b3c',
                                                       'background_color': '#aabbcc', 'background_alpha': 35}})
        self.assertEqual(values['pages']['font_size'], 7)
        self.assertEqual(values['pages']['text_color'], '#1A2B3C')
        self.assertEqual(values['pages']['background_color'], '#AABBCC')
        self.assertEqual(values['pages']['background_alpha'], 35)
        for alpha in (0, 100):
            self.assertEqual(normalize_overlay_settings({'pages': {'background_alpha': alpha}})['pages']['background_alpha'], alpha)
        for alpha in (-1, 101, '35', True, None, float('nan')):
            self.assertEqual(normalize_overlay_settings({'pages': {'background_alpha': alpha}})['pages']['background_alpha'], 100)
        for color in ('red', '#123', '#00GG00', None, []):
            values = normalize_overlay_settings({'pages': {'text_color': color, 'background_color': color}})
            self.assertEqual(values['pages']['text_color'], '#FFFFFF')
            self.assertEqual(values['pages']['background_color'], '#242830')

    def test_page_font_points_are_fixed_and_legacy_sizes_migrate_once(self):
        for points in (4, 10, 18, 72):
            for ui_points in (8, 10, 24):
                values = normalize_overlay_settings({'pages': {'font_size': points}}, ui_font_size=ui_points)
                self.assertEqual(values['pages']['font_size'], points)
                self.assertNotIn('size', values['pages'])
        for legacy, ui_points, expected in (('large', 8, 10), ('medium', 18, 12), ('small', 24, 12)):
            migrated = normalize_overlay_settings({'pages': {'size': legacy}}, ui_font_size=ui_points)
            self.assertEqual(migrated['pages']['font_size'], expected)
            self.assertEqual(normalize_overlay_settings(migrated, ui_font_size=24)['pages']['font_size'], expected)
        for invalid in (3, 73, True, '18', None):
            self.assertEqual(normalize_overlay_settings({'pages': {'font_size': invalid}})['pages']['font_size'], 10)

    def test_saved_order_preserves_known_unique_items_and_fills_missing(self):
        self.assertEqual(normalize_overlay_order(), list(OVERLAY_ORDER))
        self.assertEqual(normalize_overlay_order('pages'), list(OVERLAY_ORDER))
        self.assertEqual(normalize_overlay_order(['pages', 'pages', {}, 'unknown', 'favorite']),
                         ['pages', 'favorite', 'folder'])
        self.assertEqual(normalize_overlay_order(('folder',)), ['folder', 'favorite', 'pages'])
        values = normalize_overlay_order()
        values.reverse()
        self.assertEqual(normalize_overlay_order(), list(OVERLAY_ORDER))

    def view(self):
        view = Preferences()
        view.settings = {}
        view.recursive = Mock()
        view.recursive.get.return_value = True
        view.current_folder = ''
        view.save = Mock()
        view.apply_theme = Mock()
        view.refresh_card_labels = Mock()
        return view

    def test_preference_apply_copies_draft_and_legacy_call_preserves_it(self):
        view = self.view()
        draft = normalize_overlay_settings()
        draft['pages'] = {'visible': False, 'position': 'top_left'}
        view.commit_preferences('다크', '파일 위치 열기', '', '', True, overlays=draft)
        draft['pages']['visible'] = True
        self.assertFalse(view.settings['thumbnail_overlays']['pages']['visible'])
        view.commit_preferences('라이트', '파일 위치 열기', '', '', True)
        self.assertEqual(view.settings['thumbnail_overlays']['pages'],
                         dict(DEFAULT_OVERLAYS['pages'], visible=False, position='top_left'))
        self.assertEqual(view.refresh_card_labels.call_count, 2)

    def test_invalid_other_preference_does_not_save_overlay_draft(self):
        view = self.view()
        with self.assertRaises(ValueError):
            view.commit_preferences('다크', '파일 위치 열기', '', '', True,
                                    typography={'size': 99}, overlays=normalize_overlay_settings())
        self.assertNotIn('thumbnail_overlays', view.settings)
        view.save.assert_not_called()

    def test_order_is_copied_and_preserved_by_legacy_preference_calls(self):
        view = self.view()
        order = ['pages', 'favorite', 'folder']
        view.commit_preferences('다크', '파일 위치 열기', '', '', True, overlay_order=order)
        order.reverse()
        self.assertEqual(view.settings['thumbnail_overlay_order'], ['pages', 'favorite', 'folder'])
        view.commit_preferences('라이트', '파일 위치 열기', '', '', True)
        self.assertEqual(view.settings['thumbnail_overlay_order'], ['pages', 'favorite', 'folder'])
        with self.assertRaises(ValueError):
            view.commit_preferences('다크', '파일 위치 열기', '', '', True,
                                    typography={'size': 99}, overlay_order=list(OVERLAY_ORDER))
        self.assertEqual(view.settings['thumbnail_overlay_order'], ['pages', 'favorite', 'folder'])

    def test_invalid_explicit_page_alpha_prevents_any_preferences_save(self):
        for alpha in (-1, 101, 'bad', True):
            view = self.view()
            draft = normalize_overlay_settings()
            draft['pages']['background_alpha'] = alpha
            with self.assertRaises(ValueError):
                view.commit_preferences('다크', '파일 위치 열기', '', '', True, overlays=draft)
            self.assertNotIn('thumbnail_overlays', view.settings)
            view.save.assert_not_called()

    def test_invalid_explicit_page_font_points_prevent_any_preferences_save(self):
        for points in (3, 73, 'bad', True):
            view = self.view()
            draft = normalize_overlay_settings()
            draft['pages']['font_size'] = points
            with self.assertRaises(ValueError):
                view.commit_preferences('다크', '파일 위치 열기', '', '', True, overlays=draft)
            self.assertNotIn('thumbnail_overlays', view.settings)
            view.save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
