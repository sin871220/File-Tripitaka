"""Resizable sidebar integration using temporary settings and synthetic rows."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_settings = tempfile.TemporaryDirectory(prefix='tripitaka-sidebar-layout-settings-')
os.environ['LOCALAPPDATA'] = _settings.name
import app as module
from PIL import Image
from preferences import PALETTES

sys.excepthook = sys.__excepthook__


class SidebarLayoutSmoke(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory(prefix='tripitaka-sidebar-layout-')
        self.addCleanup(workspace.cleanup)
        self.library = Path(workspace.name).resolve()
        module.CONFIG.unlink(missing_ok=True)
        self.errors, self.messages, self.apps = [], [], []
        self.addCleanup(patch.stopall)
        patch.object(module.App, 'populate_tree').start()
        patch.object(module.App, 'load_favorite_metadata').start()
        patch.object(module.App, 'thumbnail_recipes', return_value={}).start()
        patch.object(module, 'cover', side_effect=self.cover).start()
        for name in ('launch_default', 'reveal_file', 'trash_archive', 'rename_archive'):
            patch.object(module, name, side_effect=AssertionError('External action prohibited')).start()
        patch.object(module.messagebox, 'showerror', side_effect=lambda *a, **kw: self.messages.append(a)).start()
        self.addCleanup(self.close_apps)
        self.app = self.make_app()
        self.app.current_folder = str(self.library)
        self.app.folder.set(str(self.library))
        self.paths = [self.library / f'Sample-{index:03d}.cbz' for index in range(140)]
        self.app.add_cards((self.paths, {path: index for index, path in enumerate(self.paths)},
                            {path: (1024, 1700000000) for path in self.paths}))
        self.populate_sidebar()
        self.app.update()
        self.app.scroll_view('moveto', .31)
        self.app.refresh_visible()
        self.wait(lambda: not self.app.pending and self.app.active == 0)

    @staticmethod
    def cover(*_):
        image = Image.new('RGB', (100, 150), '#618fa7')
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

    def wait(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            self.assertFalse(self.errors, self.errors)
            if predicate():
                return
            time.sleep(.005)
        self.fail('Sidebar layout did not settle')

    def pump(self, duration=.12):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.app.update()
            time.sleep(.003)
        self.assertFalse(self.errors, self.errors)

    def populate_sidebar(self, count=180):
        app = self.app
        app.folder_favorites = [str(self.library / f'Favorite-{index:03d}') for index in range(count)]
        app.refresh_favorite_folders()
        for node in app.tree.get_children():
            app.tree.delete(node)
        for index in range(180):
            app.tree.insert('', 'end', text=f'Example folder {index:03d}')
        app.update()

    def heights(self):
        return self.app.favorite_list.winfo_height(), self.app.tree.winfo_height()

    def assert_visible_inside(self, widget, container):
        self.assertTrue(widget.winfo_ismapped())
        self.assertGreater(widget.winfo_height(), 0)
        self.assertGreaterEqual(widget.winfo_rooty(), container.winfo_rooty() - 1)
        self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                             container.winfo_rooty() + container.winfo_height() + 1)

    def assert_favorite_scrollbar_visible(self):
        app = self.app
        bar, tree = app.favorite_scrollbar, app.favorite_list
        area = tree.master
        self.assertIs(bar.master, area)
        self.assert_visible_inside(bar, area)
        self.assertGreaterEqual(bar.winfo_width(), bar.winfo_reqwidth())
        self.assertGreaterEqual(bar.winfo_rootx(), area.winfo_rootx())
        self.assertLessEqual(bar.winfo_rootx() + bar.winfo_width(),
                             area.winfo_rootx() + area.winfo_width())
        self.assertGreater(tree.winfo_width(), 0)
        self.assertLessEqual(tree.winfo_rootx() + tree.winfo_width(), bar.winfo_rootx())

    def drag_favorite_scrollbar(self):
        app = self.app
        tree, bar = app.favorite_list, app.favorite_scrollbar
        tree.yview_moveto(0)
        app.update()
        x = bar.winfo_width() // 2
        thumb = [y for y in range(1, bar.winfo_height() - 1) if bar.identify(x, y) == 'thumb']
        self.assertTrue(thumb, 'The visible scrollbar must have a draggable thumb')
        start = (thumb[0] + thumb[-1]) // 2
        target = max(start + 20, int(bar.winfo_height() * .75))
        target = min(target, bar.winfo_height() - 4)
        for sequence, y in (('<ButtonPress-1>', start), ('<B1-Motion>', target),
                            ('<ButtonRelease-1>', target)):
            bar.event_generate(sequence, x=x, y=y,
                               rootx=bar.winfo_rootx() + x, rooty=bar.winfo_rooty() + y,
                               state=0x100 if sequence == '<B1-Motion>' else 0)
            app.update()
        self.pump()
        self.assertGreater(tree.yview()[0], 0, 'Dragging the scrollbar must scroll the folder list')

    def drag_sash(self, fraction):
        split = self.app.sidebar_split
        self.app.update()
        x, y = split.sash_coord(0)
        x = max(8, x + 8)
        y += 2
        target = int(split.winfo_height() * fraction) + 2
        for sequence, point in (('<ButtonPress-1>', y), ('<B1-Motion>', target),
                                 ('<ButtonRelease-1>', target)):
            split.event_generate(sequence, x=x, y=point,
                                 rootx=split.winfo_rootx() + x, rooty=split.winfo_rooty() + point,
                                 state=0x100 if sequence == '<B1-Motion>' else 0)
            self.app.update()
        self.pump()

    def test_native_divider_drag_changes_both_lists_without_rebuilding_gallery_and_persists(self):
        app = self.app
        split = app.sidebar_split
        original = self.heights()
        cards, photos = dict(app.cards), dict(app.photos)
        gallery = app.canvas.canvasy(0)
        self.drag_sash(.62)
        favorite, tree = self.heights()
        self.assertGreater(favorite, original[0] + 20)
        self.assertLess(tree, original[1] - 20)
        self.assertEqual(dict(app.cards), cards)
        self.assertEqual(dict(app.photos), photos)
        self.assertAlmostEqual(app.canvas.canvasy(0), gallery, delta=1)
        ratio = split.get_ratio()
        self.assertAlmostEqual(ratio, .62, delta=.04)
        saved = json.loads(module.CONFIG.read_text('utf-8'))
        self.assertAlmostEqual(saved['sidebar_split_ratio'], ratio, delta=.01)
        for extreme in (-.25, 1.25):
            with self.subTest(drag_extreme=extreme):
                self.drag_sash(extreme)
                for section in app.sidebar_sections.values():
                    self.assert_visible_inside(section['header'], split)
                favorite = app.sidebar_sections['favorites']
                self.assert_visible_inside(app.favorite_folder_buttons, favorite['frame'])
                self.assert_visible_inside(app.favorite_list, favorite['body'])
                self.assert_visible_inside(app.tree, app.sidebar_sections['tree']['body'])
                self.assertEqual(dict(app.cards), cards)
                self.assertAlmostEqual(app.canvas.canvasy(0), gallery, delta=1)
        split.sashpos(0, int((split.winfo_height() - int(split.cget('sashwidth'))) * ratio))
        self.pump()
        self.close_one(app)
        self.app = self.make_app()
        self.pump()
        self.assertAlmostEqual(self.app.sidebar_split.get_ratio(), ratio, delta=.03)

    def test_restart_with_either_or_both_bodies_collapsed_restores_state_and_open_ratio(self):
        for collapsed in (('favorites',), ('tree',), ('favorites', 'tree')):
            with self.subTest(collapsed=collapsed):
                app = self.app
                split = app.sidebar_split
                split.sashpos(0, int(split.winfo_height() * .46))
                self.pump()
                ratio = split.get_ratio()
                for key in collapsed:
                    app.toggle_sidebar_section(key)
                self.pump()
                self.close_one(app)
                saved = json.loads(module.CONFIG.read_text('utf-8'))
                self.assertAlmostEqual(saved['sidebar_split_ratio'], ratio, delta=.02)
                self.app = app = self.make_app()
                self.populate_sidebar()
                self.pump()
                self.assertAlmostEqual(app.sidebar_split.get_ratio(), ratio, delta=.03)
                for key, section in app.sidebar_sections.items():
                    is_collapsed = key in collapsed
                    self.assertEqual(section['collapsed'], is_collapsed)
                    self.assertEqual(saved['sidebar_collapsed'][key], is_collapsed)
                    self.assert_visible_inside(section['header'], app.sidebar_split)
                    self.assertEqual(bool(section['body'].winfo_ismapped()), not is_collapsed)
                for key in collapsed:
                    app.toggle_sidebar_section(key)
                self.pump()
                self.assertAlmostEqual(app.sidebar_split.get_ratio(), ratio, delta=.03)
                self.assertGreater(app.favorite_list.winfo_height(), 10)
                self.assertGreater(app.tree.winfo_height(), 10)
                self.assert_visible_inside(app.favorite_folder_buttons,
                                           app.sidebar_sections['favorites']['frame'])

    def test_collapse_is_symmetric_and_restores_divider_and_whole_panel_state(self):
        app = self.app
        split = app.sidebar_split
        split.sashpos(0, int(split.winfo_height() * .43))
        self.pump()
        ratio, both = split.get_ratio(), self.heights()
        app.toggle_sidebar_section('tree')
        self.pump()
        self.assertGreater(self.heights()[0], both[0] + 40)
        self.assertFalse(app.sidebar_sections['tree']['body'].winfo_ismapped())
        self.assertTrue(app.sidebar_sections['tree']['header'].winfo_ismapped())
        self.assertTrue(app.favorite_folder_buttons.winfo_ismapped())
        self.assertAlmostEqual(split.get_ratio(), ratio, delta=.02)
        app.toggle_sidebar_section('tree')
        self.pump()
        self.assertAlmostEqual(split.get_ratio(), ratio, delta=.03)
        app.toggle_sidebar_section('favorites')
        self.pump()
        self.assertGreater(self.heights()[1], both[1] + 40)
        self.assertFalse(app.sidebar_sections['favorites']['body'].winfo_ismapped())
        self.assertTrue(app.sidebar_sections['favorites']['header'].winfo_ismapped())
        app.toggle_sidebar_section('tree')
        self.pump()
        for section in app.sidebar_sections.values():
            self.assertTrue(section['header'].winfo_ismapped())
            self.assertFalse(section['body'].winfo_ismapped())
        self.drag_sash(.8)
        self.assertAlmostEqual(split.get_ratio(), ratio, delta=.02)
        app.toggle_sidebar_section('favorites')
        app.toggle_sidebar_section('tree')
        self.pump()
        self.assertAlmostEqual(split.get_ratio(), ratio, delta=.03)
        app.toggle_sidebar()
        self.app.update()
        self.assertFalse(app.sidebar_split.winfo_ismapped())
        app.toggle_sidebar()
        self.pump()
        self.assertTrue(app.sidebar_split.winfo_ismapped())
        self.assertAlmostEqual(split.get_ratio(), ratio, delta=.03)

    def test_growing_favorite_pane_reveals_more_rows_and_retains_its_scrollbar(self):
        app = self.app
        split = app.sidebar_split
        split.sashpos(0, int(split.winfo_height() * .32))
        self.pump()
        initial_height = app.favorite_list.winfo_height()
        initial_span = app.favorite_list.yview()[1] - app.favorite_list.yview()[0]
        self.assert_favorite_scrollbar_visible()
        app.toggle_sidebar_section('tree')
        self.pump()
        self.assertGreater(app.favorite_list.winfo_height(), initial_height + 40)
        span = app.favorite_list.yview()[1] - app.favorite_list.yview()[0]
        self.assertGreater(span, initial_span)
        self.assert_favorite_scrollbar_visible()
        before = app.favorite_list.yview()[0]
        app.favorite_list.yview_scroll(3, 'units')
        app.update()
        self.assertGreater(app.favorite_list.yview()[0], before)
        app.folder_favorites = app.folder_favorites[:3]
        app.refresh_favorite_folders()
        self.pump()
        self.assertEqual(app.favorite_list.yview(), (0.0, 1.0),
                         'The expanded favorite pane must fit all three fixture rows')
        self.assertFalse(app.favorite_scrollbar.winfo_ismapped())

    def test_scrollbar_retains_full_width_in_narrow_panes_and_after_visibility_changes(self):
        app = self.app
        folders = list(app.folder_favorites)
        self.assert_favorite_scrollbar_visible()
        for width in (150, 180, 220, 360, 220):
            with self.subTest(sidebar_width=width):
                app.panes.sashpos(0, width)
                # Emulate a stretched column or a larger Windows/DPI request.
                app.favorite_list.column('#0', width=360)
                self.pump()
                self.assert_favorite_scrollbar_visible()
                self.drag_favorite_scrollbar()
                app.toggle_sidebar()
                self.pump()
                self.assertFalse(app.favorite_scrollbar.winfo_ismapped())
                app.toggle_sidebar()
                self.pump()
                self.assert_favorite_scrollbar_visible()
                for key in ('favorites', 'tree'):
                    app.toggle_sidebar_section(key)
                    self.pump()
                    app.toggle_sidebar_section(key)
                    self.pump()
                    self.assert_favorite_scrollbar_visible()
                # A small CI screen may leave only one or two rows in the
                # default split. Expand before testing the fully-fitting case.
                app.toggle_sidebar_section('tree')
                self.pump()
                app.folder_favorites = folders[:3]
                app.refresh_favorite_folders()
                self.pump()
                self.assertEqual(app.favorite_list.yview(), (0.0, 1.0),
                                 'The expanded favorite pane must fit all three fixture rows')
                self.assertFalse(app.favorite_scrollbar.winfo_ismapped())
                app.folder_favorites = list(folders)
                app.refresh_favorite_folders()
                self.pump()
                self.assert_favorite_scrollbar_visible()
                app.toggle_sidebar_section('tree')
                self.pump()
                self.assert_favorite_scrollbar_visible()
        for geometry in ('1000x660', '1200x800', '1120x760'):
            with self.subTest(window_geometry=geometry):
                app.geometry(geometry)
                self.pump()
                self.assert_favorite_scrollbar_visible()

    def test_large_fonts_and_all_themes_keep_expanded_lists_and_footer_inside_sidebar(self):
        app = self.app
        app.commit_preferences('다크', app.settings['double_click'], '', '', app.recursive.get(),
                               typography=dict(family='', size=24))
        app.panes.sashpos(0, 380)
        for language in ('ko', 'en'):
            app.settings['language'] = language
            app.apply_language()
            for theme in PALETTES:
                with self.subTest(language=language, theme=theme):
                    app.settings['theme'] = theme
                    app.apply_theme()
                    app.update()
                    split = app.sidebar_split
                    split.sashpos(0, int(split.winfo_height() * .5))
                    self.pump(.035)
                    for section in app.sidebar_sections.values():
                        self.assertTrue(section['header'].winfo_ismapped())
                        self.assertTrue(section['body'].winfo_ismapped())
                        self.assertGreater(section['body'].winfo_height(), 10)
                    self.assertGreater(app.favorite_list.winfo_height(), 10)
                    self.assertGreater(app.tree.winfo_height(), 10)
                    footer = app.favorite_folder_buttons
                    self.assertTrue(footer.winfo_ismapped())
                    frame = app.sidebar_sections['favorites']['frame']
                    self.assertLessEqual(footer.winfo_rooty() + footer.winfo_height(),
                                         frame.winfo_rooty() + frame.winfo_height() + 1)
                    self.assert_favorite_scrollbar_visible()


if __name__ == '__main__':
    unittest.main(verbosity=2)
