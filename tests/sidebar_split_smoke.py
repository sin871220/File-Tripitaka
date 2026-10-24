"""Standalone native Tk checks for the sidebar divider and collapsed bodies.

Run explicitly with a desktop Tk interpreter; this module does not launch the
application, load its preferences, or touch the user's folders.
"""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sidebar_split import DEFAULT_SIDEBAR_RATIO, SidebarSplit, normalize_sidebar_ratio


class SidebarSplitSmoke(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('340x780+40+40')
        self.errors, self.changes = [], []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.host = ttk.Frame(self.root)
        self.host.pack(fill='both', expand=True)
        self.split = SidebarSplit(self.host, ratio=.32, on_change=self.changes.append)
        self.split.pack(fill='both', expand=True)
        self.sections = [ttk.Frame(self.split) for _ in range(2)]
        self.headers = [ttk.Button(frame, text=label)
                        for frame, label in zip(self.sections, ('Favorite folders', 'Folder explorer'))]
        self.bodies = [ttk.Frame(frame) for frame in self.sections]
        self.footer = ttk.Frame(self.sections[0])
        ttk.Button(self.footer, text='Add current folder').pack(side='left')
        ttk.Button(self.footer, text='Remove').pack(side='left')
        self.lists = []
        for index, (header, body) in enumerate(zip(self.headers, self.bodies)):
            header.pack(fill='x')
            listing = ttk.Treeview(body, show='tree', selectmode='browse')
            scrollbar = ttk.Scrollbar(body, orient='vertical', command=listing.yview)
            listing.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side='right', fill='y')
            listing.pack(side='left', fill='both', expand=True)
            for row in range(70):
                listing.insert('', 'end', text=f'Synthetic {index} folder {row:02d}')
            self.lists.append(listing)
        self._pack_bodies(False, False)
        self.split.set_sections(*self.sections, *self.headers, favorite_footer=self.footer)
        self.root.update()
        self.addCleanup(self.close)

    def close(self):
        self.root.destroy()
        self.assertFalse(self.errors, self.errors)

    def _pack_bodies(self, favorites, tree):
        for body in self.bodies:
            body.pack_forget()
        self.footer.pack_forget()
        if not favorites:
            self.footer.pack(side='bottom', fill='x')
            self.bodies[0].pack(fill='both', expand=True)
        if not tree:
            self.bodies[1].pack(fill='both', expand=True)

    def collapse(self, favorites, tree):
        # Application packing happens before the controller is informed.
        self._pack_bodies(favorites, tree)
        self.split.set_collapsed(favorites, tree)
        self.root.update()

    def drag(self, destination, *, release=True):
        x = self.split.winfo_width() // 2
        y = self.split.sash_coord(0)[1] + 2
        self.assertTrue(self.split.identify(x, y))
        self.split.event_generate('<ButtonPress-1>', x=x, y=y)
        self.split.event_generate('<B1-Motion>', x=x, y=destination + 2, state=0x100)
        self.root.update()
        if release:
            self.split.event_generate('<ButtonRelease-1>', x=x, y=destination + 2)
            self.root.update()

    def assert_headers_visible(self):
        for header in self.headers:
            self.assertTrue(header.winfo_ismapped())
            self.assertGreater(header.winfo_height(), 1)
            self.assertGreaterEqual(header.winfo_rooty(), self.split.winfo_rooty())
            self.assertLessEqual(header.winfo_rooty() + header.winfo_height(),
                                 self.split.winfo_rooty() + self.split.winfo_height())

    def assert_actual_fraction(self, expected, delta=.015):
        available = self.split.winfo_height() - int(self.split.cget('sashwidth'))
        self.assertAlmostEqual(self.split.sashpos(0) / available, expected, delta=delta)
        self.assertAlmostEqual(self.sections[0].winfo_height(), self.split.sashpos(0), delta=1)

    def test_ratio_normalization_rejects_invalid_saved_values(self):
        for value in (None, '', 'broken', object(), True, float('nan'), float('inf'), -float('inf')):
            self.assertEqual(normalize_sidebar_ratio(value), DEFAULT_SIDEBAR_RATIO)
        self.assertEqual(normalize_sidebar_ratio(-1), .1)
        self.assertEqual(normalize_sidebar_ratio(7), .9)
        self.assertEqual(normalize_sidebar_ratio('0.45'), .45)

    def test_native_drag_saves_once_after_release(self):
        self.assertAlmostEqual(self.split.get_ratio(), .32, delta=.01)
        self.assert_actual_fraction(.32)
        target = int(self.split.winfo_height() * .55)
        self.drag(target, release=False)
        self.assertGreater(self.split.sashpos(0), target - 12)
        self.assertEqual(self.changes, [])
        x = self.split.winfo_width() // 2
        self.split.event_generate('<ButtonRelease-1>', x=x, y=target + 2)
        self.root.update()
        self.assertEqual(len(self.changes), 1)
        self.assertAlmostEqual(self.changes[0], .55, delta=.02)
        self.assertAlmostEqual(self.changes[0], self.split.get_ratio(), delta=.002)
        self.assert_actual_fraction(.55)
        self.assert_headers_visible()

    def test_programmatic_position_and_dynamic_minimums(self):
        self.split.sashpos(0, -100)
        self.root.update()
        minimum_top = self.headers[0].winfo_reqheight() + self.footer.winfo_reqheight() + 40
        self.assertGreaterEqual(self.sections[0].winfo_height(), minimum_top - 2)
        self.assertGreater(self.bodies[0].winfo_height(), 20)
        self.assertEqual(len(self.changes), 1)
        self.split.sashpos(0, 10000)
        self.root.update()
        self.assertGreaterEqual(self.sections[1].winfo_height(), self.headers[1].winfo_reqheight() + 70)
        self.assert_headers_visible()
        with self.assertRaises(tk.TclError):
            self.split.sashpos(1)

    def test_either_collapsed_body_gives_space_to_other_and_restores(self):
        self.split.sashpos(0, 370)
        self.root.update()
        self.assertAlmostEqual(self.split.sashpos(0), 370, delta=1)
        original = self.split.get_ratio()
        callbacks = len(self.changes)
        for flags, tiny, large in (((True, False), 0, 1), ((False, True), 1, 0)):
            self.collapse(*flags)
            self.assertLessEqual(self.sections[tiny].winfo_height(), self.headers[tiny].winfo_reqheight() + 2)
            self.assertGreater(self.sections[large].winfo_height(), self.split.winfo_height() - 80)
            self.assertAlmostEqual(self.split.get_ratio(), original, delta=.002)
            self.assertFalse(self.bodies[tiny].winfo_ismapped())
            self.assert_headers_visible()
            before = self.split.sashpos(0)
            self.drag(self.split.winfo_height() // 2)
            self.assertEqual(self.split.sashpos(0), before)
            self.collapse(False, False)
            self.assertAlmostEqual(self.split.get_ratio(), original, delta=.01)
            self.assert_actual_fraction(original)
        self.assertEqual(len(self.changes), callbacks)

    def test_both_collapsed_keep_headers_at_top_and_block_sash_drag(self):
        original = self.split.get_ratio()
        self.collapse(True, True)
        self.assert_headers_visible()
        self.assertFalse(any(body.winfo_ismapped() for body in self.bodies))
        top = self.headers[0].winfo_rooty()
        self.assertLess(self.headers[1].winfo_rooty() - top,
                        sum(header.winfo_reqheight() for header in self.headers) + 12)
        before = self.split.sashpos(0)
        self.drag(450)
        self.assertEqual(self.split.sashpos(0), before)
        self.split.sashpos(0, 400)
        self.assertEqual(self.split.sashpos(0), before)
        self.collapse(False, False)
        self.assertAlmostEqual(self.split.get_ratio(), original, delta=.01)
        self.assert_actual_fraction(original)
        self.assertEqual(self.changes, [])

    def test_resize_hide_and_theme_preserve_fraction(self):
        self.split.sashpos(0, 350)
        self.root.update()
        original = self.split.get_ratio()
        callbacks = len(self.changes)
        for width, height in ((360, 1000), (320, 560), (340, 780)):
            self.root.geometry(f'{width}x{height}')
            self.root.update()
            self.assertAlmostEqual(self.split.get_ratio(), original, delta=.015)
            self.assert_actual_fraction(original)
            self.assert_headers_visible()
        self.host.pack_forget()
        self.root.update()
        self.root.geometry('380x940')
        self.root.update()
        self.host.pack(fill='both', expand=True)
        self.root.update()
        self.assertAlmostEqual(self.split.get_ratio(), original, delta=.015)
        self.assert_actual_fraction(original)
        for color in ('#d0d0d0', '#333944', '#102536', '#176fc5'):
            self.split.set_theme({'border': color})
            self.root.update()
            self.assertEqual(self.split.cget('background'), color)
            self.assertAlmostEqual(self.split.get_ratio(), original, delta=.015)
            self.assert_actual_fraction(original)
        self.assertEqual(len(self.changes), callbacks)

    def test_small_window_clamp_keeps_preferred_ratio_for_later_resize(self):
        original = self.split.get_ratio()
        self.root.geometry('340x150')
        self.root.update()
        self.assertAlmostEqual(self.split.get_ratio(), original, delta=.002)
        self.assert_headers_visible()
        self.assertGreater(self.sections[0].winfo_height(), self.headers[0].winfo_reqheight())
        self.assertGreater(self.sections[1].winfo_height(), self.headers[1].winfo_reqheight())
        self.root.geometry('340x780')
        self.root.update()
        self.assert_actual_fraction(original)
        self.assertEqual(self.changes, [])

    def test_destroy_cancels_pending_layout_and_drag_callbacks(self):
        self.drag(400, release=False)
        self.split.event_generate('<ButtonRelease-1>', x=100, y=402)
        self.split.set_theme({'border': '#242a33'})
        self.split.destroy()
        self.root.update()
        self.assertFalse(self.split._alive)
        self.assertIsNone(self.split._layout_after)
        self.assertIsNone(self.split._settle_after)
        self.assertIsNone(self.split._sample_after)
        self.assertIsNone(self.split._finish_after)
        self.assertFalse(self.errors)


if __name__ == '__main__':
    unittest.main(verbosity=2)
