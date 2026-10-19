"""Native Tk gallery scrolling checks with an isolated synthetic library.

Run ``python tests/scroll_smoke.py`` on a desktop with Tk available. No user
library, saved preferences, or external viewer is read or changed.
"""
from contextlib import ExitStack
from itertools import count
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_settings = tempfile.TemporaryDirectory(prefix='file-tripitaka-scroll-settings-')
os.environ['LOCALAPPDATA'] = _settings.name
import app as module
from PIL import Image

sys.excepthook = sys.__excepthook__


class ScrollSmoke(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix='file-tripitaka-scroll-')
        self.addCleanup(self.workspace.cleanup)
        self.folder = Path(self.workspace.name).resolve()
        module.CONFIG.unlink(missing_ok=True)
        self.errors = []
        self.messages = []
        self.addCleanup(patch.stopall)
        patch.object(module.App, 'save').start()
        patch.object(module.App, 'populate_tree').start()
        patch.object(module.App, 'load_favorite_metadata').start()
        patch.object(module.App, 'thumbnail_recipes', return_value={}).start()
        patch.object(module, 'cover', side_effect=lambda *args: Image.new('RGB', (160, 180), '#3060a0')).start()
        patch.object(module.messagebox, 'showerror',
                     side_effect=lambda *args, **kwargs: self.messages.append(args)).start()
        self.app = module.App()
        self.app.report_callback_exception = lambda *args: self.errors.append(args)
        self.addCleanup(self.close_app)
        self.app.update()
        self.app.current_folder = str(self.folder)
        self.app.folder.set(str(self.folder))
        self.paths = [self.folder / f'Archive-{index:05d}.zip' for index in range(7444)]
        self.app.add_cards((self.paths, {path: index for index, path in enumerate(self.paths)},
                            {path: (1024, 1700000000) for path in self.paths}))
        self.app.update()
        self.app.scroll_view('moveto', 0.3)
        self.app.refresh_visible()
        self.wait_for(lambda: not self.app.pending and self.app.active == 0,
                      'Synthetic covers did not finish loading')

    def close_app(self):
        self.app.close()
        for pool in (self.app.pool, self.app.folder_pool, self.app.thumbnail_edit_pool):
            pool.shutdown(wait=True, cancel_futures=True)
        self.assertFalse(self.errors, self.errors)
        self.assertFalse(self.messages, self.messages)

    def pump(self, duration):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.002)

    def wait_for(self, predicate, message, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            if predicate():
                self.assertFalse(self.errors, self.errors)
                return
            time.sleep(0.002)
        self.fail(message)

    def wheel(self, delta=-120, platform='win32'):
        event = SimpleNamespace(widget=self.app.canvas, delta=delta, num=None)
        # Patch only synchronous dispatch; native Tk continues using its real OS.
        with patch.object(module.sys, 'platform', platform):
            self.app.wheel(event)

    def finish_motion(self):
        self.wait_for(lambda: not self.app.smooth_scroll.active,
                      'Wheel animation did not finish')
        self.pump(0.03)

    def assert_stays(self, position):
        self.pump(0.2)
        self.assertAlmostEqual(self.app.canvas.canvasy(0), position, delta=1)
        self.assertFalse(self.app.smooth_scroll.active)

    def test_windows_wheel_has_intermediate_frames_and_exact_distance(self):
        app = self.app
        self.assertEqual(float(app.canvas.cget('yscrollincrement')), 1)
        start = app.canvas.canvasy(0)
        positions = []
        ticks = count(0, .016)

        def move(top):
            app.move_scroll_pixel(top)
            positions.append(app.canvas.canvasy(0))

        # Keep real Tk timers, wheel dispatch and rounded canvas positions.
        # A busy CI desktop can drain several frames inside one update(), or
        # delay the first timer until a time-based animation catches up. Give
        # this frame-by-frame assertion a controlled elapsed clock and record
        # each actual move instead of depending on when update() returns.
        motion = module.SmoothScroller(
            position=lambda: app.canvas.canvasy(0), limit=app.scroll_limit,
            move=move, schedule=app.after, cancel=app.after_cancel,
            clock=lambda: next(ticks))
        with patch.object(app, 'smooth_scroll', motion):
            self.wheel()
            self.assertTrue(motion.active)
            self.assertEqual(app.canvas.canvasy(0), start, 'Wheel moved before its first animation frame')
            self.finish_motion()
        self.assertTrue(any(start < position < start + 90 for position in positions), positions)
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(all(start <= position <= start + 90 for position in positions))
        self.assertAlmostEqual(app.canvas.canvasy(0) - start, 90, delta=1)

    def test_rapid_wheel_input_accumulates_and_reverses(self):
        app = self.app
        start = app.canvas.canvasy(0)
        for _ in range(3):
            self.wheel(-120)
        self.finish_motion()
        self.assertAlmostEqual(app.canvas.canvasy(0) - start, 270, delta=1)
        start = app.canvas.canvasy(0)
        self.wheel(-120)
        self.wait_for(lambda: app.canvas.canvasy(0) > start,
                      'Initial wheel direction did not begin moving')
        reverse_at = app.canvas.canvasy(0)
        self.wheel(120)
        self.finish_motion()
        self.assertAlmostEqual(app.canvas.canvasy(0), reverse_at - 90, delta=1)

    def test_scrollbar_and_keyboard_cancel_pending_wheel_motion(self):
        app = self.app
        self.wheel()
        app.scroll_view('moveto', 0.6)
        self.assertFalse(app.smooth_scroll.active)
        self.assert_stays(app.canvas.canvasy(0))
        top = app.canvas.canvasy(0)
        index = math.ceil(top / app.row_height()) * app.columns()
        app.selected_path = app.filtered[index]
        self.wheel()
        app.move_selection(SimpleNamespace(keysym='Right'))
        self.assertEqual(app.selected_path, app.filtered[index + 1])
        self.assert_stays(app.canvas.canvasy(0))

    def test_filter_tab_and_position_restore_cancel_pending_motion(self):
        app = self.app
        self.wheel()
        app.query.set('Archive-00')
        if app.search_job is not None:
            app.after_cancel(app.search_job)
            app.search_job = None
        app.apply_search()
        self.assert_stays(app.canvas.canvasy(0))
        app.favorites = {str(path) for path in self.paths[:150]}
        self.wheel()
        app.tabs.select(1)
        app.switch_tab()
        self.assertEqual(app.active_tab, 'favorites')
        self.assert_stays(app.canvas.canvasy(0))
        self.wheel()
        app.restore_position({'fraction': 0.4})
        self.assert_stays(app.canvas.canvasy(0))

    def test_refresh_reuses_existing_card_geometry(self):
        app = self.app
        before = {index: card[1] for index, card in app.cards.items()}
        with ExitStack() as stack:
            coords = stack.enter_context(patch.object(app.canvas, 'coords', wraps=app.canvas.coords))
            itemconfigure = stack.enter_context(patch.object(app.canvas, 'itemconfigure',
                                                              wraps=app.canvas.itemconfigure))
            layouts = [stack.enter_context(patch.object(card, 'layout', wraps=card.layout))
                       for card in before.values()]
            app.refresh_visible()
            self.assertEqual(coords.call_count, 0)
            self.assertEqual(itemconfigure.call_count, 0)
            # Repeating the virtual layout is harmless only when it produces no
            # canvas writes: Windows repaint stripes came from native child
            # windows, so cards must remain the same canvas-only objects.
            self.assertTrue(all(mock.call_count <= 1 for mock in layouts))
        self.assertEqual({index: card[1] for index, card in app.cards.items()}, before)

    def assert_canvas_only_cards(self):
        app = self.app
        self.assertEqual(app.canvas.winfo_children(), [])
        items = set(app.canvas.find_all())
        self.assertTrue(items)
        self.assertNotIn('window', {app.canvas.type(item) for item in items})
        owned = set()
        for path, card, thumbnail, background in app.cards.values():
            self.assertTrue(card.alive)
            self.assertTrue(thumbnail.exists())
            self.assertEqual(thumbnail.archive_path, path)
            self.assertEqual(card.background, background)
            card_items = set(app.canvas.find_withtag(card.tag))
            self.assertTrue(card_items)
            self.assertTrue(owned.isdisjoint(card_items), 'Two cards share a canvas item')
            owned.update(card_items)
            x, y, width, height = card.geometry
            self.assertEqual(tuple(app.canvas.coords(background)),
                             (x, y, x + width - 1, y + height - 1))
            for item in card_items:
                bounds = app.canvas.bbox(item)
                if bounds is None:  # Deliberately hidden text/badge.
                    continue
                self.assertGreaterEqual(bounds[0], x - 2)
                self.assertGreaterEqual(bounds[1], y - 2)
                self.assertLessEqual(bounds[2], x + width + 2)
                self.assertLessEqual(bounds[3], y + height + 2)
        self.assertEqual(items, owned, 'Orphaned or duplicated canvas drawings remain')
        self.assertLess(len(app.cards), 80)
        self.assertTrue(set(app.photos).issubset({card[2] for card in app.cards.values()}))

    def test_thousands_of_scroll_updates_keep_one_canvas_surface(self):
        app = self.app
        self.assert_canvas_only_cards()
        base = app.row_height() * 100
        height = app.scroll_height()
        # Thousands of sub-row updates exercise the Windows failure mode while
        # remaining independent of a display capture or a real user library.
        # Only ten rows enter/leave the virtual viewport during each sweep.
        for step in range(2048):
            offset = (step % 512) * 7
            if (step // 512) % 2:
                offset = 511 * 7 - offset
            app.canvas.yview_moveto((base + offset) / height)
            app.refresh_visible()
            if step % 64 == 0:
                app.update_idletasks()
                self.assert_canvas_only_cards()
        app.update()
        self.assert_canvas_only_cards()
        # A full jump must discard old drawings rather than leaving horizontal
        # image strips at any prior canvas coordinates.
        old_cards = set(card[1] for card in app.cards.values())
        app.scroll_view('moveto', 1)
        app.refresh_visible()
        self.assert_canvas_only_cards()
        for card in old_cards:
            self.assertFalse(card.alive)
            self.assertEqual(app.canvas.find_withtag(card.tag), ())
        self.assertIn(7443, app.cards)

    def test_virtual_rows_remain_bounded_and_shared_cards_survive(self):
        app = self.app
        self.assertEqual(len(app.filtered), 7444)
        before = dict(app.cards)
        self.assertLess(len(before), 80)
        top = app.canvas.canvasy(0) + app.row_height()
        app.scroll_view('moveto', top / app.scroll_height())
        app.refresh_visible()
        shared = set(before) & set(app.cards)
        self.assertTrue(shared)
        self.assertLessEqual(len(set(app.cards) - set(before)), app.columns())
        self.assertTrue(all(app.cards[index][1] is before[index][1] for index in shared))
        for fraction in (0, 0.5, 1):
            app.scroll_view('moveto', fraction)
            app.refresh_visible()
            self.assertLess(len(app.cards), 80)
        self.assertIn(7443, app.cards)
        self.assertFalse(app.smooth_scroll.active)


if __name__ == '__main__':
    unittest.main()
