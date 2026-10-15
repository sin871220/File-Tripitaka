"""Live language switching without restarting or rebuilding archive cards."""
import os
import sys
import tempfile
import json
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
settings = tempfile.TemporaryDirectory()
os.environ['LOCALAPPDATA'] = settings.name
import app as module
from localization import translate, EN, set_language
from tkinter import ttk
from PIL import Image
module.cover = lambda *args: Image.new('RGB', (100, 150), 'blue')
app = module.App()
sys.excepthook = sys.__excepthook__
errors = []
app.report_callback_exception = lambda *args: errors.append(str(args))
app.update()

def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)

def apply_dialog():
    dialog = app.settings_window
    button = next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget('text') in ('적용', 'Apply'))
    button.invoke()
    app.update()
    assert not dialog.winfo_exists()

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    files = [root / name for name in ('설정.zip', 'a.zip', 'b.zip')]
    for path in files: path.touch()
    app.current_folder = str(root)
    app.folder.set(str(root))
    app.add_cards((files, {p:i for i,p in enumerate(files)}, {p:(100, 0) for p in files}))
    app.update()
    cards_before = dict(app.cards)
    app.select_card(files[0])
    app.open_settings()
    app.language_choice.set('English')
    apply_dialog()
    assert app.title() == 'File Tripitaka v' + module.APP_VERSION
    assert app.tabs.tab(0, 'text') == 'All'
    assert app.settings['language'] == 'en'
    with patch.object(module.tk.Menu, 'tk_popup'):
        app.context(SimpleNamespace(x_root=0, y_root=0), files[0])
    labels = [app.context_menu.entrycget(i, 'label') for i in range(app.context_menu.index('end') + 1)]
    assert 'File information' in labels and 'Copy path' in labels
    assert app.selected_path == files[0]
    assert app.cards == cards_before
    assert any(card[1].title_label.cget('text') == '설정.zip' for card in app.cards.values())
    assert translate('미리보기 불가\n압축파일에 지원하는 이미지가 없습니다.') == 'Preview unavailable\nNo supported images in this archive.'
    sorter = next(w for w in descendants(app) if isinstance(w, ttk.Combobox) and 'Name ascending' in w.cget('values'))
    sorter.set('Name descending')
    sorter.event_generate('<<ComboboxSelected>>')
    app.update()
    assert app.sort_order.get() == '이름 내림차순'
    app.open_settings()
    dialog = app.settings_window
    assert dialog.title() == 'Settings · File Tripitaka'
    key_box = next(w for w in descendants(dialog) if isinstance(w, ttk.Combobox) and 'Toggle favorite' in w.cget('values'))
    key_box.set('Toggle favorite')
    apply_dialog()
    assert app.settings['enter_action'] == '즐겨찾기 추가/해제'
    app.activate_selection('enter')
    assert str(files[0]) in app.favorites
    app.open_settings()
    app.language_choice.set('한국어')
    apply_dialog()
    assert app.title() == module.APP_TITLE
    assert app.tabs.tab(0, 'text') == '전체'
    assert app.settings['language'] == 'ko'
    assert app.sort_order.get() == '이름 내림차순'
    app.settings['language'] = 'en'
    app.save()
    assert json.loads(module.CONFIG.read_text('utf-8'))['language'] == 'en'
    app.close()
    second = module.App()
    second.update()
    assert second.title() == 'File Tripitaka v' + module.APP_VERSION
    assert second.tabs.tab(0, 'text') == 'All'
    second.close()
assert not errors, errors
print('LANGUAGE GUI PASS: ko/en/ko, settings, localized combos with stable models, actions, literal filenames, retained cards/selection')
