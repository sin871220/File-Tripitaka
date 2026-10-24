"""Gallery cards drawn entirely by a single canvas.

Canvas window items embed native child windows.  On Windows, moving those
windows while scrolling can leave stale strips of their old backing pixels.
These cards deliberately use only canvas rectangles, text and image items, so
the viewport and every part of a card are repainted together by Tk.
"""
from itertools import count
from tkinter import TclError
from tkinter import font as tkfont
import weakref

from PIL import Image, ImageTk


_card_ids = count()


class CardThumbnail:
    """Pixels and placeholder text belonging to one canvas gallery card."""

    def __init__(self, card):
        # Pending archive workers can outlive a recycled visible card.  They
        # may retain this handle, but must not retain its Tk canvas or fonts.
        self._card_ref = weakref.ref(card)
        self.archive_path = card.path
        self.photo = None
        self.text = '표지 읽는 중…'
        self._source = None
        self._revision = 0
        self._photo_key = None

    @property
    def card(self):
        return self._card_ref()

    @property
    def alive(self):
        card = self.card
        return card is not None and card.alive

    def exists(self):
        card = self.card
        try:
            return card is not None and card.alive and bool(card.canvas.winfo_exists())
        except TclError:
            return False

    def _set_photo(self, photo):
        if self.photo is photo:
            return
        self.photo = photo
        card = self.card
        if card is not None and card.on_photo is not None:
            card.on_photo(self, photo)

    def show_image(self, image, max_size):
        if not self.exists():
            return
        bounds = tuple(max(1, int(value)) for value in max_size)
        # Keep only a bounded source, rather than the decoded archive image.
        # Repeated layout/theme work must never recreate the same PhotoImage.
        # An explicit update may reuse a PIL object whose pixels changed in
        # place.  Only layout work is cached; every update gets fresh pixels.
        source = image.copy()
        source.thumbnail(bounds, Image.Resampling.LANCZOS)
        self._source = source
        self._revision += 1
        self.text = ''
        self.card._render_thumbnail()

    def show_error(self, text):
        if not self.exists():
            return
        self._source = None
        self._photo_key = None
        self.text = str(text)
        self.card.canvas.itemconfigure(self.card._image_item, image='', state='hidden')
        self._set_photo(None)
        self.card._render_thumbnail()

    def _clear(self):
        self._source = None
        self._photo_key = None
        self._set_photo(None)


