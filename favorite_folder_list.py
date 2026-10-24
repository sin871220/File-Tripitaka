"""A favorite-folder Treeview whose top-level rows can be reordered by dragging."""
from tkinter import TclError, ttk


class FavoriteFolderList(ttk.Treeview):
    """Keep ordinary Treeview clicks; publish an order after a completed drag.

    ``on_reorder`` receives top-level item IDs, without knowing the folder model.
    A controller may append its normal click/open handler to ButtonRelease-1:
    only a dragged or cancelled release is consumed here. Before rebuilding the
    rows, call ``cancel_drag()`` so old item IDs cannot survive an active drag.
    """

    DRAG_THRESHOLD = 6
    AUTOSCROLL_DELAY = 70
    AUTOSCROLL_MARGIN = 24

    def __init__(self, parent, *, on_reorder=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._on_reorder = on_reorder
        self._alive = True
        self._drag_item = None
        self._original_order = ()
        self._press_x = self._press_y = 0
        self._pointer_x = self._pointer_y = 0
        self._dragging = False
        self._suppress_release = False
        self._scroll_after = None
        self.bind('<ButtonPress-1>', self._press)
        self.bind('<B1-Motion>', self._motion)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Escape>', self._escape)
        self.bind('<Unmap>', self._unmapped, add='+')
        self.bind('<Destroy>', self._destroyed, add='+')

    def cancel_drag(self, restore=False):
        """Cancel a gesture and optionally restore its initial visible order."""
        active = self._drag_item is not None or self._dragging
        self._cancel_scroll()
        if restore and self._alive and self._original_order:
            for index, item in enumerate(self._original_order):
                if self.exists(item) and not self.parent(item):
                    self.move(item, '', index)
        if active:
            self._suppress_release = True
        self._drag_item = None
        self._dragging = False
        self._original_order = ()

    def _press(self, event):
        self.cancel_drag(restore=True)
        self._suppress_release = False
        item = self.identify_row(event.y)
        if (not item or self.parent(item)
                or self.identify_region(event.x, event.y) not in ('tree', 'cell')):
            return
        self._drag_item = item
        self._original_order = self.get_children('')
        self._press_x = self._pointer_x = event.x
        self._press_y = self._pointer_y = event.y
        # The Treeview class binding performs normal selection/focus after this.

    def _motion(self, event):
        if self._drag_item is None:
            return 'break' if self._suppress_release else None
        if not self.exists(self._drag_item):
            self.cancel_drag()
            return 'break'
        self._pointer_x, self._pointer_y = event.x, event.y
        if not self._dragging:
            distance = (event.x - self._press_x) ** 2 + (event.y - self._press_y) ** 2
            if distance < self.DRAG_THRESHOLD ** 2:
                return
            self._dragging = True
            self.selection_set(self._drag_item)
            self.focus(self._drag_item)
        self._move_to_pointer()
        self._schedule_scroll()
        # Native Treeview motion must not select a different row while dragging.
        return 'break'

    def _move_to_pointer(self):
        item = self._drag_item
        if item is None or not self.exists(item):
            return
        rows = list(self.get_children(''))
        if item not in rows:
            return
        target = self.identify_row(self._pointer_y)
        remaining = [row for row in rows if row != item]
        if not remaining or target == item:
            return
        if target in remaining:
            box = self.bbox(target)
            if not box:
                return
            index = remaining.index(target) + int(self._pointer_y >= box[1] + box[3] / 2)
        elif self._pointer_y <= self.AUTOSCROLL_MARGIN:
            target = self._visible_boundary_row(-1)
            if target not in remaining:
                return
            index = remaining.index(target)
        elif self._pointer_y >= self.winfo_height() - self.AUTOSCROLL_MARGIN:
            target = self._visible_boundary_row(1)
            if target not in remaining:
                return
            index = remaining.index(target) + 1
        else:
            # The blank area below the final visible row is an end insertion.
            final_box = self.bbox(rows[-1])
            if not final_box or self._pointer_y < final_box[1] + final_box[3]:
                return
            index = len(remaining)
        if rows.index(item) != index:
            self.move(item, '', index)

    def _visible_boundary_row(self, direction):
        # identify_row is empty outside the viewport and over a header/border.
        # Search inward from the edge, rather than jumping to the global first
        # or last row of a partially scrolled list.
        height = self.winfo_height()
        positions = range(1, height) if direction < 0 else range(height - 2, -1, -1)
        for y in positions:
            item = self.identify_row(y)
            if item and not self.parent(item):
                return item
        return None

    def _scroll_direction(self):
        margin = min(self.AUTOSCROLL_MARGIN, max(8, self.winfo_height() // 4))
        if self._pointer_y < margin:
            return -1
        if self._pointer_y >= self.winfo_height() - margin:
            return 1
        return 0

    def _schedule_scroll(self):
        if not self._dragging or not self._scroll_direction():
            self._cancel_scroll()
        elif self._scroll_after is None:
            self._scroll_after = self.after(self.AUTOSCROLL_DELAY, self._autoscroll)

    def _autoscroll(self):
        self._scroll_after = None
        if not self._alive or not self._dragging or self._drag_item is None:
            return
        if not self.exists(self._drag_item):
            self.cancel_drag()
            return
        direction = self._scroll_direction()
        if not direction:
            return
        before = self.yview()
        self.yview_scroll(direction, 'units')
        self._move_to_pointer()
        if self.yview() != before:
            self._schedule_scroll()

    def _release(self, _event):
        consumed = self._dragging or self._suppress_release
        order = self.get_children('') if self._dragging else ()
        changed = bool(self._dragging and order != self._original_order)
        self._cancel_scroll()
        self._drag_item = None
        self._dragging = False
        self._original_order = ()
        self._suppress_release = False
        if changed and self._on_reorder is not None:
            self._on_reorder(list(order))
        return 'break' if consumed else None

    def _escape(self, _event):
        if self._drag_item is not None or self._dragging:
            self.cancel_drag(restore=True)
            return 'break'

    def _cancel_scroll(self):
        if self._scroll_after is not None:
            try:
                self.after_cancel(self._scroll_after)
            except TclError:
                pass
            self._scroll_after = None

    def _unmapped(self, event):
        if event.widget is self:
            self.cancel_drag(restore=True)

    def _destroyed(self, event):
        if event.widget is self:
            self._alive = False
            self.cancel_drag()
            self._on_reorder = None
