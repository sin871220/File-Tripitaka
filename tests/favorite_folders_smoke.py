"""Favorite-folder removal and native reordering with temporary libraries only."""
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_settings = tempfile.TemporaryDirectory(prefix='tripitaka-favorite-folders-settings-')
os.environ['LOCALAPPDATA'] = _settings.name
import app as module
from PIL import Image

sys.excepthook = sys.__excepthook__


class FavoriteFoldersSmoke(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory(prefix='tripitaka-favorite-folders-libraries-')
        self.addCleanup(workspace.cleanup)
        self.workspace = Path(workspace.name).resolve()
        self.a = self.workspace / 'Library All'
        self.b = self.workspace / '설정'
        self.c = self.workspace / 'Library Keep'
        self.d = self.workspace / 'No tab folder'
        image = io.BytesIO()
        Image.new('RGB', (100, 150), '#598ca8').save(image, 'PNG')
        self.archives = {}
        for folder in (self.a, self.b, self.c, self.d):
            folder.mkdir()
            (folder / 'cover.png').write_bytes(image.getvalue())
            (folder / 'keep.txt').write_text(f'This file belongs to {folder.name}.', encoding='utf-8')
            paths = []
            for index in range(48):
                path = folder / f'Book-{index:03d}.cbz'
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('001.png', image.getvalue())
                    archive.writestr('002.png', image.getvalue())
                paths.append(path)
            self.archives[folder] = paths
        self.disk_before = self.disk_snapshot()
        module.CONFIG.unlink(missing_ok=True)
        self.apps, self.errors, self.messages = [], [], []
        self.addCleanup(patch.stopall)
        patch.object(module.App, 'populate_tree').start()
        patch.object(module.App, 'thumbnail_recipes', return_value={}).start()
        patch.object(module, 'cover', side_effect=self.cover).start()
        for name in ('launch_default', 'reveal_file', 'trash_archive', 'rename_archive'):
            patch.object(module, name, side_effect=AssertionError('External file actions prohibited')).start()
        for name in ('showerror', 'showwarning', 'showinfo'):
            patch.object(module.messagebox, name,
                         side_effect=lambda *args, **kwargs: self.messages.append(args)).start()
        self.confirm = patch.object(module.messagebox, 'askyesno', return_value=False).start()
        self.addCleanup(self.close_apps)
        self.app = self.make_app()
        self.app.navigate(self.a)
        self.wait_library(self.a)
        self.app.folder_favorites = [str(folder) for folder in (self.a, self.b, self.c, self.d)]
        self.app.refresh_favorite_folders()
        self.file_favorites = {str(self.archives[self.b][0]), str(self.archives[self.c][0])}
        self.app.favorites = set(self.file_favorites)
        self.app.save()

    @staticmethod
    def cover(*_):
        image = Image.new('RGB', (100, 150), '#598ca8')
        image.info['page_count'] = 2
        return image

    def disk_snapshot(self):
        return ({str(path.relative_to(self.workspace)): path.read_bytes()
                 for path in self.workspace.rglob('*') if path.is_file()},
                {str(path.relative_to(self.workspace))
                 for path in self.workspace.rglob('*') if path.is_dir()})

    def assert_disk_unchanged(self):
        self.assertEqual(self.disk_snapshot(), self.disk_before)

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
        self.fail('Favorite-folder operation timed out')

    def settle(self):
        self.wait(lambda: not self.app.pending and self.app.active == 0 and self.app.results.empty())

    def pump(self, duration=.12):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.app.update()
            time.sleep(.003)
        self.assertFalse(self.errors, self.errors)

    def wait_library(self, folder):
        expected = {folder, *self.archives[folder]}
        self.wait(lambda: self.app.current_folder == str(folder) and set(self.app.files) == expected)
        self.settle()

    def add(self, folder):
        key = self.app.add_folder_tab(folder)
        self.wait_library(folder)
        self.assertEqual(self.app.active_tab, key)
        return key

    def select_favorite(self, folder):
        node = str(self.app.folder_favorites.index(str(folder)))
        self.app.favorite_list.selection_set(node)
        self.app.favorite_list.focus(node)
        return node

    def gallery_state(self):
        app = self.app
        return dict(cards=dict(app.cards), photos=dict(app.photos), filtered=tuple(app.filtered),
                    selected=app.selected_path, top=app.canvas.canvasy(0),
                    active=app.active_tab, tab=app.tabs.select(), root=app.current_folder,
                    all_root=app.all_folder, generation=app.scan_generation,
                    history=copy.deepcopy(app.history), query=app.query.get(),
                    sort=app.sort_order.get(), kind=app.kind_filter.get(),
                    grouping=app.group_order.get())

    def menu_order(self):
        with patch.object(module.tk.Menu, 'tk_popup'):
            self.app.show_folder_tab_menu()
        menu = self.app.folder_tab_menu
        return [menu.entrycget(index, 'label').removeprefix('✓ ')
                for index in range(menu.index('end') + 1)
                if menu.type(index) == 'command' and menu.entrycget(index, 'state') != 'disabled']

    def mouse_event(self, tree, sequence, x, y):
        tree.event_generate(sequence, x=x, y=y,
                            rootx=tree.winfo_rootx() + x, rooty=tree.winfo_rooty() + y,
                            state=0x100 if sequence == '<B1-Motion>' else 0)
        self.app.update()

    def test_cancel_preserves_favorite_tab_gallery_disk_and_literal_name_in_both_languages(self):
        app = self.app
        self.add(self.c)
        b_key = self.add(self.b)
        for language in ('ko', 'en'):
            with self.subTest(language=language):
                app.settings['language'] = language
                app.apply_language()
                self.pump()
                self.select_favorite(self.b)
                app.save()
                before = (list(app.folder_favorites), copy.deepcopy(app.folder_tabs),
                          copy.deepcopy(app.folder_tab_views), self.gallery_state(),
                          module.CONFIG.read_bytes())
                self.confirm.reset_mock()
                app.remove_favorite_folder()
                self.settle()
                self.confirm.assert_called_once()
                args, kwargs = self.confirm.call_args
                title = args[0] if args else kwargs['title']
                message = args[1] if len(args) > 1 else kwargs['message']
                self.assertEqual(title, module.tr('즐겨찾는 폴더 제거'))
                self.assertIn(self.b.name, message)
                if language == 'ko':
                    self.assertIn('(탭도 같이 삭제됩니다)', message)
                    self.assertIn('실제 폴더와 파일은 삭제되지 않습니다.', message)
                else:
                    self.assertIn('The actual folder and files will not be deleted.', message)
                self.assertEqual(kwargs['icon'], 'warning')
                self.assertEqual(kwargs['default'], 'no')
                self.assertIs(kwargs['parent'], app)
                self.assertEqual((app.folder_favorites, app.folder_tabs, app.folder_tab_views,
                                  self.gallery_state(), module.CONFIG.read_bytes()), before)
                self.assertEqual(app.active_tab, b_key)
                self.assertEqual(app.favorites, self.file_favorites)
                self.assert_disk_unchanged()

    def test_confirm_removes_active_matching_tab_returns_all_and_preserves_disk(self):
        app = self.app
        c_key = self.add(self.c)
        b_key = self.add(self.b)
        self.select_favorite(self.b)
        self.confirm.return_value = True
        app.remove_favorite_folder()
        self.wait_library(self.a)
        self.confirm.assert_called_once()
        self.assertEqual(app.folder_favorites, [str(folder) for folder in (self.a, self.c, self.d)])
        self.assertEqual([tab['id'] for tab in app.folder_tabs], [c_key])
        self.assertNotIn(b_key, app.folder_tab_views)
        self.assertEqual(app.tabs.tabs(), ('all', 'favorites', c_key))
        self.assertEqual(app.active_tab, 'all')
        self.assertEqual(app.all_folder, str(self.a))
        self.assertEqual(app.favorites, self.file_favorites)
        saved = json.loads(module.CONFIG.read_text('utf-8'))
        self.assertEqual(saved['folder_favorites'], app.folder_favorites)
        self.assertEqual(saved['folder_tabs'], app.folder_tabs)
        self.assertEqual(saved['active_library_tab'], 'all')
        self.assert_disk_unchanged()

    def test_confirm_removes_inactive_or_unopened_favorite_without_changing_current_gallery(self):
        app = self.app
        b_key = self.add(self.b)
        c_key = self.add(self.c)
        self.confirm.return_value = True
        for folder in (self.b, self.d):
            with self.subTest(folder=folder.name):
                self.select_favorite(folder)
                before = self.gallery_state()
                app.remove_favorite_folder()
                self.settle()
                self.assertNotIn(str(folder), app.folder_favorites)
                self.assertEqual([tab['id'] for tab in app.folder_tabs], [c_key])
                self.assertNotIn(b_key, app.folder_tab_views)
                self.assertEqual(self.gallery_state(), before)
                self.assertEqual(app.favorites, self.file_favorites)
                self.assert_disk_unchanged()
        self.assertEqual(self.confirm.call_count, 2)
        self.assertEqual(app.folder_favorites, [str(self.a), str(self.c)])

    def test_native_drag_reorders_and_persists_without_navigation_or_gallery_changes(self):
        app = self.app
        c_key = self.add(self.c)
        app.canvas.yview_moveto(.36)
        app.refresh_visible()
        self.settle()
        app.select_card(next(iter(app.cards.values()))[0])
        app.remember_position()
        app.sidebar_split.sashpos(0, int(app.sidebar_split.winfo_height() * .5))
        self.pump()
        tree = app.favorite_list
        source = self.select_favorite(self.d)
        tree.see(source)
        app.update()
        start = tree.bbox(source)
        target = tree.bbox('0')
        self.assertTrue(start and target)
        x = max(35, start[0] + 20)
        start_y = start[1] + start[3] // 2
        target_y = target[1] + 2
        before = self.gallery_state()
        with patch.object(app, 'navigate', wraps=app.navigate) as navigate:
            self.mouse_event(tree, '<ButtonPress-1>', x, start_y)
            self.mouse_event(tree, '<B1-Motion>', x, target_y)
            self.mouse_event(tree, '<ButtonRelease-1>', x, target_y)
            self.settle()
            navigate.assert_not_called()
        expected = [str(folder) for folder in (self.d, self.a, self.b, self.c)]
        self.assertEqual(app.folder_favorites, expected)
        self.assertEqual(self.gallery_state(), before)
        self.assertEqual(tree.item(tree.selection()[0], 'values'), (str(self.d),))
        self.assertEqual(self.menu_order(), [Path(folder).name for folder in expected])
        saved = json.loads(module.CONFIG.read_text('utf-8'))
        self.assertEqual(saved['folder_favorites'], expected)
        self.assertEqual(saved['active_library_tab'], c_key)
        app.reorder_favorite_folders(['0', '0', '2', '3'])
        app.reorder_favorite_folders(['0', '1', '2', '99'])
        self.assertEqual(app.folder_favorites, expected)
        self.assertEqual(self.gallery_state(), before)
        self.close_one(app)
        self.app = self.make_app()
        self.wait_library(self.c)
        self.assertEqual(self.app.folder_favorites, expected)
        self.assertEqual(self.app.active_tab, c_key)
        self.assertEqual(self.menu_order(), [Path(folder).name for folder in expected])
        self.assertEqual(self.app.favorites, self.file_favorites)
        self.assert_disk_unchanged()

    def test_simple_click_still_navigates_once(self):
        app = self.app
        tree = app.favorite_list
        app.update()
        box = tree.bbox('1')
        self.assertTrue(box)
        x, y = max(35, box[0] + 20), box[1] + box[3] // 2
        with patch.object(app, 'navigate', wraps=app.navigate) as navigate:
            self.mouse_event(tree, '<ButtonPress-1>', x, y)
            self.mouse_event(tree, '<ButtonRelease-1>', x, y)
            self.wait_library(self.b)
            navigate.assert_called_once_with(str(self.b))
        self.assertEqual(app.active_tab, 'all')
        self.assertEqual(app.folder_favorites, [str(folder) for folder in (self.a, self.b, self.c, self.d)])
        self.confirm.assert_not_called()
        self.assert_disk_unchanged()


if __name__ == '__main__':
    unittest.main(verbosity=2)
