"""Native Tk checks for the single-surface gallery renderer.

Use ``python tests/gallery_card_smoke.py`` on a desktop with Tk available. All
images and file names are synthetic; no user library or saved settings is read.
"""
import gc
from itertools import permutations
from pathlib import Path
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
import unittest
import weakref
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gallery_card import GalleryCard
from PIL import Image, ImageDraw, ImageTk
from preferences import PALETTES
from thumbnail_overlays import SIZE_SCALES, normalize_overlay_settings


class GalleryCardSmoke(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('860x680+40+40')
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.canvas = tk.Canvas(self.root, highlightthickness=0, background='#171B23')
        self.canvas.pack(fill='both', expand=True)
        self.root.update()
        self.photos = []
        self.path = Path('synthetic-library/Archive-001.cbz')
        self.card = GalleryCard(self.canvas, self.path, 20, 30, 240, 340,
                                PALETTES['다크'], ('TkDefaultFont', 11),
                                on_photo=lambda thumbnail, photo: self.photos.append((thumbnail, photo)))
        self.root.update()
        self.addCleanup(self.close)

    def close(self):
        self.card.destroy()
        self.root.destroy()
        self.assertFalse(self.errors, self.errors)

    def items(self):
        return self.canvas.find_withtag(self.card.tag)

    def assert_inside(self, card=None):
        card = card or self.card
        x, y, width, height = card.geometry
        for item in self.canvas.find_withtag(card.tag):
            box = self.canvas.bbox(item)
            if box is None:
                continue
            self.assertGreaterEqual(box[0], x - 2, (self.canvas.type(item), box))
            self.assertGreaterEqual(box[1], y - 2, (self.canvas.type(item), box))
            self.assertLessEqual(box[2], x + width + 2, (self.canvas.type(item), box))
            self.assertLessEqual(box[3], y + height + 2, (self.canvas.type(item), box))

    def test_all_content_uses_canvas_items_without_native_child_windows(self):
        self.card.set_text('Archive-001.cbz', '12.0 MB · 2026-10-19')
        self.card.set_favorite(True)
        self.card.thumbnail.show_image(Image.new('RGB', (127, 180), '#3080d0'), (220, 250))
        self.root.update_idletasks()
        self.assertEqual(self.canvas.winfo_children(), [])
        types = {self.canvas.type(item) for item in self.items()}
        self.assertTrue({'rectangle', 'image', 'text'}.issubset(types), types)
        self.assertNotIn('window', types)
        self.assertEqual(set(self.canvas.find_all()), set(self.items()))
        self.assertEqual(self.canvas.type(self.card.background), 'rectangle')
        self.assertEqual(self.canvas.type(self.card.title_item), 'text')
        self.assertEqual(self.canvas.type(self.card.info_item), 'text')
        self.assertEqual(self.canvas.type(self.card.badge_item), 'text')
        self.assertEqual(self.card.thumbnail.archive_path, self.path)
        self.assert_inside()

    def test_text_wraps_and_keeps_metadata_and_image_inside_its_card(self):
        self.card.layout(20, 30, 180, 340)
        name = 'A synthetic archive title that wraps across several words.cbz'
        details = '12.0 MB · 2026-10-19'
        self.card.set_text(name, details)
        self.card.thumbnail.show_image(Image.new('RGB', (600, 900), '#30c090'), (160, 240))
        self.root.update_idletasks()
        self.assertEqual(self.card.name, name)
        self.assertEqual(self.card.details, details)
        title_box = self.canvas.bbox(self.card.title_item)
        info_box = self.canvas.bbox(self.card.info_item)
        line_height = tkfont.Font(root=self.root, font=self.canvas.itemcget(
            self.card.title_item, 'font')).metrics('linespace')
        self.assertIsNotNone(title_box)
        self.assertGreater(title_box[3] - title_box[1], line_height)
        self.assertLessEqual(title_box[3], info_box[1] + 1)
        for item in self.items():
            if self.canvas.type(item) == 'image':
                image_box = self.canvas.bbox(item)
                if image_box:
                    self.assertLessEqual(image_box[3], title_box[1] + 1)
        self.assert_inside()
        self.card.set_text('', '')
        self.root.update_idletasks()
        self.assertEqual((self.card.name, self.card.details), ('', ''))
        for item in (self.card.title_item, self.card.info_item):
            self.assertTrue(self.canvas.itemcget(item, 'state') == 'hidden'
                            or not self.canvas.itemcget(item, 'text'))
        self.assert_inside()

    def test_selection_favorite_and_theme_remain_independent(self):
        card = self.card
        card.set_text('Archive-001.cbz', '12.0 MB')
        card.set_selected(True)
        card.set_favorite(True)
        self.assertTrue(card.selected)
        self.assertTrue(card.favorite)
        self.assertEqual(self.canvas.itemcget(card.background, 'outline'), PALETTES['다크']['accent'])
        self.assertEqual(self.canvas.itemcget(card.badge_item, 'text'), '★')
        self.assertNotEqual(self.canvas.itemcget(card.badge_item, 'state'), 'hidden')
        for name, palette in PALETTES.items():
            with self.subTest(theme=name):
                card.set_theme(palette, ('TkDefaultFont', 13))
                self.root.update_idletasks()
                self.assertEqual(self.canvas.itemcget(card.background, 'fill'), palette['field'])
                self.assertEqual(self.canvas.itemcget(card.background, 'outline'), palette['accent'])
                self.assertEqual(self.canvas.itemcget(card.title_item, 'fill'), palette['fg'])
                self.assertEqual(self.canvas.itemcget(card.info_item, 'fill'), palette['muted'])
                self.assertTrue(card.selected)
                self.assertTrue(card.favorite)
                self.assert_inside()
        card.set_selected(False)
        card.set_favorite(False)
        self.assertFalse(card.selected)
        self.assertFalse(card.favorite)
        self.assertEqual(self.canvas.itemcget(card.background, 'outline'), PALETTES['블루']['border'])
        self.assertTrue(self.canvas.itemcget(card.badge_item, 'state') == 'hidden'
                        or not self.canvas.itemcget(card.badge_item, 'text'))
        self.assertEqual(self.canvas.winfo_children(), [])

    def test_folder_marker_is_vector_local_and_independent_of_favorite(self):
        card = self.card
        card.set_text('Image folder', '12.0 MB')
        card.thumbnail.show_image(Image.new('RGB', (127, 180), '#3080d0'), (220, 260))
        items = self.items()
        image_area = card._image_area
        photo = card.thumbnail.photo
        self.assertEqual(self.canvas.itemcget(card.folder_item, 'state'), 'hidden')
        self.assertEqual(self.canvas.type(card.folder_item), 'polygon')
        card.set_folder(True)
        card.set_favorite(True)
        for name, palette in PALETTES.items():
            with self.subTest(theme=name):
                card.set_theme(palette, ('TkDefaultFont', 13))
                self.root.update_idletasks()
                folder = self.canvas.bbox(card.folder_item)
                favorite = self.canvas.bbox(card.badge_item)
                self.assertIsNotNone(folder)
                self.assertIsNotNone(favorite)
                self.assertLess(folder[2], favorite[0])
                self.assertEqual(self.canvas.itemcget(card.folder_item, 'outline'), palette['border'])
                self.assertTrue(card.folder)
                self.assertTrue(card.favorite)
                self.assert_inside()
        # The marker can be toggled without allocating image or canvas items.
        card.set_theme(PALETTES['다크'], ('TkDefaultFont', 11))
        self.assertEqual(card._image_area, image_area)
        self.assertIs(card.thumbnail.photo, photo)
        with patch.object(self.canvas, 'coords', wraps=self.canvas.coords) as coords, \
                patch.object(self.canvas, 'itemconfigure', wraps=self.canvas.itemconfigure) as configure:
            card.set_folder(True)
            coords.assert_not_called()
            configure.assert_not_called()
        card.set_folder(False)
        self.assertFalse(card.folder)
        self.assertEqual(self.canvas.itemcget(card.folder_item, 'state'), 'hidden')
        self.assertNotEqual(self.canvas.itemcget(card.badge_item, 'state'), 'hidden')
        self.assertEqual(set(self.items()), set(items))
        self.assertEqual(self.canvas.winfo_children(), [])

    def test_folder_marker_click_uses_card_selection_and_tiny_cards_hide_it(self):
        selected = []
        self.card.set_folder(True)
        self.card.bind('<Button-1>', lambda event: selected.append(self.path))
        self.root.update()
        box = self.canvas.bbox(self.card.folder_item)
        x, y = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
        self.canvas.event_generate('<Motion>', x=x, y=y)
        self.canvas.event_generate('<ButtonPress-1>', x=x, y=y)
        self.canvas.event_generate('<ButtonRelease-1>', x=x, y=y)
        self.root.update()
        self.assertEqual(selected, [self.path])
        items = self.items()
        self.card.layout(20, 30, 45, 25)
        self.assertEqual(self.canvas.itemcget(self.card.folder_item, 'state'), 'hidden')
        self.card.layout(20, 30, 240, 340)
        self.assertNotEqual(self.canvas.itemcget(self.card.folder_item, 'state'), 'hidden')
        self.assertEqual(set(self.items()), set(items))
        self.assert_inside()

    def test_same_corner_stacks_star_folder_pages_in_reading_order(self):
        card = self.card
        card.set_text('Image folder', '12.0 MB')
        card.set_folder(True)
        card.set_favorite(True)
        card.set_page_count(30)
        for position in ('top_left', 'top_right', 'bottom_left', 'bottom_right'):
            with self.subTest(position=position):
                options = normalize_overlay_settings()
                for value in options.values():
                    value['position'] = position
                card.set_overlays(options)
                self.root.update_idletasks()
                boxes = [self.canvas.bbox(item) for item in (
                    card.badge_item, card.folder_item, card.page_background_item)]
                self.assertTrue(all(boxes))
                for first, second in zip(boxes, boxes[1:]):
                    self.assertLess(first[3], second[1], boxes)
                left, top, right, bottom = card._image_area
                for box in boxes:
                    self.assertGreaterEqual(box[0], left)
                    self.assertGreaterEqual(box[1], top)
                    self.assertLessEqual(box[2], right)
                    self.assertLessEqual(box[3], bottom)
                if position.startswith('top'):
                    self.assertLessEqual(boxes[0][1] - top, 4)
                else:
                    self.assertLessEqual(bottom - boxes[-1][3], 4)
                self.assertEqual(self.canvas.itemcget(card.page_item, 'text'), '30P')
                self.assert_inside()

    def test_hidden_or_inapplicable_overlays_leave_no_stack_gap(self):
        card = self.card
        options = normalize_overlay_settings()
        for value in options.values():
            value['position'] = 'top_right'
        card.set_overlays(options)
        card.set_folder(True)
        card.set_favorite(True)
        card.set_page_count(321)
        star_top = self.canvas.bbox(card.badge_item)[1]
        folder_top = self.canvas.bbox(card.folder_item)[1]
        card.set_favorite(False)  # Favorites tab deliberately passes false.
        self.assertEqual(self.canvas.itemcget(card.badge_item, 'state'), 'hidden')
        # Tk's polygon stroke bbox may extend a pixel beyond its allocated
        # edge; removing the star still promotes the folder to that first row.
        promoted_top = self.canvas.bbox(card.folder_item)[1]
        self.assertLess(promoted_top, folder_top)
        self.assertLessEqual(abs(promoted_top - star_top), 1)
        card.set_folder(False)  # Archive cards have no folder marker.
        self.assertEqual(self.canvas.itemcget(card.folder_item, 'state'), 'hidden')
        self.assertLessEqual(abs(self.canvas.bbox(card.page_background_item)[1] - star_top), 1)
        options['pages']['visible'] = False
        card.set_overlays(options)
        for item in (card.page_item, card.page_background_item):
            self.assertEqual(self.canvas.itemcget(item, 'state'), 'hidden')
        card.set_favorite(True)
        options['favorite']['visible'] = False
        card.set_overlays(options)
        self.assertTrue(card.favorite)
        self.assertEqual(self.canvas.itemcget(card.badge_item, 'state'), 'hidden')
        card.set_page_count(None)
        options['pages']['visible'] = True
        card.set_overlays(options)
        self.assertEqual(self.canvas.itemcget(card.page_item, 'state'), 'hidden')

    def test_custom_order_applies_to_all_corners_and_keeps_bottom_groups_anchored(self):
        card = self.card
        card.set_folder(True)
        card.set_favorite(True)
        card.set_page_count(30)
        items = {'favorite': card.badge_item, 'folder': card.folder_item,
                 'pages': card.page_background_item}
        for order in permutations(items):
            for position in ('top_left', 'top_right', 'bottom_left', 'bottom_right'):
                with self.subTest(order=order, position=position):
                    options = normalize_overlay_settings()
                    for value in options.values():
                        value['position'] = position
                    card.set_overlays(options)
                    card.set_overlay_order(order)
                    boxes = [self.canvas.bbox(items[kind]) for kind in order]
                    self.assertTrue(all(boxes))
                    for first, second in zip(boxes, boxes[1:]):
                        self.assertLess(first[3], second[1], boxes)
                        self.assertLessEqual(second[1] - first[3], 6, boxes)
                    left, top, right, bottom = card._image_area
                    for box in boxes:
                        self.assertGreaterEqual(box[0], left)
                        self.assertGreaterEqual(box[1], top)
                        self.assertLessEqual(box[2], right)
                        self.assertLessEqual(box[3], bottom)
                    if position.startswith('top'):
                        self.assertLessEqual(boxes[0][1] - top, 4)
                    else:
                        self.assertLessEqual(bottom - boxes[-1][3], 4)

    def test_reordering_retains_images_items_and_hiding_middle_closes_its_gap(self):
        card = self.card
        card.thumbnail.show_image(Image.new('RGB', (127, 180), '#3080d0'), (220, 260))
        card.set_folder(True)
        card.set_favorite(True)
        card.set_page_count(30)
        options = normalize_overlay_settings()
        for value in options.values():
            value['position'] = 'top_right'
        card.set_overlays(options)
        items, photo = self.items(), card.thumbnail.photo
        with patch.object(ImageTk, 'PhotoImage', wraps=ImageTk.PhotoImage) as images:
            requested = ['pages', 'favorite', 'folder']
            card.set_overlay_order(requested)
            requested.reverse()  # The live card must not retain a mutable draft.
            self.assertEqual(card.overlay_order, ['pages', 'favorite', 'folder'])
            folder_before = self.canvas.bbox(card.folder_item)
            card.set_favorite(False)
            page = self.canvas.bbox(card.page_background_item)
            folder = self.canvas.bbox(card.folder_item)
            self.assertLess(folder[1], folder_before[1])
            self.assertLess(page[3], folder[1])
            self.assertLessEqual(folder[1] - page[3], 6)
            self.assertEqual(self.canvas.itemcget(card.badge_item, 'state'), 'hidden')
            images.assert_not_called()
        self.assertIs(card.thumbnail.photo, photo)
        # Reordering raises existing markers into their new paint order.
        self.assertEqual(set(self.items()), set(items))
        self.assertEqual(self.canvas.winfo_children(), [])
        self.assert_inside()

    def test_star_and_folder_sizes_are_independent_and_keep_existing_large_geometry(self):
        card = self.card
        card.set_folder(True)
        card.set_favorite(True)
        card.set_page_count(30)
        card.thumbnail.show_image(Image.new('RGB', (127, 180), '#3080d0'), (220, 260))
        photo, items = card.thumbnail.photo, set(self.items())
        badge_font, page_font = card._badge_font, card._page_font
        page_box = self.canvas.bbox(card.page_background_item)
        fonts = set(tkfont.names(root=self.root))
        options = normalize_overlay_settings()
        base_size = max(17, abs(int(card.font[1])) + 4)
        for star_size in ('large', 'medium', 'small'):
            for folder_size in ('large', 'medium', 'small'):
                with self.subTest(star_size=star_size, folder_size=folder_size):
                    options['favorite']['size'] = star_size
                    options['folder']['size'] = folder_size
                    with patch.object(ImageTk, 'PhotoImage', wraps=ImageTk.PhotoImage) as images:
                        card.set_overlays(options)
                        images.assert_not_called()
                    self.assertEqual(int(badge_font.cget('size')),
                                     max(1, int(base_size * SIZE_SCALES[star_size] + .5)))
                    coords = self.canvas.coords(card.folder_item)
                    self.assertAlmostEqual(max(coords[::2]) - min(coords[::2]),
                                           28 * SIZE_SCALES[folder_size])
                    self.assertAlmostEqual(max(coords[1::2]) - min(coords[1::2]),
                                           22 * SIZE_SCALES[folder_size])
                    self.assertIs(card._badge_font, badge_font)
                    self.assertIs(card._page_font, page_font)
                    self.assertEqual(self.canvas.bbox(card.page_background_item), page_box)
                    self.assertEqual(set(tkfont.names(root=self.root)), fonts)
                    self.assertIs(card.thumbnail.photo, photo)
                    self.assertEqual(set(self.items()), items)
                    self.assert_inside()

    def test_custom_sizes_keep_stacks_inside_every_corner_after_font_and_theme_changes(self):
        card = self.card
        card.set_folder(True)
        card.set_favorite(True)
        card.set_page_count(30)
        card.set_overlay_order(['pages', 'folder', 'favorite'])
        options = normalize_overlay_settings()
        for size in ('large', 'medium', 'small'):
            options['favorite']['size'] = size
            options['folder']['size'] = size
            for theme, palette in PALETTES.items():
                for family, font_size in (('TkDefaultFont', 8), ('Courier', 24)):
                    card.set_theme(palette, (family, font_size))
                    for position in ('top_left', 'top_right', 'bottom_left', 'bottom_right'):
                        with self.subTest(size=size, theme=theme, family=family, position=position):
                            for value in options.values():
                                value['position'] = position
                            card.set_overlays(options)
                            self.assertEqual(card._badge_font.cget('family'), family)
                            self.assertEqual(int(card._badge_font.cget('size')),
                                             max(1, int(max(17, font_size + 4) * SIZE_SCALES[size] + .5)))
                            boxes = [self.canvas.bbox(item) for item in
                                     (card.page_background_item, card.folder_item, card.badge_item)]
                            self.assertTrue(all(boxes))
                            for first, second in zip(boxes, boxes[1:]):
                                self.assertLess(first[3], second[1], boxes)
                            left, top, right, bottom = card._image_area
                            for box in boxes:
                                self.assertGreaterEqual(box[0], left)
                                self.assertGreaterEqual(box[1], top)
                                self.assertLessEqual(box[2], right)
                                self.assertLessEqual(box[3], bottom)
                            self.assert_inside()

    def test_page_badge_is_one_group_count_and_updates_without_new_images(self):
        card = self.card
        card.thumbnail.show_image(Image.new('RGB', (381, 180), '#3080d0'), (660, 260))
        photo = card.thumbnail.photo
        items = self.items()
        for previews in (1, 2, 3):
            card.layout(20, 30, 240 * previews, 340)
            stable_photo = card.thumbnail.photo
            card.set_page_count(30)
            self.assertEqual(self.canvas.itemcget(card.page_item, 'text'), '30P')
            self.assertEqual(sum(self.canvas.itemcget(item, 'text') == '30P'
                                 for item in self.items() if self.canvas.type(item) == 'text'), 1)
            options = normalize_overlay_settings()
            options['pages']['position'] = 'bottom_left'
            with patch.object(ImageTk, 'PhotoImage', wraps=ImageTk.PhotoImage) as image:
                card.set_overlays(options)
                card.set_page_count(41)
                card.set_favorite(True)
                card.set_folder(True)
                image.assert_not_called()
            self.assertIs(card.thumbnail.photo, stable_photo)
            self.assertEqual(set(self.items()), set(items))
            self.assert_inside()
        self.assertIsNotNone(photo)
        self.assertEqual(self.canvas.winfo_children(), [])

    def test_overlays_fit_the_thumbnail_after_large_fonts_resize_and_theme(self):
        card = self.card
        card.set_text('Synthetic image folder with a name', '12.0 MB · 2026-10-24')
        card.set_folder(True)
        card.set_favorite(True)
        card.set_page_count(123456)
        options = normalize_overlay_settings()
        for value in options.values():
            value['position'] = 'bottom_right'
        card.set_overlays(options)
        for font_size in (8, 24):
            for name, palette in PALETTES.items():
                for width, height in ((240, 340), (120, 180), (45, 25)):
                    with self.subTest(font_size=font_size, theme=name, size=(width, height)):
                        card.set_theme(palette, ('TkDefaultFont', font_size))
                        card.layout(20, 30, width, height)
                        self.root.update_idletasks()
                        left, top, right, bottom = card._image_area
                        boxes = []
                        for item in (card.badge_item, card.folder_item, card.page_background_item):
                            box = self.canvas.bbox(item)
                            if box is not None:
                                self.assertGreaterEqual(box[0], left)
                                self.assertGreaterEqual(box[1], top)
                                self.assertLessEqual(box[2], right)
                                self.assertLessEqual(box[3], bottom)
                                boxes.append(box)
                        for first, second in zip(boxes, boxes[1:]):
                            self.assertLess(first[3], second[1], boxes)
                        self.assert_inside()

    def test_page_badge_click_uses_card_selection_and_settings_are_detached(self):
        card = self.card
        options = normalize_overlay_settings()
        card.set_overlays(options)
        options['pages']['visible'] = False
        card.set_page_count(30)
        selected = []
        card.bind('<Button-1>', lambda event: selected.append(self.path))
        self.root.update()
        box = self.canvas.bbox(card.page_background_item)
        self.assertIsNotNone(box)
        x, y = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
        self.canvas.event_generate('<Motion>', x=x, y=y)
        self.canvas.event_generate('<ButtonPress-1>', x=x, y=y)
        self.canvas.event_generate('<ButtonRelease-1>', x=x, y=y)
        self.root.update()
        self.assertEqual(selected, [self.path])
        card.set_page_count(-1)
        self.assertEqual(self.canvas.itemcget(card.page_item, 'state'), 'hidden')
        card.set_page_count('unknown')
        self.assertIsNone(card.page_count)

    def test_images_preserve_aspect_and_cannot_draw_across_rows(self):
        self.card.set_text('Archive-001.cbz', '12.0 MB · 2026-10-19')
        for size in ((127, 180), (1800, 200), (200, 1800), (381, 180)):
            with self.subTest(size=size):
                image = Image.new('RGB', size, '#2080c0')
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, size[0] // 3, size[1]), fill='#d04030')
                self.card.thumbnail.show_image(image, (220, 260))
                self.root.update_idletasks()
                photo = self.card.thumbnail.photo
                self.assertIsNotNone(photo)
                self.assertIs(self.photos[-1][0], self.card.thumbnail)
                self.assertIs(self.photos[-1][1], photo)
                rendered = ImageTk.getimage(photo)
                self.assertGreater(rendered.width, 0)
                self.assertGreater(rendered.height, 0)
                self.assertLessEqual(rendered.width, 220)
                self.assertLessEqual(rendered.height, 260)
                self.assertAlmostEqual(rendered.width / rendered.height, size[0] / size[1],
                                       delta=max(1 / rendered.height, size[0] / size[1] / rendered.height))
                image_items = [item for item in self.items() if self.canvas.type(item) == 'image'
                               and self.canvas.itemcget(item, 'state') != 'hidden']
                self.assertEqual(len(image_items), 1)
                self.assertEqual(self.canvas.itemcget(image_items[0], 'image'), str(photo))
                title_box = self.canvas.bbox(self.card.title_item)
                image_box = self.canvas.bbox(image_items[0])
                self.assertLessEqual(image_box[3], title_box[1] + 1)
                self.assert_inside()

    def test_resubmitting_a_mutated_image_refreshes_the_actual_pixels(self):
        thumbnail = self.card.thumbnail
        image = Image.new('RGB', (127, 180), '#d02030')
        thumbnail.show_image(image, (220, 260))
        original = thumbnail.photo
        self.assertIsNotNone(original)
        before = ImageTk.getimage(original).convert('RGB')
        self.assertEqual(before.getpixel((before.width // 2, before.height // 2)), (208, 32, 48))
        # The renderer may cache an unchanged layout, but the same PIL object
        # can carry newly edited pixels. Explicit submission must replace them.
        image.paste('#2040e0', (0, 0, image.width, image.height))
        thumbnail.show_image(image, (220, 260))
        self.root.update_idletasks()
        self.assertIsNot(thumbnail.photo, original)
        self.assertEqual(self.photos[-1], (thumbnail, thumbnail.photo))
        after = ImageTk.getimage(thumbnail.photo).convert('RGB')
        self.assertEqual(after.getpixel((after.width // 2, after.height // 2)), (32, 64, 224))
        image_items = [item for item in self.items() if self.canvas.type(item) == 'image'
                       and self.canvas.itemcget(item, 'state') != 'hidden']
        self.assertEqual(len(image_items), 1)
        self.assertEqual(self.canvas.itemcget(image_items[0], 'image'), str(thumbnail.photo))
        self.assert_inside()

    def test_unchanged_geometry_does_not_write_or_rebuild_canvas_items(self):
        self.card.set_text('Archive-001.cbz', '12.0 MB')
        self.card.thumbnail.show_image(Image.new('RGB', (127, 180), '#3080d0'), (220, 260))
        before_items = self.items()
        before_photo = self.card.thumbnail.photo
        with patch.object(self.canvas, 'coords', wraps=self.canvas.coords) as coords, \
                patch.object(self.canvas, 'itemconfigure', wraps=self.canvas.itemconfigure) as configure:
            for _ in range(1000):
                self.card.layout(*self.card.geometry)
            self.assertEqual(coords.call_count, 0)
            self.assertEqual(configure.call_count, 0)
        self.assertEqual(self.items(), before_items)
        self.assertIs(self.card.thumbnail.photo, before_photo)
        old_geometry = self.card.geometry
        old_bounds = {item: self.canvas.bbox(item) for item in self.items()}
        self.card.layout(old_geometry[0] + 270, old_geometry[1] + 350,
                         old_geometry[2], old_geometry[3])
        self.root.update_idletasks()
        self.assertEqual(self.items(), before_items)
        for item, previous in old_bounds.items():
            current = self.canvas.bbox(item)
            if previous and current:
                self.assertEqual(current, tuple(value + (270 if i % 2 == 0 else 350)
                                                for i, value in enumerate(previous)))
        self.assert_inside()

    def test_error_replaces_image_and_destroy_releases_every_item_and_binding(self):
        thumbnail = self.card.thumbnail
        thumbnail.show_image(Image.new('RGB', (127, 180), '#3080d0'), (220, 260))
        thumbnail.show_error('Preview unavailable\nSynthetic decoding failure')
        self.root.update_idletasks()
        self.assertIsNone(thumbnail.photo)
        self.assertIn('Synthetic decoding failure', thumbnail.text)
        self.assertEqual(self.photos[-1], (thumbnail, None))
        for item in self.items():
            if self.canvas.type(item) == 'image':
                self.assertTrue(self.canvas.itemcget(item, 'state') == 'hidden'
                                or not self.canvas.itemcget(item, 'image'))
        self.assert_inside()
        thumbnail.show_image(Image.new('RGB', (127, 180), '#3080d0'), (220, 260))
        callbacks = [self.card.bind('<Button-1>', lambda event: None),
                     self.card.bind('<Enter>', lambda event: None)]
        for command in callbacks:
            self.assertTrue(command, 'Card.bind must return its Tk callback ID')
            self.assertTrue(self.canvas.tk.call('info', 'commands', command))
        self.card.destroy()
        self.root.update_idletasks()
        self.assertFalse(self.card.alive)
        self.assertFalse(thumbnail.exists())
        self.assertIsNone(thumbnail.photo)
        self.assertEqual(self.photos[-1], (thumbnail, None))
        self.assertEqual(self.items(), ())
        self.assertEqual(self.canvas.find_all(), ())
        for command in callbacks:
            self.assertFalse(self.canvas.tk.call('info', 'commands', command))
        self.card.destroy()  # Repeated virtual-list cleanup is safe.
        self.assertEqual(self.canvas.find_all(), ())

    def test_worker_retained_thumbnail_does_not_keep_tk_resources_alive(self):
        # Dispose earlier Tk fixtures on their UI thread. A process-wide GC
        # pass from a worker could also collect unrelated old Tcl interpreters.
        gc.collect()
        fonts_before = set(tkfont.names(root=self.root))
        card = GalleryCard(self.canvas, Path('synthetic-library/Background.cbz'),
                           300, 30, 240, 340, PALETTES['다크'], ('TkDefaultFont', 11))
        thumbnail = card.thumbnail  # An archive worker can retain this handle.
        thumbnail.show_image(Image.new('RGB', (127, 180), '#30c090'), (220, 260))
        card_ref = weakref.ref(card)
        allocated_fonts = set(tkfont.names(root=self.root)) - fonts_before
        self.assertTrue(allocated_fonts)
        card.destroy()  # Virtual rows are removed by the UI thread.
        self.assertTrue(allocated_fonts.isdisjoint(tkfont.names(root=self.root)))
        self.assertIsNone(thumbnail.photo)
        last_reference = [card]
        del card
        failures = []
        unraisable = []

        def release_from_worker():
            try:
                last_reference.clear()
            except BaseException as error:
                failures.append(error)

        # If the retained thumbnail owns a card/font, dropping the last card
        # reference here may invoke Tcl or leave the card alive on a worker.
        with patch.object(sys, 'unraisablehook', side_effect=lambda event: unraisable.append(
                (event.exc_type, str(event.exc_value)))):
            worker = threading.Thread(target=release_from_worker, daemon=True)
            worker.start()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive(), 'Worker disposal attempted a blocking Tk call')
        self.assertFalse(failures, failures)
        self.assertFalse(unraisable, unraisable)
        self.assertIsNone(card_ref(), 'A stale thumbnail retained its recycled card')
        self.assertFalse(thumbnail.exists())
        self.assertEqual(self.canvas.winfo_children(), [])

    def test_badge_click_uses_the_same_card_selection_binding(self):
        selected = []
        self.card.set_text('Archive-001.cbz', '12.0 MB')
        self.card.set_favorite(True)
        self.card.bind('<Button-1>', lambda event: selected.append(self.path))
        self.root.update()
        box = self.canvas.bbox(self.card.badge_item)
        self.assertIsNotNone(box)
        x, y = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
        self.canvas.event_generate('<Motion>', x=x, y=y)
        self.root.update()
        self.assertIn(self.card.tag, self.canvas.gettags('current'))
        self.canvas.event_generate('<ButtonPress-1>', x=x, y=y)
        self.canvas.event_generate('<ButtonRelease-1>', x=x, y=y)
        self.root.update()
        self.assertEqual(selected, [self.path])
        self.assertEqual(self.canvas.winfo_children(), [])


if __name__ == '__main__':
    unittest.main()
