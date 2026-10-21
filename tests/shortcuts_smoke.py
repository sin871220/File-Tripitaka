"""Exercise configurable shortcuts through real Tk events using temporary data.

Run with ``python tests/shortcuts_smoke.py`` on a desktop with Tk available.
No external viewer is launched and no file is sent to the real Trash.
"""
import io
import json
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
_settings = tempfile.TemporaryDirectory(prefix='file-tripitaka-shortcut-settings-')
os.environ['LOCALAPPDATA'] = _settings.name
import app as module
from PIL import Image

sys.excepthook = sys.__excepthook__


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class ShortcutSmoke(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix='file-tripitaka-shortcuts-')
        self.addCleanup(self.workspace.cleanup)
        self.library = Path(self.workspace.name).resolve()
        module.CONFIG.write_text(json.dumps({
            'double_click': '파일 위치 열기',
            'enter_action': '즐겨찾기 추가/해제',
            'space_action': '없음',
        }), 'utf-8')
        self.errors = []
        self.messages = []
        self.editors = []
        self.addCleanup(patch.stopall)
        patch.object(module, 'cover', lambda *args: Image.new('RGB', (80, 100), 'blue')).start()
        patch.object(module.App, 'load_favorite_metadata').start()
        patch.object(module.messagebox, 'showerror',
                     side_effect=lambda *args, **kwargs: self.messages.append(args)).start()
        # A failed isolation assertion must never operate on a real user file.
        self.trash = patch.object(module, 'trash_archive',
                                  side_effect=AssertionError('A shortcut test reached the real Trash path')).start()
        self.app = module.App()
        self.app.report_callback_exception = lambda *args: self.errors.append(args)
        self.addCleanup(self.close_app)
        self.app.update()

    def close_app(self):
        if self.app.winfo_exists():
            self.app.close()
        for editor in self.editors:
            editor._executor.shutdown(wait=True, cancel_futures=True)
        for pool in (self.app.pool, self.app.folder_pool, self.app.thumbnail_edit_pool):
            pool.shutdown(wait=True, cancel_futures=True)
        self.assertFalse(self.errors, self.errors)

    def wait_for(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            if predicate():
                self.assertFalse(self.errors, self.errors)
                return
            time.sleep(0.01)
        self.fail('Tk operation did not complete')

    def load(self, count=120, favorite_tab=False):
        app = self.app
        files = []
        for index in range(count):
            path = self.library / f'item-{index:03d}.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('page.txt', 'Temporary shortcut fixture')
            files.append(path)
        app.current_folder = str(self.library)
        app.folder.set(str(self.library))
        app.only_favorites.set(favorite_tab)
        app.active_tab = 'favorites' if favorite_tab else 'all'
        app.favorites = set(map(str, files)) if favorite_tab else set()
        app.pending_restore = None
        app.add_cards((files, {path: index for index, path in enumerate(files)},
                       {path: (1024, 1700000000) for path in files}))
        app.update()
        return files

    def key(self, sequence, widget=None):
        target = widget or self.app.canvas
        target.focus_force()
        self.app.update()
        target.event_generate(sequence)
        self.app.update()

    def settings_dialog(self):
        self.app.open_settings()
        self.app.update()
        return self.app.settings_window

    def cancel_settings(self, dialog):
        cancel = next(widget for widget in descendants(dialog)
                      if isinstance(widget, module.ttk.Button) and widget.cget('text') == '취소')
        cancel.invoke()
        self.app.update()

    def assignment(self, dialog, command, slot=0):
        return dialog.shortcut_vars[command][slot].get()

    def test_legacy_keys_dispatch_and_input_isolation(self):
        app = self.app
        files = self.load()
        app.select_card(files[2])
        with patch.object(app, 'execute_action') as execute:
            self.key('<Return>')
            execute.assert_called_once_with(files[2], '즐겨찾기 추가/해제')
            execute.reset_mock()
            # Windows Tk reports keypad Enter as Return (VK_RETURN); it has no
            # native KP_Enter keycode to synthesize. Alias coverage also lives
            # in test_shortcuts, independent of the platform's GUI key map.
            self.key('<Return>' if sys.platform == 'win32' else '<KP_Enter>')
            execute.assert_called_once_with(files[2], '즐겨찾기 추가/해제')
            execute.reset_mock()
            self.key('<space>')
            execute.assert_not_called()
            app.double_click(files[2])
            execute.assert_called_once_with(files[2], '파일 위치 열기')

        with patch.object(app, 'rename_file') as rename, patch.object(app, 'delete_file') as delete:
            self.key('<F2>')
            rename.assert_called_once()
            self.key('<Delete>')
            delete.assert_called_once()
            rename.reset_mock()
            delete.reset_mock()
            search = next(widget for widget in descendants(app)
                          if isinstance(widget, module.ttk.Entry)
                          and str(widget.cget('textvariable')) == str(app.query))
            search.insert(0, 'item')
            search.icursor(0)
            self.key('<Delete>', search)
            self.key('<F2>', search)
            self.assertEqual(search.get(), 'tem')
            delete.assert_not_called()
            rename.assert_not_called()
        self.trash.assert_not_called()

    def test_favorite_key_removal_keeps_viewport_and_next_selection(self):
        app = self.app
        self.load(favorite_tab=True)
        app.canvas.yview_moveto(.4)
        app.refresh_visible()
        index = int(max(0, app.canvas.canvasy(0)) // app.row_height()) * app.columns() + app.columns()
        selected = app.filtered[index]
        next_path = app.filtered[index + 1]
        app.select_card(selected)
        before = {card[0]: card for card in app.cards.values()}
        top = app.canvas.canvasy(0)
        generation = app.generation
        with patch.object(app, 'apply_search', wraps=app.apply_search) as refresh:
            self.key('<Return>')
            refresh.assert_not_called()
        self.assertNotIn(str(selected), app.favorites)
        self.assertNotIn(selected, app.filtered)
        self.assertEqual(app.selected_path, next_path)
        self.assertEqual(app.canvas.canvasy(0), top)
        self.assertEqual(app.generation, generation)
        after = {card[0]: card for card in app.cards.values()}
        survivors = before.keys() & after.keys()
        self.assertTrue(survivors)
        for path in survivors:
            self.assertEqual(before[path], after[path])
        self.assertTrue(selected.is_file())

    def test_view_shortcuts_toggle_with_or_without_a_selected_file(self):
        app = self.app
        previous = {command: list(keys) for command, keys in app.settings['shortcuts'].items()}
        dialog = self.settings_dialog()
        self.assertIn('sidebar', dialog.shortcut_buttons)
        self.assertIn('fit', dialog.shortcut_buttons)
        dialog.settings_assign_shortcut('sidebar', 0, 'F8')
        dialog.settings_assign_shortcut('fit', 0, 'F9')
        dialog.settings_apply()
        app.update()
        for command, keys in previous.items():
            if command not in ('sidebar', 'fit'):
                self.assertEqual(app.settings['shortcuts'][command], keys)
        self.assertEqual(app.filtered, [])
        self.assertIsNone(app.selected_path)
        was_hidden = app.sidebar_hidden
        self.key('<F8>')
        self.assertEqual(app.sidebar_hidden, not was_hidden)
        self.assertEqual(str(app.sidebar) in app.panes.panes(), was_hidden)
        self.key('<F8>')
        self.assertEqual(app.sidebar_hidden, was_hidden)
        self.assertFalse(app.fit_enabled.get())
        self.key('<F9>')
        self.assertTrue(app.fit_enabled.get())
        self.assertTrue(app.fit_button.instate(['selected']))
        self.assertEqual(app.fit_button.cget('text'), '창에 맞춤 ON')
        self.key('<F9>')
        self.assertFalse(app.fit_enabled.get())
        self.assertIsNone(app.fit_columns)
        self.assertEqual(app.fit_button.cget('text'), '창에 맞춤 OFF')
        files = self.load(count=12)
        app.select_card(files[2])
        self.key('<F8>')
        self.key('<F8>')
        self.key('<F9>')
        self.key('<F9>')
        self.assertEqual(app.selected_path, files[2])
        self.assertEqual(app.filtered, files)
        saved = json.loads(module.CONFIG.read_text('utf-8'))
        self.assertEqual(saved['shortcuts']['sidebar'], ['F8'])
        self.assertEqual(saved['shortcuts']['fit'], ['F9'])

    def test_view_shortcuts_work_across_the_main_window_before_gallery_focus(self):
        app = self.app
        app.settings['shortcuts']['sidebar'] = ['F8']
        app.settings['shortcuts']['fit'] = ['F9']
        app.refresh_shortcuts()
        self.assertIsNone(app.selected_path)
        self.assertEqual(app.filtered, [])

        # These targets never need a preceding click on the thumbnail canvas.
        dynamic = module.ttk.Label(app, text='Newly mapped main-window widget')
        dynamic.pack()
        app.update()
        targets = (app, app.tree, app.favorite_list, app.sidebar_toggle,
                   app.fit_button, app.canvas, dynamic)
        for target in targets:
            with self.subTest(widget=target.winfo_class()):
                self.assertFalse(app.sidebar_hidden)
                with patch.object(app, 'activate_command', wraps=app.activate_command) as activate:
                    self.key('<F8>', target)
                    self.assertTrue(app.sidebar_hidden)
                    activate.assert_called_once_with('sidebar')
                # A hidden sidebar cannot retain keyboard focus. The next key
                # still works without another mouse click.
                app.focus_get().event_generate('<F8>')
                app.update()
                self.assertFalse(app.sidebar_hidden)
                self.assertFalse(app.fit_enabled.get())
                with patch.object(app, 'activate_command', wraps=app.activate_command) as activate:
                    self.key('<F9>', target)
                    self.assertTrue(app.fit_enabled.get())
                    activate.assert_called_once_with('fit')
                self.key('<F9>', target)
                self.assertFalse(app.fit_enabled.get())
        dynamic.destroy()

    def test_view_shortcuts_override_button_and_tree_keys_once(self):
        app = self.app
        for command, keys in app.settings['shortcuts'].items():
            app.settings['shortcuts'][command] = [key for key in keys if key not in ('Enter', 'Space')]
        app.settings['shortcuts']['sidebar'] = ['Enter']
        app.settings['shortcuts']['fit'] = ['Space']
        app.refresh_shortcuts()

        for target in (app.fit_button, app.sidebar_toggle, app.canvas):
            with self.subTest(space_target=target.winfo_class()):
                with patch.object(app, 'activate_command', wraps=app.activate_command) as activate:
                    self.key('<space>', target)
                    target.event_generate('<KeyRelease-space>')
                    app.update()
                    self.assertTrue(app.fit_enabled.get())
                    self.assertFalse(app.sidebar_hidden)
                    activate.assert_called_once_with('fit')
                self.key('<space>', target)
                target.event_generate('<KeyRelease-space>')
                app.update()
                self.assertFalse(app.fit_enabled.get())

        ordinary_action = []
        ordinary_button = module.ttk.Button(app, text='Ordinary button',
                                           command=lambda: ordinary_action.append(True))
        ordinary_button.pack()
        app.update()
        self.key('<space>', ordinary_button)
        ordinary_button.event_generate('<KeyRelease-space>')
        app.update()
        self.assertTrue(app.fit_enabled.get())
        self.assertEqual(ordinary_action, [])
        ordinary_button.destroy()

        # A view shortcut must precede the Treeview's own Return binding.
        for target in (app.tree, app.favorite_list):
            tree_action = []
            target.bind('<Return>', lambda event: tree_action.append(True))
            self.key('<Return>', target)
            self.assertTrue(app.sidebar_hidden)
            self.assertEqual(tree_action, [])
            self.assertEqual(app.focus_get(), app.canvas)
            self.key('<Return>', app)
            self.assertFalse(app.sidebar_hidden)

    def test_window_view_shortcuts_protect_inputs_dialogs_and_file_actions(self):
        app = self.app
        app.settings['shortcuts']['sidebar'] = ['F8']
        app.settings['shortcuts']['fit'] = ['F9']
        app.refresh_shortcuts()
        holder = module.ttk.Frame(app)
        holder.pack()
        inputs = [widget for widget in descendants(app)
                  if isinstance(widget, module.ttk.Entry)]
        inputs.extend((module.tk.Entry(holder), module.tk.Text(holder, height=1, width=12),
                       module.tk.Spinbox(holder, from_=0, to=5),
                       module.ttk.Spinbox(holder, from_=0, to=5),
                       module.ttk.Combobox(holder, state='readonly', values=('A', 'B'))))
        for widget in inputs:
            if widget.master is holder:
                widget.pack(side='left')
        app.update()
        for target in inputs:
            with self.subTest(input_class=target.winfo_class()):
                self.key('<F8>', target)
                self.key('<F9>', target)
                self.assertFalse(app.sidebar_hidden)
                self.assertFalse(app.fit_enabled.get())
        holder.destroy()

        dialog = self.settings_dialog()
        self.key('<F8>', dialog)
        self.key('<F9>', dialog)
        self.assertFalse(app.sidebar_hidden)
        self.assertFalse(app.fit_enabled.get())
        # Even a queued main-window key must be harmless while a modal grab is active.
        for target in (app, app.canvas):
            self.key('<F8>', target)
            self.key('<F9>', target)
        self.assertFalse(app.sidebar_hidden)
        self.assertFalse(app.fit_enabled.get())
        self.cancel_settings(dialog)

        files = self.load(count=3)
        app.select_card(files[0])
        with patch.object(app, 'rename_file') as rename:
            for target in (app, app.tree, app.favorite_list, app.fit_button):
                self.key('<F2>', target)
            rename.assert_not_called()
            self.key('<F2>', app.canvas)
            rename.assert_called_once()
        self.trash.assert_not_called()

    def test_capture_conflicts_cancel_and_defaults_are_drafts(self):
        from shortcuts import defaults

        app = self.app
        self.load()
        app.canvas.yview_moveto(.4)
        app.refresh_visible()
        top = app.canvas.canvasy(0)
        generation = app.generation
        before = dict(app.cards)
        saved = json.loads(json.dumps(app.settings))
        dialog = self.settings_dialog()
        original_rename = self.assignment(dialog, 'rename')
        dialog.settings_capture_shortcut('rename', 0)
        app.update()
        capture = dialog.shortcut_capture
        self.key('<F8>', capture.key_entry)
        self.assertEqual(capture.key_var.get(), 'F8')
        capture.settings_cancel()
        app.update()
        self.assertFalse(capture.winfo_exists())
        self.assertTrue(dialog.winfo_exists())
        self.assertEqual(self.assignment(dialog, 'rename'), original_rename)

        dialog.settings_capture_shortcut('favorite', 1)
        app.update()
        capture = dialog.shortcut_capture
        self.key('<space>', capture.key_entry)
        self.assertEqual(capture.key_var.get(), 'Space')
        capture.settings_accept()
        app.update()
        self.assertEqual(self.assignment(dialog, 'favorite', 1), 'Space')
        dialog.settings_capture_shortcut('favorite', 1)
        app.update()
        capture = dialog.shortcut_capture
        capture.settings_clear()
        app.update()
        self.assertEqual(self.assignment(dialog, 'favorite', 1), '')

        dialog.settings_capture_shortcut('rename', 0)
        app.update()
        capture = dialog.shortcut_capture
        self.key('<F8>', capture.key_entry)
        capture.settings_accept()
        app.update()
        self.assertFalse(capture.winfo_exists())
        self.assertEqual(self.assignment(dialog, 'rename'), 'F8')
        original_favorite = self.assignment(dialog, 'favorite', 1)
        message_count = len(self.messages)
        dialog.settings_capture_shortcut('favorite', 1)
        app.update()
        capture = dialog.shortcut_capture
        self.key('<F8>', capture.key_entry)
        capture.settings_accept()
        app.update()
        self.assertEqual(self.assignment(dialog, 'favorite', 1), original_favorite)
        self.assertGreater(len(self.messages), message_count)
        self.assertTrue(capture.winfo_exists())
        self.assertTrue(capture.error_var.get())
        capture.settings_cancel()
        app.update()

        dialog.settings_capture_shortcut('rename', 0)
        app.update()
        capture = dialog.shortcut_capture
        self.key('<Escape>', capture.key_entry)
        self.assertFalse(capture.winfo_exists())
        self.assertTrue(dialog.winfo_exists())
        self.assertEqual(dialog.grab_current(), dialog)

        dialog.settings_capture_shortcut('favorite', 1)
        app.update()
        capture = dialog.shortcut_capture
        self.key('<Control-Escape>', capture.key_entry)
        self.assertTrue(capture.winfo_exists())
        self.assertEqual(capture.key_var.get(), 'Ctrl+Escape')
        capture.settings_cancel()
        app.update()

        dialog.settings_assign_shortcut('thumbnail_edit', 0, 'F9')
        dialog.settings_assign_shortcut('thumbnail_edit', 1, 'Ctrl+E')
        dialog.settings_reset_shortcuts()
        app.update()
        for command, keys in defaults().items():
            self.assertEqual([variable.get() for variable in dialog.shortcut_vars[command]
                              if variable.get()], keys)
        self.assertEqual(app.settings, saved)
        self.cancel_settings(dialog)
        self.assertEqual(app.settings, saved)
        self.assertEqual(app.canvas.canvasy(0), top)
        self.assertEqual(app.generation, generation)
        self.assertEqual(app.cards, before)

    def test_apply_persists_custom_keys_and_preserves_double_click(self):
        from shortcuts import legacy_actions

        app = self.app
        files = self.load()
        app.canvas.yview_moveto(.4)
        app.refresh_visible()
        selected = next(iter(app.cards.values()))[0]
        app.select_card(selected)
        top = app.canvas.canvasy(0)
        generation = app.generation
        before = dict(app.cards)
        double_click = app.settings['double_click']
        dialog = self.settings_dialog()
        dialog.settings_assign_shortcut('rename', 0, 'F8')
        self.assertIn('thumbnail_edit', dialog.shortcut_buttons)
        self.assertEqual([self.assignment(dialog, 'thumbnail_edit', slot) for slot in (0, 1)], ['', ''])
        self.assertTrue(any(isinstance(widget, module.ttk.Label)
                            and widget.cget('text') == '썸네일 영역 편집'
                            for widget in descendants(dialog)))
        dialog.settings_assign_shortcut('thumbnail_edit', 0, 'F9')
        dialog.settings_assign_shortcut('thumbnail_edit', 1, 'Ctrl+F10')
        with self.assertRaisesRegex(ValueError, '중복'):
            dialog.settings_assign_shortcut('thumbnail_edit', 1, 'F8')
        self.assertEqual(self.assignment(dialog, 'thumbnail_edit', 1), 'Ctrl+F10')
        dialog.settings_apply()
        app.update()
        self.assertFalse(dialog.winfo_exists())
        self.assertEqual(app.settings['double_click'], double_click)
        self.assertEqual(app.settings['shortcuts']['rename'], ['F8'])
        self.assertEqual(app.settings['shortcuts']['thumbnail_edit'], ['F9', 'Ctrl+F10'])
        self.assertEqual(app.settings['shortcuts']['favorite'], ['Enter'])
        self.assertEqual(legacy_actions(app.settings['shortcuts'])['space_action'], '없음')
        self.assertEqual(app.canvas.canvasy(0), top)
        self.assertEqual(app.generation, generation)
        self.assertEqual(app.cards, before)
        with patch.object(app, 'rename_file') as rename:
            self.key('<F2>')
            rename.assert_not_called()
            self.key('<F8>')
            rename.assert_called_once()

        with patch.object(module.tk.Menu, 'tk_popup'):
            app.context(SimpleNamespace(x_root=0, y_root=0), selected)
        menu = app.context_menu
        rename_item = next(index for index in range(menu.index('end') + 1)
                           if menu.type(index) == 'command'
                           and menu.entrycget(index, 'label') == '파일 이름 바꾸기')
        self.assertEqual(menu.entrycget(rename_item, 'accelerator'), 'F8')
        editor_item = next(index for index in range(menu.index('end') + 1)
                           if menu.type(index) == 'command'
                           and menu.entrycget(index, 'label') == '썸네일 영역 편집')
        self.assertEqual(menu.entrycget(editor_item, 'accelerator'), 'F9, Ctrl+F10')

        app.close()
        saved = json.loads(module.CONFIG.read_text('utf-8'))
        self.assertEqual(saved['shortcuts']['rename'], ['F8'])
        self.assertEqual(saved['shortcuts']['thumbnail_edit'], ['F9', 'Ctrl+F10'])
        self.assertEqual(saved['shortcuts']['favorite'], ['Enter'])
        self.assertEqual(saved['space_action'], '없음')
        self.assertEqual(saved['double_click'], double_click)
        # Do not start a background scan when checking a restored preference.
        saved['folder'] = ''
        module.CONFIG.write_text(json.dumps(saved), 'utf-8')
        self.app = module.App()
        app = self.app
        app.report_callback_exception = lambda *args: self.errors.append(args)
        app.update()
        self.assertEqual(app.settings['shortcuts']['rename'], ['F8'])
        self.assertEqual(app.settings['shortcuts']['thumbnail_edit'], ['F9', 'Ctrl+F10'])
        self.assertEqual(app.settings['shortcuts']['favorite'], ['Enter'])
        self.assertEqual(app.settings['double_click'], double_click)
        self.load(count=3)
        app.select_card(files[0])
        with patch.object(app, 'rename_file') as rename:
            self.key('<F8>')
            rename.assert_called_once()
        with patch.object(app, 'edit_thumbnail') as edit:
            self.key('<F9>')
            # Aqua may synthesize extra Option bits for printable keysyms;
            # a function key exercises Ctrl dispatch without layout ambiguity.
            self.key('<Control-F10>')
            self.assertEqual(edit.call_count, 2)

    def test_editor_shortcut_opens_once_preserves_view_and_protects_inputs_and_modals(self):
        app = self.app
        app.settings['shortcuts']['thumbnail_edit'] = ['F8']
        app.refresh_shortcuts()
        self.key('<F8>')
        self.assertIsNone(app.thumbnail_editor_window, 'No file selection must be harmless')
        self.load()
        app.canvas.yview_moveto(.4)
        app.refresh_visible()
        selected = next(iter(app.cards.values()))[0]
        image = io.BytesIO()
        Image.new('RGB', (600, 900), '#3070b0').save(image, 'PNG')
        with zipfile.ZipFile(selected, 'w') as archive:
            archive.writestr('page.png', image.getvalue())
        app.select_card(selected)
        top = app.canvas.canvasy(0)
        generation = app.generation
        search = next(widget for widget in descendants(app)
                      if isinstance(widget, module.ttk.Entry)
                      and str(widget.cget('textvariable')) == str(app.query))
        self.key('<F8>', search)
        self.assertIsNone(app.thumbnail_editor_window)
        for target in (app.tree, app.favorite_list, app.thumbnail_edit_button):
            self.key('<F8>', target)
            self.assertIsNone(app.thumbnail_editor_window)
        dialog = self.settings_dialog()
        self.key('<F8>', dialog)
        self.key('<F8>', app.canvas)
        self.assertIsNone(app.thumbnail_editor_window)
        self.cancel_settings(dialog)

        # Use actual Tk dispatch and an actual temporary PNG archive to verify
        # the shortcut reaches the editor rather than another file action.
        self.key('<F8>')
        editor = app.thumbnail_editor_window
        self.assertIsNotNone(editor)
        self.editors.append(editor)
        self.wait_for(lambda: editor._image is not None and not editor._busy)
        self.assertIs(app.grab_current(), editor)
        self.assertEqual(app.canvas.canvasy(0), top)
        self.assertEqual(app.selected_path, selected)
        self.assertEqual(app.generation, generation)
        with patch.object(module, 'ThumbnailEditor', wraps=module.ThumbnailEditor) as constructor:
            # A queued gallery key during a modal editor must not start another
            # editor. Calling the same command directly also reuses that editor.
            self.key('<F8>', app.canvas)
            app.activate_command('thumbnail_edit')
            app.update()
            constructor.assert_not_called()
            self.assertIs(app.thumbnail_editor_window, editor)
        editor.close()
        app.update()
        self.assertEqual(app.canvas.canvasy(0), top)
        self.assertEqual(app.selected_path, selected)
        self.assertFalse(self.messages, self.messages)

    def test_settings_layout_at_large_font_in_both_languages(self):
        from localization import set_language
        from preferences import PALETTES

        app = self.app
        app.commit_preferences('다크', app.settings['double_click'], '', '', app.recursive.get(),
                               typography=dict(family='', size=24))
        for theme, language in ((theme, language) for theme in PALETTES
                                for language in ('ko', 'en')):
            with self.subTest(theme=theme, language=language):
                app.settings['theme'] = theme
                app.apply_theme()
                app.settings['language'] = language
                app.apply_language()
                dialog = self.settings_dialog()
                self.assertFalse(any(isinstance(widget, (module.tk.Canvas, module.ttk.Scrollbar))
                                     for widget in descendants(dialog)))
                self.assertEqual(len(dialog.settings_tabs.tabs()), 5)
                self.assertEqual(dialog.action_var.get(), '파일 위치 열기')
                self.assertNotIn('없음', tuple(dialog.action_box.cget('values')))
                self.assertEqual(dialog.shortcut_buttons['reveal'][0].cget('text'),
                                 '없음' if language == 'ko' else 'None')
                for tab in dialog.settings_tabs.tabs():
                    dialog.settings_tabs.select(tab)
                    app.update()
                    left, top = dialog.winfo_rootx(), dialog.winfo_rooty()
                    right, bottom = left + dialog.winfo_width(), top + dialog.winfo_height()
                    for widget in descendants(dialog):
                        if not widget.winfo_ismapped():
                            continue
                        self.assertGreaterEqual(widget.winfo_rootx(), left)
                        self.assertGreaterEqual(widget.winfo_rooty(), top)
                        self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right)
                        self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom)
                dialog.destroy()
                app.update()
        set_language('ko')


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        __import__('faulthandler').disable()
        module.FAULT_LOG.close()
        __import__('logging').shutdown()
        _settings.cleanup()
