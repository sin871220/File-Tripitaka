"""Non-destructive, asynchronous archive thumbnail selection dialog.

Coordinates stored by this editor are fractions of the EXIF-oriented image.
Archive access and Pillow decoding run in a worker; every Tk call stays on the
thread that created the dialog. The original archive is never modified.
"""
from concurrent.futures import CancelledError, ThreadPoolExecutor
import math
from pathlib import Path
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

import archive_core
from dialog_geometry import _workarea, center_dialog
from localization import translate as tr


THUMBNAIL_RATIO = 127 / 180
RATIO_LABELS = ('썸네일 비율 (127:180)', '자유 비율', '원본 비율')


def _clamp_box(box):
    # Arithmetic such as anchor - anchor / ratio * ratio can stray a tiny
    # fraction below zero at an image edge. Persist only strictly valid bounds.
    return tuple(min(1.0, max(0.0, value)) for value in box)


def valid_box(box):
    """Return a normalized rectangle or None for an invalid saved selection."""
    try:
        values = tuple(float(value) for value in box)
        if (len(values) == 4 and all(math.isfinite(value) for value in values)
                and 0 <= values[0] < values[2] <= 1
                and 0 <= values[1] < values[3] <= 1):
            return values
    except (TypeError, ValueError, OverflowError):
        pass
    return None


