import heapq
import unittest

from smooth_scroll import SmoothScroller, wheel_pixels


class FakeViewport:
    def __init__(self, position=0.0, limit=2000.0, rounded=False):
        self.position = position
        self.limit = limit
        self.rounded = rounded
        self.now = 0.0
        self.jobs = []
        self.cancelled = set()
        self.next_job = 0
        self.moves = []
        self.scroller = SmoothScroller(
            lambda: self.position, lambda: self.limit, self.move,
            self.schedule, self.cancel, lambda: self.now)

    def move(self, offset):
        self.moves.append((self.now, offset))
        self.position = round(offset) if self.rounded else offset

    def schedule(self, delay, callback):
        self.next_job += 1
        heapq.heappush(self.jobs, (self.now + delay / 1000,
                                   self.next_job, callback))
        return self.next_job

    def cancel(self, job):
        self.cancelled.add(job)

    def advance(self, milliseconds):
        until = self.now + milliseconds / 1000
        while self.jobs and self.jobs[0][0] <= until:
            due, job, callback = heapq.heappop(self.jobs)
            self.now = due
            if job not in self.cancelled:
                callback()
        self.now = until

    def finish(self):
        for _ in range(1000):
            if not self.scroller.active:
                return
            self.advance(16)
        raise AssertionError('Scrolling did not finish')


