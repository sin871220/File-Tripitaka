"""Fixed library tabs and a separate, horizontally scrolling folder strip.

The small Notebook-compatible interface keeps callers independent of the
canvas painting used for the strip. Folder labels are always literal text.
"""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, font as tkfont

from smooth_scroll import wheel_pixels


_PALETTE = dict(bg='#F4F6FA', panel='#FFFFFF', fg='#202938', muted='#627087',
                border='#D9E3EF', accent='#087BFA', hover='#E7F1FF', field='#F5F8FC')


class LibraryTabBar(ttk.Frame):
    """All/Favorites and Add stay fixed while only folder tabs can scroll."""

    def __init__(self, parent, on_add=None, on_close=None, on_hover=None, on_reorder=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._alive = True
        self._palette = dict(_PALETTE)
        self._font_spec = ('TkDefaultFont', 10)
        self._font = tkfont.Font(root=self, font=self._font_spec)
        self._labels = {'all': '전체', 'favorites': '★ 즐겨찾기'}
        self._folders = []
        self._selected = 'all'
        self._hovered = None
        self._on_add = on_add
        self._on_close = on_close
        self._on_hover = on_hover
        self._on_reorder = on_reorder
        self._drag = None
        self._drag_after = None
        self._overflow_after = None
        self._arrows_visible = False
        self._content_width = 0
        self.folder_bounds = {}
        self._close_bounds = {}
        self._fixed_bounds = {}
        self.columnconfigure(3, weight=1)
        self.rowconfigure(0, weight=1)

        self.fixed_canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, cursor='hand2')
        self.fixed_canvas.grid(row=0, column=0, sticky='ns')
        self.left_button = ttk.Button(self, text='‹', width=2, style='LibraryTabArrow.TButton',
                                      command=lambda: self._scroll(-self._page_step()))
        self.left_button.grid(row=0, column=2, sticky='ns', padx=(4, 0))
        self.folder_canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0,
                                       xscrollincrement=1, takefocus=True, cursor='hand2')
        self.folder_canvas.grid(row=0, column=3, sticky='nsew')
        self.right_button = ttk.Button(self, text='›', width=2, style='LibraryTabArrow.TButton',
                                       command=lambda: self._scroll(self._page_step()))
        self.right_button.grid(row=0, column=4, sticky='ns', padx=(0, 4))
        self.plus_button = ttk.Button(self, text='＋', width=3, style='LibraryTabPlus.TButton',
                                      command=self._add)
        self.plus_button.grid(row=0, column=1, sticky='ns', padx=(4, 0))
        self.left_button.grid_remove()
        self.right_button.grid_remove()

        self.fixed_canvas.bind('<Button-1>', self._fixed_click)
        self.fixed_canvas.bind('<Motion>', self._fixed_motion)
        self.fixed_canvas.bind('<Leave>', self._leave)
        self.folder_canvas.bind('<Button-1>', self._folder_click)
        self.folder_canvas.bind('<B1-Motion>', self._folder_drag)
        self.folder_canvas.bind('<ButtonRelease-1>', self._folder_drop)
        self.folder_canvas.bind('<Motion>', self._folder_motion)
        self.folder_canvas.bind('<Leave>', self._leave)
        for sequence in ('<MouseWheel>', '<Shift-MouseWheel>', '<Button-4>', '<Button-5>'):
            self.folder_canvas.bind(sequence, self._wheel)
        self.folder_canvas.bind('<Left>', lambda _event: self._scroll_key(-1))
        self.folder_canvas.bind('<Right>', lambda _event: self._scroll_key(1))
        self.folder_canvas.bind('<Home>', lambda _event: self._edge_key(False))
        self.folder_canvas.bind('<End>', lambda _event: self._edge_key(True))
        self.folder_canvas.bind('<Escape>', lambda _event: self._cancel_drag_key())
        self.folder_canvas.bind('<Configure>', self._resize)
        self.bind('<Configure>', self._resize, add='+')
        self.bind('<Destroy>', self._destroyed, add='+')
        self.set_theme(self._palette, self._font_spec)

    def tabs(self):
        return ('all', 'favorites', *(record['id'] for record in self._folders))

    def _resolve(self, value):
        identifiers = self.tabs()
        if value in identifiers:
            return value
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise tk.TclError(f'Unknown tab: {value!r}') from None
        if not 0 <= number < len(identifiers):
            raise tk.TclError(f'Tab index out of range: {value!r}')
        return identifiers[number]

    def select(self, value=None):
        if value is None:
            return self._selected
        target = self._resolve(value)
        if target != self._selected:
            self._selected = target
            self._draw()
            self.ensure_visible(target)
            self.event_generate('<<NotebookTabChanged>>', when='tail')
        else:
            self.ensure_visible(target)

    def index(self, value):
        if value == 'end':
            return len(self.tabs())
        if isinstance(value, str) and value.startswith('@'):
            try:
                x, y = map(int, value[1:].split(','))
            except ValueError:
                raise tk.TclError('Expected tab position @x,y') from None
            fixed_x, fixed_y = x - self.fixed_canvas.winfo_x(), y - self.fixed_canvas.winfo_y()
            for identifier, box in self._fixed_bounds.items():
                if self._inside(box, fixed_x, fixed_y):
                    return self.tabs().index(identifier)
            local_x, local_y = x - self.folder_canvas.winfo_x(), y - self.folder_canvas.winfo_y()
            if 0 <= local_x < self.folder_canvas.winfo_width() and 0 <= local_y < self.folder_canvas.winfo_height():
                identifier = self._folder_at(self.folder_canvas.canvasx(local_x), local_y)
                if identifier is not None:
                    return self.tabs().index(identifier)
            raise tk.TclError('No tab at that position')
        return self.tabs().index(self._resolve(value))

    def tab(self, value, option=None, **kwargs):
        identifier = self._resolve(value)
        if kwargs:
            if set(kwargs) != {'text'}:
                raise tk.TclError('Only the tab text can be configured')
            label = str(kwargs['text'])
            if identifier in self._labels:
                self._labels[identifier] = label
            else:
                next(record for record in self._folders if record['id'] == identifier)['label'] = label
            self._rebuild()
        text = (self._labels[identifier] if identifier in self._labels else
                next(record['label'] for record in self._folders if record['id'] == identifier))
        details = {'text': text, 'state': 'normal'}
        if option is None:
            return details
        if option not in details:
            raise tk.TclError(f'Unknown tab option: {option!r}')
        return details[option]

    def set_base_labels(self, all_label, favorites_label):
        self._labels = {'all': str(all_label), 'favorites': str(favorites_label)}
        self._rebuild()

    def set_folder_tabs(self, records):
        # A controller refresh is authoritative. A pending mouse release must
        # never publish an order based on records that it has just replaced.
        self._stop_drag()
        folders, seen = [], {'all', 'favorites'}
        for source in records:
            if not isinstance(source, dict):
                continue
            identifier = source.get('id')
            if not isinstance(identifier, str) or not identifier or identifier in seen:
                continue
            path = str(source.get('path', ''))
            label = source.get('label', Path(path).name or path)
            folders.append({'id': identifier, 'path': path, 'label': str(label)})
            seen.add(identifier)
        self._folders = folders
        if self._selected not in self.tabs():
            # The controller chooses and loads a fallback view when closing.
            self._selected = 'all'
        if self._hovered not in self.tabs():
            self._hovered = None
        self._rebuild()

    def set_theme(self, palette, font):
        if not self._alive:
            return
        self._palette = dict(palette)
        self._font_spec = tuple(font)
        self._font.configure(family=font[0], size=font[1])
        style = ttk.Style(self)
        for name in ('LibraryTabArrow.TButton', 'LibraryTabPlus.TButton'):
            style.configure(name, padding=(5, 6), font=self._font,
                            background=palette['field'], foreground=palette['fg'],
                            borderwidth=1, relief='flat')
            style.map(name, background=[('active', palette['hover'])],
                      foreground=[('disabled', palette['muted'])])
        self._rebuild()

    def _rebuild(self):
        if not self._alive:
            return
        height = max(36, self._font.metrics('linespace') + 20)
        self._height = height
        self._fixed_bounds = {}
        x = 0
        for identifier in ('all', 'favorites'):
            width = max(80, self._font.measure(self._labels[identifier]) + 46)
            self._fixed_bounds[identifier] = (x, 0, x + width, height)
            x += width
        self.fixed_canvas.configure(width=x, height=height, bg=self._palette['bg'])
        self.folder_canvas.configure(height=height, bg=self._palette['bg'])
        self.folder_bounds, self._close_bounds = {}, {}
        x = 0
        for record in self._folders:
            width = min(240, max(100, self._font.measure(record['label'][:8192]) + 52))
            self.folder_bounds[record['id']] = (x, 0, x + width, height)
            self._close_bounds[record['id']] = (x + width - 29, 2, x + width - 3, height - 2)
            x += width + 3
        self._content_width = max(0, x - 3)
        self.folder_canvas.configure(scrollregion=(0, 0, max(1, self._content_width), height))
        self._draw()
        if not self._drag or not self._drag['active']:
            self.ensure_visible(self._selected)
        self._update_arrows()
        self._queue_overflow_layout()

    def _draw_tab(self, canvas, identifier, box, text, close=False):
        p = self._palette
        x1, y1, x2, y2 = box
        selected = identifier == self._selected
        background = p['panel'] if selected else p['hover'] if identifier == self._hovered else p['field']
        canvas.create_rectangle(x1, y1, x2 - 1, y2 - 1, fill=background, outline=p['border'])
        if selected:
            canvas.create_rectangle(x1, y2 - 3, x2 - 1, y2 - 1, fill=p['accent'], outline='')
        if close:
            label_width = max(1, x2 - x1 - 45)
            canvas.create_text(x1 + 13, (y1 + y2) / 2, text=self._fit_label(text, label_width),
                               anchor='w', fill=p['fg'] if selected else p['muted'], font=self._font)
            canvas.create_text(x2 - 16, (y1 + y2) / 2, text='×', fill=p['muted'], font=self._font)
        else:
            canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=text,
                               fill=p['fg'] if selected else p['muted'], font=self._font)

    def _draw(self):
        if not self._alive:
            return
        self.fixed_canvas.delete('all')
        self.folder_canvas.delete('all')
        for identifier, box in self._fixed_bounds.items():
            self._draw_tab(self.fixed_canvas, identifier, box, self._labels[identifier])
        for record in self._folders:
            self._draw_tab(self.folder_canvas, record['id'], self.folder_bounds[record['id']],
                           record['label'], close=True)

    def _fit_label(self, value, width):
        value = str(value)
        if self._font.measure(value[:8192]) <= width and len(value) <= 8192:
            return value
        low, high = 0, min(len(value), 8192)
        while low < high:
            middle = (low + high + 1) // 2
            if self._font.measure(value[:middle] + '…') <= width:
                low = middle
            else:
                high = middle - 1
        return value[:low] + '…'

    @staticmethod
    def _inside(box, x, y):
        return box[0] <= x < box[2] and box[1] <= y < box[3]

    def _folder_at(self, x, y):
        return next((identifier for identifier, box in self.folder_bounds.items()
                     if self._inside(box, x, y)), None)

    def _fixed_click(self, event):
        self._stop_drag(restore=True)
        for identifier, box in self._fixed_bounds.items():
            if self._inside(box, event.x, event.y):
                self.select(identifier)
                break
        return 'break'

    def _folder_click(self, event):
        self._stop_drag(restore=True)
        x = self.folder_canvas.canvasx(event.x)
        identifier = self._folder_at(x, event.y)
        if identifier is not None:
            if self._inside(self._close_bounds[identifier], x, event.y):
                if self._on_close is not None:
                    self._on_close(identifier)
            else:
                self.folder_canvas.focus_set()
                self.select(identifier)
                # select() may reveal a partially clipped tab and move xview.
                # Record the grab point after that adjustment, keeping the
                # dragged tab centered consistently even for uneven widths.
                start, _, end, _ = self.folder_bounds[identifier]
                self._drag = dict(identifier=identifier, start_x=event.x,
                                  x=event.x, y=event.y, active=False, pressed=True,
                                  grab=self.folder_canvas.canvasx(event.x) - start,
                                  width=end - start,
                                  initial=tuple(record['id'] for record in self._folders))
        return 'break'

    def _folder_drag(self, event):
        drag = self._drag
        if drag is None:
            return 'break'
        if not int(getattr(event, 'state', 0)) & 0x100:
            self._folder_drop(event)
            return 'break'
        drag.update(x=event.x, y=event.y, pressed=True)
        if not drag['active']:
            if abs(event.x - drag['start_x']) < 6:
                return 'break'
            drag['active'] = True
            self.folder_canvas.configure(cursor='sb_h_double_arrow')
        self._drag_to_pointer()
        self._queue_drag_scroll()
        return 'break'

    def _drag_to_pointer(self):
        drag = self._drag
        if drag is None or not drag['active'] or not self._folders:
            return
        identifiers = [record['id'] for record in self._folders]
        if drag['identifier'] not in identifiers:
            self._stop_drag()
            return
        center = self.folder_canvas.canvasx(drag['x']) - drag['grab'] + drag['width'] / 2
        target = min(range(len(identifiers)), key=lambda index: abs(
            center - (self.folder_bounds[identifiers[index]][0] + self.folder_bounds[identifiers[index]][2]) / 2))
        current = identifiers.index(drag['identifier'])
        if current != target:
            self._folders.insert(target, self._folders.pop(current))
            self._rebuild()

    def _drag_scroll_direction(self):
        drag = self._drag
        if drag is None or not drag['active'] or not drag['pressed'] or not self._arrows_visible:
            return 0
        canvas = self.folder_canvas
        if drag['y'] < -24 or drag['y'] > canvas.winfo_height() + 24:
            return 0
        if drag['x'] < 24:
            return -1
        if drag['x'] > canvas.winfo_width() - 24:
            return 1
        return 0

    def _queue_drag_scroll(self):
        direction = self._drag_scroll_direction()
        if direction == 0:
            self._cancel_drag_scroll()
        elif self._drag_after is None:
            self._drag_after = self.after(40, self._drag_scroll_tick)

    def _drag_scroll_tick(self):
        self._drag_after = None
        if not self._alive or self._drag is None or self.tk.call('grab', 'current'):
            return
        direction = self._drag_scroll_direction()
        if direction:
            before = self.folder_canvas.canvasx(0)
            self._scroll(direction * 24)
            self._drag_to_pointer()
            if abs(self.folder_canvas.canvasx(0) - before) >= .5:
                self._queue_drag_scroll()

    def _cancel_drag_scroll(self):
        if self._drag_after is not None:
            try:
                self.after_cancel(self._drag_after)
            except tk.TclError:
                pass
            self._drag_after = None

    def _stop_drag(self, restore=False):
        self._cancel_drag_scroll()
        drag, self._drag = self._drag, None
        if self._alive:
            try:
                self.folder_canvas.configure(cursor='hand2')
            except tk.TclError:
                # A native destroy can tear down canvases before the frame's
                # own Destroy binding releases its timer and font resources.
                pass
        if restore and drag is not None and drag['active']:
            records = {record['id']: record for record in self._folders}
            if set(records) == set(drag['initial']):
                self._folders = [records[identifier] for identifier in drag['initial']]
                self._rebuild()
        return drag

    def _folder_drop(self, _event):
        drag = self._stop_drag()
        if drag is not None and drag['active']:
            order = [record['id'] for record in self._folders]
            if tuple(order) != drag['initial'] and self._on_reorder is not None:
                self._on_reorder(order)
            self.ensure_visible(self._selected)
        return 'break'

    def _cancel_drag_key(self):
        self._stop_drag(restore=True)
        return 'break'

    def _hover(self, identifier):
        if identifier == self._hovered:
            return
        self._hovered = identifier
        self._draw()
        if self._on_hover is not None:
            path = next((record['path'] for record in self._folders if record['id'] == identifier), None)
            self._on_hover(path)

    def _fixed_motion(self, event):
        self._hover(next((identifier for identifier, box in self._fixed_bounds.items()
                          if self._inside(box, event.x, event.y)), None))

    def _folder_motion(self, event):
        self._hover(self._folder_at(self.folder_canvas.canvasx(event.x), event.y))

    def _leave(self, _event):
        self._cancel_drag_scroll()
        self._hover(None)

    def _add(self):
        if self._on_add is not None:
            self._on_add()

    def _page_step(self):
        return max(80, int(self.folder_canvas.winfo_width() * .7))

    def _scroll(self, pixels):
        if not self._alive:
            return
        width = max(1, self.folder_canvas.winfo_width())
        maximum = max(0, self._content_width - width)
        target = min(maximum, max(0, self.folder_canvas.canvasx(0) + pixels))
        self.folder_canvas.xview_moveto(target / max(1, self._content_width))
        self._update_arrows()

    def _wheel(self, event):
        # Native menus/popdowns can hold a Tcl grab without a Python widget.
        # Only this canvas gets a wheel binding; the gallery keeps its own one.
        if self.tk.call('grab', 'current'):
            return 'break'
        self._scroll(wheel_pixels(getattr(event, 'delta', 0), getattr(event, 'num', None)))
        return 'break'

    def _scroll_key(self, direction):
        self._scroll(direction * self._page_step())
        return 'break'

    def _edge_key(self, end):
        self._scroll(self._content_width if end else -self._content_width)
        return 'break'

    def ensure_visible(self, value):
        if (not self._alive or value not in self.folder_bounds
                or (self._drag is not None and self._drag['active'])):
            return
        width = self.folder_canvas.winfo_width()
        if width <= 1:
            return
        left = self.folder_canvas.canvasx(0)
        start, _, end, _ = self.folder_bounds[value]
        if start < left:
            self._scroll(start - left)
        elif end > left + width:
            self._scroll(end - (left + width))

    def _resize(self, _event):
        if not self._alive:
            return
        if not self._drag or not self._drag['active']:
            self.ensure_visible(self._selected)
        self._update_arrows()
        self._queue_overflow_layout()

    def _queue_overflow_layout(self):
        if self._alive and self._overflow_after is None:
            self._overflow_after = self.after_idle(self._layout_overflow)

    def _layout_overflow(self):
        self._overflow_after = None
        if not self._alive or self.winfo_width() <= 1:
            return
        # Determine overflow without reserving either arrow. Comparing against
        # the current canvas width would oscillate around the fit threshold:
        # showing arrows shrinks that same viewport, and hiding expands it.
        available = max(1, self.winfo_width() - self.fixed_canvas.winfo_reqwidth()
                        - self.plus_button.winfo_reqwidth() - 4)
        visible = self._content_width > available
        if visible != self._arrows_visible:
            self._arrows_visible = visible
            if visible:
                self.left_button.grid()
                self.right_button.grid()
            else:
                self.left_button.grid_remove()
                self.right_button.grid_remove()
                self._cancel_drag_scroll()
        if not self._drag or not self._drag['active']:
            self.ensure_visible(self._selected)
        self._update_arrows()

    def _update_arrows(self):
        if not self._alive:
            return
        left = self.folder_canvas.canvasx(0)
        width = self.folder_canvas.winfo_width()
        self.left_button.state(['disabled'] if left <= .5 else ['!disabled'])
        self.right_button.state(['disabled'] if left + width >= self._content_width - .5 else ['!disabled'])

    def _cleanup(self):
        if not self._alive:
            return
        self._stop_drag()
        if self._overflow_after is not None:
            try:
                self.after_cancel(self._overflow_after)
            except tk.TclError:
                pass
            self._overflow_after = None
        self._alive = False
        try:
            self.fixed_canvas.delete('all')
            self.folder_canvas.delete('all')
        except tk.TclError:
            pass
        self._font = None

    def _destroyed(self, event):
        if event.widget is self:
            self._cleanup()

    def destroy(self):
        self._cleanup()
        super().destroy()