class GalleryCard:
    """One card, identified by a unique tag shared by all its canvas items."""

    def __init__(self, canvas, path, x, y, width, height, palette, font, on_photo=None):
        self.canvas = canvas
        self.path = path
        self.palette = dict(palette)
        self.font = tuple(font)
        self.on_photo = on_photo
        self.tag = f'gallery-card-{next(_card_ids)}'
        self.alive = True
        self.geometry = None
        self.selected = False
        self.favorite = False
        self.folder = False
        self.name = ''
        self.details = ''
        self._bindings = {}
        self._font = tkfont.Font(root=canvas, font=self.font)
        self._badge_font = tkfont.Font(root=canvas, family=self.font[0],
                                      size=max(17, abs(int(self.font[1])) + 4), weight='bold')
        self.background = canvas.create_rectangle(0, 0, 0, 0, tags=(self.tag,))
        self._image_item = canvas.create_image(0, 0, anchor='center', state='hidden', tags=(self.tag,))
        self._placeholder_item = canvas.create_text(0, 0, anchor='n', justify='center',
                                                    state='hidden', tags=(self.tag,))
        self.title_item = canvas.create_text(0, 0, anchor='n', justify='center',
                                             state='hidden', tags=(self.tag,))
        self.info_item = canvas.create_text(0, 0, anchor='n', justify='center',
                                            state='hidden', tags=(self.tag,))
        self.badge_item = canvas.create_text(0, 0, text='★', anchor='ne', state='hidden',
                                             tags=(self.tag,))
        # A vector marker stays legible without depending on emoji/CJK glyphs.
        # Allocate it even for archives so toggling item kinds never churns the
        # virtual gallery's canvas items or its existing event bindings.
        self.folder_item = canvas.create_polygon(0, 0, 0, 0, 0, 0,
                                                  state='hidden', tags=(self.tag,))
        self.thumbnail = CardThumbnail(self)
        self._image_area = (0, 0, 1, 1)
        self._apply_colors()
        self.layout(x, y, width, height)

    def _apply_colors(self):
        p = self.palette
        self.canvas.itemconfigure(self.background, fill=p['field'],
                                  outline=p['accent'] if self.selected else p['border'],
                                  width=2 if self.selected else 1)
        for item in (self.title_item, self._placeholder_item):
            self.canvas.itemconfigure(item, fill=p['fg'], font=self._font)
        self.canvas.itemconfigure(self.info_item, fill=p['muted'], font=self._font)
        self.canvas.itemconfigure(self.badge_item, fill='#FFD21F', font=self._badge_font)
        self.canvas.itemconfigure(self.folder_item, fill='#F3C65D',
                                  outline=p['border'], width=1)

    def layout(self, x, y, width, height):
        if not self.alive:
            return
        geometry = (x, y, max(1, width), max(1, height))
        if self.geometry == geometry:
            return
        self.geometry = geometry
        self._layout_content()

    def _fit_text(self, item, text, width, height):
        """Fit actual Tk text bounds, preserving the unabridged public text."""
        self.canvas.itemconfigure(item, width=max(1, width - 2), state='normal')
        self.canvas.coords(item, 0, 0)

        def fits(value):
            self.canvas.itemconfigure(item, text=value)
            bounds = self.canvas.bbox(item)
            if bounds is None:
                return True, 0
            measured_height = bounds[3] - bounds[1]
            return bounds[2] - bounds[0] <= width and measured_height <= height, measured_height

        if not text or width < 3 or height < 1:
            self.canvas.itemconfigure(item, text='', state='hidden')
            return 0
        # File names are normally at most a few hundred characters.  Bound
        # pathological caller input before asking Tk to lay out its paragraphs.
        candidate = text if len(text) <= 8192 else text[:8192] + '…'
        valid, measured_height = fits(candidate)
        if valid:
            return measured_height
        valid, _ = fits('…')
        if not valid:
            self.canvas.itemconfigure(item, text='', state='hidden')
            return 0
        low, high = 0, min(len(text), 8192)
        while low < high:
            middle = (low + high + 1) // 2
            valid, _ = fits(text[:middle].rstrip() + '…')
            if valid:
                low = middle
            else:
                high = middle - 1
        _, measured_height = fits(text[:low].rstrip() + '…')
        return measured_height

    def _place_text(self, item, center, top):
        # Canvas text has small font-dependent bbox offsets.  Correct those
        # offsets so even a final line sits within its allocated rectangle.
        self.canvas.coords(item, center, top)
        bounds = self.canvas.bbox(item)
        if bounds is not None and bounds[1] != top:
            self.canvas.move(item, 0, top - bounds[1])

    def _layout_content(self):
        x, y, width, height = self.geometry
        c = self.canvas
        # The one-pixel overlap between adjacent cards is provided by App.
        c.coords(self.background, x, y, x + width - 1, y + height - 1)
        center = x + width / 2
        inner_height = max(0, height - 18)
        text_width = max(1, width - 30)
        line_height = self._font.metrics('linespace')
        # At most four name lines and two metadata lines.  Their combined
        # budget leaves at least roughly half the card for its cover image.
        info_budget = min(2 * line_height, int(inner_height * .18))
        name_budget = min(4 * line_height, int(inner_height * .34))
        info_height = self._fit_text(self.info_item, self.details, text_width, info_budget)
        name_height = self._fit_text(self.title_item, self.name, text_width, name_budget)
        bottom = y + height - 9
        if info_height:
            bottom -= info_height
            self._place_text(self.info_item, center, bottom)
        if name_height:
            bottom -= name_height
            self._place_text(self.title_item, center, bottom)
        cover_bottom = bottom - (8 if name_height or info_height else 0)
        self._image_area = (x + 8, y + 8, max(x + 8, x + width - 8),
                            max(y + 8, cover_bottom))
        self._render_thumbnail()
        self._render_folder()
        self._render_badge()

    def _render_thumbnail(self):
        if not self.alive or self.geometry is None:
            return
        c = self.canvas
        left, top, right, bottom = self._image_area
        width, height = max(0, int(right - left)), max(0, int(bottom - top))
        thumb = self.thumbnail
        if thumb._source is None:
            c.itemconfigure(self._image_item, image='', state='hidden')
            thumb._set_photo(None)
            self._fit_text(self._placeholder_item, thumb.text, width, height)
            bounds = c.bbox(self._placeholder_item)
            if bounds is not None:
                self._place_text(self._placeholder_item, (left + right) / 2,
                                 top + (height - (bounds[3] - bounds[1])) / 2)
            return
        c.itemconfigure(self._placeholder_item, text='', state='hidden')
        if width < 1 or height < 1:
            c.itemconfigure(self._image_item, image='', state='hidden')
            thumb._photo_key = None
            thumb._set_photo(None)
            return
        source = thumb._source
        factor = min(1, width / source.width, height / source.height)
        size = (max(1, min(width, int(source.width * factor))),
                max(1, min(height, int(source.height * factor))))
        key = (thumb._revision, size)
        if key != thumb._photo_key or thumb.photo is None:
            rendered = source if source.size == size else source.resize(size, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(rendered, master=c)
            c.itemconfigure(self._image_item, image=photo, state='normal')
            thumb._photo_key = key
            thumb._set_photo(photo)
        else:
            c.itemconfigure(self._image_item, state='normal')
        c.coords(self._image_item, (left + right) / 2, (top + bottom) / 2)

    def _render_badge(self):
        x, y, width, height = self.geometry
        self.canvas.coords(self.badge_item, x + width - 5, y + 3)
        self.canvas.itemconfigure(self.badge_item, state='normal' if self.favorite else 'hidden')
        bounds = self.canvas.bbox(self.badge_item)
        if bounds is not None and (bounds[0] < x + 1 or bounds[1] < y + 1
                                   or bounds[2] > x + width - 1 or bounds[3] > y + height - 1):
            self.canvas.itemconfigure(self.badge_item, state='hidden')
        self.canvas.tag_raise(self.badge_item)

    def _render_folder(self):
        if not self.alive or self.geometry is None:
            return
        x, y, width, height = self.geometry
        # Leave enough room at the other edge for the independent favorite
        # star. Tiny synthetic cards simply omit the optional type marker.
        visible = (self.folder and width >= 48 + self._badge_font.measure('★')
                   and height >= 35)
        self.canvas.itemconfigure(self.folder_item, state='normal' if visible else 'hidden')
        if visible:
            left, top = x + 8, y + 8
            self.canvas.coords(self.folder_item,
                               left, top + 3, left + 10, top + 3,
                               left + 13, top + 7, left + 28, top + 7,
                               left + 28, top + 22, left, top + 22)
            self.canvas.tag_raise(self.folder_item)

    def set_theme(self, palette, font):
        if not self.alive:
            return
        font = tuple(font)
        if self.palette == palette and self.font == font:
            return
        font_changed = self.font != font
        self.palette = dict(palette)
        self.font = font
        if font_changed:
            self._font.configure(family=font[0], size=font[1])
            self._badge_font.configure(family=font[0], size=max(17, abs(int(font[1])) + 4))
        self._apply_colors()
        if font_changed:
            self._layout_content()

    def set_selected(self, selected):
        selected = bool(selected)
        if self.alive and self.selected != selected:
            self.selected = selected
            self.canvas.itemconfigure(self.background,
                                      outline=self.palette['accent'] if selected else self.palette['border'],
                                      width=2 if selected else 1)

    def set_text(self, name, details):
        name, details = str(name), str(details)
        if self.alive and (self.name != name or self.details != details):
            self.name, self.details = name, details
            self._layout_content()

    def set_favorite(self, favorite):
        favorite = bool(favorite)
        if self.alive and self.favorite != favorite:
            self.favorite = favorite
            self._render_badge()

    def set_folder(self, folder):
        folder = bool(folder)
        if self.alive and self.folder != folder:
            self.folder = folder
            self._render_folder()

    def bind(self, sequence, callback):
        if not self.alive:
            return None
        previous = self._bindings.pop(sequence, None)
        if previous is not None:
            self.canvas.tag_unbind(self.tag, sequence, previous)
        funcid = self.canvas.tag_bind(self.tag, sequence, callback)
        self._bindings[sequence] = funcid
        return funcid

    def destroy(self):
        if not self.alive:
            return
        self.alive = False
        self.thumbnail._clear()
        for sequence, funcid in self._bindings.items():
            try:
                self.canvas.tag_unbind(self.tag, sequence, funcid)
            except TclError:
                pass  # The parent canvas may already be gone during shutdown.
        self._bindings.clear()
        try:
            self.canvas.delete(self.tag)
        except TclError:
            pass
        # Explicitly release Tcl-owned font names on the UI thread.  Letting a
        # pending archive handle own their last reference could otherwise run
        # tkinter.Font.__del__ from a worker's garbage collection.
        self._font = None
        self._badge_font = None
        self.on_photo = None
