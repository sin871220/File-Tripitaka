import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
import os
import tempfile
settings_dir = tempfile.TemporaryDirectory()
os.environ['LOCALAPPDATA'] = settings_dir.name
from pathlib import Path
import tempfile
import json
import app as module
from viewer import default_action, available_actions
sys.excepthook = sys.__excepthook__
from PIL import Image
module.cover = lambda *args: Image.new('RGB', (320, 340), 'blue')
app = module.App()
errors = []
app.report_callback_exception = lambda *args: errors.append(str(args))
app.update()
assert app.title() == module.APP_TITLE

def assert_canvas_cards():
    # The gallery must paint through one Canvas surface. Native child windows
    # have a separate Windows repaint path and can leave strips while moving.
    assert app.canvas.winfo_children() == []
    assert all(app.canvas.type(item) in ('rectangle', 'image', 'text')
               for item in app.canvas.find_all())
    for _, card, thumbnail, background in app.cards.values():
        assert card.alive and thumbnail.exists()
        assert app.canvas.type(background) == 'rectangle'
        assert app.canvas.type(card.title_item) == 'text'
        assert app.canvas.type(card.info_item) == 'text'

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp).resolve()
    (root / 'child').mkdir()
    original_drives = module.logical_drive_roots
    module.logical_drive_roots = lambda: [str(root / 'drive-c'), str(root / 'drive-d')]
    app.populate_tree(root)
    drive_nodes = [node for node in app.tree.get_children() if app.tree_paths[node] in (root / 'drive-c', root / 'drive-d')]
    assert len(drive_nodes) == 2
    assert all(app.tree.item(node, 'image') == (str(app.tree_icons['drive']),) for node in drive_nodes)
    folder_node = next(node for node in app.tree.get_children() if node not in drive_nodes)
    app.tree.focus(folder_node)
    app.collapse_tree()
    assert app.tree.item(folder_node, 'image') == (str(app.tree_icons['folder']),)
    app.expand_tree()
    assert app.tree.item(folder_node, 'image') == (str(app.tree_icons['folder_open']),)
    assert all(not app.tree.item(node, 'open') for node in drive_nodes)
    assert all(app.tree.get_children(node) for node in drive_nodes)
    module.logical_drive_roots = original_drives
    app.populate_tree(root)
    app.current_folder = str(root)
    app.folder.set(str(root))
    files = [root / f'{i}.zip' for i in range(7444)]
    app.add_cards((files, {p:i for i,p in enumerate(files)}, {p:(1024, 1700000000) for p in files}))
    app.update_idletasks()
    app.refresh_visible()
    assert 0 < len(app.cards) < 80
    assert_canvas_cards()
    for index, (_, card, _, background) in app.cards.items():
        x = (index % app.columns()) * app.cell_width()
        y = (index // app.columns()) * app.row_height()
        assert card.geometry == (x, y, app.cell_width() + 1, app.row_height() + 1)
        assert app.canvas.coords(background) == [x, y, x + app.cell_width(), y + app.row_height()]
    gallery_width = app.canvas.winfo_width()
    app.toggle_sidebar()
    app.update()
    assert str(app.sidebar) not in app.panes.panes()
    assert app.canvas.winfo_width() > gallery_width
    assert app.sidebar_hidden and app.settings['sidebar_hidden']
    app.toggle_sidebar()
    app.update()
    assert str(app.sidebar) in app.panes.panes()
    assert not app.sidebar_hidden
    sidebar_cards = dict(app.cards)
    sidebar_generation = app.generation
    tree_identity = str(app.tree)
    favorite_identity = str(app.favorite_list)
    for section in ('favorites', 'tree'):
        app.toggle_sidebar_section(section)
        assert not app.sidebar_sections[section]['body'].winfo_manager()
        app.toggle_sidebar_section(section)
        assert app.sidebar_sections[section]['body'].winfo_manager() == 'pack'
    assert app.cards == sidebar_cards and app.generation == sidebar_generation
    assert str(app.tree) == tree_identity and str(app.favorite_list) == favorite_identity
    app.toggle_sidebar_section('favorites')
    def tab_spans():
        positions = {0: [], 1: []}
        y = max(1, (app.tabs.winfo_height() - 1) // 2)
        for x in range(app.tabs.winfo_width()):
            try:
                positions[app.tabs.index(f'@{x},{y}')].append(x)
            except module.tk.TclError:
                pass
        return {key: (min(xs), max(xs)) for key, xs in positions.items() if xs}
    for mode, background in (('라이트', '#F4F6FA'), ('다크', '#171B23'), ('네이비', '#0B1B27'), ('블루', '#0D2A50')):
        app.settings['theme'] = mode
        app.apply_theme()
        app.update_idletasks()
        assert app.canvas.cget('bg') == background
        all_spans = tab_spans()
        assert len(all_spans) == 2
        app.tabs.select(1)
        app.switch_tab()
        app.update_idletasks()
        assert tab_spans() == all_spans
        app.tabs.select(0)
        app.switch_tab()
        app.update_idletasks()
    app.settings['theme'] = '라이트'
    app.apply_theme()
    for fraction in (0.25, 0.5, 1.0):
        app.canvas.yview_moveto(fraction)
        app.refresh_visible()
        assert len(app.cards) < 80
    assert 7443 in app.cards
    from types import SimpleNamespace
    from unittest.mock import Mock
    app.select_card(app.filtered[0])
    app.move_selection(SimpleNamespace(keysym='Right'))
    assert app.selected_path == app.filtered[1]
    app.move_selection(SimpleNamespace(keysym='Down'))
    assert app.selected_path == app.filtered[1 + app.columns()]
    app.select_card(app.filtered[-1])
    app.move_selection(SimpleNamespace(keysym='Down'))
    assert app.selected_path == app.filtered[-1]
    app.move_selection(SimpleNamespace(keysym='Up'))
    assert app.selected_path == app.filtered[-1 - app.columns()]
    assert app.canvas.yview()[0] > .9
    original_execute = app.execute_action
    app.execute_action = Mock()
    app.settings.update(enter_action='파일 위치 열기', space_action='없음')
    app.settings['shortcuts'] = module.migrate_shortcuts(dict(enter_action='파일 위치 열기', space_action='없음'))
    app.refresh_shortcuts()
    app.activate_selection('enter')
    app.execute_action.assert_called_once_with(app.selected_path, '파일 위치 열기')
    app.execute_action.reset_mock()
    app.activate_selection('space')
    app.execute_action.assert_not_called()
    app.execute_action = original_execute
    app.settings.update(enter_action=default_action(), space_action=default_action())
    app.settings['shortcuts'] = module.migrate_shortcuts(dict(enter_action=default_action(), space_action=default_action()))
    app.refresh_shortcuts()
    app.select_card(app.filtered[-1])
    selected_before_fit = app.selected_path
    columns_before_fit = app.columns()
    app.fit_button.invoke()
    app.update_idletasks()
    assert app.fit_enabled.get() and app.fit_button.instate(['selected'])
    assert app.fit_button.cget('text') == '창에 맞춤 ON'
    assert app.columns() == columns_before_fit
    assert app.selected_path == selected_before_fit
    assert app.columns() * app.cell_width() <= app.canvas.winfo_width()
    assert app.canvas.winfo_width() - app.columns() * app.cell_width() < app.columns()
    last_column = next(card for index, card in app.cards.items() if index % app.columns() == app.columns() - 1)
    fitted_card = last_column[1]
    assert fitted_card.geometry[0] + fitted_card.geometry[2] == app.canvas.winfo_width() + 1
    assert app.canvas.coords(last_column[3])[2] == app.canvas.winfo_width()
    for desired_columns in (4, 5):
        app.thumb_size.set((app.canvas.winfo_width() // desired_columns - 35))
        app.size_changed()
        assert not app.fit_enabled.get() and app.fit_button.instate(['!selected'])
        app.after_cancel(app.size_job)
        app.apply_size()
        assert app.columns() == desired_columns
        app.fit_button.invoke()
        assert app.columns() == desired_columns
        app.geometry('1240x760')
        app.update()
        app.fit_thumbnails()
        assert app.columns() == desired_columns
        last_index = next(index for index in app.cards if index % desired_columns == desired_columns - 1)
        fitted_card = app.cards[last_index][1]
        assert fitted_card.geometry[0] + fitted_card.geometry[2] == app.canvas.winfo_width() + 1
        assert app.canvas.coords(app.cards[last_index][3])[2] == app.canvas.winfo_width()
        app.geometry('1120x760')
        app.update()
        app.fit_thumbnails()
    app.fit_button.invoke()
    assert not app.fit_enabled.get() and app.fit_columns is None
    assert app.fit_button.cget('text') == '창에 맞춤 OFF'
    app.fit_button.invoke()
    assert app.fit_enabled.get() and app.fit_columns is not None
    assert app.preview_count.get() == '1장'
    assert app.sampling_control.instate(['disabled'])
    app.preview_count.set('3장')
    app.preview_sampling.set('비율 보기')
    app.change_preview_count()
    assert app.cell_width() == app.display_size * 3 + 35
    assert app.settings['preview_count'] == 3 and app.settings['preview_sampling'] == '비율 보기'
    assert app.sampling_control.instate(['readonly'])
    assert app.selected_path == app.filtered[-1]
    assert app.canvas.yview()[0] > .9
    app.preview_count.set('2장')
    app.preview_sampling.set('순차 보기')
    app.change_preview_count()
    assert app.cell_width() == app.display_size * 2 + 35
    app.preview_count.set('1장')
    app.change_preview_count()
    assert app.sampling_control.instate(['disabled'])
    app.canvas.yview_moveto(1)
    app.refresh_visible()

    app.remember_position()
    saved = app.views[str(root)].copy()
    app.thumb_size.set(280)
    app.apply_size()
    assert app.cell_width() == 315
    app.canvas.yview_moveto(1)
    app.refresh_visible()
    assert app.canvas.yview()[0] > .9
    before_cards = {i: tuple(card) for i, card in app.cards.items()}
    before_scroll = app.canvas.yview()
    before_generation = app.generation
    before_pending = list(app.pending)
    app.toggle_favorite(files[-1])
    assert app.cards == before_cards
    assert app.canvas.yview() == before_scroll
    assert app.generation == before_generation
    assert app.pending == before_pending
    app.toggle_favorite(files[-1])
    assert app.cards == before_cards
    assert not app.cards[7443][1].favorite
    assert app.canvas.itemcget(app.cards[7443][1].badge_item, 'state') == 'hidden'
    app.toggle_favorite(files[-1])
    app.refresh_visible()
    card = next(card for card in app.cards.values() if card[0] == files[-1])
    assert card[1].favorite
    badge = card[1].badge_item
    assert app.canvas.itemcget(badge, 'text') == '★'
    assert app.canvas.itemcget(badge, 'state') == 'normal'
    assert app.canvas.itemcget(badge, 'fill') == '#FFD21F'
    assert app.canvas.itemcget(badge, 'anchor') == 'ne'
    assert not card[1].name.startswith('★ ')
    assert not app.canvas.itemcget(card[1].title_item, 'text').startswith('★ ')
    app.only_favorites.set(True)
    app.apply_search()
    assert app.filtered == [files[-1]]
    app.favorite_folder()
    favorite_node = str(app.folder_favorites.index(str(root)))
    assert app.favorite_list.item(favorite_node, 'text') == root.name
    assert app.favorite_list.item(favorite_node, 'image') == (str(app.tree_icons['folder']),)
    assert str(root) in app.folder_favorites
    app.update()
    original_navigate = app.navigate
    from unittest.mock import Mock
    app.navigate = Mock()
    bounds = app.favorite_list.bbox(favorite_node)
    assert bounds
    app.favorite_list.event_generate('<ButtonRelease-1>', x=bounds[0] + 30, y=bounds[1] + bounds[3] // 2)
    app.update()
    app.navigate.assert_called_once_with(str(root))
    assert app.active_tab == 'all'
    app.navigate = original_navigate
    app.populate_tree(root)
    node = app.tree.get_children()[0]
    app.finish_tree(node, [root / 'child'], None)
    assert len(app.tree.get_children(node)) == 1
    app.update()
    child = app.tree.get_children(node)[0]
    tree_before = app.tree.get_children()
    original_navigate = app.navigate
    app.navigate = Mock()
    bounds = app.tree.bbox(child)
    assert bounds
    app.tree.event_generate('<ButtonRelease-1>', x=bounds[0] + 65, y=bounds[1] + bounds[3] // 2)
    app.update()
    app.navigate.assert_called_once_with(root / 'child', update_tree=False)
    assert app.tree.get_children() == tree_before and app.tree.exists(child)
    app.navigate.reset_mock()
    from unittest.mock import patch
    from types import SimpleNamespace
    with patch.object(app.tree, 'identify_element', return_value='Treeitem.indicator'):
        app.open_tree_folder(SimpleNamespace(x=5, y=5))
    app.navigate.assert_not_called()
    event = SimpleNamespace(x=65, y=bounds[1] + bounds[3] // 2)
    with patch.object(app.tree, 'identify_row', return_value=child), patch.object(app.tree, 'identify_element', return_value='Treeitem.text'):
        app.tree.item(child, open=False)
        app.toggle_tree_folder(event)
        assert bool(app.tree.item(child, 'open'))
        app.open_tree_folder(event)
        app.navigate.assert_not_called()
        app.toggle_tree_folder(event)
        assert not bool(app.tree.item(child, 'open'))
        app.open_tree_folder(event)
    app.navigate = original_navigate
    app.only_favorites.set(False)
    app.apply_search()
    app.restore_position(saved)
    assert app.canvas.yview()[0] > .9
    app.favorites.update(str(p) for p in files[::5])
    outside = root.parent / 'outside-favorite.zip'
    app.favorites.add(str(outside))
    app.remember_position()
    all_position = app.canvas.yview()[0]
    app.tabs.select(1)
    app.switch_tab()
    assert app.active_tab == 'favorites'
    assert 1000 < len(app.filtered) < 2000
    assert outside in app.filtered
    assert all(not card.favorite and app.canvas.itemcget(card.badge_item, 'state') == 'hidden'
               for _, card, _, _ in app.cards.values())
    app.toggle_favorite(outside)
    assert outside not in app.filtered
    app.toggle_favorite(outside)
    app.canvas.yview_moveto(.5)
    app.refresh_visible()
    favorite_position = app.canvas.yview()[0]
    top_before = app.canvas.canvasy(0)
    generation_before = app.generation
    before = {card[0]: card for card in app.cards.values()}
    remove_index = min(len(app.filtered) - 1, int(top_before // app.row_height()) * app.columns() + app.columns())
    removed = app.filtered[remove_index]
    removed_frame = before[removed][1]
    expected_next = app.filtered[remove_index + 1]
    app.settings['enter_action'] = '즐겨찾기 추가/해제'
    app.settings['shortcuts'] = module.migrate_shortcuts(dict(enter_action='즐겨찾기 추가/해제', space_action=app.settings['space_action']))
    app.refresh_shortcuts()
    app.select_card(removed)
    app.activate_selection('enter')
    assert app.selected_path == expected_next
    assert removed not in app.filtered
    assert not removed_frame.alive
    assert app.canvas.canvasy(0) == top_before
    assert app.generation == generation_before
    after = {card[0]: card for card in app.cards.values()}
    survivors = set(before) & set(after)
    assert survivors
    assert all(before[path] == after[path] for path in survivors)
    app.toggle_favorite(removed)
    assert app.canvas.canvasy(0) == top_before
    for _ in range(5):
        app.tabs.select(0)
        app.switch_tab()
        assert abs(app.canvas.yview()[0] - all_position) < .002
        app.tabs.select(1)
        app.switch_tab()
        assert abs(app.canvas.yview()[0] - favorite_position) < .01
        assert len(app.cards) < 80
    app.tabs.select(0)
    app.switch_tab()
    app.save()
    settings = json.loads(module.CONFIG.read_text())
    assert str(files[-1]) in settings['file_favorites']
    assert settings['thumb_size'] == 280
    display_before = dict(app.cards)
    display_scroll = app.canvas.yview()
    display_generation = app.generation
    hidden = dict(show_filename=False, show_extension=False, show_size=False, show_date=False)
    app.commit_preferences('라이트', default_action(), '', '', app.recursive.get(), hidden)
    assert app.cards == display_before and app.canvas.yview() == display_scroll
    assert app.generation == display_generation
    assert all(app.canvas.itemcget(card.title_item, 'state') == 'hidden'
               and app.canvas.itemcget(card.info_item, 'state') == 'hidden'
               for _, card, _, _ in app.cards.values())
    mixed = dict(show_filename=True, show_extension=False, show_size=True, show_date=False)
    app.commit_preferences('라이트', default_action(), '', '', app.recursive.get(), mixed)
    assert all(card.name == path.stem and 'MB' in card.details and '·' not in card.details
               and app.canvas.itemcget(card.title_item, 'text') == path.stem
               and 'MB' in app.canvas.itemcget(card.info_item, 'text')
               and '·' not in app.canvas.itemcget(card.info_item, 'text')
               and app.canvas.itemcget(card.title_item, 'state') == 'normal'
               and app.canvas.itemcget(card.info_item, 'state') == 'normal'
               for path, card, _, _ in app.cards.values())
    assert_canvas_cards()
    app.commit_preferences('라이트', default_action(), '', '', app.recursive.get(), dict.fromkeys(hidden, True))
    font_generation = app.generation
    font_cards = {card[0]: card for card in app.cards.values()}
    app.commit_preferences('라이트', default_action(), '', '', app.recursive.get(), typography=dict(family=app.ui_font, size=18))
    assert app.font_size == 18 and app.generation == font_generation
    remaining = {card[0]: card for card in app.cards.values()}
    assert all(remaining[p] == font_cards[p] for p in remaining.keys() & font_cards.keys())
    assert app.canvas.yview()[0] > .9
    app.commit_preferences('라이트', default_action(), '', '', app.recursive.get(), typography=dict(family='', size=10))
    app.commit_preferences('다크', '파일 위치 열기', '', '', app.recursive.get())
    assert app.canvas.cget('bg') == '#171B23'
    before_theme_cards = dict(app.cards)
    app.open_settings()
    app.update_idletasks()
    assert app.settings_window.winfo_exists()
    dialog = app.settings_window
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    combos = [w for w in descendants(dialog) if w.winfo_class() == 'TCombobox']
    action_combo = next(w for w in combos if '파일 위치 열기' in w.cget('values'))
    opening_choices = [w for w in combos if '파일 위치 열기' in w.cget('values')]
    assert len(opening_choices) == 1
    assert '없음' not in opening_choices[0].cget('values')
    assert hasattr(dialog, 'shortcut_vars')

    settings_tabs = next(w for w in descendants(dialog) if w.winfo_class() == 'TNotebook')
    style = module.ttk.Style(app)
    assert style.lookup('TSpinbox', 'foreground') == app.palette['fg']
    assert style.lookup('TSpinbox', 'fieldbackground') == app.palette['field']
    assert not any(w.winfo_class() in ('Canvas', 'TScrollbar', 'Scrollbar') for w in descendants(dialog))
    for page in settings_tabs.tabs():
        settings_tabs.select(page)
        app.update_idletasks()
        assert not any(w.winfo_class() in ('Canvas', 'TScrollbar') for w in descendants(dialog))
    settings_tabs.select(0)
    app.update_idletasks()

    for choice in available_actions():
        action_combo.set(choice)
        action_combo.event_generate('<<ComboboxSelected>>')
        app.update_idletasks()
        buttons = [w for w in descendants(dialog) if w.winfo_class() == 'TButton' and w.winfo_ismapped()]
        assert all(w.winfo_rooty() + w.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height() for w in buttons)
    app.settings_window.destroy()
    app.commit_preferences('라이트', default_action(), '', '', app.recursive.get())
    assert app.canvas.cget('bg') == '#F4F6FA'
    assert app.cards == before_theme_cards
    app.close()
    second = module.App()
    second.report_callback_exception = lambda *args: errors.append(str(args))
    second.update_idletasks()
    second.add_cards((files, {p:i for i,p in enumerate(files)}, {p:(1024, 1700000000) for p in files}))
    second.update_idletasks()
    assert str(files[-1]) in second.favorites
    assert str(root) in second.folder_favorites
    assert second.display_size == 280
    assert second.sidebar_sections['favorites']['collapsed'] is True
    assert second.sidebar_sections['tree']['collapsed'] is False
    assert not second.sidebar_sections['favorites']['body'].winfo_manager()
    assert second.font_size == 10
    assert 'font_size' in second.settings
    assert second.canvas.yview()[0] > .9
    second.tabs.select(1)
    second.switch_tab()
    assert abs(second.canvas.yview()[0] - favorite_position) < .01
    second.tabs.select(0)
    second.switch_tab()
    second.navigate(root / 'child')
    second.add_cards(([], {}, {}))
    second.tabs.select(1)
    second.switch_tab()
    assert outside in second.filtered
    assert files[-1] in second.filtered
    assert len(second.files) == 0
    assert second.current_folder == str(root / 'child')
    second.go_back()
    assert second.current_folder == str(root)
    second.active_tab = 'favorites'
    second.only_favorites.set(True)
    second.favorites = {str(files[0]), str(files[1])}
    second.apply_search()
    second.settings.update(enter_action='즐겨찾기 추가/해제', space_action='즐겨찾기 추가/해제')
    second.settings['shortcuts'] = module.migrate_shortcuts(dict(enter_action='즐겨찾기 추가/해제', space_action='즐겨찾기 추가/해제'))
    second.refresh_shortcuts()
    second.select_card(files[0])
    second.activate_selection('enter')
    assert second.filtered == [files[1]] and second.selected_path == files[1]
    second.activate_selection('space')
    assert second.selected_path is None
    assert second.filtered == [] and second.cards == {}
    assert second.canvas.canvasy(0) == 0
    second.close()
assert not errors, errors
print('GUI PASS: global favorites, yellow badge only on All, favorite removal, empty-folder independence, 7,444 entries, scroll, size, anchor restore, folder/file favorites, filter, tree, saved settings')
