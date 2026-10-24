"""Native Tk checks for the fixed library tabs and scrolling folder strip."""
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import font as tkfont
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from folder_tab_bar import LibraryTabBar
from preferences import PALETTES


class FolderTabBarSmoke(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('920x240+40+40')
        self.errors, self.changes, self.closes, self.adds, self.hovered, self.reorders = [], [], [], [], [], []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.bar = LibraryTabBar(self.root, on_add=lambda: self.adds.append(True),
                                 on_close=self.closes.append, on_hover=self.hovered.append,
                                 on_reorder=self.reorders.append)
        self.bar.pack(fill='x', padx=10, pady=10)
        self.bar.bind('<<NotebookTabChanged>>', lambda _event: self.changes.append(self.bar.select()))
        self.records = [{'id': f'folder:{index}', 'label': f'자료 {index:02d} — 긴 이름의 예시 폴더',
                         'path': f'/synthetic-library/Folder-{index:02d}'} for index in range(20)]
        self.bar.set_folder_tabs(self.records)
        self.root.update()
        self.addCleanup(self.close)

    def close(self):
        self.root.destroy()
        self.assertFalse(self.errors, self.errors)

    def fixed_geometry(self):
        widgets = (self.bar.fixed_canvas, self.bar.plus_button)
        return [(widget.winfo_x(), widget.winfo_y(), widget.winfo_width(), widget.winfo_height())
                for widget in widgets]

    def test_fixed_controls_stay_visible_while_folder_tabs_scroll(self):
        bar = self.bar
        before = self.fixed_geometry()
        self.assertTrue(bar.left_button.instate(['disabled']))
        self.assertFalse(bar.right_button.instate(['disabled']))
        bar.folder_canvas.event_generate('<MouseWheel>', delta=-120)
        self.root.update()
        self.assertGreater(bar.folder_canvas.canvasx(0), 0)
        self.assertEqual(self.fixed_geometry(), before)
        bar.right_button.invoke()
        self.root.update()
        self.assertEqual(self.fixed_geometry(), before)
        bar.plus_button.invoke()
        self.assertEqual(self.adds, [True])
        for width in (620, 1000, 720):
            self.root.geometry(f'{width}x240')
            self.root.update()
            self.assertGreater(bar.folder_canvas.winfo_width(), 0)
            self.assertGreaterEqual(bar.fixed_canvas.winfo_x(), 0)
            self.assertLessEqual(bar.plus_button.winfo_x() + bar.plus_button.winfo_width(), bar.winfo_width())
            self.assertLessEqual(bar.fixed_canvas.winfo_x() + bar.fixed_canvas.winfo_width(), bar.folder_canvas.winfo_x())
        for canvas in (bar.fixed_canvas, bar.folder_canvas):
            self.assertFalse(canvas.winfo_children())
            self.assertTrue(all(canvas.type(item) in ('rectangle', 'text') for item in canvas.find_all()))

    def test_selecting_offscreen_tab_reveals_it_and_boundary_buttons_work(self):
        bar = self.bar
        bar.select('folder:19')
        self.root.update()
        self.assertEqual(bar.select(), 'folder:19')
        self.assertEqual(bar.index(bar.select()), 21)
        start, _, end, _ = bar.folder_bounds['folder:19']
        viewport = bar.folder_canvas.canvasx(0)
        self.assertGreaterEqual(start, viewport - 1)
        self.assertLessEqual(end, viewport + bar.folder_canvas.winfo_width() + 1)
        self.assertTrue(bar.right_button.instate(['disabled']))
        bar.select('folder:0')
        self.root.update()
        self.assertTrue(bar.left_button.instate(['disabled']))
        self.assertIn('folder:19', self.changes)
        self.assertIn('folder:0', self.changes)
        count = len(self.changes)
        bar.select('folder:0')
        self.root.update()
        self.assertEqual(len(self.changes), count)

    def test_notebook_facade_hit_testing_and_literal_labels(self):
        bar = self.bar
        bar.set_base_labels('All', '★ Favorites')
        records = [{'id': 'special', 'label': '설정', 'path': '/synthetic-library/설정'}]
        bar.set_folder_tabs(records)
        self.root.update()
        self.assertEqual(bar.tabs(), ('all', 'favorites', 'special'))
        self.assertEqual(bar.index('end'), 3)
        self.assertEqual(bar.tab(0, 'text'), 'All')
        self.assertEqual(bar.tab(1, 'text'), '★ Favorites')
        self.assertEqual(bar.tab('special', 'text'), '설정')
        spans = {0: [], 1: []}
        y = max(1, (bar.winfo_height() - 1) // 2)
        for x in range(bar.winfo_width()):
            try:
                index = bar.index(f'@{x},{y}')
            except tk.TclError:
                continue
            if index in spans:
                spans[index].append(x)
        before = {key: (min(xs), max(xs)) for key, xs in spans.items()}
        self.assertTrue(all(xs for xs in spans.values()))
        for index in (1, 0, 2):
            bar.select(index)
            self.root.update()
            for key, (left, right) in before.items():
                self.assertEqual(bar.index(f'@{left},{y}'), key)
                self.assertEqual(bar.index(f'@{right},{y}'), key)
        self.assertEqual(bar.select(), 'special')
        with self.assertRaises(tk.TclError):
            bar.index(f'@{bar.plus_button.winfo_x() + 2},{y}')

    def test_folder_click_close_and_wheel_do_not_reach_gallery(self):
        bar = self.bar
        external_wheel = []
        self.root.bind('<MouseWheel>', lambda _event: external_wheel.append(True))
        bar.folder_canvas.event_generate('<MouseWheel>', delta=-120)
        self.root.update()
        self.assertFalse(external_wheel)
        bar.ensure_visible('folder:0')
        self.root.update()
        x1, y1, x2, y2 = bar.folder_bounds['folder:0']
        offset = bar.folder_canvas.canvasx(0)
        bar.folder_canvas.event_generate('<Button-1>', x=int(x1 - offset + 15), y=int((y1 + y2) / 2))
        self.root.update()
        self.assertEqual(bar.select(), 'folder:0')
        bar.folder_canvas.event_generate('<Button-1>', x=int(x2 - offset - 15), y=int((y1 + y2) / 2))
        self.assertEqual(self.closes, ['folder:0'])
        # The controller owns removal, so a close request does not silently
        # change the user's currently loaded view by itself.
        self.assertIn('folder:0', bar.tabs())

    def test_themes_keep_base_tab_geometry_and_destroy_releases_fonts(self):
        bar = self.bar
        for name, palette in PALETTES.items():
            with self.subTest(theme=name):
                bar.set_theme(palette, ('TkDefaultFont', 12))
                self.root.update()
                geometry = self.fixed_geometry()
                bar.select('favorites')
                self.root.update()
                self.assertEqual(self.fixed_geometry(), geometry)
                self.assertEqual(bar.folder_canvas.cget('background'), palette['bg'])
                bar.select('folder:19')
                self.root.update()
                self.assertEqual(self.fixed_geometry(), geometry)
        font_name = str(bar._font)
        self.assertIn(font_name, tkfont.names(root=self.root))
        bar.destroy()
        self.assertNotIn(font_name, tkfont.names(root=self.root))

    def test_arrows_appear_only_for_overflow_and_recheck_after_resize_or_close(self):
        bar = self.bar
        self.assertTrue(bar.left_button.winfo_ismapped())
        self.assertTrue(bar.right_button.winfo_ismapped())
        fixed = self.fixed_geometry()
        short = [{'id': f'short:{index}', 'label': f'F{index}', 'path': f'/synthetic/{index}'}
                 for index in range(3)]
        bar.set_folder_tabs(short)
        self.root.update()
        self.assertFalse(bar.left_button.winfo_ismapped())
        self.assertFalse(bar.right_button.winfo_ismapped())
        self.assertEqual(self.fixed_geometry(), fixed)
        self.root.geometry('500x240')
        self.root.update()
        self.assertTrue(bar.left_button.winfo_ismapped())
        self.assertTrue(bar.right_button.winfo_ismapped())
        bar.select('short:2')
        self.root.update()
        self.assertTrue(bar.right_button.instate(['disabled']))
        self.root.geometry('1100x240')
        self.root.update()
        self.assertFalse(bar.left_button.winfo_ismapped())
        self.assertFalse(bar.right_button.winfo_ismapped())
        self.root.geometry('500x240')
        self.root.update()
        self.assertTrue(bar.right_button.winfo_ismapped())
        bar.set_folder_tabs(short[:1])  # The controller has closed two tabs.
        self.root.update()
        self.assertFalse(bar.left_button.winfo_ismapped())
        self.assertFalse(bar.right_button.winfo_ismapped())
        bar.set_folder_tabs([])
        self.root.update()
        self.assertFalse(bar.left_button.winfo_ismapped())
        self.assertFalse(bar.right_button.winfo_ismapped())

    def _drag(self, identifier, target_identifier):
        bar = self.bar
        canvas = bar.folder_canvas
        box = bar.folder_bounds[identifier]
        target = bar.folder_bounds[target_identifier]
        offset = canvas.canvasx(0)
        source_x = int((box[0] + box[2]) / 2 - offset)
        target_x = int((target[0] + target[2]) / 2 - offset)
        y = int((box[1] + box[3]) / 2)
        canvas.event_generate('<ButtonPress-1>', x=source_x, y=y)
        self.root.update()
        canvas.event_generate('<B1-Motion>', x=target_x, y=y, state=0x100)
        self.root.update()
        canvas.event_generate('<ButtonRelease-1>', x=target_x, y=y)
        self.root.update()

    def test_folder_drag_reorders_only_folder_tabs_and_preserves_selection_and_close(self):
        bar = self.bar
        records = [{'id': f'short:{index}', 'label': f'F{index}', 'path': f'/synthetic/{index}'}
                   for index in range(3)]
        bar.set_folder_tabs(records)
        self.root.update()
        fixed = self.fixed_geometry()
        self._drag('short:0', 'short:2')
        self.assertEqual(bar.tabs(), ('all', 'favorites', 'short:1', 'short:2', 'short:0'))
        self.assertEqual(bar.select(), 'short:0')
        self.assertEqual(self.reorders, [['short:1', 'short:2', 'short:0']])
        self.assertEqual(self.fixed_geometry(), fixed)
        self.assertFalse(self.closes)
        self._drag('short:0', 'short:1')
        self.assertEqual(bar.tabs(), ('all', 'favorites', 'short:0', 'short:1', 'short:2'))
        self.assertEqual(bar.select(), 'short:0')
        self.assertEqual(set(bar.tabs()[2:]), {record['id'] for record in records})
        self.assertEqual(self.fixed_geometry(), fixed)
        # A normal click and sub-threshold motion only select the tab.
        before = len(self.reorders)
        canvas = bar.folder_canvas
        canvas.event_generate('<ButtonPress-1>', x=50, y=bar.winfo_height() // 2)
        canvas.event_generate('<B1-Motion>', x=53, y=bar.winfo_height() // 2, state=0x100)
        canvas.event_generate('<ButtonRelease-1>', x=53, y=bar.winfo_height() // 2)
        self.root.update()
        self.assertEqual(len(self.reorders), before)
        box = bar.folder_bounds['short:0']
        canvas.event_generate('<ButtonPress-1>', x=int(box[2] - 15), y=bar.winfo_height() // 2)
        canvas.event_generate('<ButtonRelease-1>', x=int(box[2] - 15), y=bar.winfo_height() // 2)
        self.root.update()
        self.assertEqual(self.closes, ['short:0'])
        self.assertEqual(len(self.reorders), before)

    def test_drag_edge_scroll_stops_on_release_and_destroy(self):
        bar = self.bar
        canvas = bar.folder_canvas
        fixed = self.fixed_geometry()
        before = canvas.canvasx(0)
        y = max(2, canvas.winfo_height() // 2)
        canvas.event_generate('<ButtonPress-1>', x=100, y=y)
        self.root.update()
        canvas.event_generate('<B1-Motion>', x=canvas.winfo_width() - 2, y=y, state=0x100)
        self.root.update()
        deadline = time.monotonic() + .18
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertGreater(canvas.canvasx(0), before)
        self.assertEqual(self.fixed_geometry(), fixed)
        self.assertIsNotNone(bar._drag_after)
        canvas.event_generate('<ButtonRelease-1>', x=canvas.winfo_width() - 2, y=y)
        self.root.update()
        self.assertIsNone(bar._drag_after)
        offset = canvas.canvasx(0)
        deadline = time.monotonic() + .1
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertEqual(canvas.canvasx(0), offset)
        self.assertTrue(self.reorders)
        selected_box = bar.folder_bounds[bar.select()]
        source_x = int((selected_box[0] + selected_box[2]) / 2 - canvas.canvasx(0))
        canvas.event_generate('<ButtonPress-1>', x=source_x, y=y)
        canvas.event_generate('<B1-Motion>', x=canvas.winfo_width() - 2, y=y, state=0x100)
        self.root.update()
        self.assertIsNotNone(bar._drag_after)
        bar.destroy()
        self.assertIsNone(bar._drag_after)
        self.assertIsNone(bar._overflow_after)


if __name__ == '__main__':
    unittest.main(verbosity=2)
