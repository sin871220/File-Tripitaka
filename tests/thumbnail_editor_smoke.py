"""Real Tk thumbnail editor integration tests using only temporary archives.

Run ``python tests/thumbnail_editor_smoke.py`` on a desktop with Tk available.
``create_demo_library`` is also useful for isolated visual QA: every archive
contains genuine colored PNG pages and a distinct archive comment.
"""
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
import weakref
from unittest.mock import patch
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_settings = tempfile.TemporaryDirectory(prefix='file-tripitaka-editor-settings-')
os.environ['LOCALAPPDATA'] = _settings.name
import app as module
import thumbnail_editor
from PIL import Image, ImageDraw, ImageTk

sys.excepthook = sys.__excepthook__


def create_demo_library(folder, count=80):
    """Create safe sample archives; identical pages have distinct archive IDs."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    pages = []
    for width, height in ((600, 900), (1400, 400), (300, 1600)):
        image = Image.new('RGB', (width, height), '#00dc30')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width // 3 - 1, height), fill='#f03030')
        draw.rectangle((width * 2 // 3, 0, width, height), fill='#0050ff')
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        pages.append(stream.getvalue())
    paths = []
    for index in range(count):
        path = folder / f'Sample-{index:03d}.cbz'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for page, data in enumerate(pages, 1):
                archive.writestr(f'pages/{page:03d}.png', data)
            archive.comment = path.name.encode('utf-8')
        paths.append(path)
    return paths


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class ThumbnailEditorSmoke(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix='file-tripitaka-editor-')
        self.addCleanup(self.workspace.cleanup)
        self.folder = Path(self.workspace.name).resolve() / 'library'
        module.CONFIG.unlink(missing_ok=True)
        (module.DATA / 'thumbnail_edits.json').unlink(missing_ok=True)
        self.errors = []
        self.messages = []
        self.closed = False
        self.addCleanup(patch.stopall)
        patch.object(module.App, 'load_favorite_metadata').start()
        for name in ('open_archive', 'reveal'):
            patch.object(module.App, name, side_effect=AssertionError('External action prohibited in smoke fixture')).start()
        patch.object(module, 'trash_archive', side_effect=AssertionError('Real Trash must never be used')).start()
        patch.object(module.messagebox, 'showerror',
                     side_effect=lambda *args, **kwargs: self.messages.append(args)).start()
        self.app = module.App()
        self.app.report_callback_exception = lambda *args: self.errors.append(args)
        self.addCleanup(self.close_app)
        self.app.update()

    def close_app(self):
        if not self.closed:
            if getattr(self.app, 'rename_window', None) is not None:
                self.app.rename_window.destroy()
                self.app.rename_window = None
            self.app.close()
            self.closed = True
        # Worker teardown finishes before temporary archive cleanup on Windows.
        self.app.pool.shutdown(wait=True, cancel_futures=True)
        self.app.folder_pool.shutdown(wait=True, cancel_futures=True)
        self.app.thumbnail_edit_pool.shutdown(wait=True, cancel_futures=True)
        self.assertFalse(self.errors, self.errors)
        self.assertFalse(self.messages, self.messages)

    def wait_for(self, predicate, message='Tk operation did not complete', timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            if predicate():
                self.assertFalse(self.errors, self.errors)
                return
            time.sleep(0.01)
        self.fail(message)

    def load(self, count=80, fraction=0.45):
        paths = create_demo_library(self.folder, count)
        app = self.app
        app.current_folder = str(self.folder)
        app.folder.set(str(self.folder))
        app.query.set('')
        if app.search_job is not None:
            app.after_cancel(app.search_job)
            app.search_job = None
        app.pending_restore = None
        app.views.clear()
        app.tab_views.clear()
        app.sort_order.set('이름 오름차순')
        app.settings['preview_count'] = 1
        app.settings['preview_sampling'] = '순차 보기'
        stats = {path: path.stat() for path in paths}
        app.add_cards((paths, {path: info.st_mtime_ns for path, info in stats.items()},
                       {path: (info.st_size, info.st_mtime) for path, info in stats.items()}))
        app.update()
        app.canvas.yview_moveto(fraction)
        app.refresh_visible()
        self.wait_for(lambda: not app.pending and app.active == 0
                      and all(card[2] in app.photos for card in app.cards.values()),
                      'Fixture thumbnails did not load')
        index = min(len(paths) - 1, int(app.canvas.canvasy(0) // app.row_height()) * app.columns())
        path = app.filtered[index]
        app.select_card(path)
        return paths, path

    def card(self, path):
        return next(card for card in self.app.cards.values() if card[0] == path)

    def open_editor(self, path, context=False):
        app = self.app
        if context:
            with patch.object(module.tk.Menu, 'tk_popup'):
                app.context(SimpleNamespace(x_root=100, y_root=100), path)
            menu = app.context_menu
            index = next(index for index in range(menu.index('end') + 1)
                         if menu.type(index) == 'command'
                         and menu.entrycget(index, 'label') == '썸네일 영역 편집')
            menu.invoke(index)
        else:
            app.edit_thumbnail(path)
        editor = app.thumbnail_editor_window
        self.wait_for(lambda: editor._image is not None
                      and not editor.apply_button.instate(['disabled']),
                      'Editor did not load its initial image')
        self.assertEqual(len(editor.entries), 3)
        self.assertEqual(tuple(map(bool, editor.resizable())), (True, True))
        for widget in (editor.canvas, editor.apply_button, editor.reset_button):
            bottom = widget.winfo_rooty() - editor.winfo_rooty() + widget.winfo_height()
            self.assertGreater(widget.winfo_width(), 1)
            self.assertLessEqual(bottom, editor.winfo_height())
        return editor

    def drag_blue_region(self, editor):
        editor.full_button.invoke()
        editor.ratio_combo.current(1)  # Free aspect ratio, using the actual control.
        editor.ratio_combo.event_generate('<<ComboboxSelected>>')
        # A new editor starts with the full image selected. Resize its real
        # corner handles; dragging inside that selection would only move it.
        for start, end in (((0, 0), (0.72, 0.03)), ((1, 1), (0.96, 0.88))):
            first = tuple(round(value) for value in editor._to_canvas(*start))
            last = tuple(round(value) for value in editor._to_canvas(*end))
            editor.canvas.event_generate('<ButtonPress-1>', x=first[0], y=first[1])
            editor.canvas.event_generate('<B1-Motion>', x=last[0], y=last[1], state=0x100)
            editor.canvas.event_generate('<ButtonRelease-1>', x=last[0], y=last[1])
        self.app.update()
        self.assertGreater(editor.selection[0], 0.69)
        self.assertLess(editor.selection[0], editor.selection[2])
        self.assertGreater(editor.selection[3] - editor.selection[1], 0.7)
        return tuple(editor.selection)

    def apply_crop(self, path, editor):
        before = self.app.photos[self.card(path)[2]]
        box = self.drag_blue_region(editor)
        editor.apply_button.invoke()
        self.wait_for(lambda: not editor._busy and self.app.thumbnail_edits.get(path) is not None
                      and self.card(path)[2] in self.app.photos
                      and self.app.photos[self.card(path)[2]] is not before,
                      'Applying crop did not refresh the gallery thumbnail')
        return box

    def assert_blue_center(self, photo):
        image = ImageTk.getimage(photo).convert('RGB')
        red, green, blue = image.getpixel((image.width // 2, image.height // 2))
        self.assertGreater(blue, red + 100)
        self.assertGreater(blue, green + 100)

    def test_context_apply_reopen_reset_keep_scroll_and_other_cards(self):
        app = self.app
        _, path = self.load()
        original_bytes = path.read_bytes()
        before_cards = dict(app.cards)
        before_photos = dict(app.photos)
        before_scroll = app.canvas.canvasy(0)
        old_revision = app.thumbnail_revisions.get(str(path), 0)
        editor = self.open_editor(path, context=True)
        box = self.apply_crop(path, editor)
        label = self.card(path)[2]
        edited_photo = app.photos[label]
        self.assert_blue_center(edited_photo)
        self.assertEqual(app.selected_path, path)
        self.assertAlmostEqual(app.canvas.canvasy(0), before_scroll, delta=1)
        self.assertEqual(app.cards, before_cards)
        for other_label, photo in before_photos.items():
            if other_label is not label:
                self.assertIs(app.photos[other_label], photo)
        # Deliver an old in-flight automatic cover explicitly. The per-file
        # revision must reject it even though its gallery generation is current.
        app.active += 1
        app.results.put(('cover', app.generation,
                         (label, Image.new('RGB', (80, 100), 'magenta'), old_revision), None))
        self.wait_for(lambda: app.results.empty())
        self.assertIs(app.photos[label], edited_photo)
        self.assertNotIn(str(path), app.preview_errors)
        editor.close()
        editor = self.open_editor(path)
        self.assertEqual(editor.entries[editor._entry_index][0], 'pages/001.png')
        for actual, expected in zip(editor.selection, box):
            self.assertAlmostEqual(actual, expected, places=8)
        self.assertFalse(editor.reset_button.instate(['disabled']))
        editor.reset_button.invoke()
        self.wait_for(lambda: not editor._busy and editor._image is not None
                      and app.thumbnail_edits.get(path) is None
                      and label in app.photos and app.photos[label] is not edited_photo,
                      'Reset did not restore the automatic thumbnail')
        automatic = ImageTk.getimage(app.photos[label]).convert('RGB')
        red, green, blue = automatic.getpixel((automatic.width // 2, automatic.height // 2))
        self.assertGreater(green, red + 100)
        self.assertGreater(green, blue + 100)
        self.assertEqual(app.cards, before_cards)
        self.assertEqual(app.selected_path, path)
        self.assertAlmostEqual(app.canvas.canvasy(0), before_scroll, delta=1)
        self.assertEqual(path.read_bytes(), original_bytes)
        editor.close()

    def test_app_rename_external_move_and_rescan_restore_recipe(self):
        app = self.app
        _, path = self.load()
        original_bytes = path.read_bytes()
        editor = self.open_editor(path)
        box = self.apply_crop(path, editor)
        editor.close()
        app.rename_file(path)
        dialog = app.rename_window
        entry = next(widget for widget in descendants(dialog)
                     if isinstance(widget, module.ttk.Entry))
        entry.delete(0, 'end')
        entry.insert(0, 'Renamed sample')
        button = next(widget for widget in descendants(dialog)
                      if isinstance(widget, module.ttk.Button)
                      and widget.cget('text') == '이름 바꾸기')
        button.invoke()
        renamed = path.with_name('Renamed sample.cbz')
        self.wait_for(lambda: app.selected_path == renamed and renamed in app.filtered)
        self.assertFalse(path.exists())
        self.assertEqual(renamed.read_bytes(), original_bytes)
        self.assertEqual(app.thumbnail_edits.get(renamed)['0']['box'], list(box))
        editor = self.open_editor(renamed)
        self.assertEqual(list(editor.selection), list(box))
        editor.close()
        moved_folder = self.folder / 'Moved folder'
        moved_folder.mkdir()
        moved = renamed.rename(moved_folder / 'Externally moved.cbz')
        app.scan()
        self.wait_for(lambda: moved in app.files and renamed not in app.files,
                      'Rescan did not discover the externally moved archive')
        self.assertEqual(app.thumbnail_edits.get(moved)['0']['box'], list(box))
        editor = self.open_editor(moved)
        self.assertEqual(list(editor.selection), list(box))
        self.assertEqual(moved.read_bytes(), original_bytes)
        editor.close()

    def test_modal_wheel_does_not_scroll_gallery(self):
        app = self.app
        _, path = self.load()
        editor = self.open_editor(path)
        original_top = app.canvas.canvasy(0)
        self.assertIs(app.grab_current(), editor)
        # Preview/footer events bubble to the application's global bindings;
        # synthetic main-canvas events also exercise retargeting under a grab.
        for widget in (editor.preview_canvas, editor.status_label,
                       editor.apply_button, app.canvas):
            for sequence, options in (('<MouseWheel>', {'delta': -120}),
                                      ('<Button-4>', {}), ('<Button-5>', {})):
                with self.subTest(widget=str(widget), sequence=sequence):
                    try:
                        widget.event_generate(sequence, x=2, y=2, **options)
                    except module.tk.TclError as error:
                        if sequence not in ('<Button-4>', '<Button-5>'):
                            raise
                        # Some native Tk ports reject Linux button numbers.
                        # Verify their registered app dispatch path directly.
                        self.assertIn('button', str(error).lower())
                        self.assertTrue(app.bind_all(sequence))
                        app.wheel(SimpleNamespace(widget=widget, num=int(sequence[-2]), delta=0))
                    app.update()
                    self.assertAlmostEqual(app.canvas.canvasy(0), original_top, delta=1)
        old_zoom = editor._zoom
        editor.canvas.event_generate('<MouseWheel>', delta=120, x=50, y=50)
        app.update()
        self.assertGreater(editor._zoom, old_zoom, 'Editor canvas wheel must still zoom')
        self.assertAlmostEqual(app.canvas.canvasy(0), original_top, delta=1)
        editor.close()
        app.canvas.event_generate('<MouseWheel>', delta=-120, x=50, y=50)
        self.wait_for(lambda: app.canvas.canvasy(0) > original_top,
                      'Main gallery wheel must resume after the modal closes')

    def test_apply_refreshes_loaded_card_while_normal_cover_workers_are_blocked(self):
        app = self.app
        _, path = self.load()
        editor = self.open_editor(path)
        label = self.card(path)[2]
        original_photo = app.photos[label]
        before_cards = dict(app.cards)
        before_photos = dict(app.photos)
        original_top = app.canvas.canvasy(0)
        other_cards = [card for card in app.cards.values() if card[0] != path]
        self.assertGreater(len(other_cards), 6)
        background_paths = {card[0] for card in other_cards}
        release, started = threading.Event(), threading.Event()
        render_release, render_started = threading.Event(), threading.Event()
        started_count = 0
        started_lock = threading.Lock()
        original_cover = module.cover
        original_edited_cover = module.render_edited_cover

        def blocked_normal_cover(current, *args, **kwargs):
            nonlocal started_count
            if current in background_paths:
                with started_lock:
                    started_count += 1
                    if started_count >= 3:
                        started.set()
                if not release.wait(10):
                    raise RuntimeError('Fixture normal cover worker was not released')
            return original_cover(current, *args, **kwargs)

        def paused_edited_cover(current, *args, **kwargs):
            if current == path:
                render_started.set()
                if not render_release.wait(8):
                    raise RuntimeError('Fixture edited cover worker was not released')
            return original_edited_cover(current, *args, **kwargs)

        with patch.object(module, 'cover', side_effect=blocked_normal_cover), \
                patch.object(module, 'render_edited_cover', side_effect=paused_edited_cover):
            # Requeue already-rendered surrounding covers to reproduce a busy
            # directory without destroying or scrolling the target's loaded card.
            app.pending.extend((app.generation, current, current_label)
                               for current, _, current_label, _ in other_cards)
            self.wait_for(lambda: started.is_set() and app.active == 3,
                          'Could not saturate all normal thumbnail workers')
            self.assertGreater(len(app.pending), 3)
            try:
                self.drag_blue_region(editor)
                editor.apply_button.invoke()
                self.wait_for(render_started.is_set,
                              'Edited card waited behind the normal thumbnail backlog', timeout=3)
                self.assertIs(app.photos.get(label), original_photo,
                              'Keep the existing image until the edited replacement is ready')
                self.assertIs(label.photo, original_photo)
                self.assertTrue(label.exists())
                render_release.set()
                self.wait_for(lambda: not editor._busy and label in app.photos
                              and app.photos[label] is not original_photo,
                              'Priority render did not refresh the edited card', timeout=3)
                self.assert_blue_center(app.photos[label])
                self.assertFalse(release.is_set())
                self.assertEqual(app.active, 3, 'Normal covers must still be blocked')
                edited_photo = app.photos[label]
                edited_revision = app.thumbnail_revisions.get(str(path), 0)
                editor.reset_button.invoke()
                self.wait_for(lambda: not editor._busy and app.thumbnail_edits.get(path) is None
                              and label in app.photos and app.photos[label] is not edited_photo,
                              'Reset waited behind the normal thumbnail backlog', timeout=3)
                reset_photo = app.photos[label]
                automatic = ImageTk.getimage(reset_photo).convert('RGB')
                red, green, blue = automatic.getpixel((automatic.width // 2, automatic.height // 2))
                self.assertGreater(green, max(red, blue) + 100)
                # An old cover from before Reset must not overwrite its newer
                # result even though the gallery generation has not changed.
                app.active += 1
                app.results.put(('cover', app.generation,
                                 (label, Image.new('RGB', (80, 100), 'magenta'), edited_revision), None))
                self.wait_for(lambda: app.results.empty())
                self.assertIs(app.photos[label], reset_photo)
                self.assertEqual(app.active, 3)
                current_revision = app.thumbnail_revisions[str(path)]
                count = app.settings.get('preview_count', 1)
                sampling = app.settings.get('preview_sampling', '순차 보기')
                for result_generation, revision, result_count, result_sampling in (
                        (app.scan_generation, edited_revision, count, sampling),
                        (app.scan_generation, current_revision, count + 1, sampling),
                        (app.scan_generation, current_revision, count, '비율 보기'),
                        (app.scan_generation - 1, current_revision, count, sampling)):
                    app.results.put(('thumbnail_refresh', result_generation,
                                     (path, revision, result_count, result_sampling,
                                      Image.new('RGB', (80, 100), 'magenta')), None))
                    self.wait_for(lambda: app.results.empty())
                    self.assertIs(app.photos[label], reset_photo,
                                  'An obsolete priority result must not replace the current image')
                    self.assertEqual(app.active, 3,
                                     'Priority results must not consume normal cover worker slots')
                self.assertFalse(release.is_set())
                self.assertEqual(app.cards, before_cards)
                for other_label, photo in before_photos.items():
                    if other_label is not label:
                        self.assertIs(app.photos[other_label], photo)
                self.assertEqual(app.selected_path, path)
                self.assertAlmostEqual(app.canvas.canvasy(0), original_top, delta=1)
            finally:
                render_release.set()
                release.set()
                self.wait_for(lambda: not app.pending and not app.active,
                              'Normal thumbnail workers did not finish after release')
        editor.close()

    def test_save_failures_explain_reason_preserve_preview_and_allow_retry(self):
        app = self.app
        _, path = self.load(count=8, fraction=0)
        cases = (
            (module.ThumbnailFileChangedError('fixture source changed'),
             '읽는 동안 압축파일이 변경되었습니다. 편집기를 다시 열어 적용해 주세요.'),
            (PermissionError('fixture access denied'),
             '파일을 읽거나 설정을 저장할 수 없습니다. 다른 프로그램의 사용 여부와 접근 권한을 확인해 주세요.'),
            (FileNotFoundError('fixture source missing'),
             '압축파일 또는 설정 폴더를 찾을 수 없습니다. 파일 위치를 확인해 주세요.'),
            (OSError('fixture volume error'),
             '썸네일 편집 정보를 저장하지 못했습니다.'),
        )
        for language in ('ko', 'en'):
            with self.subTest(language=language):
                app.settings['language'] = language
                app.apply_language()
                editor = self.open_editor(path)
                box = self.drag_blue_region(editor)
                label = self.card(path)[2]
                old_photo = app.photos[label]
                old_revision = app.thumbnail_revisions.get(str(path), 0)
                before_cards = dict(app.cards)
                before_top = app.canvas.canvasy(0)
                for error, reason in cases:
                    with self.subTest(error=type(error).__name__):
                        with patch.object(app.thumbnail_edits, 'set', side_effect=error):
                            editor.apply_button.invoke()
                            self.wait_for(lambda error=error: not editor._busy
                                          and type(error).__name__ in editor._status_var.get(),
                                          'Save failure was not reported back to the editor')
                        status = editor._status_var.get()
                        self.assertIn(module.tr(reason), status)
                        self.assertIn(f'{type(error).__name__}: {error}', status)
                        self.assertIn(str(module.DATA / 'error.log'), status)
                        self.assertIn('Error details:' if language == 'en' else '오류 정보:', status)
                        self.assertFalse(editor.apply_button.instate(['disabled']))
                        self.assertIs(app.photos.get(label), old_photo)
                        self.assertIsNone(app.thumbnail_edits.get(path))
                        self.assertEqual(app.thumbnail_revisions.get(str(path), 0), old_revision)
                        self.assertEqual(app.cards, before_cards)
                        self.assertEqual(app.selected_path, path)
                        self.assertAlmostEqual(app.canvas.canvasy(0), before_top, delta=1)
                # No dialog reopening or selection loss is required after the
                # error: the next Apply invokes the real store and succeeds.
                editor.apply_button.invoke()
                self.wait_for(lambda: not editor._busy and label in app.photos
                              and app.photos[label] is not old_photo
                              and app.thumbnail_edits.get(path) is not None,
                              'Apply remained unusable after a failed save')
                self.assertEqual(app.thumbnail_edits.get(path)['0']['box'], list(box))
                self.assert_blue_center(app.photos[label])
                edited_photo = app.photos[label]
                editor.reset_button.invoke()
                self.wait_for(lambda: not editor._busy and editor._image is not None
                              and app.thumbnail_edits.get(path) is None
                              and label in app.photos and app.photos[label] is not edited_photo)
                editor.close()

    def test_free_default_thumbnail_ratio_resize_and_saved_boxes_are_preserved(self):
        app = self.app
        _, path = self.load(count=8, fraction=0)
        editor = self.open_editor(path)
        expected_ratio = 127 / 180
        self.assertEqual(editor._ratio_var.get(), module.tr('자유 비율'))
        self.assertEqual(editor.selection, (0, 0, 1, 1))

        def physical_ratio():
            left, top, right, bottom = editor.selection
            return ((right - left) * editor._image.width
                    / ((bottom - top) * editor._image.height))

        # Exercise both a landscape spread and a very tall page. Normalized
        # coordinates alone have different ratios, so test actual image pixels.
        for entry_index in (1, 2):
            with self.subTest(entry_index=entry_index):
                editor.entry_combo.current(entry_index)
                editor.entry_combo.event_generate('<<ComboboxSelected>>')
                self.wait_for(lambda: editor._entry_index == entry_index
                              and editor._image is not None)
                self.assertEqual(editor._ratio_var.get(), module.tr('자유 비율'))
                self.assertEqual(editor.selection, (0, 0, 1, 1))
                editor.ratio_combo.current(0)
                editor.ratio_combo.event_generate('<<ComboboxSelected>>')
                app.update()
                self.assertAlmostEqual(physical_ratio(), expected_ratio, places=8)
                before = tuple(editor.selection)
                left, top, right, bottom = before
                first = tuple(round(value) for value in editor._to_canvas(right, bottom))
                last = tuple(round(value) for value in editor._to_canvas(
                    left + (right - left) * 0.7, top + (bottom - top) * 0.8))
                editor.canvas.event_generate('<ButtonPress-1>', x=first[0], y=first[1])
                editor.canvas.event_generate('<B1-Motion>', x=last[0], y=last[1], state=0x100)
                editor.canvas.event_generate('<ButtonRelease-1>', x=last[0], y=last[1])
                app.update()
                self.assertNotEqual(tuple(editor.selection), before)
                self.assertAlmostEqual(physical_ratio(), expected_ratio, places=8)
                box = tuple(editor.selection)
                self.wait_for(lambda: editor._preview_image is not None)
                editor._draw_preview()
                frame = next(item for item in editor.preview_canvas.find_all()
                             if editor.preview_canvas.type(item) == 'rectangle')
                x1, y1, x2, y2 = editor.preview_canvas.coords(frame)
                self.assertAlmostEqual((x2 - x1) / (y2 - y1), expected_ratio,
                                       delta=2 / (y2 - y1))
                old_photo = app.photos[self.card(path)[2]]
                editor.apply_button.invoke()
                self.wait_for(lambda: not editor._busy and app.thumbnail_edits.get(path) is not None
                              and self.card(path)[2] in app.photos
                              and app.photos[self.card(path)[2]] is not old_photo)
                recipe = app.thumbnail_edits.get(path)['0']
                self.assertEqual(recipe['entry'], f'pages/{entry_index + 1:03d}.png')
                self.assertEqual(recipe['box'], list(box))
                editor.close()
                editor = self.open_editor(path)
                self.assertEqual(editor._ratio_var.get(), module.tr('자유 비율'))
                self.assertEqual(tuple(editor.selection), box)
                self.assertAlmostEqual(physical_ratio(), expected_ratio, places=8)
        editor.close()
        # Previously saved 320:340 crops must retain their coordinates when a
        # newer editor defaults to Free and offers the new 127:180 fixed ratio.
        legacy_height = 0.8 * 600 / (900 * (320 / 340))
        legacy_box = (0.1, 0.15, 0.9, 0.15 + legacy_height)
        app.thumbnail_edits.set(path, 0, 'pages/001.png', legacy_box)
        editor = self.open_editor(path)
        self.assertEqual(editor._ratio_var.get(), module.tr('자유 비율'))
        self.assertEqual(tuple(editor.selection), legacy_box)
        self.assertAlmostEqual(physical_ratio(), 320 / 340, places=8)
        editor.apply_button.invoke()
        self.wait_for(lambda: not editor._busy)
        self.assertEqual(app.thumbnail_edits.get(path)['0']['box'], list(legacy_box))
        editor.close()

    def test_main_edit_button_follows_selection_and_opens_correct_archive(self):
        app = self.app
        button = app.thumbnail_edit_button
        self.assertTrue(button.instate(['disabled']))
        _, path = self.load(count=8, fraction=0)
        self.assertFalse(button.instate(['disabled']))
        self.assertIs(button.master, app.thumbnail_scale.master)
        self.assertIs(button.master, app.fit_button.master)
        self.assertIs(button.master, app.sampling_control.master)
        center = button.winfo_rooty() + button.winfo_height() / 2
        for control in (app.thumbnail_scale, app.fit_button, app.sampling_control):
            self.assertAlmostEqual(control.winfo_rooty() + control.winfo_height() / 2,
                                   center, delta=2)
        right_margin = (app.winfo_rootx() + app.winfo_width()
                        - button.winfo_rootx() - button.winfo_width())
        self.assertGreaterEqual(right_margin, 0)
        self.assertLessEqual(right_margin, 24)
        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                             app.winfo_rooty() + app.winfo_height())
        button.invoke()
        editor = app.thumbnail_editor_window
        self.assertEqual(editor.path, path)
        self.wait_for(lambda: editor._image is not None)
        editor.close()
        app.query.set('no matching fixture archive')
        self.wait_for(lambda: not app.filtered and button.instate(['disabled']),
                      'Edit button stayed enabled after its selected file was filtered out')
        self.assertEqual(app.selected_path, path)
        app.query.set('')
        self.wait_for(lambda: path in app.filtered and not button.instate(['disabled']),
                      'Edit button did not reenable when the selected file became visible')

    def test_main_toolbar_fits_same_row_in_both_languages_and_window_widths(self):
        app = self.app
        button = app.thumbnail_edit_button
        cluster = app.thumbnail_controls
        tools = cluster.master
        self.assertIs(button.master, cluster)
        self.assertIs(app.thumbnail_scale.master, cluster)
        self.assertIs(app.fit_button.master, cluster)
        self.assertIs(app.sampling_control.master, cluster)
        top_buttons = [widget for widget in tools.winfo_children()
                       if isinstance(widget, module.ttk.Button)]
        self.assertEqual(len(top_buttons), 1, 'Only Top belongs outside the right-hand cluster')
        top_button = top_buttons[0]
        for language in ('ko', 'en'):
            app.settings['language'] = language
            app.apply_language()
            for width in (980, 1120, 1600):
                for sidebar in (True, False):
                    with self.subTest(language=language, width=width, sidebar=sidebar):
                        if app.sidebar_hidden == sidebar:
                            app.toggle_sidebar()
                        app.geometry(f'{width}x760')
                        app.update()
                        controls = [widget for widget in cluster.winfo_children()
                                    if isinstance(widget, (module.ttk.Button, module.ttk.Checkbutton,
                                                           module.ttk.Combobox, module.ttk.Scale,
                                                           module.ttk.Label))]
                        controls.sort(key=lambda widget: int(widget.grid_info()['column']))
                        self.assertEqual(len(controls), 7)
                        self.assertEqual(controls[0].cget('text'), module.tr('썸네일 크기'))
                        center = button.winfo_rooty() + button.winfo_height() / 2
                        left, right = cluster.winfo_rootx(), cluster.winfo_rootx() + cluster.winfo_width()
                        issues = []
                        for widget in controls:
                            text = widget.cget('text') if 'text' in widget.keys() else str(widget)
                            if not widget.winfo_ismapped():
                                issues.append(f'{text} hidden')
                            if (widget.winfo_rootx() < left or
                                    widget.winfo_rootx() + widget.winfo_width() > right):
                                issues.append(f'{text} outside row: x={widget.winfo_rootx() - left}, '
                                              f'width={widget.winfo_width()}, row={cluster.winfo_width()}')
                            if not isinstance(widget, module.ttk.Scale) and widget.winfo_width() < widget.winfo_reqwidth():
                                issues.append(f'{text} clipped: {widget.winfo_width()} < {widget.winfo_reqwidth()}')
                            if abs(widget.winfo_rooty() + widget.winfo_height() / 2 - center) > 2:
                                issues.append(f'{text} occupies a different vertical row')
                        for previous, following in zip(controls, controls[1:]):
                            gap = following.winfo_rootx() - previous.winfo_rootx() - previous.winfo_width()
                            if not 0 <= gap <= 12:
                                issues.append(f'Internal cluster gap is {gap}px between '
                                              f'{previous.winfo_name()} and {following.winfo_name()}')
                        right_margin = tools.winfo_rootx() + tools.winfo_width() - right
                        if not 0 <= right_margin <= 10:
                            issues.append(f'Controls are not right aligned: margin={right_margin}')
                        top_gap = left - top_button.winfo_rootx() - top_button.winfo_width()
                        # A desktop/CI window manager may cap the requested
                        # 1600px window to its physical screen width. Verify
                        # the actual cluster never expands to absorb free
                        # space, rather than assuming a particular screen.
                        if top_gap < 6:
                            issues.append(f'Extra width must separate Top from the whole cluster: gap={top_gap}')
                        if cluster.winfo_width() > cluster.winfo_reqwidth():
                            issues.append('Extra width stretched the thumbnail cluster')
                        if abs(top_button.winfo_rooty() + top_button.winfo_height() / 2 - center) > 2:
                            issues.append('Top and the thumbnail cluster occupy different rows')
                        if app.thumbnail_scale.winfo_width() < 32:
                            issues.append(f'Slider collapsed to {app.thumbnail_scale.winfo_width()} pixels')
                        if app.thumbnail_scale.winfo_width() > 140:
                            issues.append('Slider stretched inside the right-hand cluster')
                        if (button.winfo_rootx() + button.winfo_width()
                                > app.winfo_rootx() + app.winfo_width()):
                            issues.append('Edit button extends beyond the main window')
                        self.assertFalse(issues, '; '.join(issues) +
                                         f' (actual_window={app.winfo_width()}, row={tools.winfo_width()}, cluster={cluster.winfo_width()}, '
                                         f'requested={cluster.winfo_reqwidth()}, '
                                         f'fixed={cluster.winfo_reqwidth() - app.thumbnail_scale.winfo_reqwidth()}, '
                                         f'slider={app.thumbnail_scale.winfo_width()})')

    def test_two_and_three_slots_save_independently_and_keep_reverse_order(self):
        app = self.app
        self.load(count=24, fraction=0.15)
        for count in (2, 3):
            with self.subTest(count=count):
                app.preview_count.set(f'{count}장')
                app.change_preview_count()
                self.wait_for(lambda: not app.pending and not app.active
                              and all(card[2] in app.photos for card in app.cards.values()))
                path = sorted(app.cards.values(), key=lambda card: str(card[0]))[count][0]
                app.select_card(path)
                editor = self.open_editor(path)
                self.assertEqual(editor.slots, count)
                self.assertFalse(editor.slot_combo.instate(['disabled']))
                expected = {}
                # All slots use the same source member, selecting a different
                # solid stripe. The resulting gallery pixels reveal slot order.
                for slot, left in enumerate((0.73, 0.38, 0.03)[:count]):
                    editor.slot_combo.current(slot)
                    editor.slot_combo.event_generate('<<ComboboxSelected>>')
                    self.wait_for(lambda slot=slot: editor._slot == slot
                                  and editor._image is not None and not editor._busy)
                    editor.entry_combo.current(0)
                    editor.entry_combo.event_generate('<<ComboboxSelected>>')
                    self.wait_for(lambda: editor._entry_index == 0 and editor._image is not None)
                    box = (left, 0.15, left + 0.24, 0.85)
                    editor.selection = box
                    editor._selection_changed()
                    before = app.photos[self.card(path)[2]]
                    editor.apply_button.invoke()
                    expected[str(slot)] = {'entry': 'pages/001.png', 'box': list(box)}
                    self.wait_for(lambda: not editor._busy and not app.pending and not app.active
                                  and self.card(path)[2] in app.photos
                                  and app.photos[self.card(path)[2]] is not before)
                    self.assertEqual(app.thumbnail_edits.get(path), expected,
                                     'Saving one slot must preserve the other slot recipes')
                photo = ImageTk.getimage(app.photos[self.card(path)[2]]).convert('RGB')
                # Logical slots 1,2,3 are physically rendered 3,2,1 (or 2,1).
                expected_channels = (1, 2) if count == 2 else (0, 1, 2)
                for index, channel in enumerate(expected_channels):
                    pixel = photo.getpixel((int((index + 0.5) * photo.width / count), photo.height // 2))
                    self.assertGreater(pixel[channel], max(value for i, value in enumerate(pixel)
                                                           if i != channel) + 100,
                                       f'Unexpected physical order for {count} slots: {pixel}')
                editor.slot_combo.current(1)
                editor.slot_combo.event_generate('<<ComboboxSelected>>')
                self.wait_for(lambda: editor._slot == 1 and editor._image is not None)
                editor.reset_button.invoke()
                expected.pop('1')
                self.wait_for(lambda: not editor._busy and editor._image is not None
                              and app.thumbnail_edits.get(path) == expected)
                self.assertEqual(app.thumbnail_edits.get(path), expected,
                                 'Reset must remove only the selected slot')
                editor.close()
                editor = self.open_editor(path)
                self.assertEqual(editor.recipes, expected)
                self.assertEqual(list(editor.selection), expected['0']['box'])
                editor.close()

    def test_english_light_dark_large_font_controls_fit_minimum_window(self):
        app = self.app
        _, path = self.load(count=8, fraction=0)
        app.font_size = 24
        app.ui_font = module.configure_fonts(app, app.ui_font, app.font_size)
        app.settings['language'] = 'en'
        app.apply_language()
        for theme in ('라이트', '다크'):
            with self.subTest(theme=theme):
                app.settings['theme'] = theme
                app.apply_theme()
                editor = self.open_editor(path)
                self.assertEqual(editor.font_size, 14)
                self.assertEqual(editor.title(), 'Edit thumbnail region')
                width, height = editor.minsize()
                editor.geometry(f'{width}x{height}')
                app.update()
                for widget in descendants(editor):
                    if not isinstance(widget, (module.ttk.Button, module.ttk.Combobox,
                                               module.ttk.Entry, module.ttk.Scale)):
                        continue
                    x = widget.winfo_rootx() - editor.winfo_rootx()
                    y = widget.winfo_rooty() - editor.winfo_rooty()
                    self.assertGreaterEqual(x, 0, str(widget))
                    self.assertGreaterEqual(y, 0, str(widget))
                    self.assertLessEqual(x + widget.winfo_width(), editor.winfo_width(), str(widget))
                    self.assertLessEqual(y + widget.winfo_height(), editor.winfo_height(), str(widget))
                    if isinstance(widget, module.ttk.Button):
                        self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth(),
                                                f'Button text clipped: {widget.cget("text")}')
                self.assertNotEqual(editor.palette['fg'], editor.palette['panel'])
                editor.close()

    def test_close_while_editor_worker_is_reading_is_safe(self):
        _, path = self.load(count=8, fraction=0)
        started, release = threading.Event(), threading.Event()
        original_read = thumbnail_editor.archive_core.read_image_entry

        def delayed_read(*args, **kwargs):
            started.set()
            if not release.wait(8):
                raise RuntimeError('Fixture reader was not released')
            return original_read(*args, **kwargs)

        with patch.object(thumbnail_editor.archive_core, 'read_image_entry', side_effect=delayed_read):
            self.app.edit_thumbnail(path)
            editor = self.app.thumbnail_editor_window
            self.wait_for(started.is_set, 'Editor worker did not begin reading')
            try:
                self.app.close()
                self.closed = True
                self.assertTrue(editor._closed.is_set())
            finally:
                release.set()
            editor._executor.shutdown(wait=True, cancel_futures=True)
        self.assertTrue(editor._results.empty())
        self.assertFalse(self.errors, self.errors)

    def test_closed_editor_releases_ui_resources_before_reader_finishes(self):
        _, path = self.load(count=8, fraction=0)
        editor = self.open_editor(path)
        self.wait_for(lambda: editor._photo is not None)
        variables = [weakref.ref(value) for value in vars(editor).values()
                     if isinstance(value, module.tk.Variable)]
        self.assertEqual(len(variables), 8)
        photo = weakref.ref(editor._photo)
        started, release = threading.Event(), threading.Event()
        original_read = thumbnail_editor.archive_core.read_image_entry

        def delayed_read(*args, **kwargs):
            started.set()
            if not release.wait(8):
                raise RuntimeError('Fixture reader was not released')
            return original_read(*args, **kwargs)

        with patch.object(thumbnail_editor.archive_core, 'read_image_entry', side_effect=delayed_read):
            editor.change_entry(1)
            self.wait_for(started.is_set, 'Editor worker did not begin its next read')
            try:
                editor.close()
                self.assertTrue(editor._closed.is_set())
                self.assertFalse(editor.winfo_exists())
                self.assertTrue(all(reference() is None for reference in variables),
                                'A closed editor retained Tcl variables while its worker was running')
                self.assertIsNone(photo(), 'A closed editor retained its Tk image')
            finally:
                release.set()
            editor._executor.shutdown(wait=True, cancel_futures=True)
        self.assertTrue(editor._results.empty())


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        __import__('faulthandler').disable()
        module.FAULT_LOG.close()
        __import__('logging').shutdown()
        _settings.cleanup()
