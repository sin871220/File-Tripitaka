"""Time-based scrolling independent of Tk widgets and event dispatch."""

import math
import sys
import time


def wheel_pixels(delta=0, number=None, platform=sys.platform):
    """Convert a native wheel event into signed vertical pixel distance."""
    if number == 4:
        return -90.0
    if number == 5:
        return 90.0
    if platform == 'darwin':
        return -float(delta) * 6.0
    return -float(delta) / 120.0 * 90.0


class SmoothScroller:
    """Ease a viewport toward accumulated wheel input at roughly 60 FPS.

    ``position`` and ``limit`` return the current offset and maximum offset in
    pixels. ``move`` accepts an absolute offset. ``schedule`` and ``cancel``
    use the same calling convention as Tk's ``after`` and ``after_cancel``.
    The viewport may round offsets to whole pixels; animation keeps its own
    fractional position until it finishes.
    """

    FRAME_MS = 16
    TIME_CONSTANT = 0.035
    FINISH_DISTANCE = 0.1
    POSITION_TOLERANCE = 1.0

    def __init__(self, position, limit, move, schedule, cancel,
                 clock=time.monotonic):
        self._read_position = position
        self._read_limit = limit
        self._move = move
        self._schedule = schedule
        self._cancel = cancel
        self._clock = clock
        self._job = None
        self._generation = 0
        self._position = None
        self._expected = None
        self._target = None
        self._last_time = None

    @property
    def active(self):
        return self._target is not None

    @staticmethod
    def _clamp(value, limit):
        return min(limit, max(0.0, value))

    def _viewport(self):
        limit = max(0.0, float(self._read_limit()))
        return self._clamp(float(self._read_position()), limit), limit

    def scroll_by(self, delta_pixels):
        delta = float(delta_pixels)
        if not math.isfinite(delta) or delta == 0:
            return
        actual, limit = self._viewport()
        if self.active:
            expected = self._clamp(self._expected, limit)
            if abs(actual - expected) > self.POSITION_TOLERANCE:
                self.stop()
        if not self.active:
            self._generation += 1
            self._position = self._expected = actual
            self._target = actual
            self._last_time = self._clock()
        else:
            self._position = self._clamp(self._position, limit)
            self._target = self._clamp(self._target, limit)

        remaining = self._target - self._position
        if delta * remaining < 0:
            # Reversing should respond immediately, without spending the next
            # frames consuming travel left over from the previous direction.
            self._target = self._position
        self._target = self._clamp(self._target + delta, limit)
        if self._target == self._position:
            self.stop()
        elif self._job is None:
            self._queue_frame()

    def _queue_frame(self):
        generation = self._generation
        self._job = self._schedule(
            self.FRAME_MS, lambda: self._tick(generation))

    def _tick(self, generation):
        if generation != self._generation or not self.active:
            return
        self._job = None
        actual, limit = self._viewport()
        expected = self._clamp(self._expected, limit)
        if abs(actual - expected) > self.POSITION_TOLERANCE:
            # Scrollbar, keyboard, or programmatic navigation takes priority.
            self.stop()
            return

        self._position = self._clamp(self._position, limit)
        self._target = self._clamp(self._target, limit)
        now = self._clock()
        elapsed = max(0.0, now - self._last_time)
        self._last_time = now
        remaining = self._target - self._position
        progress = -math.expm1(-elapsed / self.TIME_CONSTANT)
        next_position = self._position + remaining * progress
        finished = abs(self._target - next_position) <= self.FINISH_DISTANCE
        if finished:
            next_position = self._target

        self._position = self._expected = next_position
        self._move(next_position)
        if generation != self._generation or not self.active:
            return
        if finished:
            self.stop()
        else:
            self._queue_frame()

    def stop(self):
        """Cancel pending animation without changing the visible position."""
        self._generation += 1
        job, self._job = self._job, None
        self._position = self._expected = self._target = None
        self._last_time = None
        if job is not None:
            self._cancel(job)
