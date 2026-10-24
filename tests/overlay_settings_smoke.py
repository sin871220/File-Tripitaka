"""Real Tk overlay settings, counts and viewport checks using temporary images."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_settings = tempfile.TemporaryDirectory(prefix='tripitaka-overlay-settings-')
os.environ['LOCALAPPDATA'] = _settings.name
import app as module
from PIL import Image
from thumbnail_overlays import DEFAULT_OVERLAYS, OVERLAY_ORDER, POSITION_LABELS, SIZE_LABELS

sys.excepthook = sys.__excepthook__


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class OverlaySettingsSmoke(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory(prefix='tripitaka-overlay-library-')
        self.addCleanup(workspace.cleanup)
        self.library = Path(workspace.name).resolve()
        data = io.BytesIO()
        Image.new('RGB', (127, 180), '#6399aa').save(data, 'PNG')
        self.folder = self.library / '000-Folder'
        self.folder.mkdir()
        for index in range(7):
            (self.folder / f'{index}.png').write_bytes(data.getvalue())
        for index in range(60):
            with zipfile.ZipFile(self.library / f'Archive-{index:03d}.cbz', 'w') as archive:
                for page in range(5):
                    archive.writestr(f'{page}.png', data.getvalue())
        module.CONFIG.unlink(missing_ok=True)
        (module.DATA / 'thumbnail_edits.json').unlink(missing_ok=True)
        self.apps, self.errors, self.messages = [], [], []
        self.addCleanup(patch.stopall)
        patch.object(module.App, 'populate_tree').start()
        patch.object(module.App, 'update_shortcut_language').start()
        for name in ('launch_default', 'reveal_file', 'trash_archive'):
            patch.object(module, name, side_effect=AssertionError('External action prohibited')).start()
        patch.object(module.messagebox, 'showerror', side_effect=lambda *a, **kw: self.messages.append(a)).start()
        self.addCleanup(self.close_apps)
        self.app = self.make_app()
        self.load(self.app)

    def make_app(self):
        app = module.App()
        app.report_callback_exception = lambda *args: self.errors.append(args)
        self.apps.append(app)
        app.update()
        return app

    def close_apps(self):
        for app in self.apps:
            if not app.closing:
                app.close()
            for pool in (app.pool, app.folder_pool, app.thumbnail_edit_pool):
                pool.shutdown(wait=True, cancel_futures=True)
        self.assertFalse(self.errors, self.errors)
        self.assertFalse(self.messages, self.messages)

    def wait(self, predicate, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            self.assertFalse(self.errors, self.errors)
            if predicate():
                return
            time.sleep(.01)
        self.fail('Overlay GUI operation timed out')

    def settle(self):
        self.wait(lambda: not self.app.pending and self.app.active == 0 and self.app.results.empty())

    def load(self, app):
        files, modified, metadata, kinds = module.scan_items(self.library)
        app.item_kinds.update(kinds)
        app.current_folder = str(self.library)
        app.folder.set(str(self.library))
        app.add_cards((files, modified, metadata))
        app.update()
        self.settle()

    def test_counts_preview_modes_edit_and_favorites_tab(self):
        app = self.app
        folder_card = app.cards[0][1]
        self.assertEqual(folder_card.path, self.folder)
        self.assertEqual(folder_card.page_count, 7)
        self.assertTrue(all(card.page_count == 5 for _, card, _, _ in list(app.cards.values())[1:]))
        app.toggle_favorite(self.folder)
        self.assertEqual(app.canvas.itemcget(folder_card.badge_item, 'state'), 'normal')
        for count in (2, 3):
            app.preview_count.set(f'{count}장')
            app.change_preview_count()
            app.update()
            self.settle()
            card = app.cards[0][1]
            self.assertEqual(card.page_count, 7)
            self.assertEqual(app.canvas.itemcget(card.page_item, 'text'), '7P')
        app.thumbnail_edits.set(self.folder, 0, '4.png', (.1, .1, .9, .9))
        previous_photo = app.cards[0][2].photo
        app.refresh_thumbnail(self.folder)
        self.wait(lambda: app.cards[0][1].page_count == 7 and app.cards[0][2].photo is not previous_photo)
        app.tabs.select(1)
        app.switch_tab()
        app.update()
        self.settle()
        card = next(value[1] for value in app.cards.values() if value[0] == self.folder)
        self.assertEqual(card.page_count, 7)
        self.assertEqual(app.canvas.itemcget(card.badge_item, 'state'), 'hidden')
        self.assertEqual(app.canvas.itemcget(card.folder_item, 'state'), 'normal')
        self.assertEqual(app.canvas.itemcget(card.page_item, 'state'), 'normal')

    def test_apply_updates_existing_cards_preserves_scroll_and_restart_settings(self):
        app = self.app
        app.canvas.yview_moveto(.45)
        app.refresh_visible()
        self.settle()
        before = dict(app.cards)
        photos = dict(app.photos)
        view = app.canvas.yview()
        app.open_settings()
        dialog = app.settings_window
        dialog.settings_tabs.select(1)
        app.update()
        self.assertEqual(set(dialog.settings_overlay_size_controls), {'favorite', 'folder'})
        sizes = {'favorite': 'medium', 'folder': 'small'}
        for kind, size in sizes.items():
            combo = dialog.settings_overlay_size_controls[kind]
            combo.set(SIZE_LABELS[size])
            combo.event_generate('<<ComboboxSelected>>')
            self.assertEqual(dialog.settings_overlay_size[kind].get(), size)
            self.assertEqual(dialog.settings_overlay_preview.overlays[kind]['size'], size)
        for kind in OVERLAY_ORDER:
            combo = dialog.settings_overlay_controls[kind]
            combo.set(POSITION_LABELS['bottom_left'])
            combo.event_generate('<<ComboboxSelected>>')
            self.assertEqual(dialog.settings_overlay_position[kind].get(), 'bottom_left')
        dialog.settings_overlay_selected.set('pages')
        dialog.settings_overlay_up.invoke()
        dialog.settings_overlay_up.invoke()
        order = ['pages', 'favorite', 'folder']
        self.assertEqual(dialog.settings_overlay_order, order)
        dialog.settings_overlay_visible['pages'].set(False)
        self.assertTrue(dialog.settings_overlay_controls['pages'].instate(['disabled']))
        dialog.settings_apply()
        app.update()
        self.assertEqual(app.cards, before)
        self.assertEqual(dict(app.photos), photos)
        self.assertEqual(app.canvas.yview(), view)
        self.assertTrue(all(card.overlays['favorite']['size'] == 'medium'
                            and card.overlays['folder']['size'] == 'small'
                            for _, card, _, _ in app.cards.values()))
        self.assertTrue(all(app.canvas.itemcget(card.page_item, 'state') == 'hidden'
                            for _, card, _, _ in app.cards.values()))
        saved = json.loads(module.CONFIG.read_text('utf-8'))['thumbnail_overlays']
        self.assertEqual(json.loads(module.CONFIG.read_text('utf-8'))['thumbnail_overlay_order'], order)
        self.assertFalse(saved['pages']['visible'])
        self.assertEqual(saved['favorite']['size'], 'medium')
        self.assertEqual(saved['folder']['size'], 'small')
        self.assertNotIn('size', saved['pages'])
        self.assertTrue(all(value['position'] == 'bottom_left' for value in saved.values()))
        app.close()
        for pool in (app.pool, app.folder_pool, app.thumbnail_edit_pool):
            pool.shutdown(wait=True, cancel_futures=True)
        self.app = self.make_app()
        self.wait(lambda: self.app.active == 0 and not self.app.pending)
        self.assertEqual(self.app.settings['thumbnail_overlays'], saved)
        self.assertEqual(self.app.settings['thumbnail_overlay_order'], order)
        self.assertTrue(all(card.overlays == saved for _, card, _, _ in self.app.cards.values()))
        self.assertTrue(all(card.overlay_order == order for _, card, _, _ in self.app.cards.values()))

    def test_real_selection_and_move_buttons_keep_row_values_and_preview_order(self):
        app = self.app
        app.open_settings()
        dialog = app.settings_window
        dialog.settings_tabs.select(1)
        app.update()
        for kind in OVERLAY_ORDER:
            dialog.settings_overlay_position[kind].set('bottom_right')
        self.assertFalse(any(widget.winfo_class() == 'TRadiobutton' for widget in descendants(dialog)))
        visible = {kind: variable.get() for kind, variable in dialog.settings_overlay_visible.items()}
        dialog.settings_overlay_rows['folder'].event_generate('<Button-1>', x=2, y=2)
        app.update()
        self.assertEqual(dialog.settings_overlay_selected.get(), 'folder')
        self.assertEqual({kind: variable.get() for kind, variable in dialog.settings_overlay_visible.items()}, visible)
        check = dialog.settings_overlay_checks['folder']
        check.invoke()
        self.assertFalse(dialog.settings_overlay_visible['folder'].get())
        self.assertEqual(dialog.settings_overlay_selected.get(), 'folder')
        dialog.settings_overlay_labels['pages'].event_generate('<Button-1>', x=2, y=2)
        dialog.settings_overlay_labels['folder'].event_generate('<Button-1>', x=2, y=2)
        app.update()
        self.assertEqual(dialog.settings_overlay_selected.get(), 'folder')
        self.assertFalse(dialog.settings_overlay_visible['folder'].get(),
                         'A hidden item must remain selectable without becoming visible')
        check.invoke()
        self.assertTrue(dialog.settings_overlay_visible['folder'].get())
        dialog.settings_overlay_labels['pages'].event_generate('<Button-1>', x=2, y=2)
        app.update()
        self.assertEqual(dialog.settings_overlay_selected.get(), 'pages')
        self.assertEqual({kind: variable.get() for kind, variable in dialog.settings_overlay_visible.items()}, visible)
        for kind in OVERLAY_ORDER:
            state = ['alternate'] if kind == 'pages' else ['!alternate']
            self.assertTrue(dialog.settings_overlay_rows[kind].instate(state))
            self.assertTrue(dialog.settings_overlay_labels[kind].instate(state))
            self.assertFalse(dialog.settings_overlay_checks[kind].instate(['alternate']),
                             'Selection must not turn visibility checkboxes indeterminate')
        self.assertTrue(dialog.settings_overlay_down.instate(['disabled']))
        dialog.settings_overlay_up.invoke()
        dialog.settings_overlay_up.invoke()
        self.assertEqual(dialog.settings_overlay_order, ['pages', 'favorite', 'folder'])
        self.assertEqual(dialog.settings_overlay_selected.get(), 'pages')
        self.assertTrue(dialog.settings_overlay_up.instate(['disabled']))
        preview = dialog.settings_overlay_preview
        self.assertEqual(preview.overlay_order, ['pages', 'favorite', 'folder'])
        boxes = [preview.canvas.bbox(item) for item in
                 (preview.page_background_item, preview.badge_item, preview.folder_item)]
        self.assertLessEqual(boxes[0][3], boxes[1][1])
        self.assertLessEqual(boxes[1][3], boxes[2][1] + 1)
        dialog.settings_overlay_visible['folder'].set(False)
        dialog.settings_overlay_down.invoke()
        self.assertEqual(dialog.settings_overlay_order, ['favorite', 'pages', 'folder'])
        self.assertFalse(dialog.settings_overlay_visible['folder'].get())
        self.assertEqual(dialog.settings_overlay_position['pages'].get(), 'bottom_right')
        for index, kind in enumerate(dialog.settings_overlay_order):
            self.assertEqual(int(dialog.settings_overlay_rows[kind].grid_info()['row']), index)
            self.assertIs(dialog.settings_overlay_controls[kind].master, dialog.settings_overlay_rows[kind])
        dialog.settings_reset_overlays()
        self.assertEqual(dialog.settings_overlay_order, list(OVERLAY_ORDER))
        self.assertEqual(preview.overlay_order, list(OVERLAY_ORDER))
        self.assertEqual(preview.overlays, DEFAULT_OVERLAYS)
        dialog.settings_overlay_down.invoke()
        self.assertNotEqual(preview.overlay_order, list(OVERLAY_ORDER))
        dialog.destroy()
        self.assertEqual(app.settings['thumbnail_overlay_order'], list(OVERLAY_ORDER))

    def test_drag_handles_names_and_hidden_rows_reorder_without_changing_fields(self):
        app = self.app
        app.open_settings()
        dialog = app.settings_window
        dialog.settings_tabs.select(1)
        app.update()
        for kind in OVERLAY_ORDER:
            dialog.settings_overlay_position[kind].set('bottom_right')
        visible = {kind: variable.get() for kind, variable in dialog.settings_overlay_visible.items()}

        def emit(widget, sequence, rootx, rooty):
            widget.event_generate(sequence, x=rootx - widget.winfo_rootx(),
                                  y=rooty - widget.winfo_rooty(), rootx=rootx, rooty=rooty,
                                  state=0x100 if sequence == '<B1-Motion>' else 0)
            app.update()

        def drag(widget, target_kind, direction):
            rootx = widget.winfo_rootx() + widget.winfo_width() // 2
            rooty = widget.winfo_rooty() + widget.winfo_height() // 2
            target = dialog.settings_overlay_rows[target_kind]
            # Move just beyond the target row's center in the travel direction.
            destination = target.winfo_rooty() + target.winfo_height() // 2 + direction * 3
            emit(widget, '<ButtonPress-1>', rootx, rooty)
            emit(widget, '<B1-Motion>', rootx, destination)
            emit(widget, '<ButtonRelease-1>', rootx, destination)

        handle = dialog.settings_overlay_handles['favorite']
        rootx = handle.winfo_rootx() + handle.winfo_width() // 2
        rooty = handle.winfo_rooty() + handle.winfo_height() // 2
        emit(handle, '<ButtonPress-1>', rootx, rooty)
        emit(handle, '<ButtonRelease-1>', rootx, rooty)
        self.assertEqual(dialog.settings_overlay_order, list(OVERLAY_ORDER),
                         'A click without drag motion must only select the row')
        drag(handle, 'pages', 1)
        self.assertEqual(dialog.settings_overlay_order, ['folder', 'pages', 'favorite'])
        self.assertEqual(dialog.settings_overlay_selected.get(), 'favorite')
        self.assertEqual(dialog.settings_overlay_preview.overlay_order, ['folder', 'pages', 'favorite'])
        drag(dialog.settings_overlay_labels['favorite'], 'folder', -1)
        self.assertEqual(dialog.settings_overlay_order, list(OVERLAY_ORDER))
        self.assertEqual({kind: variable.get() for kind, variable in dialog.settings_overlay_visible.items()}, visible)
        self.assertTrue(all(variable.get() == 'bottom_right' for variable in dialog.settings_overlay_position.values()))

        dialog.settings_overlay_checks['folder'].invoke()
        self.assertFalse(dialog.settings_overlay_visible['folder'].get())
        drag(dialog.settings_overlay_labels['folder'], 'favorite', -1)
        self.assertEqual(dialog.settings_overlay_order, ['folder', 'favorite', 'pages'])
        self.assertFalse(dialog.settings_overlay_visible['folder'].get(),
                         'Dragging a hidden row must not enable its checkbox')
        self.assertEqual(dialog.settings_overlay_selected.get(), 'folder')
        preview = dialog.settings_overlay_preview
        self.assertEqual(preview.overlay_order, ['folder', 'favorite', 'pages'])
        self.assertEqual(preview.canvas.itemcget(preview.folder_item, 'state'), 'hidden')
        self.assertLessEqual(preview.canvas.bbox(preview.badge_item)[3],
                             preview.canvas.bbox(preview.page_background_item)[1])

        before = list(dialog.settings_overlay_order)
        check = dialog.settings_overlay_checks['pages']
        check.invoke()
        self.assertEqual(dialog.settings_overlay_order, before)
        self.assertEqual(dialog.settings_overlay_selected.get(), 'pages')
        self.assertFalse(check.bind('<B1-Motion>'), 'Visibility controls must not initiate row drags')
        combo = dialog.settings_overlay_controls['favorite']
        combo.focus_force()
        combo.set(POSITION_LABELS['top_left'])
        combo.event_generate('<<ComboboxSelected>>')
        app.update()
        self.assertEqual(dialog.settings_overlay_position['favorite'].get(), 'top_left')
        self.assertEqual(dialog.settings_overlay_order, before)
        self.assertFalse(combo.bind('<B1-Motion>'), 'Position controls must not initiate row drags')
        dialog.destroy()
        self.assertEqual(app.settings['thumbnail_overlay_order'], list(OVERLAY_ORDER))

    def test_draft_preview_cancel_reset_and_localized_compact_settings(self):
        app = self.app
        original = app.settings['thumbnail_overlays']
        for theme in ('라이트', '다크', '네이비', '블루'):
            app.settings['theme'] = theme
            app.apply_theme()
            app.open_settings()
            dialog = app.settings_window
            dialog.settings_tabs.select(1)
            app.update()
            for kind in OVERLAY_ORDER:
                dialog.settings_overlay_position[kind].set('bottom_right')
            preview = dialog.settings_overlay_preview
            self.assertTrue(all(value['position'] == 'bottom_right' for value in preview.overlays.values()))
            for kind, size in (('favorite', 'medium'), ('folder', 'small')):
                combo = dialog.settings_overlay_size_controls[kind]
                self.assertEqual(tuple(combo.cget('values')), tuple(SIZE_LABELS.values()))
                combo.set(SIZE_LABELS[size])
                combo.event_generate('<<ComboboxSelected>>')
                self.assertEqual(preview.overlays[kind]['size'], size)
            dialog.settings_overlay_visible['folder'].set(False)
            self.assertEqual(preview.canvas.itemcget(preview.folder_item, 'state'), 'hidden')
            self.assertTrue(dialog.settings_overlay_size_controls['folder'].instate(['disabled']))
            self.assertEqual(dialog.settings_overlay_size['folder'].get(), 'small')
            dialog.settings_reset_overlays()
            self.assertEqual(preview.overlays, DEFAULT_OVERLAYS)
            self.assertTrue(all(variable.get() == 'large' for variable in dialog.settings_overlay_size.values()))
            self.assertTrue(all(not combo.instate(['disabled'])
                                for combo in dialog.settings_overlay_size_controls.values()))
            for kind, combo in dialog.settings_overlay_controls.items():
                self.assertEqual(tuple(combo.cget('values')), tuple(POSITION_LABELS.values()))
                self.assertLessEqual(combo.winfo_rooty() + combo.winfo_height(), dialog.winfo_rooty() + dialog.winfo_height())
            self.assertFalse(any(widget.winfo_class() in ('Scrollbar', 'TScrollbar') for widget in descendants(dialog)))
            dialog.settings_overlay_size['favorite'].set('small')
            self.assertEqual(preview.overlays['favorite']['size'], 'small')
            dialog.destroy()
            self.assertFalse(preview.alive)
            self.assertEqual(app.settings['thumbnail_overlays'], original)
        app.settings['language'] = 'en'
        app.apply_language()
        app.open_settings()
        dialog = app.settings_window
        dialog.settings_tabs.select(1)
        app.update()
        self.assertEqual(tuple(dialog.settings_overlay_controls['pages'].cget('values')),
                         ('Top left', 'Top right', 'Bottom left', 'Bottom right'))
        self.assertEqual(set(dialog.settings_overlay_size_controls), {'favorite', 'folder'})
        for kind, label, size in (('favorite', 'Medium', 'medium'), ('folder', 'Small', 'small')):
            combo = dialog.settings_overlay_size_controls[kind]
            self.assertEqual(tuple(combo.cget('values')), ('Large', 'Medium', 'Small'))
            combo.set(label)
            combo.event_generate('<<ComboboxSelected>>')
            self.assertEqual(dialog.settings_overlay_size[kind].get(), size)
            self.assertEqual(dialog.settings_overlay_preview.overlays[kind]['size'], size)
        dialog.settings_overlay_controls['pages'].set('Top right')
        dialog.settings_overlay_controls['pages'].event_generate('<<ComboboxSelected>>')
        self.assertEqual(dialog.settings_overlay_position['pages'].get(), 'top_right')
        dialog.settings_apply()
        self.assertEqual(app.settings['thumbnail_overlays']['pages']['position'], 'top_right')
        self.assertEqual(app.settings['thumbnail_overlays']['favorite']['size'], 'medium')
        self.assertEqual(app.settings['thumbnail_overlays']['folder']['size'], 'small')


if __name__ == '__main__':
    unittest.main(verbosity=2)
