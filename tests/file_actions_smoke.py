"""Exercise file actions through Tk without touching the user's library or Trash.

Run with ``python tests/file_actions_smoke.py`` on a desktop with Tk available.
All settings, archives, and the fake Trash live in temporary directories.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_settings = tempfile.TemporaryDirectory(prefix='file-tripitaka-actions-settings-')
os.environ['LOCALAPPDATA'] = _settings.name
import app as module
from dialog_geometry import _workarea
from localization import set_language
from PIL import Image

sys.excepthook = sys.__excepthook__


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class FileActionsSmoke(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix='file-tripitaka-actions-')
        self.addCleanup(self.workspace.cleanup)
        self.base = Path(self.workspace.name).resolve()
        self.library = self.base / 'library'
        self.outside = self.base / 'elsewhere'
        self.trash = self.base / 'fake-trash'
        for folder in (self.library, self.outside, self.trash):
            folder.mkdir()
        module.CONFIG.unlink(missing_ok=True)
        self.errors = []
        self.messages = []
        self.addCleanup(patch.stopall)
        patch.object(module, 'cover', lambda *args: Image.new('RGB', (80, 100), 'blue')).start()
        # Tests explicitly deliver metadata results, avoiding timing-dependent I/O.
        patch.object(module.App, 'load_favorite_metadata').start()
        patch.object(module.messagebox, 'showerror', side_effect=lambda *args, **kwargs: self.messages.append(args)).start()
        self.confirm = patch.object(module.messagebox, 'askyesno', return_value=True).start()
        self.move_to_trash = patch.object(module, 'trash_archive', side_effect=self.fake_trash).start()
        self.app = module.App()
        self.app.report_callback_exception = lambda *args: self.errors.append(args)
        self.addCleanup(self.close_app)
        self.app.update()

    def close_app(self):
        app = self.app
        if app.winfo_exists():
            if getattr(app, 'rename_window', None) is not None:
                app.rename_window.destroy()
                app.rename_window = None
            app.close()
        self.assertFalse(self.errors, self.errors)

    def fake_trash(self, path):
        path = Path(path)
        self.assertTrue(path.is_relative_to(self.base), 'Never trash a non-fixture path')
        path.rename(self.trash / path.name)

    def archive(self, name, folder=None):
        path = (folder or self.library) / name
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('page.txt', 'Temporary file-action fixture')
        return path

    def load(self, files, favorites=(), favorite_tab=False):
        app = self.app
        app.current_folder = str(self.library)
        app.folder.set(str(self.library))
        app.query.set('')
        if app.search_job is not None:
            app.after_cancel(app.search_job)
            app.search_job = None
        app.sort_order.set('이름 오름차순')
        app.favorites = {str(path) for path in favorites}
        app.only_favorites.set(favorite_tab)
        app.active_tab = 'favorites' if favorite_tab else 'all'
        app.pending_restore = None
        app.views.clear()
        app.tab_views.clear()
        app.metadata.clear()
        app.modified.clear()
        app.preview_errors.clear()
        stats = {path: path.stat() for path in set(files) | set(favorites)}
        metadata = {path: (stat.st_size, stat.st_mtime) for path, stat in stats.items()}
        modified = {path: stat.st_mtime_ns for path, stat in stats.items()}
        app.add_cards((list(files), modified, metadata))
        app.update()
        return modified, metadata

    def rename_dialog(self, path, name):
        app = self.app
        self.assertEqual(app.rename_file(path), 'break')
        dialog = app.rename_window
        entry = next(child for child in descendants(dialog) if isinstance(child, module.ttk.Entry))
        self.assertEqual(entry.get(), path.stem)
        entry.delete(0, 'end')
        entry.insert(0, name)
        commit = next(child for child in descendants(dialog)
                      if isinstance(child, module.ttk.Button) and child.cget('text') in ('이름 바꾸기', 'Rename'))
        return dialog, commit

    def assert_survivors_retained(self, before):
        after = {card[0]: card for card in self.app.cards.values()}
        survivors = before.keys() & after.keys()
        self.assertTrue(survivors)
        for path in survivors:
            self.assertEqual(before[path], after[path], path)

    def test_rename_dialog_size_and_original_name_copy(self):
        app = self.app
        files = [self.archive('short.zip'), self.archive('a' * 245 + '.zip'),
                 self.archive('한字a-' * 30 + '.zip'),
                 self.archive('자료-Collection-' * 3 + '.zip')]
        self.load(files)
        app.font_size = 24
        app.ui_font = module.configure_fonts(app, app.ui_font, app.font_size)
        for language in ('ko', 'en'):
            app.settings['language'] = language
            app.apply_language()
            for theme in ('라이트', '다크', '네이비', '블루'):
                app.settings['theme'] = theme
                app.apply_theme()
                initial_widths = {}
                for path in files:
                    with self.subTest(language=language, theme=theme, filename=path.name):
                        app.rename_file(path)
                        dialog = app.rename_window
                        app.update()
                        original = next(child for child in descendants(dialog)
                                        if isinstance(child, module.tk.Text))
                        entry = next(child for child in descendants(dialog)
                                     if isinstance(child, module.ttk.Entry))
                        buttons = [child for child in descendants(dialog)
                                   if isinstance(child, module.ttk.Button)]
                        area = _workarea(app)
                        available_width, available_height = area[2] - area[0], area[3] - area[1]
                        self.assertEqual(tuple(map(bool, dialog.resizable())), (True, True))
                        self.assertEqual(str(original.cget('state')), 'disabled')
                        self.assertEqual(original.cget('wrap'), 'char')
                        self.assertEqual(original.get('1.0', 'end-1c'), path.name)
                        self.assertEqual(original.cget('bg'), app.palette['panel'])
                        self.assertEqual(original.cget('fg'), app.palette['fg'])
                        original.delete('1.0', 'end')
                        original.insert('1.0', 'must not replace the original name')
                        self.assertEqual(original.get('1.0', 'end-1c'), path.name)

                        def assert_visible():
                            self.assertLessEqual(dialog.winfo_width(), available_width)
                            self.assertLessEqual(dialog.winfo_height(), available_height)
                            last_line = original.dlineinfo('end-1c')
                            self.assertIsNotNone(last_line, 'The complete original name must be visible')
                            self.assertLessEqual(last_line[1] + last_line[3], original.winfo_height())
                            for widget in [original, entry, *buttons]:
                                x = widget.winfo_rootx() - dialog.winfo_rootx()
                                y = widget.winfo_rooty() - dialog.winfo_rooty()
                                self.assertGreaterEqual(x, 0)
                                self.assertGreaterEqual(y, 0)
                                self.assertLessEqual(x + widget.winfo_width(), dialog.winfo_width())
                                self.assertLessEqual(y + widget.winfo_height(), dialog.winfo_height())

                        assert_visible()
                        initial_widths[path] = dialog.winfo_width()
                        name_font = module.tkfont.Font(root=dialog, font=original.cget('font'))
                        text_width = name_font.measure(path.name)
                        first_line = original.dlineinfo('1.0')
                        last_line = original.dlineinfo('end-1c')
                        if text_width <= available_width - 80:
                            self.assertEqual(last_line[1], first_line[1],
                                             'A name that fits this monitor must initially use one line')
                        elif text_width > available_width:
                            self.assertGreater(last_line[1], first_line[1],
                                               'Names wider than the monitor must wrap')
                        # Exercise a real mouse drag before checking select-all.
                        original.focus_force()
                        app.update()
                        first, last = original.bbox('1.1'), original.bbox('1.4')
                        y = first[1] + first[3] // 2
                        original.event_generate('<ButtonPress-1>', x=first[0] + 1, y=y)
                        original.event_generate('<B1-Motion>', x=last[0] + 1, y=y, state=0x100)
                        original.event_generate('<ButtonRelease-1>', x=last[0] + 1, y=y)
                        app.update()
                        self.assertEqual(original.get('sel.first', 'sel.last'), path.name[1:4])
                        original.event_generate('<Control-a>')
                        app.update()
                        self.assertEqual((original.index('sel.first'), original.index('sel.last')),
                                         ('1.0', original.index('end-1c')))
                        original.event_generate('<<Copy>>')
                        app.update()
                        self.assertEqual(app.clipboard_get(), path.name)
                        entry.delete(0, 'end')
                        entry.insert(0, 'editable-new-name')
                        self.assertEqual(entry.get(), 'editable-new-name')
                        # Resizing must reflow the name without pushing fixed
                        # controls outside the window, even below its minimum.
                        initial_width = dialog.winfo_width()
                        narrow = max(dialog.minsize()[0], min(initial_width, 420))
                        wide = min(available_width - 40, max(initial_width + 180, 700))
                        for width in (wide, narrow, wide):
                            dialog.geometry(f'{width}x1')
                            app.update()
                            self.assertGreaterEqual(dialog.winfo_height(), dialog.minsize()[1])
                            assert_visible()
                        cancel = next(button for button in buttons
                                      if button.cget('text') in ('취소', 'Cancel'))
                        cancel.invoke()
                        self.assertFalse(dialog.winfo_exists())
                        self.assertTrue(path.is_file())
                if initial_widths[files[0]] + 10 < available_width - 40:
                    self.assertGreater(initial_widths[files[1]], initial_widths[files[0]],
                                       'A long original name should open a wider dialog')
        set_language('ko')

    def test_file_actions(self):
        app = self.app
        files = [self.archive(f'item-{index:03d}.zip') for index in range(120)]
        with self.subTest('rename updates paths and preserves scroll and surviving cards'):
            self.load(files, favorites=files)
            app.canvas.yview_moveto(.4)
            app.refresh_visible()
            index = int(max(0, app.canvas.canvasy(0)) // app.row_height()) * app.columns() + app.columns()
            old = app.filtered[index]
            new = old.with_stem(old.stem + '-renamed')
            app.select_card(old)
            old_metadata = app.metadata[old]
            app.preview_errors.add(str(old))
            app.views['other-folder'] = dict(anchor=str(old), selected=str(old))
            app.tab_views['other-folder'] = {'all': dict(anchor=str(old), selected=str(old))}
            app.tab_views['__global_favorites__'] = {'favorites': dict(anchor=str(old), selected=str(old))}
            app.pending_restore = dict(anchor=str(old), selected=str(old))
            before = {card[0]: card for card in app.cards.values()}
            top = app.canvas.canvasy(0)
            generation = app.generation
            revision = app.file_revision
            dialog, commit = self.rename_dialog(old, new.stem)
            with patch.object(app, 'apply_search', wraps=app.apply_search) as refresh:
                commit.invoke()
                refresh.assert_not_called()
            self.assertFalse(dialog.winfo_exists())
            self.assertTrue(new.is_file())
            self.assertFalse(old.exists())
            self.assertNotIn(old, app.files)
            self.assertIn(new, app.files)
            self.assertNotIn(old, app.filtered)
            self.assertIn(new, app.filtered)
            self.assertEqual(app.selected_path, new)
            self.assertNotIn(str(old), app.favorites)
            self.assertIn(str(new), app.favorites)
            self.assertNotIn(old, app.modified)
            self.assertNotIn(old, app.metadata)
            self.assertEqual(app.metadata[new], old_metadata)
            self.assertNotIn(str(old), app.preview_errors)
            self.assertIn(str(new), app.preview_errors)
            for view in (app.views['other-folder'], app.tab_views['other-folder']['all'],
                         app.tab_views['__global_favorites__']['favorites'], app.pending_restore):
                self.assertEqual((view['anchor'], view['selected']), (str(new), str(new)))
            self.assertEqual(app.canvas.canvasy(0), top)
            self.assertEqual(app.generation, generation)
            self.assertEqual(app.file_revision, revision + 1)
            self.assert_survivors_retained(before)
            settings = json.loads(module.CONFIG.read_text('utf-8'))
            self.assertIn(str(new), settings['file_favorites'])
            self.assertNotIn(str(old), settings['file_favorites'])

        with self.subTest('rename conflict stays in dialog without changing files'):
            existing = app.filtered[index + 1]
            revision = app.file_revision
            dialog, commit = self.rename_dialog(new, existing.stem)
            commit.invoke()
            self.assertTrue(dialog.winfo_exists())
            self.assertTrue(new.exists() and existing.exists())
            self.assertEqual(app.file_revision, revision)
            self.assertTrue(self.messages)
            cancel = next(child for child in descendants(dialog)
                          if isinstance(child, module.ttk.Button) and child.cget('text') == '취소')
            cancel.invoke()
            self.assertFalse(dialog.winfo_exists())

        with self.subTest('delete cancel and native-trash failure leave UI and file untouched'):
            app.select_card(new)
            before = dict(app.cards)
            top = app.canvas.canvasy(0)
            revision = app.file_revision
            self.confirm.return_value = False
            app.delete_file()
            self.move_to_trash.assert_not_called()
            self.assertEqual(app.cards, before)
            self.assertTrue(new.exists())
            self.confirm.assert_called_once()
            self.assertEqual(self.confirm.call_args.kwargs['default'], 'no')
            self.confirm.return_value = True
            self.move_to_trash.side_effect = module.FileOperationError('unavailable', 'Fixture volume has no Trash')
            app.delete_file()
            self.assertEqual(app.cards, before)
            self.assertEqual(app.file_revision, revision)
            self.assertEqual(app.selected_path, new)
            self.assertEqual(app.canvas.canvasy(0), top)
            self.assertTrue(new.exists())
            self.move_to_trash.side_effect = self.fake_trash

        with self.subTest('delete selects next file and retains scroll and surviving cards'):
            before = {card[0]: card for card in app.cards.values()}
            next_path = app.filtered[app.filtered.index(new) + 1]
            generation = app.generation
            with patch.object(app, 'apply_search', wraps=app.apply_search) as refresh:
                app.delete_file()
                refresh.assert_not_called()
            self.assertFalse(new.exists())
            self.assertTrue((self.trash / new.name).is_file())
            self.assertNotIn(new, app.files)
            self.assertNotIn(new, app.filtered)
            self.assertNotIn(str(new), app.favorites)
            self.assertNotIn(new, app.modified)
            self.assertNotIn(new, app.metadata)
            self.assertNotIn(str(new), app.preview_errors)
            self.assertEqual(app.selected_path, next_path)
            self.assertEqual(app.canvas.canvasy(0), top)
            self.assertEqual(app.generation, generation)
            self.assert_survivors_retained(before)

        with self.subTest('global favorites rename and deletion work outside current folder'):
            outside = self.archive('outside.zip', self.outside)
            in_folder = [path for path in app.files if path.exists()]
            self.load(in_folder, favorites=[outside], favorite_tab=True)
            self.assertEqual(app.filtered, [outside])
            renamed = outside.with_stem('outside-renamed')
            dialog, commit = self.rename_dialog(outside, renamed.stem)
            commit.invoke()
            self.assertEqual(app.filtered, [renamed])
            self.assertEqual(app.selected_path, renamed)
            self.assertNotIn(renamed, app.files)
            self.assertEqual(app.favorites, {str(renamed)})
            app.delete_file()
            self.assertEqual(app.files, in_folder)
            self.assertEqual(app.filtered, [])
            self.assertEqual(app.cards, {})
            self.assertIsNone(app.selected_path)
            self.assertEqual(app.canvas.canvasy(0), 0)
            empty_view = app.tab_views['__global_favorites__']['favorites']
            self.assertIsNone(empty_view['anchor'])
            self.assertIsNone(empty_view['selected'])
            self.assertEqual(empty_view['fraction'], 0)
            settings = json.loads(module.CONFIG.read_text('utf-8'))
            self.assertEqual(settings['file_favorites'], [])
            self.assertIsNone(settings['tab_views']['__global_favorites__']['favorites']['selected'])

        with self.subTest('stale scans cannot resurrect renamed or deleted paths'):
            first = self.archive('race-first.zip')
            second = self.archive('race-second.zip')
            modified, metadata = self.load([first, second], favorites=[first, second])
            revision = app.file_revision
            renamed = first.with_stem('race-renamed')
            _, commit = self.rename_dialog(first, renamed.stem)
            commit.invoke()
            app.delete_file(second)
            # Both a full old listing and a listing that missed the old name
            # must include the renamed item when it belongs to the scan root.
            for snapshot in ([first, second], []):
                app.results.put(('scan', app.scan_generation,
                                 (snapshot, modified, metadata, revision, self.library, True), None))
                app.poll()
                self.assertEqual(app.files, [renamed])
                self.assertEqual(app.filtered, [renamed])
                self.assertNotIn(first, app.modified)
                self.assertNotIn(second, app.modified)
            out_of_scope = app.changed_snapshot([], {}, {}, revision, self.outside, True)
            self.assertEqual(out_of_scope, ([], {}, {}))
            app.results.put(('favorite_meta', revision, (modified, metadata), None))
            app.poll()
            self.assertNotIn(first, app.metadata)
            self.assertNotIn(second, app.metadata)
            self.assertIn(renamed, app.metadata)
            self.assertEqual(app.favorites, {str(renamed)})

        with self.subTest('localized context commands and keyboard bindings target selection'):
            set_language('en')
            app.select_card(renamed)
            with patch.object(module.tk.Menu, 'tk_popup'):
                app.context(SimpleNamespace(x_root=0, y_root=0), renamed)
            menu = app.context_menu
            labels = {menu.entrycget(index, 'label'): index
                      for index in range(menu.index('end') + 1) if menu.type(index) == 'command'}
            self.assertIn('Rename file', labels)
            self.assertIn('Move file to Trash', labels)
            self.assertEqual(menu.entrycget(labels['Rename file'], 'accelerator'), 'F2')
            self.assertEqual(menu.entrycget(labels['Move file to Trash'], 'accelerator'), app.shortcut_label('trash'))
            with patch.object(app, 'rename_file') as rename, patch.object(app, 'delete_file') as delete:
                menu.invoke(labels['Rename file'])
                rename.assert_called_once_with(renamed)
                menu.invoke(labels['Move file to Trash'])
                delete.assert_called_once_with(renamed)
                rename.reset_mock()
                delete.reset_mock()
                app.canvas.focus_force()
                app.update()
                app.canvas.event_generate('<F2>')
                app.canvas.event_generate('<Delete>')
                app.update()
                rename.assert_called_once_with()
                delete.assert_called_once_with()
            self.assertTrue(renamed.exists())
            self.assertFalse(self.errors, self.errors)
            set_language('ko')


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        # Windows keeps open log files locked during TemporaryDirectory cleanup.
        __import__('faulthandler').disable()
        module.FAULT_LOG.close()
        __import__('logging').shutdown()
        _settings.cleanup()
