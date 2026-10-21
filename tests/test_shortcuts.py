"""Shortcut migration and dispatch must preserve intentional user choices."""
import copy
from types import SimpleNamespace
import unittest

import shortcuts


class ShortcutTests(unittest.TestCase):
    def event(self, keysym, state=0, platform='win32'):
        return shortcuts.event_key(SimpleNamespace(keysym=keysym, state=state), platform)

    def test_defaults_follow_os_and_return_fresh_maps(self):
        mac = shortcuts.defaults('darwin')
        windows = shortcuts.defaults('win32')
        self.assertEqual(mac['reveal'], ['Enter', 'Space'])
        self.assertEqual(windows['viewer'], ['Enter', 'Space'])
        self.assertEqual(mac['trash'], ['Delete', 'Cmd+Backspace'])
        self.assertEqual(windows['trash'], ['Delete'])
        self.assertEqual(windows['rename'], ['F2'])
        self.assertEqual(windows['sidebar'], [])
        self.assertEqual(windows['fit'], [])
        self.assertEqual(windows['thumbnail_edit'], [])
        self.assertEqual(mac['thumbnail_edit'], [])
        self.assertEqual(shortcuts.validate(mac, 'darwin'), mac)
        mac['reveal'].clear()
        self.assertEqual(shortcuts.defaults('darwin')['reveal'], ['Enter', 'Space'])

    def test_legacy_choices_import_once_without_changing_double_click(self):
        settings = dict(enter_action='즐겨찾기 추가/해제', space_action='없음',
                        double_click='다른 뷰어 프로그램 열기')
        before = copy.deepcopy(settings)
        mapping = shortcuts.migrate(settings, 'win32')
        self.assertEqual(mapping['favorite'], ['Enter'])
        self.assertIsNone(shortcuts.command_for_key(mapping, 'Space'))
        self.assertEqual(settings, before)
        self.assertEqual(mapping['rename'], ['F2'])
        self.assertEqual(shortcuts.legacy_actions(mapping, 'win32'),
                         dict(enter_action='즐겨찾기 추가/해제', space_action='없음'))
        # Old cross-platform viewer settings use the same normalization as the UI.
        self.assertEqual(shortcuts.migrate(dict(enter_action='꿀뷰 열기'), 'darwin')['reveal'],
                         ['Enter', 'Space'])

    def test_null_and_saved_empty_assignments_stay_unassigned(self):
        legacy = shortcuts.migrate(dict(enter_action=None, space_action=None), 'win32')
        self.assertIsNone(shortcuts.command_for_key(legacy, 'Enter'))
        self.assertIsNone(shortcuts.command_for_key(legacy, 'Space'))
        saved = {command: [] for command in shortcuts.COMMANDS}
        settings = dict(shortcuts=saved, enter_action='꿀뷰 열기', space_action='꿀뷰 열기')
        self.assertEqual(shortcuts.migrate(settings, 'win32'), saved)
        self.assertEqual(shortcuts.legacy_actions(saved, 'win32'),
                         dict(enter_action='없음', space_action='없음'))

    def test_corrupt_or_foreign_settings_keep_only_usable_assignments(self):
        settings = dict(shortcuts=dict(reveal=['Return', 'Space'], viewer=['Enter'],
                        custom_viewer=['Unsupported'], favorite='F', rename=['F2'],
                        trash=['Cmd+Backspace', 'Delete'], unknown=['F4']))
        clean = shortcuts.migrate(settings, 'win32')
        self.assertEqual(clean['reveal'], ['Enter', 'Space'])
        self.assertEqual(clean['viewer'], [])
        self.assertEqual(clean['rename'], ['F2'])
        self.assertEqual(clean['trash'], ['Delete'])
        self.assertEqual(shortcuts.validate(clean, 'win32'), clean)
        self.assertEqual(shortcuts.migrate({'shortcuts': 'bad'}, 'win32'),
                         shortcuts.defaults('win32'))

    def test_saved_six_command_mapping_preserves_choices_and_adds_empty_view_rows(self):
        saved = dict(reveal=['Ctrl+R'], viewer=['Space'], custom_viewer=[],
                     favorite=['Enter'], rename=[], trash=['Delete'])
        settings = dict(shortcuts=saved)
        before = copy.deepcopy(settings)
        self.assertEqual(shortcuts.migrate(settings, 'win32'),
                         dict(saved, sidebar=[], fit=[], thumbnail_edit=[]))
        self.assertEqual(settings, before)

    def test_existing_eight_commands_keep_their_assignments_when_editor_is_added(self):
        saved = dict(reveal=['Ctrl+R'], viewer=['Space'], custom_viewer=[],
                     favorite=['Enter'], rename=['F2'], trash=['Delete'],
                     sidebar=['Ctrl+B'], fit=['Ctrl+F'])
        settings = dict(shortcuts=saved, double_click='파일 위치 열기')
        before = copy.deepcopy(settings)
        for platform in ('win32', 'darwin'):
            with self.subTest(platform=platform):
                self.assertEqual(shortcuts.migrate(settings, platform),
                                 dict(saved, thumbnail_edit=[]))
        self.assertEqual(settings, before)

    def test_editor_supports_two_keys_and_rejects_conflicts(self):
        mapping = shortcuts.validate(dict(thumbnail_edit=['F8', 'Ctrl+E']), 'win32')
        self.assertEqual(shortcuts.command_labels('win32')['thumbnail_edit'], '썸네일 영역 편집')
        self.assertEqual(shortcuts.command_for_key(mapping, 'F8'), 'thumbnail_edit')
        self.assertEqual(shortcuts.command_for_key(mapping, 'control+e'), 'thumbnail_edit')
        self.assertEqual(shortcuts.migrate(dict(shortcuts=mapping), 'win32'), mapping)
        for conflicting in (dict(thumbnail_edit=['F2'], rename=['F2']),
                            dict(thumbnail_edit=['Return'], favorite=['Enter']),
                            dict(thumbnail_edit=['Ctrl+E', 'control+e'])):
            with self.subTest(mapping=conflicting), self.assertRaisesRegex(ValueError, '중복'):
                shortcuts.validate(conflicting, 'win32')
        with self.assertRaisesRegex(ValueError, '최대 2개'):
            shortcuts.validate(dict(thumbnail_edit=['F6', 'F7', 'F8']), 'win32')

    def test_editor_enter_space_do_not_become_unsupported_legacy_actions(self):
        for platform in ('win32', 'darwin'):
            with self.subTest(platform=platform):
                mapping = shortcuts.validate(dict(thumbnail_edit=['Enter', 'Space']), platform)
                self.assertEqual(shortcuts.legacy_actions(mapping, platform),
                                 dict(enter_action='없음', space_action='없음'))
                self.assertEqual(shortcuts.command_for_key(mapping, 'Return'), 'thumbnail_edit')
                self.assertEqual(shortcuts.command_for_key(mapping, 'Space'), 'thumbnail_edit')

    def test_view_keys_dispatch_and_reject_conflicts_with_existing_commands(self):
        mapping = shortcuts.validate(dict(sidebar=['Ctrl+B'], fit=['Ctrl+F']), 'win32')
        self.assertEqual(shortcuts.command_for_key(mapping, 'control+b'), 'sidebar')
        self.assertEqual(shortcuts.command_for_key(mapping, 'Ctrl+F'), 'fit')
        self.assertEqual(shortcuts.migrate(dict(shortcuts=mapping), 'win32'), mapping)
        self.assertEqual(shortcuts.command_labels('win32')['sidebar'], '폴더 패널 접기/펴기')
        self.assertEqual(shortcuts.command_labels('win32')['fit'], '창에 맞춤 ON/OFF')
        for conflicting in (dict(sidebar=['Return'], viewer=['Enter']),
                            dict(fit=['F2'], rename=['F2']),
                            dict(sidebar=['Ctrl+B'], fit=['control+b'])):
            with self.subTest(mapping=conflicting), self.assertRaisesRegex(ValueError, '중복'):
                shortcuts.validate(conflicting, 'win32')

    def test_view_commands_do_not_become_unsupported_legacy_actions(self):
        mapping = shortcuts.validate(dict(sidebar=['Enter'], fit=['Space']), 'win32')
        self.assertEqual(shortcuts.legacy_actions(mapping, 'win32'),
                         dict(enter_action='없음', space_action='없음'))
        self.assertEqual(shortcuts.command_for_key(mapping, 'Enter'), 'sidebar')
        self.assertEqual(shortcuts.command_for_key(mapping, 'Space'), 'fit')

    def test_key_aliases_and_modifier_order_have_one_identity(self):
        aliases = {'Return': 'Enter', 'KP_Enter': 'Enter', 'KeypadEnter': 'Enter',
                   'space': 'Space', ' ': 'Space', 'del': 'Delete', 'a': 'A',
                   'shift+control+a': 'Ctrl+Shift+A',
                   'command+option+BackSpace': 'Alt+Cmd+Backspace',
                   'Ctrl+!': 'Ctrl+Shift+1', 'Ctrl++': 'Ctrl+Shift+='}
        for value, expected in aliases.items():
            with self.subTest(value=value):
                self.assertEqual(shortcuts.normalize_key(value), expected)
        for value in (None, '', '없음', 'None'):
            self.assertEqual(shortcuts.normalize_key(value), '')
        with self.assertRaises(ValueError):
            shortcuts.normalize_key('A+B')

    def test_duplicate_aliases_same_or_different_commands_are_rejected(self):
        for mapping in ({'reveal': ['Return'], 'favorite': ['Enter']},
                        {'favorite': ['Ctrl+A', 'control+a']},
                        {'favorite': ['KP_Enter'], 'trash': ['KeypadEnter']}):
            with self.subTest(mapping=mapping), self.assertRaisesRegex(ValueError, '중복'):
                shortcuts.validate(mapping, 'win32')
        with self.assertRaises(ValueError):
            shortcuts.validate({'favorite': ['A', 'B', 'C']}, 'win32')
        with self.assertRaises(ValueError):
            shortcuts.validate({'unknown': ['F4']}, 'win32')

    def test_navigation_keys_are_reserved_but_modified_chords_are_supported(self):
        for key in ('Left', 'Right', 'Up', 'Down', 'Home', 'End', 'Prior', 'Next', 'Tab', 'Esc'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                shortcuts.validate({'favorite': [key]}, 'win32')
        self.assertEqual(shortcuts.validate({'favorite': ['Ctrl+Home']}, 'win32')['favorite'],
                         ['Ctrl+Home'])
        with self.assertRaisesRegex(ValueError, 'macOS'):
            shortcuts.validate({'trash': ['Cmd+Backspace']}, 'win32')

    def test_event_masks_ignore_caps_num_lock_and_native_keypad_fn_bits(self):
        self.assertEqual(self.event('F2', 0x2 | 0x8 | 0x20), 'F2')
        self.assertEqual(self.event('Delete', 0x2 | 0x8), 'Delete')
        self.assertEqual(self.event('a', 0x4 | 0x1), 'Ctrl+Shift+A')
        self.assertEqual(self.event('A', 0x2), 'A')
        self.assertEqual(self.event('KP_Enter', 0x8), 'Enter')
        self.assertEqual(self.event('Return', 0x20 | 0x40, 'darwin'), 'Enter')
        self.assertEqual(self.event('BackSpace', 0x8, 'darwin'), 'Cmd+Backspace')
        self.assertEqual(self.event('a', 0x10, 'darwin'), 'Alt+A')
        self.assertEqual(self.event('a', 0x10), 'Alt+A')
        self.assertEqual(self.event('a', 0x20000), 'Alt+A')
        self.assertEqual(self.event('exclam', 0x4 | 0x1), 'Ctrl+Shift+1')

    def test_modifier_and_unsupported_events_never_trigger_a_command(self):
        mapping = shortcuts.defaults('win32')
        for keysym in ('Shift_L', 'Control_R', 'Alt_L', 'Meta_L', 'Caps_Lock', 'Fn', '한'):
            key = self.event(keysym)
            self.assertIsNone(key)
            self.assertIsNone(shortcuts.command_for_key(mapping, key))
        self.assertEqual(shortcuts.command_for_key(mapping, 'KP_Enter'), 'viewer')
        self.assertIsNone(shortcuts.command_for_key(mapping, 'Ctrl+Enter'))
        mapping = shortcuts.validate({'rename': ['Enter'], 'trash': ['Space']}, 'win32')
        self.assertEqual(shortcuts.legacy_actions(mapping, 'win32'),
                         dict(enter_action='파일 이름 바꾸기', space_action='휴지통으로 보내기'))


if __name__ == '__main__':
    unittest.main()
