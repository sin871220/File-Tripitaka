"""Exercise wheel routing through real Tk widgets, including Tcl-only popups.

Run ``python tests/wheel_routing_smoke.py`` on a desktop with Tk available.
The library, settings and editor pages are generated in temporary directories;
no user archive, saved preference or external viewer is touched.
"""
from contextlib import contextmanager
import io
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_settings = tempfile.TemporaryDirectory(prefix='file-tripitaka-wheel-settings-')
os.environ['LOCALAPPDATA'] = _settings.name
import app as module
from PIL import Image

sys.excepthook = sys.__excepthook__


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class WheelRoutingSmoke(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix='file-tripitaka-wheel-')
        self.addCleanup(self.workspace.cleanup)
        self.folder = Path(self.workspace.name).resolve()
        module.CONFIG.unlink(missing_ok=True)
        self.errors = []
        self.messages = []
        self.editors = []
        self.addCleanup(patch.stopall)
        for name in ('save', 'populate_tree', 'load_favorite_metadata'):
            patch.object(module.App, name).start()
        patch.object(module.App, 'thumbnail_recipes', return_value={}).start()
        patch.object(module, 'cover', side_effect=lambda *args: Image.new('RGB', (100, 140), '#3060a0')).start()
        for name in ('open_archive', 'reveal'):
            patch.object(module.App, name, side_effect=AssertionError('External action prohibited')).start()
        patch.object(module, 'trash_archive', side_effect=AssertionError('Real Trash prohibited')).start()
        patch.object(module.messagebox, 'showerror',
                     side_effect=lambda *args, **kwargs: self.messages.append(args)).start()
        self.app = module.App()
        self.app.report_callback_exception = lambda *args: self.errors.append(args)
        self.addCleanup(self.close_app)
        self.app.update()
        self.app.current_folder = str(self.folder)
        self.app.folder.set(str(self.folder))
        self.paths = [self.folder / f'Archive-{index:05d}.zip' for index in range(7444)]
        self.app.add_cards((self.paths, {path: index for index, path in enumerate(self.paths)},
                            {path: (1024, 1700000000) for path in self.paths}))
        self.app.update()
        self.app.scroll_view('moveto', 0.3)
        self.app.refresh_visible()
        self.wait_for(lambda: not self.app.pending and self.app.active == 0)

    def close_app(self):
        self.app.close()
        for editor in self.editors:
            editor._executor.shutdown(wait=True, cancel_futures=True)
        for pool in (self.app.pool, self.app.folder_pool, self.app.thumbnail_edit_pool):
            pool.shutdown(wait=True, cancel_futures=True)
        self.assertFalse(self.errors, self.errors)
        self.assertFalse(self.messages, self.messages)

    def pump(self, duration=0.05):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.002)
        self.assertFalse(self.errors, self.errors)

    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            if predicate():
                self.assertFalse(self.errors, self.errors)
                return
            time.sleep(0.002)
        self.fail('Tk operation did not complete')

    def wheel(self, target, delta=None):
        # Native class bindings get their platform's ordinary wheel units.
        delta = (-1 if sys.platform == 'darwin' else -120) if delta is None else delta
        self.app.tk.call('event', 'generate', str(target), '<MouseWheel>',
                         '-delta', delta, '-x', 8, '-y', 8)
        self.app.update()
        self.assertFalse(self.errors, self.errors)

    def gallery_wheel(self):
        # Normalized Windows input also checks the reported platform's path
        # without changing Tk's actual platform or native class bindings.
        with patch.object(module.sys, 'platform', 'win32'):
            return self.app.wheel(SimpleNamespace(widget=self.app.canvas, delta=-120, num=None))

    def main_combos(self):
        combos = [widget for widget in descendants(self.app) if isinstance(widget, module.ttk.Combobox)]
        # Localization intentionally wraps each displayed variable in another
        # StringVar, so match the stable widget structure rather than Tcl IDs.
        sorter = next(widget for widget in combos if len(widget.cget('values')) == 4)
        count = next(widget for widget in self.app.thumbnail_controls.winfo_children()
                     if isinstance(widget, module.ttk.Combobox)
                     and int(widget.grid_info()['column']) == 4)
        return sorter, count, self.app.sampling_control, self.app.kind_control, self.app.group_control

    @contextmanager
    def popup(self, combo):
        """Create Tk's real Tcl-owned popup without blocking Aqua's menu loop.

        Tk 8.6 uses a listbox on Aqua as well as Windows/X11; its real Post is
        nonblocking. Tk 9 Aqua instead uses a native menu tracking loop, so
        construct that real menu without posting it. Inspect the actual popup
        children rather than assuming an implementation from the OS/version.
        Python has no widget object for either implementation's popup.
        """
        app = self.app
        tk = app.tk
        original_grab = str(tk.call('grab', 'current', app._w))
        kind = str(tk.call('tk', 'windowingsystem'))
        combo.winfo_toplevel().focus_force()
        app.update()
        pop = str(tk.call('ttk::combobox::PopdownWindow', combo._w))
        if tk.getboolean(tk.call('winfo', 'exists', pop + '.f.l')):
            self.assertEqual(str(tk.call('winfo', 'class', pop + '.f.l')), 'Listbox')
            tk.call('ttk::combobox::Post', combo._w)
            target = pop + '.f.l'
        elif kind == 'aqua' and tk.getboolean(tk.call('winfo', 'exists', pop + '.menu')):
            self.assertTrue(tk.call('info', 'commands', 'ttk::combobox::ConfigureAquaMenu'))
            tk.call('ttk::combobox::ConfigureAquaMenu', combo._w, max(100, combo.winfo_width()))
            tk.call('wm', 'geometry', pop, '180x100+20+20')
            tk.call('wm', 'deiconify', pop)
            target = pop + '.menu'
        else:
            self.fail(f'Unsupported combobox popup structure: {kind} {pop}')
        # Map/focus callbacks may complete the real listbox geometry and reveal
        # its selected item. Drain those before measuring its scroll range.
        app.update()
        tk.call('grab', 'set', pop)
        app.update()
        self.assertTrue(tk.getboolean(tk.call('winfo', 'viewable', pop)), pop)
        self.assertEqual(str(tk.call('grab', 'current', app._w)), pop)
        # This is the exact former failure: Tkinter cannot resolve a popup
        # created by Tcl rather than a Python BaseWidget constructor.
        with self.assertRaises(KeyError):
            app.grab_current()
        try:
            yield pop, target
        finally:
            if tk.getboolean(tk.call('winfo', 'exists', pop)):
                tk.call('ttk::combobox::Unpost', combo._w)
                tk.call('destroy', pop)
            if original_grab and tk.getboolean(tk.call('winfo', 'exists', original_grab)):
                tk.call('grab', 'set', original_grab)
            app.update()
            self.assertFalse(self.errors, self.errors)

    def test_gallery_native_wheel_still_animates_without_global_bindings(self):
        app = self.app
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.assertTrue(app.canvas.bind(sequence), sequence)
            self.assertFalse(app.bind_all(sequence), sequence)
        start = app.canvas.canvasy(0)
        self.wheel(app.canvas)
        self.wait_for(lambda: not app.smooth_scroll.active)
        self.assertGreater(app.canvas.canvasy(0), start)
        self.assertLess(len(app.cards), 80, 'The 7,444-item library must remain virtualized')

    def test_all_main_dropdown_popups_ignore_gallery_and_raw_widget_paths(self):
        app = self.app
        app.preview_count.set('2장')
        app.change_preview_count()
        app.scroll_view('moveto', 0.3)
        for combo in self.main_combos():
            with self.subTest(variable=str(combo.cget('textvariable'))):
                with self.popup(combo) as (pop, target):
                    before = app.canvas.canvasy(0)
                    with patch.object(app.smooth_scroll, 'scroll_by', wraps=app.smooth_scroll.scroll_by) as motion:
                        for raw in (pop, target, '.unregistered.native.widget'):
                            self.assertIsNone(app.wheel(SimpleNamespace(widget=raw, delta=-120, num=None)))
                        # A popup grab also blocks a directly queued gallery event.
                        self.assertIsNone(self.gallery_wheel())
                        self.wheel(target)
                        motion.assert_not_called()
                    self.assertAlmostEqual(app.canvas.canvasy(0), before, delta=1)

    def test_main_controls_keep_native_wheel_semantics_without_gallery_motion(self):
        app = self.app
        app.preview_count.set('2장')
        app.change_preview_count()
        combos = self.main_combos()
        entries = [widget for widget in descendants(app) if isinstance(widget, module.ttk.Entry)
                   and not isinstance(widget, module.ttk.Combobox)]
        targets = [app, app.tabs, app.thumbnail_controls, app.thumbnail_scale, app.fit_button,
                   app.thumbnail_edit_button, *entries, *combos]
        for target in targets:
            with self.subTest(widget=str(target), kind=target.winfo_class()):
                app.smooth_scroll.stop()
                with patch.object(app.smooth_scroll, 'scroll_by', wraps=app.smooth_scroll.scroll_by) as motion:
                    self.assertIsNone(app.wheel(SimpleNamespace(widget=target, delta=-120, num=None)))
                    self.wheel(target)
                    motion.assert_not_called()
                # Closed comboboxes may deliberately select another sort/count
                # and rebuild the gallery. Only accidental wheel motion is barred.
                self.assertFalse(app.smooth_scroll.active)

    def test_both_sidebar_lists_scroll_themselves(self):
        app = self.app
        for tree in (app.tree, app.favorite_list):
            with self.subTest(tree=str(tree)):
                for node in tree.get_children():
                    tree.delete(node)
                for index in range(180):
                    tree.insert('', 'end', text=f'Example folder {index:03d}')
                app.update()
                tree.yview_moveto(0.25)
                before = tree.yview()[0]
                gallery = app.canvas.canvasy(0)
                with patch.object(app.smooth_scroll, 'scroll_by', wraps=app.smooth_scroll.scroll_by) as motion:
                    self.wheel(tree)
                    motion.assert_not_called()
                self.assertGreater(tree.yview()[0], before)
                self.assertAlmostEqual(app.canvas.canvasy(0), gallery, delta=1)

    def test_native_scrollbars_operate_their_own_views(self):
        app = self.app
        for index in range(180):
            app.tree.insert('', 'end', text=f'Example folder {index:03d}')
        tree_scroll = next(widget for widget in descendants(app.sidebar)
                           if isinstance(widget, module.ttk.Scrollbar))
        app.update()
        for scrollbar, view in ((app.scroll, app.canvas), (tree_scroll, app.tree)):
            with self.subTest(scrollbar=str(scrollbar)):
                view.yview_moveto(0.3)
                before = view.yview()[0]
                gallery = app.canvas.canvasy(0)
                with patch.object(app.smooth_scroll, 'scroll_by', wraps=app.smooth_scroll.scroll_by) as motion:
                    scrollbar.event_generate('<Enter>')
                    self.wheel(scrollbar)
                    motion.assert_not_called()
                # Some Tk 8.6 themes have no scrollbar wheel class binding;
                # their actual arrow/drag command must still operate its view.
                if not scrollbar.bind_class(scrollbar.winfo_class(), '<MouseWheel>'):
                    command = app.tk.splitlist(scrollbar.cget('command'))
                    app.tk.call(*command, 'scroll', 1, 'units')
                    app.update()
                self.assertGreater(view.yview()[0], before)
                if view is app.tree:
                    self.assertAlmostEqual(app.canvas.canvasy(0), gallery, delta=1)

    def test_scrollbar_decimal_units_and_fractional_pages(self):
        app = self.app
        for amount, mode in (('3.0', 'units'), ('0.025', 'units'), ('-0.025', 'units'),
                             ('1', 'units'), ('0.5', 'pages'), ('-0.25', 'pages')):
            with self.subTest(amount=amount, mode=mode):
                app.scroll_view('moveto', 0.3)
                before = app.canvas.canvasy(0)
                self.gallery_wheel()
                self.assertTrue(app.smooth_scroll.active)
                app.scroll_view('scroll', amount, mode)
                step = 30 if mode == 'units' else app.canvas.winfo_height() * 0.9
                self.assertAlmostEqual(app.canvas.canvasy(0) - before, float(amount) * step, delta=1)
                self.assertFalse(app.smooth_scroll.active)
                self.pump(0.03)

    def test_leaving_canvas_focusing_controls_and_popup_grabs_stop_momentum(self):
        app = self.app
        for sequence in ('<Leave>', '<FocusOut>'):
            with self.subTest(sequence=sequence):
                self.gallery_wheel()
                self.assertTrue(app.smooth_scroll.active)
                app.canvas.event_generate(sequence)
                self.assertFalse(app.smooth_scroll.active)
                before = app.canvas.canvasy(0)
                self.pump(0.1)
                self.assertAlmostEqual(app.canvas.canvasy(0), before, delta=1)
        # A popup can take the grab between a wheel event and its first timer.
        with self.popup(self.main_combos()[0]):
            app.smooth_scroll.scroll_by(90)
            before = app.canvas.canvasy(0)
            self.wait_for(lambda: not app.smooth_scroll.active)
            self.assertAlmostEqual(app.canvas.canvasy(0), before, delta=1)

    def test_settings_all_tabs_native_controls_and_shortcut_capture_are_isolated(self):
        app = self.app
        app.open_settings()
        app.update()
        dialog = app.settings_window
        widgets = list(descendants(dialog))
        self.assertEqual(len(dialog.settings_tabs.tabs()), 5)
        self.assertFalse(any(isinstance(widget, module.tk.Canvas) for widget in widgets),
                         'Settings pages must not acquire scrolling canvas wrappers')
        gallery = app.canvas.canvasy(0)
        with patch.object(app.smooth_scroll, 'scroll_by', wraps=app.smooth_scroll.scroll_by) as motion:
            for tab in dialog.settings_tabs.tabs():
                dialog.settings_tabs.select(tab)
                app.update()
                for widget in widgets:
                    if widget.winfo_ismapped():
                        self.wheel(widget)
            for combo in (widget for widget in widgets if isinstance(widget, module.ttk.Combobox)):
                # Hidden notebook children still have valid popdown commands;
                # select the actual containing page before mapping their popup.
                page = combo
                while page.master is not dialog.settings_tabs:
                    page = page.master
                dialog.settings_tabs.select(page)
                app.update()
                with self.popup(combo) as (_pop, target):
                    is_list = str(app.tk.call('winfo', 'class', target)) == 'Listbox'
                    if is_list:
                        # The selected font may start at the end of the list;
                        # wheel downward from a known position with room below.
                        app.tk.call(target, 'yview', 'moveto', 0)
                        app.update_idletasks()
                    first = app.tk.splitlist(app.tk.call(target, 'yview')) if is_list else ()
                    overflow = is_list and float(first[1]) - float(first[0]) < 1 - 1e-9
                    # A coarse wheel tick also works with Tk 8.6 Aqua's pixel
                    # accumulator; no platform-specific tiny delta is required.
                    self.wheel(target, delta=-120)
                    if overflow:
                        after = app.tk.splitlist(app.tk.call(target, 'yview'))
                        wheel_lines = None
                        if sys.platform == 'win32':
                            import ctypes
                            lines = ctypes.c_uint()
                            if ctypes.windll.user32.SystemParametersInfoW(0x0068, 0, ctypes.byref(lines), 0):
                                wheel_lines = lines.value
                        if wheel_lines != 0:
                            details = (f'popup={target}, before={first}, after={after}, '
                                       f'height={app.tk.call("winfo", "height", target)}, '
                                       f'reqheight={app.tk.call("winfo", "reqheight", target)}, '
                                       f'rows={app.tk.call(target, "cget", "-height")}, '
                                       f'items={app.tk.call(target, "size")}, '
                                       f'bindtags={app.tk.call("bindtags", target)}, '
                                       f'focus={app.tk.call("focus")}, '
                                       f'grab={app.tk.call("grab", "current", app._w)}, '
                                       f'wheel lines={wheel_lines}')
                            self.assertGreater(float(after[0]), float(first[0]),
                                               'Native popup wheel did not move: ' + details)
                        # System wheel scrolling may be disabled. The real
                        # overflowing list must still support its own scrollbar.
                        app.tk.call(target, 'yview', 'moveto', 0)
                        app.tk.call(target, 'yview', 'scroll', 1, 'units')
                        direct = app.tk.splitlist(app.tk.call(target, 'yview'))
                        self.assertGreater(float(direct[0]), 0)
                    self.assertIsNone(self.gallery_wheel())
            dialog.settings_capture_shortcut(next(iter(dialog.shortcut_buttons)), 0)
            app.update()
            capture = dialog.shortcut_capture
            self.wheel(capture.key_entry)
            self.wheel(capture)
            self.assertFalse(capture.key_var.get())
            capture.settings_cancel()
            motion.assert_not_called()
        self.assertAlmostEqual(app.canvas.canvasy(0), gallery, delta=1)
        dialog.destroy()

    def open_editor(self):
        path = self.folder / 'Temporary-editor.cbz'
        with zipfile.ZipFile(path, 'w') as archive:
            for index, color in enumerate(('#ff3030', '#00c030', '#3060ff')):
                data = io.BytesIO()
                Image.new('RGB', (600, 900), color).save(data, 'PNG')
                archive.writestr(f'page-{index}.png', data.getvalue())
        editor = module.ThumbnailEditor(self.app, path, self.app.palette, slots=3, recipes={})
        self.app.thumbnail_editor_window = editor
        self.editors.append(editor)
        self.wait_for(lambda: editor._image is not None and not editor._busy)
        return editor

    def test_editor_zoom_preview_footer_and_modal_gallery_routing(self):
        app = self.app
        editor = self.open_editor()
        gallery = app.canvas.canvasy(0)
        before = editor._zoom
        self.wheel(editor.canvas, delta=1 if sys.platform == 'darwin' else 120)
        self.assertGreater(editor._zoom, before)
        zoom = editor._zoom
        self.assertEqual(editor._wheel(SimpleNamespace(widget=editor.canvas, delta=0, num=None,
                                                      x=8, y=8)), 'break')
        self.assertEqual(editor._zoom, zoom, 'A zero-delta wheel must not zoom out')
        with patch.object(app.smooth_scroll, 'scroll_by', wraps=app.smooth_scroll.scroll_by) as motion:
            for target in (editor.preview_canvas, editor.status_label, editor.cancel_button,
                           editor.filename_entry, editor.zoom_scale):
                self.wheel(target)
            self.assertIsNone(self.gallery_wheel())
            motion.assert_not_called()
        self.assertEqual(editor._zoom, zoom)
        self.assertAlmostEqual(app.canvas.canvasy(0), gallery, delta=1)
        editor.close()

    def test_editor_page_slot_ratio_popups_are_safe_including_close_during_popup(self):
        app = self.app
        for attribute in ('entry_combo', 'slot_combo', 'ratio_combo'):
            with self.subTest(combo=attribute):
                editor = self.open_editor()
                gallery = app.canvas.canvasy(0)
                with self.popup(getattr(editor, attribute)) as (_pop, target):
                    self.wheel(target)
                    zoom = editor._zoom
                    self.assertEqual(editor._wheel(SimpleNamespace(widget=editor.canvas, delta=120,
                                                                  num=None, x=8, y=8)), 'break')
                    self.assertEqual(editor._zoom, zoom, 'A nested popup must block queued image zoom')
                    self.assertIsNone(self.gallery_wheel())
                    editor.close()
                    self.assertFalse(editor.winfo_exists())
                self.assertAlmostEqual(app.canvas.canvasy(0), gallery, delta=1)

    def test_rename_original_name_text_scrolls_without_moving_gallery(self):
        app = self.app
        app.rename_file(self.paths[0])
        app.update()
        dialog = app.rename_window
        original = next(widget for widget in descendants(dialog) if isinstance(widget, module.tk.Text))
        original.configure(state='normal')
        original.delete('1.0', 'end')
        original.insert('1.0', '\n'.join(f'Example filename line {index}' for index in range(200)))
        original.configure(state='disabled')
        before = original.yview()[0]
        gallery = app.canvas.canvasy(0)
        # Text widgets accumulate tiny Aqua touchpad deltas before scrolling a
        # pixel; a coarse wheel event works consistently on every native Tk.
        self.wheel(original, delta=-120)
        self.pump()
        self.assertGreater(original.yview()[0], before)
        self.assertAlmostEqual(app.canvas.canvasy(0), gallery, delta=1)
        self.assertEqual(original.cget('state'), 'disabled')
        dialog.destroy()
        app.rename_window = None


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        # Windows cannot remove an open crash log from the temporary fixture.
        module.faulthandler.disable()
        module.FAULT_LOG.close()
        module.logging.shutdown()
        _settings.cleanup()
