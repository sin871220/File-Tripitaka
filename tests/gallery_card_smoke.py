"""Native Tk checks for the single-surface gallery renderer.

Use ``python tests/gallery_card_smoke.py`` on a desktop with Tk available. All
images and file names are synthetic; no user library or saved settings is read.
"""
import gc
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
