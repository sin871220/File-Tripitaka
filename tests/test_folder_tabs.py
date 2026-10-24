import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from folder_tabs import (MAX_FOLDER_TABS, new_folder_tab, normalize_active_tab,
                         normalize_folder_tabs, tab_label, tab_path_key)


class FolderTabStateTests(unittest.TestCase):
    def identity(self, number):
        return 'folder:' + f'{number:032x}'

    def test_loading_repairs_ids_deduplicates_paths_and_preserves_literals(self):
        first = self.identity(1)
        saved = [
            {'id': first, 'path': '資料/日本語/../日本語'},
            {'id': self.identity(2), 'path': './資料/日本語/'},
            {'id': first, 'path': '별도.폴더'},
            {'id': 'bad-id', 'path': '設定'},
            {'id': 'all', 'path': 'English'},
        ]
        records = normalize_folder_tabs(saved)
        self.assertEqual(len(records), 4)
        self.assertEqual(records[0], {'id': first, 'path': os.path.abspath('資料/日本語')})
        self.assertEqual(len({item['id'] for item in records}), 4)
        self.assertTrue(all(re.fullmatch(r'folder:[0-9a-f]{32}', item['id']) for item in records))
        self.assertEqual([tab_label(item['path']) for item in records],
                         ['日本語', '별도.폴더', '設定', 'English'])
        self.assertEqual(saved[0]['path'], '資料/日本語/../日本語')
        self.assertEqual(saved[2]['id'], first, 'Loading must not mutate the saved input')

    def test_invalid_saved_records_are_ignored_without_filesystem_probes(self):
        with patch.object(Path, 'stat', side_effect=AssertionError('No stat on load')), \
                patch.object(Path, 'resolve', side_effect=AssertionError('No resolve on load')), \
                patch('os.scandir', side_effect=AssertionError('No scan on load')):
            self.assertEqual(normalize_folder_tabs(None), [])
            self.assertEqual(normalize_folder_tabs({}), [])
            records = normalize_folder_tabs([
                None, [], 'folder', {}, {'path': None}, {'path': ''}, {'path': '  '},
                {'path': 'bad\0path'}, {'path': b'bytes'}, {'path': 'x' * 32769},
                {'path': '/not-mounted/example/資料'},
            ])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['path'], os.path.abspath('/not-mounted/example/資料'))

    def test_path_keys_expand_home_and_normalize_native_case(self):
        home = os.path.abspath('/tmp/folder-tab-home')
        with patch.dict(os.environ, {'HOME': home, 'USERPROFILE': home}):
            self.assertEqual(tab_path_key('~/Library/../資料'),
                             os.path.normcase(os.path.join(home, '資料')))
        with patch('os.path.normcase', side_effect=lambda value: value.casefold()):
            records = normalize_folder_tabs([{'path': '/tmp/Book'}, {'path': '/tmp/BOOK/'}])
            self.assertEqual(len(records), 1)
            found, added = new_folder_tab('/tmp/book', records)
            self.assertFalse(added)
            self.assertEqual(found['id'], records[0]['id'])

    def test_new_tabs_have_stable_distinct_identities_and_reuse_existing_path(self):
        existing = normalize_folder_tabs([{'path': '/disconnected/写真'}])
        before = [dict(item) for item in existing]
        record, added = new_folder_tab('/disconnected/写真/../写真', existing)
        self.assertFalse(added)
        self.assertEqual(record, existing[0])
        record['path'] = 'caller changed copy'
        self.assertEqual(existing, before)
        new, added = new_folder_tab(Path('/disconnected/Another'), existing)
        self.assertTrue(added)
        self.assertNotEqual(new['id'], existing[0]['id'])
        self.assertEqual(new['path'], os.path.abspath('/disconnected/Another'))
        self.assertEqual(existing, before)
        self.assertEqual(normalize_folder_tabs(existing), existing)

    def test_invalid_new_paths_raise_before_changing_existing_records(self):
        for value in (None, '', ' ', b'bytes', 'bad\0path'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                new_folder_tab(value, [])

    def test_root_labels_and_literal_names(self):
        root = Path(os.path.abspath(os.sep)).anchor
        self.assertEqual(tab_label(root), root)
        self.assertEqual(tab_label('/tmp/설정'), '설정')
        self.assertEqual(tab_label('/tmp/日本語.資料/'), '日本語.資料')
        if os.name == 'nt':
            self.assertEqual(tab_label('D:\\'), 'D:\\')
            self.assertEqual(tab_label('D:\\資料\\日本語'), '日本語')

    def test_active_tab_restoration_rejects_missing_and_corrupt_ids(self):
        records = normalize_folder_tabs([{'id': self.identity(1), 'path': '/tmp/Book'}])
        self.assertEqual(normalize_active_tab('all', records, True), 'all')
        self.assertEqual(normalize_active_tab('favorites', records), 'favorites')
        self.assertEqual(normalize_active_tab(records[0]['id'], records), records[0]['id'])
        for value in (None, '', [], {}, 'folder:missing', self.identity(2)):
            self.assertEqual(normalize_active_tab(value, records), 'all')
            self.assertEqual(normalize_active_tab(value, records, True), 'favorites')
        self.assertEqual(normalize_active_tab(None, [], 'false'), 'all')

    def test_saved_tab_capacity_is_bounded_and_existing_tab_can_still_focus(self):
        saved = [{'id': self.identity(index + 1), 'path': f'/tmp/Folder-{index}'}
                 for index in range(MAX_FOLDER_TABS + 1)]
        records = normalize_folder_tabs(saved)
        self.assertEqual(len(records), MAX_FOLDER_TABS)
        same, added = new_folder_tab(records[-1]['path'], records)
        self.assertEqual(same, records[-1])
        self.assertFalse(added)
        with self.assertRaises(ValueError):
            new_folder_tab('/tmp/New', records)


if __name__ == '__main__':
    unittest.main()