class ThumbnailEditor(tk.Toplevel):
    """Edit one of up to three thumbnail slots without changing source files.

    ``recipes`` is a saved slot-to-recipe dictionary, or a zero-argument callable
    resolved by the listing worker. ``load_image(data, max_size=..., box=...)``
    returns an oriented PIL image; by default archive_core.decode_preview is
    used. Persistence callbacks receive a completion callback that must be
    called on the Tk thread: ``on_apply(slot, entry, box, done)`` and
    ``on_reset(slot, done)``. ``done(error=None)`` reports success or failure.
    """

    def __init__(self, parent, path, palette, slots=1, sampling='순차 보기',
                 recipes=None, on_apply=None, on_reset=None, load_image=None):
        super().__init__(parent)
        self.withdraw()
        self.parent = parent
        self.path = Path(path)
        self.palette = palette
        self.slots = max(1, min(3, int(slots)))
        self.sampling = sampling
        self.recipes = {}
        self._recipe_source = recipes
        self.on_apply = on_apply
        self.on_reset = on_reset
        self.load_image = load_image or archive_core.decode_preview
        self.selection = None
        self.entries = []
        self._image = None
        self._data = None
        self._entry_index = 0
        self._slot = 0
        self._scale = 1.0
        self._offset = (0.0, 0.0)
        self._zoom = 1.0
        self._space_down = False
        self._drag = None
        self._busy = False
        self._closed = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=1,
                                            thread_name_prefix='thumbnail-editor')
        self._results = Queue()
        self._futures = {}
        self._source_generation = 0
        self._preview_generation = 0
        self._jobs = {}
        self._photo = None
        self._preview_photo = None
        self._preview_image = None
        self._zoom_setting = False
        self._slot_var = tk.StringVar(self, '1')
        self._entry_var = tk.StringVar(self)
        self._ratio_var = tk.StringVar(self, tr(RATIO_LABELS[1]))
        self._zoom_var = tk.DoubleVar(self, 100)
        self._status_var = tk.StringVar(self, tr('압축파일의 이미지를 불러오는 중…'))
        self._page_var = tk.StringVar(self)
        self._selection_var = tk.StringVar(self)
        self.ui_font = getattr(parent, 'ui_font', 'TkDefaultFont')
        # Keep the controls usable on smaller displays even when the browser's
        # card labels use very large text. The chosen CJK family is preserved.
        self.font_size = min(14, max(8, getattr(parent, 'font_size', 11)))
        self._font = (self.ui_font, self.font_size)
        self.title(tr('썸네일 영역 편집'))
        self.configure(background=palette['panel'])
        self.transient(parent)
        self.resizable(True, True)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self._build()
        self.bind('<Escape>', lambda _event: self.close())
        self.bind('<KeyPress-space>', self._space_press, add='+')
        self.bind('<KeyRelease-space>', self._space_release, add='+')
        self.bind('<FocusOut>', self._release_space, add='+')
        self.bind('<Destroy>', self._destroyed, add='+')
        self.update_idletasks()
        left, top, right, bottom = _workarea(parent)
        width = max(1, min(1120, right - left - 40))
        height = max(1, min(760, bottom - top - 70))
        control_width = max(row.winfo_reqwidth() for row in self._control_rows)
        self.minsize(min(max(760, control_width), width), min(510, height))
        center_dialog(self, parent, width, height)
        self.deiconify()
        self.grab_set()
        self.canvas.focus_set()
        self._schedule('poll', 40, self._poll)
        self._submit('listing', 0, self._read_listing, self._listed)

    def _build(self):
        p = self.palette
        style = ttk.Style(self)
        style.configure('ThumbnailEditor.TButton', font=self._font, padding=(8, 5))
        style.configure('ThumbnailEditor.TCombobox', font=self._font, padding=(6, 5))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        header = ttk.Frame(self, padding=(14, 12, 14, 7))
        header.grid(row=0, column=0, sticky='ew')
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text=tr('압축파일'), font=self._font).grid(
            row=0, column=0, padx=(0, 9))
        self._filename_var = tk.StringVar(self, self.path.name)
        self.filename_entry = ttk.Entry(header, textvariable=self._filename_var,
                                        state='readonly', font=self._font,
                                        exportselection=False)
        self.filename_entry.grid(row=0, column=1, sticky='ew')

        member = ttk.Frame(self, padding=(14, 0, 14, 7))
        member.grid(row=1, column=0, sticky='ew')
        member.columnconfigure(1, weight=1)
        self.previous_button = self._button(member, '◀ 이전 이미지',
                                            lambda: self.change_entry(-1))
        self.previous_button.grid(row=0, column=0, padx=(0, 7))
        self.entry_combo = ttk.Combobox(member, textvariable=self._entry_var,
                                        state='disabled', font=self._font,
                                        style='ThumbnailEditor.TCombobox')
        self.entry_combo.grid(row=0, column=1, sticky='ew')
        self.entry_combo.bind('<<ComboboxSelected>>', self._entry_selected)
        self.next_button = self._button(member, '다음 이미지 ▶',
                                        lambda: self.change_entry(1))
        self.next_button.grid(row=0, column=2, padx=(7, 0))
        ttk.Label(member, textvariable=self._page_var, font=self._font,
                  width=10, anchor='e').grid(row=0, column=3, padx=(7, 0))

        tools = ttk.Frame(self, padding=(14, 0, 14, 7))
        tools.grid(row=2, column=0, sticky='ew')
        ttk.Label(tools, text=tr('썸네일 위치'), font=self._font).grid(
            row=0, column=0, padx=(0, 6))
        self.slot_combo = ttk.Combobox(tools, textvariable=self._slot_var,
                                       values=[str(i + 1) for i in range(self.slots)],
                                       width=3, state='disabled', font=self._font,
                                       style='ThumbnailEditor.TCombobox')
        self.slot_combo.grid(row=0, column=1, padx=(0, 8))
        self.slot_combo.bind('<<ComboboxSelected>>', self._slot_selected)
        ttk.Label(tools, text=tr('1번은 오른쪽'), font=self._font,
                  foreground=p['muted']).grid(row=0, column=2, padx=(0, 18))
        self.ratio_combo = ttk.Combobox(tools, textvariable=self._ratio_var,
                                        values=[tr(label) for label in RATIO_LABELS],
                                        width=26, state='readonly', font=self._font,
                                        style='ThumbnailEditor.TCombobox')
        self.ratio_combo.grid(row=0, column=3, padx=(0, 8))
        self.ratio_combo.bind('<<ComboboxSelected>>', self._ratio_selected)
        self.full_button = self._button(tools, '전체 이미지', self.full_image)
        self.full_button.grid(row=0, column=4)
        self._control_rows = (header, member, tools)

        body = ttk.Frame(self, padding=(14, 0, 14, 0))
        body.grid(row=3, column=0, sticky='nsew')
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=210)
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(left, width=1, height=1, background=p['bg'],
                                highlightbackground=p['border'],
                                highlightcolor=p['accent'], highlightthickness=1,
                                cursor='crosshair', takefocus=True)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.canvas.bind('<Configure>', self._canvas_configured)
        self.canvas.bind('<ButtonPress-1>', self._pointer_down)
        self.canvas.bind('<B1-Motion>', self._pointer_drag)
        self.canvas.bind('<ButtonRelease-1>', self._pointer_up)
        self.canvas.bind('<Motion>', self._pointer_motion)
        for button in (2, 3):
            self.canvas.bind(f'<ButtonPress-{button}>', self._pan_down)
            self.canvas.bind(f'<B{button}-Motion>', self._pointer_drag)
            self.canvas.bind(f'<ButtonRelease-{button}>', self._pointer_up)
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.canvas.bind('<Button-4>', self._wheel)
        self.canvas.bind('<Button-5>', self._wheel)
        zoom = ttk.Frame(left, padding=(0, 7, 0, 0))
        zoom.grid(row=1, column=0, sticky='ew')
        zoom.columnconfigure(1, weight=1)
        self.zoom_label = ttk.Label(zoom, text='100%', font=self._font, width=6)
        self.zoom_label.grid(row=0, column=0)
        self.zoom_scale = ttk.Scale(zoom, from_=100, to=600,
                                    variable=self._zoom_var,
                                    command=self._zoom_changed)
        self.zoom_scale.grid(row=0, column=1, sticky='ew', padx=(5, 9))
        self.fit_button = self._button(zoom, '화면에 맞춤', self.fit_image)
        self.fit_button.grid(row=0, column=2)

        preview = ttk.Frame(body)
        preview.grid(row=0, column=1, sticky='nsew')
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(1, weight=1)
        ttk.Label(preview, text=tr('적용될 썸네일'), font=self._font).grid(
            row=0, column=0, sticky='w', pady=(0, 7))
        self.preview_canvas = tk.Canvas(preview, width=210, height=1,
                                        background=p['field'],
                                        highlightbackground=p['border'],
                                        highlightthickness=1)
        self.preview_canvas.grid(row=1, column=0, sticky='nsew')
        self.preview_canvas.bind('<Configure>', lambda _event: self._draw_preview())
        ttk.Label(preview, textvariable=self._selection_var, font=self._font,
                  foreground=p['muted'], wraplength=210).grid(
            row=2, column=0, sticky='w', pady=(7, 0))
        ttk.Label(preview, text=tr('드래그로 영역 선택 · 테두리로 크기 조절\n휠로 확대 · Space+드래그로 이동'),
                  font=self._font, foreground=p['muted'], wraplength=210,
                  justify='left').grid(row=3, column=0, sticky='w', pady=(7, 0))

        footer = ttk.Frame(self, padding=(14, 8, 14, 12))
        footer.grid(row=4, column=0, sticky='ew')
        footer.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(footer, textvariable=self._status_var,
                                       font=self._font, foreground=p['muted'],
                                       wraplength=1000, justify='left')
        self.status_label.grid(row=0, column=0, columnspan=3, sticky='w',
                                pady=(0, 8))
        footer.bind('<Configure>', lambda event: self.status_label.configure(
            wraplength=max(100, event.width - 10)))
        self.reset_button = self._button(footer, '자동 썸네일로 복원', self.reset_saved)
        self.reset_button.grid(row=1, column=0, sticky='w')
        self.apply_button = self._button(footer, '적용', self.apply)
        self.apply_button.grid(row=1, column=1, padx=(12, 7))
        self.cancel_button = self._button(footer, '닫기', self.close)
        self.cancel_button.grid(row=1, column=2)
        self._update_controls()

    def _button(self, parent, text, command):
        return ttk.Button(parent, text=tr(text), command=command,
                           style='ThumbnailEditor.TButton')

    def _schedule(self, name, milliseconds, callback):
        old = self._jobs.pop(name, None)
        if old:
            self.after_cancel(old)
        if self._closed.is_set():
            return
        def invoke():
            self._jobs.pop(name, None)
            if not self._closed.is_set():
                callback()
        self._jobs[name] = self.after(milliseconds, invoke)

    def _submit(self, kind, generation, work, callback):
        # Cancel obsolete work that has not started. A decoder already running
        # may finish, but its generation is checked before it touches the UI.
        for future, old_kind in tuple(self._futures.items()):
            if old_kind == kind:
                future.cancel()
        future = self._executor.submit(work)
        self._futures[future] = kind
        results, closed = self._results, self._closed
        def finished(done):
            if closed.is_set():
                return
            try:
                value, error = done.result(), None
            except CancelledError:
                value, error = None, CancelledError()
            except Exception as exc:
                value, error = None, exc
            results.put((done, kind, generation, callback, value, error))
        future.add_done_callback(finished)

    def _poll(self):
        while not self._closed.is_set():
            try:
                future, kind, generation, callback, value, error = self._results.get_nowait()
            except Empty:
                break
            self._futures.pop(future, None)
            if isinstance(error, CancelledError):
                continue
            if kind == 'source' and generation != self._source_generation:
                continue
            if kind == 'preview' and generation != (self._source_generation,
                                                    self._preview_generation):
                continue
            callback(value, error)
        self._schedule('poll', 40, self._poll)

    def _read_listing(self):
        recipes = self._recipe_source() if callable(self._recipe_source) else self._recipe_source
        return archive_core.image_entries(self.path), recipes or {}

    def _listed(self, value, error):
        if error:
            self._show_error(error)
            return
        self.entries, recipes = value
        self.recipes = {str(key): dict(recipe) for key, recipe in recipes.items()
                        if isinstance(recipe, dict)}
        self.slots = min(self.slots, len(self.entries))
        self.slot_combo.configure(values=[str(i + 1) for i in range(self.slots)])
        self.entry_combo.configure(values=[entry[0] for entry in self.entries])
        self._load_slot()

    def _slot_selected(self, _event=None):
        if not self._busy:
            self._slot = max(0, min(self.slots - 1, int(self._slot_var.get()) - 1))
            self._load_slot()

    def _load_slot(self):
        recipe = self.recipes.get(str(self._slot), {})
        names = [entry[0] for entry in self.entries]
        if recipe.get('entry') in names:
            index = names.index(recipe['entry'])
        else:
            indices = archive_core.preview_indices(len(self.entries), self.slots,
                                                    self.sampling)
            index = indices[self._slot]
        self._request_entry(index)

    def _entry_selected(self, _event=None):
        if not self._busy:
            index = self.entry_combo.current()
            if index >= 0:
                self._request_entry(index)

    def change_entry(self, step):
        if self.entries and not self._busy:
            index = max(0, min(len(self.entries) - 1, self._entry_index + step))
            if index != self._entry_index:
                self._request_entry(index)

    def _request_entry(self, index):
        self._source_generation += 1
        self._preview_generation += 1
        self._entry_index = index
        self.entry_combo.current(index)
        self._page_var.set(f'{index + 1} / {len(self.entries)}')
        self._image = self._data = self.selection = None
        self._preview_image = None
        self._preview_photo = None
        self.preview_canvas.delete('all')
        self._selection_var.set('')
        self._status_var.set(tr('이미지를 불러오는 중…'))
        self._drag = None
        self._update_controls()
        self._render()
        entry = self.entries[index]
        def read():
            data = archive_core.read_image_entry(self.path, entry)
            image = self.load_image(data, max_size=(1600, 1600))
            return data, image
        self._submit('source', self._source_generation, read, self._entry_loaded)

    def _entry_loaded(self, value, error):
        if error:
            self._show_error(error)
            return
        self._data, self._image = value
        recipe = self.recipes.get(str(self._slot), {})
        box = valid_box(recipe.get('box')) if recipe.get('entry') == self.entries[self._entry_index][0] else None
        if box:
            self.selection = box
            actual_ratio = ((box[2] - box[0]) * self._image.width
                            / ((box[3] - box[1]) * self._image.height))
            ratio = self._ratio()
            # Opening an edit starts in Free mode without reshaping the saved
            # rectangle. Keep an explicitly chosen lock only when it fits.
            if ratio is not None and abs(actual_ratio - ratio) >= .02:
                self._ratio_var.set(tr(RATIO_LABELS[1]))
        else:
            self.selection = self._default_selection()
        self._status_var.set(tr('영역을 고른 뒤 적용을 누르세요. 원본 파일은 변경되지 않습니다.'))
        self.fit_image()
        self._update_controls()
        self._selection_changed()

    def _show_error(self, error):
        self._status_var.set(tr('이미지를 불러오지 못했습니다.') + ' ' + tr(str(error)))
        self._update_controls()
        self._render()

    def _ratio(self):
        if self._ratio_var.get() == tr(RATIO_LABELS[1]):
            return None
        if self._ratio_var.get() == tr(RATIO_LABELS[2]):
            return self._image.width / self._image.height if self._image else None
        return THUMBNAIL_RATIO

    def _default_selection(self):
        if self._image is None:
            return None
        ratio = self._ratio()
        if ratio is None:
            return (0.0, 0.0, 1.0, 1.0)
        normalized_ratio = ratio * self._image.height / self._image.width
        width, height = min(1.0, normalized_ratio), min(1.0, 1 / normalized_ratio)
        return ((1 - width) / 2, (1 - height) / 2,
                (1 + width) / 2, (1 + height) / 2)

    def _ratio_selected(self, _event=None):
        if self._image is None or self._busy:
            return
        if self._ratio() is None:
            return
        # Fit the new aspect ratio around the current selection's center.
        old = self.selection or (0, 0, 1, 1)
        cx, cy = (old[0] + old[2]) / 2, (old[1] + old[3]) / 2
        ratio = self._ratio() * self._image.height / self._image.width
        width, height = old[2] - old[0], old[3] - old[1]
        if width / height > ratio:
            height = width / ratio
        else:
            width = height * ratio
        factor = min(1, 1 / width, 1 / height)
        width, height = width * factor, height * factor
        x = min(max(0, cx - width / 2), 1 - width)
        y = min(max(0, cy - height / 2), 1 - height)
        self.selection = _clamp_box((x, y, x + width, y + height))
        self._selection_changed()

    def full_image(self):
        if self._image is not None and not self._busy:
            self._ratio_var.set(tr(RATIO_LABELS[2]))
            self.selection = (0.0, 0.0, 1.0, 1.0)
            self._selection_changed()

    def _base_scale(self):
        if self._image is None:
            return 1.0
        width, height = max(1, self.canvas.winfo_width() - 32), max(1, self.canvas.winfo_height() - 32)
        return min(width / self._image.width, height / self._image.height)

    def fit_image(self):
        if self._image is None:
            return
        self._zoom = 1.0
        self._scale = self._base_scale()
        self._offset = ((self.canvas.winfo_width() - self._image.width * self._scale) / 2,
                        (self.canvas.winfo_height() - self._image.height * self._scale) / 2)
        self._set_zoom_widget()
        self._render()

    def _set_zoom_widget(self):
        self._zoom_setting = True
        self._zoom_var.set(self._zoom * 100)
        self.zoom_label.configure(text=f'{self._zoom * 100:.0f}%')
        self._zoom_setting = False

    def _zoom_changed(self, value):
        if not self._zoom_setting and self._image is not None and not self._busy:
            self._set_zoom(float(value) / 100)

    def _set_zoom(self, zoom, point=None):
        zoom = min(6, max(1, zoom))
        if self._image is None:
            return
        cx, cy = point or (self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2)
        old_scale = self._scale
        image_x, image_y = (cx - self._offset[0]) / old_scale, (cy - self._offset[1]) / old_scale
        self._zoom = zoom
        self._scale = self._base_scale() * zoom
        self._offset = (cx - image_x * self._scale, cy - image_y * self._scale)
        self._clamp_offset()
        self._set_zoom_widget()
        self._render()

    def _wheel(self, event):
        if self._image is not None and not self._busy:
            direction = 1 if getattr(event, 'num', None) == 4 or getattr(event, 'delta', 0) > 0 else -1
            self._set_zoom(self._zoom * (1.15 ** direction), (event.x, event.y))
        # The application's bind_all wheel handler must not move the gallery.
        return 'break'

    def _canvas_configured(self, _event=None):
        if self._image is not None:
            if self._zoom == 1:
                self.fit_image()
            else:
                self._scale = self._base_scale() * self._zoom
                self._clamp_offset()
        self._schedule('render', 20, self._render)

    def _clamp_offset(self):
        if self._image is None:
            return
        offsets = []
        for position, size, available in zip(self._offset,
                                             (self._image.width * self._scale,
                                              self._image.height * self._scale),
                                             (self.canvas.winfo_width(), self.canvas.winfo_height())):
            offsets.append((available - size) / 2 if size <= available - 32
                           else min(16, max(available - size - 16, position)))
        self._offset = tuple(offsets)

    def _to_image(self, x, y):
        return (min(1, max(0, (x - self._offset[0]) / (self._image.width * self._scale))),
                min(1, max(0, (y - self._offset[1]) / (self._image.height * self._scale))))

    def _to_canvas(self, x, y):
        return (self._offset[0] + x * self._image.width * self._scale,
                self._offset[1] + y * self._image.height * self._scale)

    def _handles(self):
        if not self.selection:
            return {}
        x1, y1 = self._to_canvas(*self.selection[:2])
        x2, y2 = self._to_canvas(*self.selection[2:])
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        return {'nw': (x1, y1), 'ne': (x2, y1), 'se': (x2, y2), 'sw': (x1, y2),
                'n': (cx, y1), 'e': (x2, cy), 's': (cx, y2), 'w': (x1, cy)}

    def _hit(self, x, y):
        for name, (hx, hy) in self._handles().items():
            if abs(x - hx) <= 8 and abs(y - hy) <= 8:
                return name
        if self.selection:
            ix, iy = self._to_image(x, y)
            x1, y1, x2, y2 = self.selection
            if x1 < ix < x2 and y1 < iy < y2:
                if (x1, y1, x2, y2) == (0, 0, 1, 1):
                    # A full-image box cannot move. Start a new region instead
                    # so the default Free mode supports a direct first drag.
                    return 'new'
                return 'move'
        return 'new'

    def _pointer_motion(self, event):
        if self._image is not None and not self._drag:
            hit = self._hit(event.x, event.y)
            cursor = 'fleur' if self._space_down or hit == 'move' else 'crosshair'
            self.canvas.configure(cursor=cursor)

    def _pointer_down(self, event):
        self.canvas.focus_set()
        if self._image is None or self._busy:
            return 'break'
        if self._space_down:
            return self._pan_down(event)
        x, y = self._to_image(event.x, event.y)
        self._drag = {'kind': self._hit(event.x, event.y), 'start': (x, y),
                      'box': self.selection, 'pointer': (event.x, event.y)}
        return 'break'

    def _pan_down(self, event):
        if self._image is not None and not self._busy:
            self.canvas.focus_set()
            self._drag = {'kind': 'pan', 'pointer': (event.x, event.y),
                          'offset': self._offset}
            self.canvas.configure(cursor='fleur')
        return 'break'

    def _pointer_drag(self, event):
        if not self._drag or self._image is None or self._busy:
            return 'break'
        drag = self._drag
        if drag['kind'] == 'pan':
            self._offset = (drag['offset'][0] + event.x - drag['pointer'][0],
                            drag['offset'][1] + event.y - drag['pointer'][1])
            self._clamp_offset()
            self._render()
            return 'break'
        point = self._to_image(event.x, event.y)
        kind, box = drag['kind'], drag['box']
        if kind == 'move' and box:
            dx = min(1 - box[2], max(-box[0], point[0] - drag['start'][0]))
            dy = min(1 - box[3], max(-box[1], point[1] - drag['start'][1]))
            new = (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)
        elif kind == 'new':
            new = self._rectangle(drag['start'], point)
        elif box:
            if len(kind) == 2:
                anchor = (box[2] if 'w' in kind else box[0],
                          box[3] if 'n' in kind else box[1])
                new = self._rectangle(anchor, point)
            else:
                new = self._edge_rectangle(kind, box, point)
        else:
            return 'break'
        new = _clamp_box(new)
        if valid_box(new) and (new[2] - new[0]) * self._image.width >= 1 and (new[3] - new[1]) * self._image.height >= 1:
            self.selection = new
            self._selection_changed()
        return 'break'

    def _rectangle(self, anchor, point):
        ax, ay = anchor
        dx, dy = point[0] - ax, point[1] - ay
        sx, sy = (-1 if dx < 0 else 1), (-1 if dy < 0 else 1)
        width, height = abs(dx), abs(dy)
        ratio = self._ratio()
        if ratio:
            ratio *= self._image.height / self._image.width
            width = max(width, height * ratio)
            height = width / ratio
            max_width, max_height = (ax if sx < 0 else 1 - ax), (ay if sy < 0 else 1 - ay)
            factor = min(1, max_width / max(width, 1e-12), max_height / max(height, 1e-12))
            width, height = width * factor, height * factor
        bx, by = ax + width * sx, ay + height * sy
        return _clamp_box((min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)))

    def _edge_rectangle(self, edge, box, point):
        x1, y1, x2, y2 = box
        ratio = self._ratio()
        if ratio is None:
            if edge == 'w':
                x1 = min(point[0], x2 - 1e-9)
            elif edge == 'e':
                x2 = max(point[0], x1 + 1e-9)
            elif edge == 'n':
                y1 = min(point[1], y2 - 1e-9)
            else:
                y2 = max(point[1], y1 + 1e-9)
            return _clamp_box((x1, y1, x2, y2))
        ratio *= self._image.height / self._image.width
        if edge in ('w', 'e'):
            cy = (y1 + y2) / 2
            anchor = x2 if edge == 'w' else x1
            width = max(1e-9, anchor - point[0] if edge == 'w' else point[0] - anchor)
            width = min(width, anchor if edge == 'w' else 1 - anchor,
                        2 * min(cy, 1 - cy) * ratio)
            height = width / ratio
            return _clamp_box((anchor - width if edge == 'w' else anchor, cy - height / 2,
                               anchor if edge == 'w' else anchor + width, cy + height / 2))
        cx = (x1 + x2) / 2
        anchor = y2 if edge == 'n' else y1
        height = max(1e-9, anchor - point[1] if edge == 'n' else point[1] - anchor)
        height = min(height, anchor if edge == 'n' else 1 - anchor,
                     2 * min(cx, 1 - cx) / ratio)
        width = height * ratio
        return _clamp_box((cx - width / 2, anchor - height if edge == 'n' else anchor,
                           cx + width / 2, anchor if edge == 'n' else anchor + height))

    def _pointer_up(self, _event=None):
        self._drag = None
        self.canvas.configure(cursor='fleur' if self._space_down else 'crosshair')
        return 'break'

    def _space_press(self, event):
        if event.widget is self.canvas:
            self._space_down = True
            self.canvas.configure(cursor='fleur')
            return 'break'

    def _space_release(self, event):
        if self._space_down:
            self._space_down = False
            self.canvas.configure(cursor='crosshair')
            return 'break'

    def _release_space(self, _event=None):
        self._space_down = False

    def _selection_changed(self):
        if not self.selection or self._image is None:
            return
        x1, y1, x2, y2 = self.selection
        self._selection_var.set(f'{(x2 - x1) * 100:.1f}% × {(y2 - y1) * 100:.1f}%')
        self._render()
        self._preview_generation += 1
        self._schedule('preview', 160, self._request_preview)

    def _request_preview(self):
        if self._data is None or not self.selection:
            return
        data, box = self._data, self.selection
        generation = (self._source_generation, self._preview_generation)
        def decode():
            return self.load_image(data, max_size=(320, 340), box=box)
        self._submit('preview', generation, decode, self._preview_loaded)

    def _preview_loaded(self, value, error):
        if error:
            self._status_var.set(tr('선택 영역 미리보기를 불러오지 못했습니다.') + ' ' + tr(str(error)))
            return
        self._preview_image = value
        self._draw_preview()

    def _draw_preview(self):
        if self._closed.is_set():
            return
        self.preview_canvas.delete('all')
        if self._preview_image is None:
            return
        width, height = max(1, self.preview_canvas.winfo_width() - 14), max(1, self.preview_canvas.winfo_height() - 14)
        frame_h = min(height, width / THUMBNAIL_RATIO)
        frame_w, frame_h = max(1, round(frame_h * THUMBNAIL_RATIO)), max(1, round(frame_h))
        copy = self._preview_image.copy()
        copy.thumbnail((frame_w, frame_h), Image.Resampling.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(copy, master=self)
        cx, cy = self.preview_canvas.winfo_width() / 2, self.preview_canvas.winfo_height() / 2
        self.preview_canvas.create_rectangle(cx - frame_w / 2, cy - frame_h / 2,
                                               cx + frame_w / 2, cy + frame_h / 2,
                                               outline=self.palette['border'])
        self.preview_canvas.create_image(cx, cy, image=self._preview_photo)

    def _render(self):
        if self._closed.is_set():
            return
        self.canvas.delete('all')
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        if self._image is None:
            self.canvas.create_text(width / 2, height / 2, text=tr('미리보기'),
                                    fill=self.palette['muted'], font=self._font)
            return
        # Render only the visible viewport. A 600% zoom of a tall page must not
        # allocate a huge, mostly invisible enlarged image.
        ox, oy = self._offset
        viewport = self._image.convert('RGB').transform(
            (width, height), Image.Transform.AFFINE,
            (1 / self._scale, 0, -ox / self._scale,
             0, 1 / self._scale, -oy / self._scale),
            Image.Resampling.BILINEAR, fillcolor=self.palette['bg'])
        self._photo = ImageTk.PhotoImage(viewport, master=self)
        self.canvas.create_image(0, 0, image=self._photo, anchor='nw')
        if not self.selection:
            return
        x1, y1 = self._to_canvas(*self.selection[:2])
        x2, y2 = self._to_canvas(*self.selection[2:])
        # Stipple is supported by both Windows and macOS Tk and avoids platform
        # transparency differences in canvas rectangles.
        for rectangle in ((0, 0, width, max(0, y1)),
                          (0, min(height, y2), width, height),
                          (0, max(0, y1), max(0, x1), min(height, y2)),
                          (min(width, x2), max(0, y1), width, min(height, y2))):
            if rectangle[2] > rectangle[0] and rectangle[3] > rectangle[1]:
                self.canvas.create_rectangle(*rectangle, fill='#000000',
                                              stipple='gray50', width=0)
        self.canvas.create_rectangle(x1, y1, x2, y2,
                                      outline=self.palette['accent'], width=2)
        for hx, hy in self._handles().values():
            self.canvas.create_rectangle(hx - 4, hy - 4, hx + 4, hy + 4,
                                          fill='#FFFFFF', outline=self.palette['accent'])

    def _update_controls(self):
        loaded = self._image is not None and not self._busy
        available = bool(self.entries) and not self._busy
        self.slot_combo.configure(state='readonly' if available and self.slots > 1 else 'disabled')
        self.entry_combo.configure(state='readonly' if available else 'disabled')
        for button, enabled in ((self.previous_button, available and self._entry_index > 0),
                                (self.next_button, available and self._entry_index < len(self.entries) - 1),
                                (self.apply_button, loaded and self.on_apply is not None),
                                (self.full_button, loaded), (self.fit_button, loaded),
                                (self.reset_button, available and str(self._slot) in self.recipes
                                 and self.on_reset is not None)):
            button.state(['!disabled'] if enabled else ['disabled'])
        self.ratio_combo.configure(state='readonly' if loaded else 'disabled')
        self.zoom_scale.state(['!disabled'] if loaded else ['disabled'])

    def apply(self):
        box = valid_box(self.selection)
        if self._busy or not box or self._image is None or self.on_apply is None:
            return
        slot, entry = self._slot, self.entries[self._entry_index][0]
        self._busy = True
        self._status_var.set(tr('썸네일 편집 내용을 저장하는 중…'))
        self._update_controls()
        def done(error=None):
            if self._closed.is_set():
                return
            self._busy = False
            if error:
                self._status_var.set(tr('썸네일 편집 내용을 저장하지 못했습니다.') + ' ' + tr(str(error)))
            else:
                self.recipes[str(slot)] = {'entry': entry, 'box': list(box)}
                self._status_var.set(tr('썸네일 편집 내용을 저장했습니다.'))
            self._update_controls()
        try:
            self.on_apply(slot, entry, list(box), done)
        except Exception as error:
            done(error)

    def reset_saved(self):
        if self._busy or str(self._slot) not in self.recipes or self.on_reset is None:
            return
        slot = self._slot
        self._busy = True
        self._status_var.set(tr('자동 썸네일로 복원하는 중…'))
        self._update_controls()
        def done(error=None):
            if self._closed.is_set():
                return
            self._busy = False
            if error:
                self._status_var.set(tr('자동 썸네일로 복원하지 못했습니다.') + ' ' + tr(str(error)))
                self._update_controls()
            else:
                self.recipes.pop(str(slot), None)
                self._load_slot()
        try:
            self.on_reset(slot, done)
        except Exception as error:
            done(error)

    def _shutdown(self):
        if self._closed.is_set():
            return
        self._closed.set()
        for job in self._jobs.values():
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._jobs.clear()
        for future in self._futures:
            future.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._futures.clear()
        while True:
            try:
                self._results.get_nowait()
            except Empty:
                break

    def _destroyed(self, event):
        if event.widget is self:
            self._shutdown()

    def close(self):
        if not self._closed.is_set():
            self._shutdown()
            try:
                if self.grab_current() is self:
                    self.grab_release()
            except tk.TclError:
                pass
            self.destroy()
