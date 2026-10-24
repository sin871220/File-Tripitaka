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

from thumbnail_overlays import SIZE_SCALES, normalize_overlay_order, normalize_overlay_settings


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
        self.page_count = None
        self.overlays = normalize_overlay_settings()
        self.overlay_order = normalize_overlay_order()
        self.name = ''
        self.details = ''
        self._bindings = {}
        self._font = tkfont.Font(root=canvas, font=self.font)
        self._badge_font = tkfont.Font(root=canvas, family=self.font[0],
                                      size=max(17, abs(int(self.font[1])) + 4), weight='bold')
        self._page_font = tkfont.Font(root=canvas, family=self.font[0],
                                     size=max(10, abs(int(self.font[1]))), weight='bold')
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
        self.page_background_item = canvas.create_polygon(0, 0, 0, 0, 0, 0,
                                                          smooth=True, splinesteps=12,
                                                          state='hidden', tags=(self.tag,))
        self.page_item = canvas.create_text(0, 0, anchor='nw', state='hidden',
                                            tags=(self.tag,))
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
        self.canvas.itemconfigure(self.page_background_item, fill='#242830', outline='')
        self.canvas.itemconfigure(self.page_item, fill='#FFFFFF', font=self._page_font)

    def _apply_badge_font(self):
        base_size = max(17, abs(int(self.font[1])) + 4)
        scale = SIZE_SCALES[self.overlays['favorite']['size']]
        self._badge_font.configure(family=self.font[0], size=max(1, int(base_size * scale + .5)))

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
        self._render_overlays()

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
        self._render_overlays()

    def _render_folder(self):
        self._render_overlays()

    def _render_overlays(self):
        """Lay out corner groups as a unit, in the saved display order.

        Bounds are the thumbnail region, not the card's filename area. Bottom
        groups retain the same reading order while their entire stack is
        anchored to the bottom. All items are allocated once for recycling.
        """
        if not self.alive or self.geometry is None:
            return
        c = self.canvas
        for item in (self.badge_item, self.folder_item, self.page_background_item, self.page_item):
            c.itemconfigure(item, state='hidden')
        left, top, right, bottom = self._image_area
        left, top, right, bottom = left + 2, top + 2, right - 2, bottom - 2
        available_width, available_height = right - left, bottom - top
        if available_width < 1 or available_height < 1:
            return
        order = self.overlay_order
        active = {'favorite': self.favorite, 'folder': self.folder,
                  'pages': self.page_count is not None}
        dimensions = {}
        for kind, item in (('favorite', self.badge_item), ('pages', self.page_item)):
            if not active[kind] or not self.overlays[kind]['visible']:
                continue
            if kind == 'pages':
                c.itemconfigure(item, text=f'{self.page_count}P')
            c.itemconfigure(item, state='normal', anchor='nw')
            c.coords(item, 0, 0)
            box = c.bbox(item)
            c.itemconfigure(item, state='hidden')
            if box is not None:
                pad_x, pad_y = (8, 4) if kind == 'pages' else (0, 0)
                dimensions[kind] = (box[2] - box[0] + pad_x * 2,
                                    box[3] - box[1] + pad_y * 2)
        if self.folder and self.overlays['folder']['visible']:
            # Include the one-pixel vector outline in its allocation.
            scale = SIZE_SCALES[self.overlays['folder']['size']]
            dimensions['folder'] = (28 * scale + 2, 22 * scale + 2)
        dimensions = {kind: size for kind, size in dimensions.items()
                      if size[0] <= available_width and size[1] <= available_height}

        def arrange():
            placements = {}
            for position in ('top_left', 'top_right', 'bottom_left', 'bottom_right'):
                group = [kind for kind in order if kind in dimensions
                         and self.overlays[kind]['position'] == position]
                fitted, height = [], 0
                for kind in group:
                    needed = dimensions[kind][1] + (4 if fitted else 0)
                    if height + needed <= available_height:
                        fitted.append(kind)
                        height += needed
                y = top if position.startswith('top') else bottom - height
                for kind in fitted:
                    width, item_height = dimensions[kind]
                    x = left if position.endswith('left') else right - width
                    placements[kind] = (x, y, x + width, y + item_height)
                    y += item_height + 4
            return placements

        # On unusually small cards, independent corners can meet. Omit the
        # lower-priority marker and regroup rather than drawing on one another.
        placements = arrange()
        for _ in range(3):
            colliding = None
            present = [kind for kind in order if kind in placements]
            for index, first in enumerate(present):
                a = placements[first]
                for second in present[index + 1:]:
                    b = placements[second]
                    if a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]:
                        colliding = second
                        break
                if colliding is not None:
                    break
            if colliding is None:
                break
            dimensions.pop(colliding)
            placements = arrange()

        def place_text(item, x, y):
            c.itemconfigure(item, state='normal', anchor='nw')
            c.coords(item, x, y)
            box = c.bbox(item)
            if box is not None:
                c.move(item, x - box[0], y - box[1])

        for kind in order:
            if kind not in placements:
                continue
            x1, y1, x2, y2 = placements[kind]
            if kind == 'favorite':
                place_text(self.badge_item, x1, y1)
                c.tag_raise(self.badge_item)
            elif kind == 'folder':
                x, y = x1 + 1, y1 + 1
                scale = SIZE_SCALES[self.overlays['folder']['size']]
                c.coords(self.folder_item,
                         x, y, x + 10 * scale, y, x + 13 * scale, y + 4 * scale,
                         x + 28 * scale, y + 4 * scale,
                         x + 28 * scale, y + 22 * scale, x, y + 22 * scale)
                c.itemconfigure(self.folder_item, state='normal')
                c.tag_raise(self.folder_item)
            else:
                radius = min(10, (y2 - y1) / 2)
                c.coords(self.page_background_item,
                         x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
                         x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
                         x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1)
                c.itemconfigure(self.page_background_item, state='normal')
                c.tag_raise(self.page_background_item)
                place_text(self.page_item, x1 + 8, y1 + 4)
                c.tag_raise(self.page_item)

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
            self._apply_badge_font()
            self._page_font.configure(family=font[0], size=max(10, abs(int(font[1]))))
        self._apply_colors()
        if font_changed:
            self._layout_content()
        else:
            self._render_overlays()

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

    def set_overlays(self, options):
        options = normalize_overlay_settings(options)
        if self.alive and self.overlays != options:
            font_changed = self.overlays['favorite']['size'] != options['favorite']['size']
            self.overlays = options
            if font_changed:
                self._apply_badge_font()
            self._render_overlays()

    def set_overlay_order(self, order):
        order = normalize_overlay_order(order)
        if self.alive and self.overlay_order != order:
            self.overlay_order = order
            self._render_overlays()

    def set_page_count(self, count):
        # Unknown or failed previews have no count, rather than an invented 0P.
        try:
            value = int(count) if not isinstance(count, bool) else 0
            value = value if value > 0 else None
        except (ValueError, TypeError, OverflowError):
            value = None
        if self.alive and self.page_count != value:
            self.page_count = value
            self._render_overlays()

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
        self._page_font = None
        self.on_photo = None
