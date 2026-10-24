"""Native Tk checks for favorite-folder row dragging, using synthetic rows."""
from pathlib import Path
import sys
import time
import tkinter as tk
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from favorite_folder_list import FavoriteFolderList


class FavoriteFolderListSmoke(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('360x280+40+40')
        self.errors, self.orders, self.opens = [], [], []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.listing = FavoriteFolderList(self.root, on_reorder=self.orders.append,
                                          show='tree', selectmode='browse')
        self.listing.pack(fill='both', expand=True)
        self.listing.bind('<ButtonRelease-1>', self.open_row, add='+')
        self.populate(8)
        self.addCleanup(self.close)

    def close(self):
        self.root.destroy()
        self.assertFalse(self.errors, self.errors)

    def populate(self, count):
        self.listing.cancel_drag()
        self.listing.delete(*self.listing.get_children(''))
        for index in range(count):
            self.listing.insert('', 'end', iid=str(index), text=f'Synthetic folder {index:02d}')
        self.root.update()

    def open_row(self, event):
        row = self.listing.identify_row(event.y)
        if row:
            self.opens.append(row)

    def point(self, item):
        box = self.listing.bbox(item)
        self.assertTrue(box, item)
        return 35, box[1] + box[3] // 2

    def press(self, item):
        x, y = self.point(item)
        self.listing.event_generate('<ButtonPress-1>', x=x, y=y)
        self.root.update()
        return x, y

    def move(self, x, y):
        self.listing.event_generate('<B1-Motion>', x=x, y=y, state=0x100)
        self.root.update()

    def release(self, x, y):
        self.listing.event_generate('<ButtonRelease-1>', x=x, y=y)
        self.root.update()

    def test_ordinary_click_and_small_motion_still_open_once(self):
        original = self.listing.get_children('')
        x, y = self.press('3')
        self.move(x, y + 5)
        self.release(x, y + 5)
        self.assertEqual(self.opens, ['3'])
        self.assertEqual(self.listing.selection(), ('3',))
        self.assertEqual(self.listing.get_children(''), original)
        self.assertEqual(self.orders, [])

    def test_live_reorder_keeps_identity_and_saves_once_after_release(self):
        self.press('6')
        x, y = self.point('1')
        self.move(x, y - 4)
        self.assertEqual(self.orders, [])
        self.assertEqual(self.listing.get_children('')[1], '6')
        self.assertEqual(self.listing.selection(), ('6',))
        self.assertEqual(self.listing.focus(), '6')
        self.release(x, y - 4)
        self.assertEqual(self.opens, [])
        self.assertEqual(self.orders, [list(self.listing.get_children(''))])

    def test_threshold_crossing_without_changed_order_does_not_open(self):
        original = self.listing.get_children('')
        x, y = self.press('3')
        self.move(x + 8, y)
        self.release(x + 8, y)
        self.assertEqual(self.listing.get_children(''), original)
        self.assertEqual(self.orders, [])
        self.assertEqual(self.opens, [])

    def test_escape_restores_order_and_consumes_following_release(self):
        original = self.listing.get_children('')
        self.press('6')
        x, y = self.point('1')
        self.move(x, y - 4)
        self.assertNotEqual(self.listing.get_children(''), original)
        self.listing.focus_force()
        self.listing.event_generate('<Escape>')
        self.root.update()
        self.release(x, y)
        self.assertEqual(self.listing.get_children(''), original)
        self.assertEqual(self.listing.selection(), ('6',))
        self.assertEqual(self.orders, [])
        self.assertEqual(self.opens, [])

    def test_cancel_before_refresh_does_not_use_deleted_item_ids(self):
        self.press('6')
        self.move(35, 2)
        self.assertIsNotNone(self.listing._scroll_after)
        self.populate(4)
        self.assertIsNone(self.listing._scroll_after)
        self.assertIsNone(self.listing._drag_item)
        self.release(*self.point('1'))
        self.assertEqual(self.listing.get_children(''), ('0', '1', '2', '3'))
        self.assertEqual(self.orders, [])
        self.assertEqual(self.opens, [])

    def test_long_list_autoscrolls_and_preserves_dragged_selection(self):
        self.populate(80)
        self.press('2')
        x, y = 35, self.listing.winfo_height() - 3
        self.move(x, y)
        deadline = time.monotonic() + .35
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertGreater(self.listing.yview()[0], 0)
        self.assertGreater(self.listing.index('2'), 5)
        self.assertEqual(self.listing.selection(), ('2',))
        self.release(x, y)
        self.assertEqual(len(self.orders), 1)
        self.assertEqual(self.opens, [])
        self.assertIsNone(self.listing._scroll_after)

    def test_unmap_restores_live_order_and_destroy_cancels_timer(self):
        original = self.listing.get_children('')
        self.press('6')
        self.move(35, 2)
        self.listing.pack_forget()
        self.root.update()
        self.assertEqual(self.listing.get_children(''), original)
        self.assertIsNone(self.listing._scroll_after)
        self.listing.pack(fill='both', expand=True)
        self.root.update()
        self.press('6')
        self.move(35, 2)
        self.listing.destroy()
        self.root.update()
        self.assertIsNone(self.listing._scroll_after)
        self.assertFalse(self.errors)

    def test_outside_edge_from_scrolled_middle_moves_through_visible_rows(self):
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                self.populate(80)
                self.listing.yview_moveto(.4)
                self.root.update()
                item = self.listing.identify_row(self.listing.winfo_height() // 2)
                self.assertTrue(item)
                self.press(item)
                initial_index = self.listing.index(item)
                initial_view = self.listing.yview()[0]
                y = -5 if direction < 0 else self.listing.winfo_height() + 5
                self.move(35, y)
                first_index = self.listing.index(item)
                self.assertGreater(first_index, 0)
                self.assertLess(first_index, 79)
                if direction < 0:
                    self.assertLess(first_index, initial_index)
                else:
                    self.assertGreater(first_index, initial_index)
                self.assertEqual(self.orders, [])
                # Wait for observable progress, rather than assuming two timer
                # callbacks fit into a fixed 180 ms on a shared CI desktop.
                deadline = time.monotonic() + 1.5
                while time.monotonic() < deadline:
                    self.root.update()
                    current_view = self.listing.yview()[0]
                    current_index = self.listing.index(item)
                    if ((current_view - initial_view) * direction > 0
                            and (current_index - first_index) * direction > 0):
                        break
                    time.sleep(.01)
                final_index = self.listing.index(item)
                self.assertLessEqual(abs(final_index - first_index), 4)
                if direction < 0:
                    self.assertLess(self.listing.yview()[0], initial_view)
                    self.assertLess(final_index, first_index)
                else:
                    self.assertGreater(self.listing.yview()[0], initial_view)
                    self.assertGreater(final_index, first_index)
                self.assertEqual(self.listing.selection(), (item,))
                self.listing.cancel_drag(restore=True)
                self.root.update()

    def test_outside_hits_to_offscreen_rows_use_visible_boundary_instead(self):
        original_identify = self.listing.identify_row
        try:
            for direction in (-1, 1):
                with self.subTest(direction=direction):
                    self.listing.identify_row = original_identify
                    self.populate(80)
                    self.listing.yview_moveto(.4)
                    self.root.update()
                    item = original_identify(self.listing.winfo_height() // 2)
                    self.press(item)
                    initial_index = self.listing.index(item)
                    height = self.listing.winfo_height()
                    hidden = '0' if direction < 0 else '79'
                    self.assertFalse(self.listing.bbox(hidden))
                    # Tk 8.6 may report an offscreen item for an outside y.
                    self.listing.identify_row = lambda y: hidden if y < 0 or y >= height else original_identify(y)
                    self.move(35, -5 if direction < 0 else height + 5)
                    moved = self.listing.index(item)
                    self.assertGreater(moved, 0)
                    self.assertLess(moved, 79)
                    if direction < 0:
                        self.assertLess(moved, initial_index)
                    else:
                        self.assertGreater(moved, initial_index)
                    self.assertEqual(self.listing.selection(), (item,))
                    self.assertEqual(self.orders, [])
                    self.listing.cancel_drag(restore=True)
        finally:
            self.listing.identify_row = original_identify


if __name__ == '__main__':
    unittest.main(verbosity=2)
