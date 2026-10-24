"""Folder-tab navigation checks using temporary libraries and settings only."""
import copy
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_settings = tempfile.TemporaryDirectory(prefix='tripitaka-folder-tabs-settings-')
os.environ['LOCALAPPDATA'] = _settings.name
import app as module
from PIL import Image

sys.excepthook = sys.__excepthook__


class FolderTabsSmoke(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory(prefix='tripitaka-folder-tabs-libraries-')
        self.addCleanup(workspace.cleanup)
        self.workspace = Path(workspace.name).resolve()
        self.a = self.workspace / 'Library A'
        self.b = self.workspace / '설정'
        self.c = self.workspace / 'Library C'
        self.archives = {}
        image = io.BytesIO()
        Image.new('RGB', (100, 150), '#598ca8').save(image, 'PNG')
        for library in (self.a, self.b, self.c):
            library.mkdir()
            (library / 'cover.png').write_bytes(image.getvalue())
            paths = []
            for index in range(60):
                path = library / f'Book-{index:03d}.cbz'
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('001.png', image.getvalue())
                    archive.writestr('002.png', image.getvalue())
                paths.append(path)
            self.archives[library] = paths
        module.CONFIG.unlink(missing_ok=True)
        self.apps, self.errors, self.messages, self.info = [], [], [], []
        self.addCleanup(patch.stopall)
        patch.object(module.App, 'populate_tree').start()
        patch.object(module.App, 'thumbnail_recipes', return_value={}).start()
        patch.object(module, 'cover', side_effect=self.cover).start()
        for name in ('launch_default', 'reveal_file', 'trash_archive', 'rename_archive'):
            patch.object(module, name, side_effect=AssertionError('External file actions prohibited')).start()
        patch.object(module.messagebox, 'showerror', side_effect=lambda *a, **k: self.messages.append(a)).start()
        patch.object(module.messagebox, 'showinfo', side_effect=lambda *a, **k: self.info.append(a)).start()
        self.addCleanup(self.close_apps)
        self.app = self.make_app()
        self.app.navigate(self.a)
        self.wait_library(self.a)
        self.app.folder_favorites = [str(self.a), str(self.b), str(self.c)]
        self.app.refresh_favorite_folders()
        self.app.save()

    @staticmethod
    def cover(*_):
        image = Image.new('RGB', (100, 150), '#598ca8')
        image.info['page_count'] = 2
        return image

    def make_app(self):
        app = module.App()
        app.report_callback_exception = lambda *args: self.errors.append(args)
        self.apps.append(app)
        app.update()
        return app

    def close_one(self, app):
        if not app.closing:
            app.close()
        for pool in (app.pool, app.folder_pool, app.thumbnail_edit_pool):
            pool.shutdown(wait=True, cancel_futures=True)

    def close_apps(self):
        for app in self.apps:
            self.close_one(app)
        self.assertFalse(self.errors, self.errors)
        self.assertFalse(self.messages, self.messages)

    def wait(self, predicate, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            self.assertFalse(self.errors, self.errors)
            if predicate():
                return
            time.sleep(.005)
        self.fail('Folder tab operation timed out')

    def settle(self):
        self.wait(lambda: not self.app.pending and self.app.active == 0 and self.app.results.empty())

    def wait_library(self, library):
        expected = {library, *self.archives[library]}
        self.wait(lambda: set(self.app.files) == expected and self.app.current_folder == str(library))
        self.settle()

    def add(self, library):
        key = self.app.add_folder_tab(library)
        self.assertIsInstance(key, str)
        self.wait_library(library)
        self.assertEqual(self.app.active_tab, key)
        return key

    def switch(self, key, library=None):
        self.app.tabs.select(key)
        self.app.switch_tab()
        self.app.update()
        if library is not None:
            self.wait_library(library)
        else:
            self.settle()
        self.assertEqual(self.app.active_tab, key)

    def set_view(self, query, order, kind, grouping, fraction):
        app = self.app
        app.query.set(query)
        app.sort_order.set(order)
        app.kind_filter.set(kind)
        app.group_order.set(grouping)
        app.apply_search()
        app.update()
        app.canvas.yview_moveto(fraction)
        app.refresh_visible()
        self.settle()
        if app.filtered:
            index = min(len(app.filtered) - 1,
                        int(max(0, app.canvas.canvasy(0)) // app.row_height()) * app.columns() + 1)
            app.select_card(app.filtered[index])
        app.remember_position()
        return (app.canvas.canvasy(0), app.selected_path, query, order, kind, grouping)

    def assert_view(self, expected):
        app = self.app
        top, selected, query, order, kind, grouping = expected
        self.assertAlmostEqual(app.canvas.canvasy(0), top, delta=2)
        self.assertEqual(app.selected_path, selected)
        self.assertEqual(app.query.get(), query)
        self.assertEqual(app.sort_order.get(), order)
        self.assertEqual(app.kind_filter.get(), kind)
        self.assertEqual(app.group_order.get(), grouping)

    def test_tabs_keep_independent_roots_filters_selection_and_scroll(self):
        app = self.app
        a_view = self.set_view('Book', '이름 내림차순', '압축파일', '파일 먼저', .37)
        b_key = self.add(self.b)
        b_view = self.set_view('Book-0', '이름 오름차순', '전체', '폴더 먼저', .61)
        c_key = self.add(self.c)
        c_view = self.set_view('', '수정한 날짜 내림차순', '전체', '섞어서', .23)
        self.assertEqual(app.all_folder, str(self.a))
        self.switch('all', self.a)
        self.assert_view(a_view)
        self.switch(b_key, self.b)
        self.assert_view(b_view)
        self.switch(c_key, self.c)
        self.assert_view(c_view)
        before = len(app.folder_tabs)
        self.assertEqual(self.add(self.b), b_key)
        self.assertEqual(len(app.folder_tabs), before)
        self.assert_view(b_view)
        self.assertEqual(app.all_folder, str(self.a))

    def test_plus_menu_uses_favorite_folders_and_duplicate_focuses_existing(self):
        app = self.app
        with patch.object(module.tk.Menu, 'tk_popup'):
            app.tabs.plus_button.invoke()
        menu = app.folder_tab_menu
        commands = {menu.entrycget(index, 'label'): index for index in range(menu.index('end') + 1)
                    if menu.type(index) == 'command' and menu.entrycget(index, 'state') != 'disabled'}
        self.assertEqual(set(commands), {self.a.name, self.b.name, self.c.name})
        menu.invoke(commands[self.b.name])
        self.wait_library(self.b)
        key = app.active_tab
        self.assertEqual(len(app.folder_tabs), 1)
        with patch.object(module.tk.Menu, 'tk_popup'):
            app.show_folder_tab_menu()
        menu = app.folder_tab_menu
        commands = {menu.entrycget(index, 'label'): index for index in range(menu.index('end') + 1)
                    if menu.type(index) == 'command' and menu.entrycget(index, 'state') != 'disabled'}
        self.assertEqual(set(commands), {self.a.name, '✓ ' + self.b.name, self.c.name})
        menu.invoke(commands['✓ ' + self.b.name])
        self.app.update()
        self.settle()
        self.assertEqual(app.active_tab, key)
        self.assertEqual(len(app.folder_tabs), 1)
        app.close_folder_tab(key)
        self.wait_library(self.a)
        with patch.object(module.tk.Menu, 'tk_popup'):
            app.show_folder_tab_menu()
        menu = app.folder_tab_menu
        labels = {menu.entrycget(index, 'label') for index in range(menu.index('end') + 1)
                  if menu.type(index) == 'command' and menu.entrycget(index, 'state') != 'disabled'}
        self.assertEqual(labels, {self.a.name, self.b.name, self.c.name})
        app.folder_favorites = []
        info_count = len(self.info)
        with patch.object(module.tk.Menu, 'tk_popup'):
            app.show_folder_tab_menu()
        if len(self.info) == info_count and getattr(app, 'folder_tab_menu', None) is not None:
            menu = app.folder_tab_menu
            if menu.index('end') is not None:
                self.assertFalse(any(menu.type(index) == 'command' and menu.entrycget(index, 'state') != 'disabled'
                                     for index in range(menu.index('end') + 1)))
        self.assertEqual(len(app.folder_tabs), 0)

    def test_folder_favorites_and_close_do_not_change_all_library(self):
        app = self.app
        key = self.add(self.b)
        path = self.archives[self.b][0]
        external = self.archives[self.c][0]
        app.toggle_favorite(path)
        app.toggle_favorite(external)
        self.assertEqual(set(app.files), {self.b, *self.archives[self.b]})
        self.assertEqual(set(app.filtered), set(app.files))
        card = next(value[1] for value in app.cards.values() if value[0] == path)
        self.assertTrue(card.favorite)
        self.assertEqual(app.canvas.itemcget(card.badge_item, 'state'), 'normal')
        self.switch('favorites')
        self.assertEqual(set(app.filtered), {path, external})
        self.assertTrue(all(not value[1].favorite for value in app.cards.values()))
        self.switch(key, self.b)
        app.close_folder_tab(key)
        self.wait_library(self.a)
        self.assertEqual(app.active_tab, 'all')
        self.assertEqual(app.all_folder, str(self.a))
        self.assertEqual(app.folder_tabs, [])
        self.assertTrue({str(path), str(external)} <= app.favorites)
        self.assertEqual(app.folder_favorites, [str(self.a), str(self.b), str(self.c)])

    def test_tabs_views_and_literal_folder_names_restore_after_restart(self):
        app = self.app
        a_view = self.set_view('Book', '이름 내림차순', '압축파일', '섞어서', .31)
        b_key = self.add(self.b)
        b_view = self.set_view('Book', '이름 오름차순', '압축파일', '파일 먼저', .57)
        c_key = self.add(self.c)
        self.set_view('', '용량 내림차순', '전체', '폴더 먼저', .12)
        self.switch(b_key, self.b)
        app.settings['language'] = 'en'
        app.apply_language()
        self.assertEqual(app.tabs.tab(0, 'text'), 'All')
        self.assertIn(self.b.name, app.tabs.tab(b_key, 'text'))
        app.remember_position()
        app.save()
        saved = json.loads(module.CONFIG.read_text('utf-8'))
        self.assertEqual(len(saved['folder_tabs']), 2)
        self.close_one(app)
        self.app = self.make_app()
        self.wait_library(self.b)
        self.assertEqual(self.app.active_tab, b_key)
        self.assertEqual(self.app.all_folder, str(self.a))
        self.assertEqual({record['id'] for record in self.app.folder_tabs}, {b_key, c_key})
        self.assertIn(self.b.name, self.app.tabs.tab(b_key, 'text'))
        self.assert_view(b_view)
        self.switch('all', self.a)
        self.assert_view(a_view)

    def test_delayed_folder_scan_cannot_replace_the_all_tab(self):
        app = self.app
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        original = module.scan_items

        def scan(path, *args, **kwargs):
            if Path(path) == self.b:
                entered.set()
                if not release.wait(6):
                    raise TimeoutError('Synthetic scan was not released')
            result = original(path, *args, **kwargs)
            if Path(path) == self.b:
                finished.set()
            return result

        with patch.object(module, 'scan_items', side_effect=scan):
            try:
                key = app.add_folder_tab(self.b)
                self.wait(entered.is_set)
                app.query.set('Book-00')
                app.apply_search()  # A changed filter must survive a pending scan.
                self.switch('all', self.a)
                self.assertEqual(app.all_folder, str(self.a))
            finally:
                release.set()
            self.wait(finished.is_set)
            deadline = time.monotonic() + .2
            while time.monotonic() < deadline:
                app.update()
                time.sleep(.005)
            self.settle()
        self.assertEqual(app.active_tab, 'all')
        self.assertEqual(app.current_folder, str(self.a))
        self.assertEqual(set(app.files), {self.a, *self.archives[self.a]})
        self.switch(key, self.b)
        self.assertEqual(app.query.get(), 'Book-00')
        self.assertEqual(set(app.filtered), {path for path in self.archives[self.b]
                                             if 'Book-00' in path.name})

    def test_missing_folder_and_explicit_navigation_preserve_pinned_root_and_all_history(self):
        app = self.app
        key = self.add(self.b)
        def pinned_path():
            return next(record['path'] for record in app.folder_tabs if record['id'] == key)
        self.assertEqual(pinned_path(), str(self.b))

        # Toolbar/sidebar navigation changes All, rather than relabeling a
        # pinned tab or placing its separate root into All's history.
        app.navigate(self.c)
        self.wait_library(self.c)
        self.assertEqual(app.active_tab, 'all')
        self.assertEqual(app.all_folder, str(self.c))
        self.assertEqual(app.history[-1], str(self.a))
        self.assertEqual(pinned_path(), str(self.b))
        app.go_back()
        self.wait_library(self.a)
        self.assertEqual(app.active_tab, 'all')
        self.assertEqual(app.all_folder, str(self.a))

        self.switch(key, self.b)
        self.switch('all', self.a)
        shutil.rmtree(self.b)  # Only this test's temporary library is removed.
        self.switch(key)
        self.assertEqual(app.current_folder, str(self.b))
        self.assertEqual(app.files, [])
        self.assertEqual(app.filtered, [])
        self.assertIsNone(app._loaded_folder)
        self.assertEqual(pinned_path(), str(self.b))

        self.assertFalse(self.messages, self.messages)
        app.scan()  # Refreshing an unavailable folder must remain recoverable.
        app.update()
        self.assertEqual(len(self.messages), 1)
        self.messages.clear()  # The missing-folder notice is intentional.
        self.switch('all', self.a)
        self.assertEqual(app.active_tab, 'all')
        self.assertEqual(app.all_folder, str(self.a))
        self.assertEqual(set(app.files), {self.a, *self.archives[self.a]})

    def test_layout_changes_preserve_pinned_selection_and_do_not_overwrite_all_view(self):
        app = self.app
        self.set_view('Book', '이름 내림차순', '압축파일', '파일 먼저', .31)
        key = self.add(self.b)
        all_view = copy.deepcopy(app.views[str(self.a)])
        all_tab_view = copy.deepcopy(app.tab_views[str(self.a)]['all'])
        _, selected, query, order, kind, grouping = self.set_view(
            'Book-0', '용량 내림차순', '압축파일', '섞어서', .57)

        def assert_current_view():
            self.assertEqual(app.active_tab, key)
            self.assertEqual(app.current_folder, str(self.b))
            self.assertEqual(app.selected_path, selected)
            self.assertEqual(app.query.get(), query)
            self.assertEqual(app.sort_order.get(), order)
            self.assertEqual(app.kind_filter.get(), kind)
            self.assertEqual(app.group_order.get(), grouping)
            self.assertEqual(app.folder_tab_views[key]['selected'], str(selected))
            self.assertEqual(app.views[str(self.a)], all_view)
            self.assertEqual(app.tab_views[str(self.a)]['all'], all_tab_view)

        app.thumb_size.set(min(320, app.thumb_size.get() + 30))
        app.apply_size()
        app.update()
        self.settle()
        assert_current_view()
        app.preview_count.set('2장')
        app.change_preview_count()
        app.update()
        self.settle()
        self.assertEqual(app.settings['preview_count'], 2)
        assert_current_view()

    def test_drag_reorders_folder_tabs_without_reloading_and_persists_order(self):
        app = self.app
        app.geometry('1400x760')  # Keep all three fixture tabs in the viewport.
        app.update()
        b_key = self.add(self.b)
        c_key = self.add(self.c)
        a_key = self.add(self.a)
        self.set_view('Book', '이름 내림차순', '압축파일', '파일 먼저', .43)
        app.tabs.ensure_visible(a_key)
        app.update()
        self.settle()
        selected = app.selected_path
        cards = dict(app.cards)
        photos = dict(app.photos)
        top = app.canvas.canvasy(0)
        generation = app.scan_generation
        view = copy.deepcopy(app.folder_tab_views[a_key])

        canvas = app.tabs.folder_canvas
        start_box = app.tabs.folder_bounds[a_key]
        target_box = app.tabs.folder_bounds[b_key]
        left = canvas.canvasx(0)
        start_x = round(start_box[0] + 14 - left)
        target_x = round((target_box[0] + target_box[2]) / 2 - left)
        y = round((start_box[1] + start_box[3]) / 2)
        self.assertTrue(0 < start_x < canvas.winfo_width())
        self.assertTrue(0 < target_x < canvas.winfo_width())
        canvas.event_generate('<ButtonPress-1>', x=start_x, y=y)
        app.update()
        canvas.event_generate('<B1-Motion>', x=target_x, y=y, state=0x100)
        app.update()
        canvas.event_generate('<ButtonRelease-1>', x=target_x, y=y)
        app.update()
        self.settle()

        expected = [a_key, b_key, c_key]
        self.assertEqual([record['id'] for record in app.folder_tabs], expected)
        self.assertEqual(app.tabs.tabs(), ('all', 'favorites', *expected))
        self.assertEqual(app.active_tab, a_key)
        self.assertEqual(app.tabs.select(), a_key)
        self.assertEqual(app.current_folder, str(self.a))
        self.assertEqual(app.all_folder, str(self.a))
        self.assertEqual(app.selected_path, selected)
        self.assertEqual(app.cards, cards)
        self.assertEqual(dict(app.photos), photos)
        self.assertEqual(app.canvas.canvasy(0), top)
        self.assertEqual(app.scan_generation, generation)
        self.assertEqual(app.folder_tab_views[a_key], view)
        saved = json.loads(module.CONFIG.read_text('utf-8'))
        self.assertEqual([record['id'] for record in saved['folder_tabs']], expected)
        app.reorder_folder_tabs([a_key, a_key, b_key])
        app.update()
        self.assertEqual([record['id'] for record in app.folder_tabs], expected)
        self.assertEqual(app.cards, cards)

        self.close_one(app)
        self.app = self.make_app()
        self.wait_library(self.a)
        self.assertEqual([record['id'] for record in self.app.folder_tabs], expected)
        self.assertEqual(self.app.tabs.tabs(), ('all', 'favorites', *expected))
        self.assertEqual(self.app.active_tab, a_key)
        self.assertEqual(self.app.selected_path, selected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
