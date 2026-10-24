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
        self.assertNotIn('size', values['pages'])
        invalid = normalize_overlay_settings({'favorite': {'size': []}, 'folder': {'size': 'unknown'}})
        self.assertEqual(invalid['favorite']['size'], 'large')
        self.assertEqual(invalid['folder']['size'], 'large')

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
                         {'visible': False, 'position': 'top_left'})
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


if __name__ == '__main__':
    unittest.main()
