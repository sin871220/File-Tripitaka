"""Real Tk integration checks for mixed archive/folder libraries using only fixtures."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_settings = tempfile.TemporaryDirectory(prefix='file-tripitaka-folder-gallery-settings-')
os.environ['LOCALAPPDATA'] = _settings.name
import app as module
from PIL import Image

sys.excepthook = sys.__excepthook__


class FolderGallerySmoke(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='file-tripitaka-folder-gallery-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.library = self.root / 'Library'
        self.library.mkdir()
        self.other = self.root / 'Elsewhere'
        self.other.mkdir()
        data = io.BytesIO()
        Image.new('RGB', (80, 120), '#3070a0').save(data, 'PNG')
        self.image_bytes = data.getvalue()
        (self.library / 'front.png').write_bytes(self.image_bytes)
        self.folders = []
        self.archives = []
        for index in range(36):
            folder = self.library / f'Book-{index:03d}'
            folder.mkdir()
            (folder / '1.png').write_bytes(self.image_bytes)
            (folder / '2.png').write_bytes(self.image_bytes)
            self.folders.append(folder)
            archive = self.library / f'Archive-{index:03d}.zip'
            with zipfile.ZipFile(archive, 'w') as stream:
                stream.writestr('1.png', self.image_bytes)
            self.archives.append(archive)
        nested = self.library / 'Container' / 'Nested'
        nested.mkdir(parents=True)
        (nested / 'page.png').write_bytes(self.image_bytes)
        self.folders.extend((nested, self.library))
        module.CONFIG.unlink(missing_ok=True)
        self.errors, self.messages, self.apps = [], [], []
        self.addCleanup(patch.stopall)
        patch.object(module.App, 'populate_tree').start()
        patch.object(module.App, 'thumbnail_recipes', return_value={}).start()
        patch.object(module, 'cover', side_effect=lambda *args: Image.new('RGB', (80, 120), '#3070a0')).start()
        self.launch_default = patch.object(module, 'launch_default',
                                           side_effect=AssertionError('External app prohibited')).start()
        self.reveal_file = patch.object(module, 'reveal_file',
                                       side_effect=AssertionError('External file manager prohibited')).start()
        self.trash = patch.object(module, 'trash_archive',
                                  side_effect=AssertionError('Real Trash prohibited')).start()
        self.rename = patch.object(module, 'rename_archive',
                                   side_effect=AssertionError('Real rename prohibited')).start()
        patch.object(module.messagebox, 'showerror',
                     side_effect=lambda *args, **kwargs: self.messages.append(args)).start()
        self.ask = patch.object(module.messagebox, 'askyesno',
                                side_effect=AssertionError('Folder deletion confirmation prohibited')).start()
        self.addCleanup(self.close_apps)
        self.app = self.make_app()
        self.navigate(self.library)

    def make_app(self):
        app = module.App()
        app.report_callback_exception = lambda *args: self.errors.append(args)
        self.apps.append(app)
        app.update()
        return app

    def close_apps(self):
        for app in self.apps:
            if not app.closing:
                app.close()
            for pool in (app.pool, app.folder_pool, app.thumbnail_edit_pool):
                pool.shutdown(wait=True, cancel_futures=True)
        self.assertFalse(self.errors, self.errors)
        self.assertFalse(self.messages, self.messages)

    def wait_for(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            self.assertFalse(self.errors, self.errors)
            if predicate():
                return
            time.sleep(0.005)
        self.fail('Tk integration operation did not complete')

    def settle(self):
        self.wait_for(lambda: not self.app.pending and self.app.active == 0
                      and self.app.results.empty())

    def navigate(self, path):
        generation = self.app.scan_generation
        self.app.navigate(path)
        self.wait_for(lambda: self.app.scan_generation > generation
                      and bool(self.app.files))
        self.settle()

    def set_filter(self, value):
        self.app.kind_filter.set(value)
        self.app.change_kind_filter()
        self.app.update()
        self.settle()

    def set_group(self, value):
        self.app.group_control.set(value)
        self.app.group_control.event_generate('<<ComboboxSelected>>')
        self.app.update()
        self.settle()

    def set_sort(self, value):
        self.app.sort_control.set(value)
        self.app.sort_control.event_generate('<<ComboboxSelected>>')
        self.app.update()
        self.settle()

    def assert_arrangement(self, arrangement):
        app = self.app
        folders = [path for path in app.filtered if app.item_kinds.get(path) == 'folder']
        archives = [path for path in app.filtered if app.item_kinds.get(path) != 'folder']
        self.assertEqual(folders, module.sort_archives(folders, app.sort_order.get(), app.modified))
        self.assertEqual(archives, module.sort_archives(archives, app.sort_order.get(), app.modified))
        if arrangement == '폴더 먼저':
            self.assertEqual(app.filtered, folders + archives)
        elif arrangement == '파일 먼저':
            self.assertEqual(app.filtered, archives + folders)
        else:
            self.assertEqual(app.filtered, module.sort_archives(app.filtered, app.sort_order.get(), app.modified))

    def tab(self, index):
        self.app.tabs.select(index)
        self.app.switch_tab()
        self.app.update()
        self.settle()

    def card(self, path):
        index = self.app.filtered.index(path)
        if index not in self.app.cards:
            rows = max(1, (len(self.app.filtered) + self.app.columns() - 1) // self.app.columns())
            self.app.scroll_view('moveto', (index // self.app.columns()) / rows)
            self.app.refresh_visible()
        return self.app.cards[index][1]

    def test_actual_scan_mixes_direct_image_folders_and_archives_with_filters(self):
        app = self.app
        self.assertEqual(set(app.files), set(self.folders + self.archives))
        self.assertNotIn(self.library / 'Container', app.files)
        self.assertTrue(all(app.item_kinds[path] == 'folder' for path in self.folders))
        self.assertTrue(all(app.item_kinds[path] == 'archive' for path in self.archives))
        self.assertEqual(tuple(app.kind_control.cget('values')), ('전체', '압축파일', '폴더'))
        self.set_filter('폴더')
        self.assertEqual(set(app.filtered), set(self.folders))
        frame = self.card(self.folders[0])
        self.assertTrue(frame.folder)
        self.assertEqual(app.canvas.itemcget(frame.folder_item, 'state'), 'normal')
        self.set_filter('압축파일')
        self.assertEqual(set(app.filtered), set(self.archives))
        app.query.set('Archive-01')
        app.apply_search()
        self.assertEqual(set(app.filtered), set(self.archives[10:20]))
        app.sort_order.set('이름 내림차순')
        app.apply_search()
        self.assertEqual(app.filtered, list(reversed(self.archives[10:20])))
        app.query.set('')
        self.set_filter('전체')
        app.pending_restore = None
        app.recursive.set(False)
        app.scan()
        self.wait_for(lambda: len(app.files) == len(self.archives) + 1)
        self.assertEqual(set(app.files), set(self.archives + [self.library]))

    def test_compact_sort_and_three_arrangements_apply_independently(self):
        app = self.app
        self.assertEqual(app.group_order.get(), '섞어서', 'Old settings must default to mixed')
        self.assertEqual(tuple(app.group_control.cget('values')), ('섞어서', '폴더 먼저', '파일 먼저'))
        self.assertEqual(tuple(app.sort_control.cget('values')),
                         ('이름 ▲', '이름 ▼', '수정 날짜 ▲', '수정 날짜 ▼',
                          '용량 ▲', '용량 ▼'))
        # Interleaved times make mixed date ordering observably different from
        # either partition, and equal times exercise stable name tie-breaking.
        for index, path in enumerate(app.files):
            app.modified[path] = index % 7
        for display, model in (('이름 ▲', '이름 오름차순'), ('이름 ▼', '이름 내림차순'),
                               ('수정 날짜 ▲', '수정한 날짜 오름차순'),
                               ('수정 날짜 ▼', '수정한 날짜 내림차순')):
            self.set_sort(display)
            self.assertEqual(app.sort_order.get(), model)
            for arrangement in ('섞어서', '폴더 먼저', '파일 먼저'):
                with self.subTest(sort=display, arrangement=arrangement):
                    self.set_group(arrangement)
                    self.assertEqual(app.group_order.get(), arrangement)
                    self.assert_arrangement(arrangement)
                    self.assertEqual(set(app.filtered), set(self.folders + self.archives))

    def test_size_sort_uses_all_item_sizes_and_keeps_folder_partition_direction(self):
        app = self.app
        for display, model, descending in (('용량 ▲', '용량 오름차순', False),
                                            ('용량 ▼', '용량 내림차순', True)):
            self.set_sort(display)
            self.assertEqual(app.sort_order.get(), model)
            for arrangement in ('섞어서', '폴더 먼저', '파일 먼저'):
                with self.subTest(sort=display, arrangement=arrangement):
                    self.set_group(arrangement)
                    self.assertEqual(set(app.filtered), set(self.folders + self.archives))
                    if arrangement == '섞어서':
                        groups = [app.filtered]
                    else:
                        folders = [path for path in app.filtered if app.item_kinds[path] == 'folder']
                        archives = [path for path in app.filtered if app.item_kinds[path] == 'archive']
                        self.assertEqual(app.filtered, folders + archives if arrangement == '폴더 먼저'
                                         else archives + folders)
                        groups = [folders, archives]
                    for group in groups:
                        sizes = [app.metadata[path][0] for path in group]
                        self.assertEqual(sizes, sorted(sizes, reverse=descending))
        for attribute in ('page_count_pool', 'page_count_cache', 'page_count_job'):
            self.assertFalse(hasattr(app, attribute), 'Size sorting must not add all-library page counting')

    def test_retired_page_sort_preferences_restore_to_name_sort_in_all_tabs(self):
        app = self.app
        app.close()
        for pool in (app.pool, app.folder_pool, app.thumbnail_edit_pool):
            pool.shutdown(wait=True, cancel_futures=True)
        saved = json.loads(module.CONFIG.read_text('utf-8'))
        folder = str(self.library)
        saved['sort'] = '페이지 수 내림차순'
        saved['only_favorites'] = False
        saved['file_favorites'] = [str(self.folders[0]), str(self.archives[0])]
        saved['folder_item_favorites'] = [str(self.folders[0])]
        saved.setdefault('views', {})[folder] = {'sort': '페이지 수 오름차순'}
        saved.setdefault('tab_views', {})[folder] = {'all': {'sort': '페이지 수 내림차순'}}
        saved['tab_views']['__global_favorites__'] = {
            'favorites': {'sort': '페이지 수 오름차순', 'kind_filter': '전체',
                          'group_order': '섞어서', 'query': ''}}
        module.CONFIG.write_text(json.dumps(saved, ensure_ascii=False), 'utf-8')
        self.app = app = self.make_app()
        self.wait_for(lambda: bool(app.files))
        self.settle()
        choices = ('이름 ▲', '이름 ▼', '수정 날짜 ▲', '수정 날짜 ▼', '용량 ▲', '용량 ▼')
        self.assertEqual(tuple(app.sort_control.cget('values')), choices)
        self.assertEqual(app.sort_order.get(), '이름 오름차순')
        self.assertEqual(app.sort_control.get(), '이름 ▲')
        self.assertEqual(app.filtered, module.sort_archives(app.files, '이름 오름차순', app.modified))
        self.tab(1)
        self.assertEqual(app.sort_order.get(), '이름 오름차순')
        self.assertEqual(app.sort_control.get(), '이름 ▲')
        self.assertEqual(set(app.filtered), {self.folders[0], self.archives[0]})
        self.tab(0)
        self.assertEqual(app.sort_order.get(), '이름 오름차순')
        for attribute in ('page_count_pool', 'page_count_cache', 'page_count_job'):
            self.assertFalse(hasattr(app, attribute))
        app.save()
        self.assertEqual(json.loads(module.CONFIG.read_text('utf-8'))['sort'], '이름 오름차순')

    def test_group_order_survives_favorite_reconciliation_and_single_kind_filters(self):
        app = self.app
        for path in self.folders + self.archives:
            app.toggle_favorite(path)
        self.tab(1)
        self.set_sort('이름 ▼')
        self.set_group('파일 먼저')
        self.assert_arrangement('파일 먼저')
        app.scroll_view('moveto', 0.3)
        app.refresh_visible()
        self.settle()
        index = min(len(app.filtered) - 2,
                    int(app.canvas.canvasy(0) // app.row_height()) * app.columns() + app.columns())
        selected, following = app.filtered[index:index + 2]
        app.select_card(selected)
        before = {path: frame for path, frame, _, _ in app.cards.values()}
        top, generation = app.canvas.canvasy(0), app.generation
        app.settings['shortcuts']['favorite'] = ['F6']
        app.refresh_shortcuts()
        app.canvas.focus_force()
        app.update()
        app.canvas.event_generate('<F6>')
        app.update()
        self.assertNotIn(selected, app.filtered)
        self.assertEqual(app.selected_path, following)
        self.assertEqual(app.canvas.canvasy(0), top)
        self.assertEqual(app.generation, generation)
        self.assert_arrangement('파일 먼저')
        after = {path: frame for path, frame, _, _ in app.cards.values()}
        for survivor in before.keys() & after.keys():
            self.assertIs(before[survivor], after[survivor])
        for kind in ('폴더', '압축파일'):
            self.set_filter(kind)
            self.assertTrue(app.group_control.instate(['disabled']))
            self.assertEqual(app.group_order.get(), '파일 먼저')
        self.set_filter('전체')
        self.assertTrue(app.group_control.instate(['readonly', '!disabled']))
        self.assertEqual(app.group_order.get(), '파일 먼저')
        self.assert_arrangement('파일 먼저')

    def test_group_sort_and_empty_views_restore_per_tab_and_restart(self):
        app = self.app
        for path in self.folders + self.archives:
            app.toggle_favorite(path)
        self.set_group('폴더 먼저')
        self.set_sort('이름 ▼')
        app.scroll_view('moveto', 3 * app.row_height() / app.scroll_height())
        app.refresh_visible()
        app.remember_position()
        all_view = app.views[app.current_folder].copy()
        self.tab(1)
        self.set_group('파일 먼저')
        self.set_sort('수정 날짜 ▲')
        app.scroll_view('moveto', 2 * app.row_height() / app.scroll_height())
        app.refresh_visible()
        app.remember_position()
        favorite_view = app.tab_views['__global_favorites__']['favorites'].copy()
        self.tab(0)
        self.assertEqual(app.group_order.get(), '폴더 먼저')
        self.assertEqual(app.sort_order.get(), '이름 내림차순')
        self.assertEqual(app.filtered[int(app.canvas.canvasy(0) // app.row_height()) * app.columns()],
                         Path(all_view['anchor']))
        self.tab(1)
        self.assertEqual(app.group_order.get(), '파일 먼저')
        self.assertEqual(app.sort_order.get(), '수정한 날짜 오름차순')
        self.assertEqual(app.filtered[int(app.canvas.canvasy(0) // app.row_height()) * app.columns()],
                         Path(favorite_view['anchor']))
        app.query.set('No matching group fixture')
        app.apply_search()
        self.assertEqual(app.filtered, [])
        self.tab(0)
        self.tab(1)
        self.assertEqual(app.query.get(), 'No matching group fixture')
        self.assertEqual(app.group_order.get(), '파일 먼저')
        self.assertEqual(app.filtered, [])
        app.save()
        saved = json.loads(module.CONFIG.read_text('utf-8'))
        self.assertEqual(saved['group_order'], '파일 먼저')
        self.assertEqual(saved['sort'], '수정한 날짜 오름차순')
        self.assertEqual(saved['tab_views']['__global_favorites__']['favorites']['group_order'], '파일 먼저')
        app.close()
        for pool in (app.pool, app.folder_pool, app.thumbnail_edit_pool):
            pool.shutdown(wait=True, cancel_futures=True)
        self.app = app = self.make_app()
        self.wait_for(lambda: bool(app.files))
        self.settle()
        self.assertEqual(app.group_order.get(), '파일 먼저')
        self.assertEqual(app.sort_order.get(), '수정한 날짜 오름차순')
        self.assertEqual(app.query.get(), 'No matching group fixture')
        self.assertEqual(app.filtered, [])
        self.tab(0)
        self.assertEqual(app.group_order.get(), '폴더 먼저')
        self.assertEqual(app.sort_order.get(), '이름 내림차순')
        self.assert_arrangement('폴더 먼저')

    def test_folder_favorites_are_global_and_key_removal_keeps_cards_and_next_selection(self):
        app = self.app
        self.set_filter('폴더')
        path = self.folders[0]
        frame = self.card(path)
        top = app.canvas.canvasy(0)
        generation = app.generation
        app.toggle_favorite(path)
        self.assertTrue(frame.favorite)
        self.assertIs(self.card(path), frame)
        self.assertEqual(app.canvas.canvasy(0), top)
        self.assertEqual(app.generation, generation)
        for folder in self.folders[1:]:
            app.toggle_favorite(folder)
        archive = self.other / 'Elsewhere.zip'
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.writestr('1.png', self.image_bytes)
        self.navigate(self.other)
        self.assertEqual(app.files, [archive])
        self.tab(1)
        self.set_filter('폴더')
        self.assertEqual(set(app.filtered), set(self.folders))
        app.scroll_view('moveto', 0.3)
        app.refresh_visible()
        self.settle()
        index = min(len(app.filtered) - 2,
                    int(app.canvas.canvasy(0) // app.row_height()) * app.columns() + app.columns())
        selected, following = app.filtered[index:index + 2]
        app.select_card(selected)
        self.assertFalse(self.card(selected).favorite, 'Favorites tab must not draw a star')
        before = {path: frame for path, frame, _, _ in app.cards.values()}
        top = app.canvas.canvasy(0)
        generation = app.generation
        app.settings['shortcuts']['favorite'] = ['F6']
        app.refresh_shortcuts()
        app.canvas.focus_force()
        app.update()
        app.canvas.event_generate('<F6>')
        app.update()
        self.assertNotIn(str(selected), app.favorites)
        self.assertNotIn(selected, app.filtered)
        self.assertEqual(app.selected_path, following)
        self.assertEqual(app.canvas.canvasy(0), top)
        self.assertEqual(app.generation, generation)
        after = {path: frame for path, frame, _, _ in app.cards.values()}
        self.assertTrue(before.keys() & after.keys())
        for survivor in before.keys() & after.keys():
            self.assertIs(after[survivor], before[survivor])

    def test_filter_and_scroll_are_restored_per_tab_and_folder_kind_survives_restart(self):
        app = self.app
        for folder in self.folders:
            app.toggle_favorite(folder)
        self.set_filter('압축파일')
        app.scroll_view('moveto', 3 * app.row_height() / app.scroll_height())
        app.refresh_visible()
        app.remember_position()
        all_view = app.views[app.current_folder].copy()
        self.tab(1)
        self.set_filter('폴더')
        app.scroll_view('moveto', 2 * app.row_height() / app.scroll_height())
        app.refresh_visible()
        app.remember_position()
        favorite_view = app.tab_views['__global_favorites__']['favorites'].copy()
        self.tab(0)
        self.assertEqual(app.kind_filter.get(), '압축파일')
        self.assertEqual(app.filtered[int(app.canvas.canvasy(0) // app.row_height()) * app.columns()],
                         Path(all_view['anchor']))
        self.tab(1)
        self.assertEqual(app.kind_filter.get(), '폴더')
        self.assertEqual(app.filtered[int(app.canvas.canvasy(0) // app.row_height()) * app.columns()],
                         Path(favorite_view['anchor']))
        app.save()
        saved = json.loads(module.CONFIG.read_text('utf-8'))
        self.assertEqual(set(saved['folder_item_favorites']), set(map(str, self.folders)))
        app.close()
        for pool in (app.pool, app.folder_pool, app.thumbnail_edit_pool):
            pool.shutdown(wait=True, cancel_futures=True)
        self.app = self.make_app()
        self.wait_for(lambda: bool(self.app.files))
        self.settle()
        self.assertTrue(all(self.app.item_kinds.get(folder) == 'folder' for folder in self.folders))
        self.assertEqual(self.app.kind_filter.get(), '폴더')
        self.assertEqual(set(self.app.filtered), set(self.folders))

    def test_folder_viewer_uses_saved_representative_page_and_missing_folder_falls_back(self):
        app = self.app
        folder = self.folders[0]
        with patch.object(app, 'thumbnail_recipes', return_value={'0': {'entry': '2.png', 'box': [0, 0, 1, 1]}}):
            with patch.object(app, 'execute_action') as execute:
                app.open_folder_image(folder, module.CUSTOM_VIEWER_ACTION)
                self.wait_for(lambda: execute.called)
                execute.assert_called_once_with(folder / '2.png', module.CUSTOM_VIEWER_ACTION)
        with patch.object(app, 'execute_action') as execute:
            app.open_folder_image(folder, module.DEFAULT_APP_ACTION)
            self.wait_for(lambda: execute.called)
            execute.assert_called_once_with(folder / '1.png', module.DEFAULT_APP_ACTION)
        empty = self.root / 'No images'
        empty.mkdir()
        with patch.object(app, 'reveal') as reveal, patch.object(app, 'execute_action') as execute:
            app.open_folder_image(empty, module.CUSTOM_VIEWER_ACTION)
            self.wait_for(lambda: reveal.called)
            reveal.assert_called_once_with(empty)
            execute.assert_not_called()

    def test_empty_filter_state_and_favorites_before_folder_selection_are_remembered(self):
        app = self.app
        app.toggle_favorite(self.folders[0])
        self.set_filter('폴더')
        app.query.set('No matching folder fixture')
        app.apply_search()
        self.assertEqual(app.filtered, [])
        self.tab(1)
        app.query.set('')
        self.set_filter('압축파일')
        self.assertEqual(app.filtered, [])
        self.tab(0)
        self.assertEqual(app.kind_filter.get(), '폴더')
        self.assertEqual(app.query.get(), 'No matching folder fixture')
        self.assertEqual(app.filtered, [])
        app.close()
        for pool in (app.pool, app.folder_pool, app.thumbnail_edit_pool):
            pool.shutdown(wait=True, cancel_futures=True)
        module.CONFIG.write_text(json.dumps(dict(
            folder='', only_favorites=True, kind_filter='폴더',
            file_favorites=list(map(str, self.folders)),
            folder_item_favorites=list(map(str, self.folders)))), 'utf-8')
        self.app = app = self.make_app()
        self.wait_for(lambda: len(app.filtered) == len(self.folders))
        self.settle()
        self.assertEqual(app.current_folder, '')
        app.scroll_view('moveto', 2 * app.row_height() / app.scroll_height())
        app.refresh_visible()
        app.remember_position()
        view = app.tab_views['__global_favorites__']['favorites'].copy()
        self.assertIsNotNone(view['anchor'])
        self.assertGreater(view['fraction'], 0)
        self.assertEqual(view['kind_filter'], '폴더')
        self.tab(0)
        self.assertEqual(app.filtered, [])
        self.tab(1)
        self.assertEqual(app.kind_filter.get(), '폴더')
        self.assertEqual(app.filtered[int(app.canvas.canvasy(0) // app.row_height()) * app.columns()],
                         Path(view['anchor']))

    def test_folder_rename_and_delete_are_disabled_for_keys_and_context_menu(self):
        app = self.app
        folder = self.folders[0]
        app.select_card(folder)
        originals = {path.name: path.read_bytes() for path in folder.iterdir()}
        for command in ('rename', 'trash'):
            self.assertEqual(app.activate_command(command), 'break')
        self.assertIsNone(getattr(app, 'rename_window', None))
        with patch.object(module.tk.Menu, 'tk_popup'):
            app.context(SimpleNamespace(x_root=0, y_root=0), folder)
        menu = app.context_menu
        for title in ('파일 이름 바꾸기', '파일 삭제'):
            index = next(index for index in range(menu.index('end') + 1)
                         if menu.type(index) == 'command' and menu.entrycget(index, 'label') == title)
            self.assertEqual(menu.entrycget(index, 'state'), 'disabled')
        self.trash.assert_not_called()
        self.rename.assert_not_called()
        self.ask.assert_not_called()
        self.assertEqual({path.name: path.read_bytes() for path in folder.iterdir()}, originals)

    def test_large_mixed_library_remains_virtualized_and_each_filter_is_complete(self):
        app = self.app
        paths = [self.root / (f'Folder-{index:05d}' if index % 2 else f'Archive-{index:05d}.zip')
                 for index in range(7444)]
        app.item_kinds.update({path: 'folder' if index % 2 else 'archive'
                              for index, path in enumerate(paths)})
        app.add_cards((paths, {path: index for index, path in enumerate(paths)},
                       {path: (1024, 1700000000) for path in paths}))
        app.update()
        self.settle()
        self.assertEqual(len(app.filtered), 7444)
        for kind, expected in (('폴더', 3722), ('압축파일', 3722), ('전체', 7444)):
            self.set_filter(kind)
            self.assertEqual(len(app.filtered), expected)
            for fraction in (0, 0.5, 1):
                app.scroll_view('moveto', fraction)
                app.refresh_visible()
                self.settle()
                self.assertLess(len(app.cards), 80)
                self.assertTrue(app.cards)


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        __import__('faulthandler').disable()
        module.FAULT_LOG.close()
        __import__('logging').shutdown()
        _settings.cleanup()