class SmoothScrollChecks(unittest.TestCase):
    def test_one_notch_has_monotone_intermediate_frames(self):
        view = FakeViewport()
        view.scroller.scroll_by(90)
        self.assertTrue(view.scroller.active)
        self.assertEqual(view.position, 0)
        view.advance(16)
        self.assertGreater(view.position, 0)
        self.assertLess(view.position, 90)
        view.finish()
        positions = [offset for _, offset in view.moves]
        self.assertGreater(len(positions), 3)
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(view.position, 90)

    def test_rapid_wheel_events_accumulate_the_destination(self):
        view = FakeViewport(position=100)
        for _ in range(3):
            view.scroller.scroll_by(90)
        self.assertEqual(len(view.jobs), 1)
        view.advance(16)
        view.scroller.scroll_by(90)
        view.finish()
        self.assertEqual(view.position, 460)

    def test_reverse_drops_old_pending_distance(self):
        view = FakeViewport(position=500)
        view.scroller.scroll_by(270)
        view.advance(16)
        reversal_position = view.position
        view.scroller.scroll_by(-45)
        view.advance(16)
        self.assertLess(view.position, reversal_position)
        view.finish()
        self.assertAlmostEqual(view.position, reversal_position - 45)

    def test_reverse_before_first_frame_changes_direction_immediately(self):
        view = FakeViewport(position=500)
        view.scroller.scroll_by(90)
        view.scroller.scroll_by(-30)
        view.advance(16)
        self.assertLess(view.position, 500)
        view.finish()
        self.assertEqual(view.position, 470)

    def test_upper_and_lower_bounds_never_overshoot(self):
        view = FakeViewport(position=120, limit=150)
        view.scroller.scroll_by(900)
        view.finish()
        self.assertEqual(view.position, 150)
        view.scroller.scroll_by(-900)
        view.finish()
        self.assertEqual(view.position, 0)
        self.assertTrue(all(0 <= offset <= 150 for _, offset in view.moves))

    def test_changed_limit_clamps_both_destination_and_position(self):
        view = FakeViewport(position=500, limit=1000)
        view.scroller.scroll_by(300)
        view.advance(16)
        view.limit = 400
        view.position = 400
        view.advance(16)
        self.assertEqual(view.position, 400)
        self.assertFalse(view.scroller.active)

    def test_fractional_input_is_not_discarded(self):
        view = FakeViewport(position=12.25)
        view.scroller.scroll_by(0.6)
        view.scroller.scroll_by(0.3)
        view.finish()
        self.assertAlmostEqual(view.position, 13.15)

    def test_stop_cancels_timer_and_discards_old_destination(self):
        view = FakeViewport(position=100)
        view.scroller.scroll_by(270)
        view.advance(16)
        stopped_position = view.position
        move_count = len(view.moves)
        view.scroller.stop()
        self.assertFalse(view.scroller.active)
        view.advance(1000)
        self.assertEqual(len(view.moves), move_count)
        self.assertEqual(view.position, stopped_position)
        view.scroller.scroll_by(10)
        view.finish()
        self.assertAlmostEqual(view.position, stopped_position + 10)

    def test_cancelled_callback_cannot_interfere_with_new_animation(self):
        view = FakeViewport(position=100)
        view.scroller.scroll_by(90)
        stale_callback = view.jobs[0][2]
        view.scroller.stop()
        view.scroller.scroll_by(30)
        stale_callback()
        view.finish()
        self.assertEqual(view.position, 130)

    def test_external_jump_stops_animation_without_moving_back(self):
        view = FakeViewport(position=100)
        view.scroller.scroll_by(270)
        view.advance(16)
        move_count = len(view.moves)
        view.position = 900
        view.advance(16)
        self.assertFalse(view.scroller.active)
        self.assertEqual(view.position, 900)
        self.assertEqual(len(view.moves), move_count)

    def test_whole_pixel_rounding_does_not_look_like_external_navigation(self):
        view = FakeViewport(position=100, rounded=True)
        view.scroller.scroll_by(90)
        view.finish()
        self.assertEqual(view.position, 190)
        self.assertGreater(len(view.moves), 3)

    def test_new_wheel_after_external_jump_starts_at_the_new_position(self):
        view = FakeViewport(position=100)
        view.scroller.scroll_by(270)
        view.advance(16)
        view.position = 900
        view.scroller.scroll_by(30)
        view.finish()
        self.assertEqual(view.position, 930)

    def test_idle_animation_reads_the_current_viewport(self):
        view = FakeViewport(position=100)
        view.scroller.scroll_by(90)
        view.finish()
        view.position = 500
        view.scroller.scroll_by(30)
        view.finish()
        self.assertEqual(view.position, 530)

    def test_blocked_or_empty_viewport_does_not_schedule_frames(self):
        for position, limit, delta in [(0, 100, -90), (100, 100, 90),
                                        (0, 0, 90), (0, 100, 0)]:
            with self.subTest(position=position, limit=limit, delta=delta):
                view = FakeViewport(position=position, limit=limit)
                view.scroller.scroll_by(delta)
                self.assertFalse(view.scroller.active)
                self.assertFalse(view.jobs)

    def test_easing_depends_on_elapsed_time_instead_of_number_of_callbacks(self):
        regular = FakeViewport()
        delayed = FakeViewport()
        regular.scroller.scroll_by(90)
        delayed.scroller.scroll_by(90)
        regular.advance(32)
        _, _, delayed_frame = heapq.heappop(delayed.jobs)
        delayed.now = 0.032
        delayed_frame()
        self.assertAlmostEqual(regular.position, delayed.position)


class WheelPixelsChecks(unittest.TestCase):
    def test_windows_notches_and_partial_deltas(self):
        self.assertEqual(wheel_pixels(120, platform='win32'), -90)
        self.assertEqual(wheel_pixels(-240, platform='win32'), 180)
        self.assertEqual(wheel_pixels(30, platform='win32'), -22.5)

    def test_linux_button_events(self):
        self.assertEqual(wheel_pixels(number=4, platform='linux'), -90)
        self.assertEqual(wheel_pixels(number=5, platform='linux'), 90)
        self.assertEqual(wheel_pixels(platform='linux'), 0)

    def test_mac_trackpad_preserves_small_deltas(self):
        self.assertEqual(wheel_pixels(2, platform='darwin'), -12)
        self.assertAlmostEqual(wheel_pixels(0.1, platform='darwin'), -0.6)
        self.assertAlmostEqual(wheel_pixels(-0.25, platform='darwin'), 1.5)


if __name__ == '__main__':
    unittest.main()
