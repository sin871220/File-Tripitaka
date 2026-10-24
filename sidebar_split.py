"""A resizable pair of sidebar sections with independently visible headers."""
import math
import tkinter as tk


DEFAULT_SIDEBAR_RATIO = .32


def normalize_sidebar_ratio(value):
    """Ignore malformed saved geometry instead of hiding an entire section."""
    if isinstance(value, bool):
        return DEFAULT_SIDEBAR_RATIO
    try:
        ratio = float(value)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_SIDEBAR_RATIO
    return min(.9, max(.1, ratio)) if math.isfinite(ratio) else DEFAULT_SIDEBAR_RATIO


class SidebarSplit(tk.PanedWindow):
    """Native vertical sash; collapsing either body gives space to the other.

    The application owns header/body packing. Call ``set_collapsed`` after
    updating that packing; this widget sizes the two section frames and keeps
    their headers accessible. Only a completed user drag publishes a ratio.
    """

    def __init__(self, parent, ratio=DEFAULT_SIDEBAR_RATIO, on_change=None, **kwargs):
        defaults = dict(orient='vertical', sashwidth=6, sashpad=0,
                        sashrelief='flat', showhandle=False, bd=0,
                        opaqueresize=True, cursor='sb_v_double_arrow')
        defaults.update(kwargs)
        super().__init__(parent, **defaults)
        self.ratio = normalize_sidebar_ratio(ratio)
        self._on_change = on_change
        self._sections = None
        self._headers = None
        self._footer = None
        self._collapsed = (False, False)
        self._alive = True
        self._dragging = False
        self._drag_start = self.ratio
        self._layout_after = None
        self._settle_after = None
        self._sample_after = None
        self._finish_after = None
        self.bind('<Configure>', self._configured)
        self.bind('<Map>', self._mapped)
        self.bind('<Unmap>', self._unmapped)
        self.bind('<ButtonPress-1>', self._press)
        self.bind('<B1-Motion>', self._motion)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Destroy>', self._destroyed, add='+')

    def set_sections(self, favorite_frame, tree_frame, favorite_header,
                     tree_header, favorite_footer=None):
        if self._sections is not None:
            for pane in self.panes():
                self.forget(pane)
        self._sections = (favorite_frame, tree_frame)
        self._headers = (favorite_header, tree_header)
        self._footer = favorite_footer
        for pane in self._sections:
            # A resize cursor belongs to the sash, not to the nested lists.
            pane.configure(cursor='arrow')
            self.add(pane, sticky='nsew', stretch='always', minsize=1)
        self._queue_layout()

    def set_theme(self, palette):
        self.configure(background=palette['border'])
        self._queue_layout()

    def set_collapsed(self, favorites, tree):
        values = (bool(favorites), bool(tree))
        if values != self._collapsed:
            self._abort_drag()
            self._collapsed = values
        self._queue_layout()

    def get_ratio(self):
        # Keep the user's preferred expanded split, even while a small window
        # temporarily clamps the actual sash to a section's minimum height.
        return self.ratio

    def sashpos(self, index=0, newpos=None):
        """Offer the small ttk-style sash API used by the controller/tests."""
        if int(index) != 0:
            raise tk.TclError('The sidebar has one sash')
        if newpos is None:
            return int(self.sash_coord(0)[1])
        if any(self._collapsed):
            return self.sashpos(0)
        self.update_idletasks()
        position = self._clamp_position(int(newpos))
        previous = self.get_ratio()
        self.sash_place(0, 0, position)
        self._sample_ratio()
        self._queue_layout()
        if abs(self.ratio - previous) > 1e-6 and self._on_change is not None:
            self._on_change(self.ratio)
        return self.sashpos(0)

    def _height(self):
        return max(0, self.winfo_height() - int(self.cget('sashwidth')))

    def _minimums(self):
        if self._headers is None:
            return 1, 1
        top, bottom = (max(1, header.winfo_reqheight()) for header in self._headers)
        total = self._height()
        spare = max(0, total - top - bottom)
        footer = max(0, self._footer.winfo_reqheight()) if self._footer is not None else 0
        wanted_top = 0 if self._collapsed[0] else max(56, footer + 40)
        wanted_bottom = 0 if self._collapsed[1] else 72
        wanted = wanted_top + wanted_bottom
        if wanted and wanted > spare:
            extra_top = int(spare * wanted_top / wanted)
            extra_bottom = spare - extra_top
        else:
            extra_top, extra_bottom = wanted_top, wanted_bottom
        return top + extra_top, bottom + extra_bottom

    def _clamp_position(self, position):
        low, bottom = self._minimums()
        high = max(low, self._height() - bottom)
        return min(high, max(low, position))

    def _queue_layout(self):
        if self._alive and self._layout_after is None:
            self._cancel('_settle_after')
            self._layout_after = self.after_idle(self._layout)

    def _layout(self):
        self._layout_after = None
        if not self._alive or self._sections is None or self.winfo_height() <= 1 or self._dragging:
            return
        minimums = self._minimums()
        for index, pane in enumerate(self._sections):
            self.paneconfigure(pane, minsize=minimums[index],
                               stretch='always' if not self._collapsed[index] else 'never')
        # With both bodies collapsed, the second frame may hold blank space;
        # its header still sits directly below the first header and sash.
        if all(self._collapsed):
            self.paneconfigure(self._sections[1], stretch='always')
        # Changing pane options schedules Tk's own geometry negotiation. Place
        # the sash only after that work: an immediate placement can otherwise
        # be overwritten by the pending native layout.
        self._settle_after = self.after_idle(self._settle_layout)

    def _settle_layout(self):
        self._settle_after = None
        if not self._alive or self._sections is None or self._dragging:
            return
        top, bottom = (max(1, header.winfo_reqheight()) for header in self._headers)
        total = self._height()
        position = top if self._collapsed[0] else total - bottom if self._collapsed[1] else int(total * self.ratio + .5)
        self.sash_place(0, 0, self._clamp_position(position))

    def _sample_ratio(self):
        if (not self._alive or self._sections is None or any(self._collapsed)
                or self.winfo_height() <= 1 or self._layout_after is not None
                or self._settle_after is not None):
            return
        total = self._height()
        if total > 0:
            self.ratio = normalize_sidebar_ratio(self.sash_coord(0)[1] / total)

    def _configured(self, _event):
        if not self._dragging:
            self._queue_layout()

    def _mapped(self, _event):
        self._queue_layout()

    def _unmapped(self, event):
        if event.widget is self:
            self._abort_drag()

    def _press(self, event):
        if any(self._collapsed):
            return 'break'
        if self._sections is None or not self.identify(event.x, event.y):
            return
        self._cancel('_layout_after')
        self._cancel('_settle_after')
        self._drag_start = self.get_ratio()
        self._dragging = True

    def _motion(self, _event):
        if any(self._collapsed):
            return 'break'
        if self._dragging and self._sample_after is None:
            self._sample_after = self.after_idle(self._sample_drag)

    def _sample_drag(self):
        self._sample_after = None
        if self._dragging:
            self._sample_ratio()

    def _release(self, _event):
        if any(self._collapsed):
            return 'break'
        if self._dragging and self._finish_after is None:
            self._finish_after = self.after_idle(self._finish_drag)

    def _finish_drag(self):
        self._finish_after = None
        if not self._dragging:
            return
        self._cancel('_sample_after')
        self._sample_ratio()
        self._dragging = False
        if abs(self.ratio - self._drag_start) > 1e-6 and self._on_change is not None:
            self._on_change(self.ratio)
        self._queue_layout()

    def _cancel(self, attribute):
        token = getattr(self, attribute)
        if token is not None:
            try:
                self.after_cancel(token)
            except tk.TclError:
                pass
            setattr(self, attribute, None)

    def _abort_drag(self):
        self._cancel('_sample_after')
        self._cancel('_finish_after')
        self._dragging = False

    def _destroyed(self, event):
        if event.widget is not self:
            return
        self._alive = False
        self._cancel('_layout_after')
        self._cancel('_settle_after')
        self._abort_drag()
        self._on_change = None
        self._sections = self._headers = self._footer = None
