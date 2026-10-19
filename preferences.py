from localization import translate as tr, set_language, localize_widgets, LANGUAGES
"""Theme and viewer preferences UI shared by the browser."""
import os
from datetime import datetime
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
from ui_fonts import configure_fonts, select_family
from brand import APP_NAME, APP_VERSION
from dialog_geometry import center_dialog
from viewer import (ACTIONS, KEY_ACTIONS, CUSTOM_VIEWER_ACTION, DEFAULT_APP_ACTION,
                    HONEYVIEW_ACTION, available_actions, default_action,
                    normalize_action, is_viewer, launch_viewer, choose_viewer)
from shortcuts import (defaults as default_shortcuts, migrate as migrate_shortcuts,
                       validate as validate_shortcuts, legacy_actions,
                       event_key, command_labels, normalize_key)

PALETTES = {
    '라이트': dict(bg='#F4F6FA', panel='#FFFFFF', fg='#202938', muted='#627087',
                  border='#D9E3EF', accent='#087BFA', hover='#E7F1FF', field='#F5F8FC'),
    '다크': dict(bg='#171B23', panel='#222833', fg='#E7ECF5', muted='#A1AEC2',
                border='#394353', accent='#477AE0', hover='#303D54', field='#1B202A'),
    '네이비': dict(bg='#0B1B27', panel='#0F2330', fg='#E8F1F8', muted='#9AAFC0',
                border='#294352', accent='#087BFA', hover='#193E56', field='#122C3A'),
    '블루': dict(bg='#0D2A50', panel='#123760', fg='#F0F6FF', muted='#AFCAE9',
                border='#315E8E', accent='#168BFF', hover='#20568A', field='#194773'),
}


def detect_honeyview():
    if os.name != 'nt':
        return ''
    candidates = []
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for access in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Honeyview.exe', 0, access) as key:
                        candidates.append(str(winreg.QueryValueEx(key, '')[0]).strip('"'))
                except OSError:
                    pass
    for base in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432'):
        candidates.append(str(Path(os.environ.get(base, 'C:/Program Files')) / 'Honeyview/Honeyview.exe'))
    return next((p for p in candidates if Path(p).is_file()), '')


def card_text(path, metadata, settings):
    name = path.name if settings.get('show_extension', True) else path.stem
    if not settings.get('show_filename', True):
        name = ''
    size, stamp = metadata
    fields = []
    if settings.get('show_size', True):
        fields.append(f'{size / (1024 ** 2):.1f} MB')
    if settings.get('show_date', True):
        fields.append(datetime.fromtimestamp(stamp).strftime('%Y-%m-%d') if stamp else tr('날짜 없음', settings.get('language', 'ko')))
    return name, ' · '.join(fields)


class Preferences:
    def apply_theme(self):
        self.palette = p = PALETTES.get(self.settings.get('theme', '라이트'), PALETTES['라이트'])
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background=p['panel'], foreground=p['fg'], font=(self.ui_font, self.font_size), bordercolor=p['border'])
        style.configure('TButton', padding=(12, 7), background=p['field'], borderwidth=1, relief='flat', lightcolor=p['border'], darkcolor=p['border'], focuscolor=p['accent'])
        style.configure('Toolbar.TButton', padding=(6, 7))
        style.configure('Toolbar.Fit.Toolbutton', padding=(6, 7))
        style.configure('Toolbar.TCombobox', padding=(6, 7))
        style.map('TButton', background=[('pressed', p['accent']), ('active', p['hover'])], bordercolor=[('focus', p['accent']), ('active', p['accent'])], foreground=[('disabled', p['muted'])])
        style.configure('Fit.Toolbutton', padding=(10, 7), background=p['field'], foreground=p['fg'])
        style.map('Fit.Toolbutton', background=[('selected', p['accent']), ('active', p['hover'])],
                  foreground=[('selected', '#FFFFFF'), ('!selected', p['fg'])], relief=[('selected', 'sunken'), ('!selected', 'raised')])
        style.configure('Section.TButton', anchor='w', padding=(8, 9), font=(self.ui_font, self.font_size, 'bold'))
        style.configure('TEntry', fieldbackground=p['field'], insertcolor=p['fg'], padding=(10, 8), borderwidth=1, relief='flat', lightcolor=p['border'], darkcolor=p['border'])
        style.map('TEntry', bordercolor=[('focus', p['accent'])], lightcolor=[('focus', p['accent'])], darkcolor=[('focus', p['accent'])])
        style.configure('Search.TEntry', padding=(12, 9))
        style.configure('TSpinbox', fieldbackground=p['field'], foreground=p['fg'],
                        background=p['field'], arrowcolor=p['fg'], insertcolor=p['fg'],
                        selectbackground=p['accent'], selectforeground='#FFFFFF',
                        padding=(8, 7), borderwidth=1, lightcolor=p['border'], darkcolor=p['border'])
        style.map('TSpinbox', fieldbackground=[('disabled', p['field']), ('readonly', p['field']), ('!disabled', p['field'])],
                  foreground=[('disabled', p['muted']), ('!disabled', p['fg'])],
                  arrowcolor=[('disabled', p['muted']), ('!disabled', p['fg'])],
                  bordercolor=[('focus', p['accent'])], lightcolor=[('focus', p['accent'])], darkcolor=[('focus', p['accent'])])
        style.configure('TCombobox', fieldbackground=p['field'], background=p['field'], arrowcolor=p['muted'], padding=(9, 7), borderwidth=1, lightcolor=p['border'], darkcolor=p['border'])
        style.map('TCombobox', fieldbackground=[('readonly', p['field'])], foreground=[('readonly', p['fg'])], selectbackground=[('readonly', p['field'])], selectforeground=[('readonly', p['fg'])])
        style.configure('Heading.TLabel', font=(self.ui_font, self.font_size + 4, 'bold'))
        style.configure('Treeview', background=p['panel'], fieldbackground=p['panel'], foreground=p['fg'], rowheight=max(28, self.font_size * 2 + 8), borderwidth=0)
        style.map('Treeview', background=[('selected', p['accent'])], foreground=[('selected', '#FFFFFF')])
        style.configure('TNotebook', background=p['bg'], borderwidth=0)
        # Clam has a selected-only padding map; override it explicitly.
        style.configure('TNotebook.Tab', padding=(23, 10), background=p['field'], foreground=p['muted'], borderwidth=0)
        style.map('TNotebook.Tab', padding=[('selected', (23, 10)), ('!selected', (23, 10))],
                  background=[('selected', p['panel']), ('active', p['hover'])],
                  foreground=[('selected', p['fg']), ('active', p['fg'])])
        if not hasattr(self, 'tab_images'):
            self.tab_images = [tk.PhotoImage(master=self, width=8, height=8) for _ in range(3)]
        for image, color, line in zip(self.tab_images, (p['field'], p['panel'], p['hover']),
                                       (p['border'], p['accent'], p['border'])):
            image.put(color, to=(0, 0, 8, 8))
            image.put(line, to=(0, 6, 8, 8))
        if 'Shelf.tab' not in style.element_names():
            style.element_create('Shelf.tab', 'image', self.tab_images[0],
                                 ('selected', self.tab_images[1]), ('active', self.tab_images[2]),
                                 border=(1, 1, 1, 3), sticky='nsew')
        style.layout('TNotebook.Tab', [('Shelf.tab', dict(sticky='nsew', children=[
            ('Notebook.padding', dict(sticky='nsew', children=[('Notebook.label', dict(sticky='nsew'))]))]))])
        style.configure('Card.TFrame', background=p['field'], bordercolor=p['border'], lightcolor=p['border'], darkcolor=p['border'], borderwidth=1, relief='solid')
        style.configure('SelectedCard.TFrame', background=p['field'], bordercolor=p['accent'], lightcolor=p['accent'], darkcolor=p['accent'], borderwidth=2, relief='solid')
        style.configure('Card.TLabel', background=p['field'], foreground=p['fg'])
        style.configure('CardMuted.TLabel', background=p['field'], foreground=p['muted'])
        style.configure('TScrollbar', background=p['border'], troughcolor=p['bg'], arrowcolor=p['muted'])
        style.configure('TScale', background=p['panel'], troughcolor=p['border'])
        style.configure('Muted.TLabel', foreground=p['muted'])
        self.option_add('*TCombobox*Listbox.background', p['field'])
        self.option_add('*TCombobox*Listbox.foreground', p['fg'])
        self.option_add('*TCombobox*Listbox.selectBackground', p['accent'])
        self.configure(bg=p['bg'])
        def tint(widget):
            if isinstance(widget, tk.Canvas):
                widget.configure(bg=p['bg'])
            elif isinstance(widget, tk.Listbox):
                widget.configure(bg=p['field'], fg=p['fg'], selectbackground=p['accent'], selectforeground='white', highlightthickness=0, relief='flat')
            elif isinstance(widget, tk.Label) and widget.cget('text') == '★':
                widget.configure(bg=p['field'])
            elif isinstance(widget, tk.Menu):
                widget.configure(bg=p['panel'], fg=p['fg'], activebackground=p['accent'], activeforeground='white')
            elif isinstance(widget, tk.Toplevel):
                widget.configure(bg=p['panel'])
            for child in widget.winfo_children():
                tint(child)
        tint(self)
        for _, card, _, _ in getattr(self, 'cards', {}).values():
            card.set_theme(p, (self.ui_font, self.font_size))
        if hasattr(self, 'apply_titlebar_theme'):
            self.after_idle(self.apply_titlebar_theme)

    def double_click(self, path):
        self.execute_action(path, self.settings.get('double_click', default_action()))

    def execute_action(self, path, action):
        action = normalize_action(action, keyboard=True)
        if action == '없음':
            return
        if action == '즐겨찾기 추가/해제':
            self.toggle_favorite(path)
            return
        if str(path) in getattr(self, 'preview_errors', set()):
            self.reveal(path)
            return
        if action == '파일 위치 열기':
            self.reveal(path)
        elif action == CUSTOM_VIEWER_ACTION:
            viewer = self.settings.get('custom_viewer', '')
            if not is_viewer(viewer):
                messagebox.showinfo(tr('뷰어 설정'), tr('설정에서 다른 뷰어 실행 파일을 지정해 주세요.'))
                self.open_settings()
                return
            try:
                launch_viewer(viewer, path)
            except OSError as exc:
                messagebox.showerror(tr('뷰어 실행 실패'), tr(str(exc)))
        else:
            self.open_archive(path)

    def commit_preferences(self, theme, action, honey, custom, recursive, display=None, typography=None, key_actions=None, language=None, shortcuts=None):
        if language is not None and language not in LANGUAGES:
            raise ValueError('지원하지 않는 언어입니다.')
        previous_language = self.settings.get('language', 'ko')
        if theme not in PALETTES or action not in available_actions():
            raise ValueError('테마와 더블클릭 동작을 선택해 주세요.')
        # Legacy callers may still supply Enter/Space actions. A new mapping is
        # authoritative only when explicitly supplied or already saved.
        if shortcuts is not None:
            shortcut_map = validate_shortcuts(shortcuts)
        elif key_actions is not None:
            if any(key_actions.get(key) not in available_actions(keyboard=True) for key in ('enter', 'space')):
                raise ValueError('Enter와 Space 동작을 선택해 주세요.')
            legacy = dict(self.settings, enter_action=key_actions['enter'], space_action=key_actions['space'])
            legacy.pop('shortcuts', None)
            shortcut_map = validate_shortcuts(migrate_shortcuts(legacy))
        else:
            shortcut_map = validate_shortcuts(migrate_shortcuts(self.settings))
        keys = legacy_actions(shortcut_map)
        labels = command_labels()
        selected_actions = {action} | {labels[command] for command, values in shortcut_map.items() if values}
        for selected, path in ((HONEYVIEW_ACTION, honey), (CUSTOM_VIEWER_ACTION, custom)):
            if selected in selected_actions and path and not is_viewer(path):
                raise ValueError('선택한 프로그램 파일을 찾을 수 없습니다.')
        if CUSTOM_VIEWER_ACTION in selected_actions and not custom:
            raise ValueError('다른 뷰어 프로그램의 실행 파일을 선택해 주세요.')
        # Validate every field before changing settings or live typography.
        display_values = None
        if display is not None:
            try:
                display_values = {key: bool(display[key]) for key in ('show_filename', 'show_extension', 'show_size', 'show_date')}
            except (KeyError, TypeError):
                raise ValueError('표시 설정을 확인해 주세요.')
        font_view = None
        previous_size = getattr(self, 'font_size', 10)
        if typography is not None:
            try:
                size = int(typography['size'])
            except (KeyError, ValueError, TypeError):
                raise ValueError('글자 크기는 8~24 사이의 정수로 입력해 주세요.')
            if not 8 <= size <= 24:
                raise ValueError('글자 크기는 8~24 사이로 선택해 주세요.')
            family = typography.get('family', '')
            if family and family not in font.families(self):
                raise ValueError('설치된 글꼴 목록에서 선택해 주세요.')
        if typography is not None:
            self.remember_position()
            font_view = self.views.get(self.current_folder, {}).copy()
            self.settings.update(font_family=family, font_size=size)
            self.font_size = size
            self.ui_font = configure_fonts(self, family, size)
        changed = recursive != self.recursive.get()
        self.settings.update(theme=theme, double_click=action, shortcuts=shortcut_map,
                             viewer=honey, custom_viewer=custom, **keys)
        if display_values is not None:
            self.settings.update(display_values)
        if language is not None:
            self.settings['language'] = language
        self.recursive.set(recursive)
        if hasattr(self, 'refresh_shortcuts'):
            self.refresh_shortcuts()
        self.save()
        if hasattr(self, 'refresh_card_labels'):
            self.refresh_card_labels()
        self.apply_theme()
        if typography is not None:
            self.update_region()
            if self.font_size != previous_size and font_view:
                self.restore_position(font_view)
            else:
                self.refresh_visible()
        if language is not None and hasattr(self, 'apply_language'):
            self.apply_language()
            if language != previous_language:
                self.update_shortcut_language()
        if changed and self.current_folder:
            self.scan()

    def open_settings(self):
        existing = getattr(self, 'settings_window', None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return
        dialog = self.settings_window = tk.Toplevel(self)
        dialog.withdraw()
        dialog.title(tr('설정 · {name}'.format(name=tr(APP_NAME))))
        dialog.geometry('720x590')
        dialog.minsize(680, 560)
        dialog.transient(self)
        language = tk.StringVar(dialog, value=LANGUAGES.get(self.settings.get('language', 'ko'), '한국어'))
        self.language_choice = language
        theme = tk.StringVar(dialog, value=self.settings.get('theme', '라이트'))
        action = tk.StringVar(dialog, value=normalize_action(self.settings.get('double_click', default_action())))
        honey = tk.StringVar(dialog, value=self.settings.get('viewer') or detect_honeyview())
        custom = tk.StringVar(dialog, value=self.settings.get('custom_viewer', ''))
        recursive = tk.BooleanVar(dialog, value=self.recursive.get())
        shortcut_map = migrate_shortcuts(self.settings)
        labels = command_labels()
        shortcut_vars = {command: [tk.StringVar(dialog, value=(shortcut_map[command][index]
                         if index < len(shortcut_map[command]) else '')) for index in range(2)]
                         for command in labels}
        dialog.shortcut_vars = shortcut_vars
        dialog.shortcut_buttons = {}
        dialog.action_var = action
        pages = ttk.Notebook(dialog)
        pages.pack(fill='both', expand=True, padx=14, pady=(14, 0))
        def make_page():
            page = ttk.Frame(pages)
            inner = ttk.Frame(page, padding=18)
            inner.pack(fill='both', expand=True)
            return page, inner
        general, content = make_page()
        display_outer, display_page = make_page()
        font_outer, font_page = make_page()
        pages.add(general, text=tr('일반'))
        pages.add(display_outer, text=tr('표시 설정'))
        pages.add(font_outer, text=tr('글꼴'))
        opening_outer, opening = make_page()
        pages.add(opening_outer, text=tr('열기 동작'))
        shortcuts_outer, shortcuts_page = make_page()
        pages.add(shortcuts_outer, text=tr('단축키'))
        dialog.settings_tabs = pages
        def fit_dialog():
            if not dialog.winfo_exists():
                return
            dialog.update_idletasks()
            width = max(720, dialog.winfo_reqwidth())
            height = max(590, dialog.winfo_reqheight())
            dialog.minsize(width, height)
            if not getattr(dialog, '_initial_position_set', False):
                # Set before centering: update_idletasks can run another pending fit.
                dialog._initial_position_set = True
                center_dialog(dialog, self, width, height)
                dialog.deiconify()
                dialog.grab_set()
            else:
                # Keep a position the user has chosen by dragging the dialog.
                dialog.geometry(f'{width}x{height}')
        display = {key: tk.BooleanVar(dialog, value=self.settings.get(key, True))
                   for key in ('show_filename', 'show_extension', 'show_size', 'show_date')}
        ttk.Label(display_page, text=tr('썸네일 카드 표시'), style='Heading.TLabel').pack(anchor='w', pady=(0, 16))
        extension = ttk.Checkbutton(display_page, text=tr('파일명에 확장자 표시'), variable=display['show_extension'])
        def filename_changed():
            extension.configure(state='normal' if display['show_filename'].get() else 'disabled')
        ttk.Checkbutton(display_page, text=tr('파일명'), variable=display['show_filename'], command=filename_changed).pack(anchor='w', pady=6)
        extension.pack(anchor='w', padx=24, pady=(0, 10))
        ttk.Checkbutton(display_page, text=tr('용량'), variable=display['show_size']).pack(anchor='w', pady=6)
        ttk.Checkbutton(display_page, text=tr('날짜 (수정한 날짜)'), variable=display['show_date']).pack(anchor='w', pady=6)
        ttk.Label(display_page, text=tr('체크한 항목만 카드에 표시합니다. 전체 경로와 파일 정보는 그대로 확인할 수 있습니다.'), wraplength=510, style='Muted.TLabel').pack(anchor='w', pady=(18, 0))
        filename_changed()
        automatic_font = '자동 선택 (CJK 우선)'
        family_choice = tk.StringVar(dialog, value=self.settings.get('font_family') or automatic_font)
        size_choice = tk.StringVar(dialog, value=str(self.font_size))
        ttk.Label(font_page, text=tr('글꼴과 글자 크기'), style='Heading.TLabel').pack(anchor='w', pady=(0, 18))
        ttk.Label(font_page, text=tr('글꼴')).pack(anchor='w')
        family_box = ttk.Combobox(font_page, state='readonly', textvariable=family_choice,
                                  values=[automatic_font] + sorted(set(font.families(self)), key=str.casefold))
        family_box.pack(fill='x', pady=(5, 16))
        ttk.Label(font_page, text=tr('글자 크기 (pt · 8~24)')).pack(anchor='w')
        size_box = ttk.Spinbox(font_page, from_=8, to=24, textvariable=size_choice, width=8)
        size_box.pack(anchor='w', pady=(5, 16))
        ttk.Label(font_page, text=tr('미리보기'), style='Muted.TLabel').pack(anchor='w')
        preview = ttk.Label(font_page, text=tr('한글 · 日本語 · 漢字 · ABC 123'), wraplength=490)
        preview.pack(fill='x', pady=(8, 16))
        def update_preview(*_):
            try:
                value = int(size_choice.get())
                if not 8 <= value <= 24:
                    return
            except ValueError:
                return
            selected = (select_family(font.families(self)) or self.ui_font) if family_choice.get() == automatic_font else family_choice.get()
            preview.configure(font=(selected, value))
        family_choice.trace_add('write', update_preview)
        size_choice.trace_add('write', update_preview)
        update_preview()
        ttk.Label(font_page, text=tr('일본어·한자가 보이지 않으면 자동 선택 또는 Noto Sans CJK KR을 선택하세요. 적용을 누르기 전에는 미리보기에만 반영됩니다.'), wraplength=490, style='Muted.TLabel').pack(anchor='w')
        ttk.Label(content, text=tr('화면 및 파일 열기'), style='Heading.TLabel').pack(anchor='w', pady=(0, 18))
        ttk.Label(content, text=tr('언어')).pack(anchor='w')
        ttk.Combobox(content, state='readonly', textvariable=language, values=list(LANGUAGES.values())).pack(fill='x', pady=(5, 16))
        ttk.Label(content, text=tr('화면 모드')).pack(anchor='w')
        ttk.Combobox(content, state='readonly', textvariable=theme, values=list(PALETTES)).pack(fill='x', pady=(5, 16))
        ttk.Label(opening, text=tr('카드 실행 동작'), style='Heading.TLabel').pack(anchor='w', pady=(0, 14))
        choices = []
        for label, variable, values in [('더블클릭', action, available_actions())]:
            row = ttk.Frame(opening)
            row.pack(fill='x', pady=5)
            ttk.Label(row, text=label, width=12).pack(side='left')
            box = ttk.Combobox(row, state='readonly', textvariable=variable, values=values)
            box.pack(side='left', fill='x', expand=True)
            choices.append(box)
            dialog.action_box = box
        paths = ttk.Frame(opening)
        paths.pack(fill='x', pady=(16, 0))
        path_boxes = {}
        viewer_fields = [(CUSTOM_VIEWER_ACTION, '다른 뷰어 실행 파일 경로', custom)]
        if sys.platform != 'darwin':
            viewer_fields.insert(0, (HONEYVIEW_ACTION, '꿀뷰 실행 파일 경로', honey))
        for mode, title, variable in viewer_fields:
            panel = ttk.Frame(paths)
            ttk.Label(panel, text=title).pack(anchor='w')
            entry = ttk.Entry(panel, textvariable=variable)
            entry.pack(fill='x', pady=5)
            def browse(var=variable):
                selected = choose_viewer(parent=dialog)
                if selected:
                    var.set(selected)
            ttk.Button(panel, text=tr('찾아보기'), command=browse).pack(anchor='w')
            if sys.platform == 'darwin':
                ttk.Label(panel, text=tr('macOS에서는 .app 또는 실행 파일을 선택하세요.'), style='Muted.TLabel').pack(anchor='w', pady=5)
            path_boxes[mode] = panel
        def find():
            honey.set(detect_honeyview())
        if HONEYVIEW_ACTION in path_boxes:
            ttk.Button(path_boxes[HONEYVIEW_ACTION], text=tr('꿀뷰 자동 찾기'), command=find).pack(anchor='w', pady=5)
        for index in range(len(path_boxes)):
            paths.columnconfigure(index, weight=1)
        def change(event=None):
            selected = {action.get()} | {labels[command] for command, values in shortcut_vars.items()
                                        if any(variable.get() for variable in values)}
            for index, mode in enumerate(path_boxes):
                path_boxes[mode].grid_forget()
                if mode in selected:
                    path_boxes[mode].grid(row=0, column=index, sticky='new', padx=(0, 12) if index < len(path_boxes) - 1 else 0)
            dialog.after_idle(fit_dialog)
        ttk.Label(shortcuts_page, text=tr('기능별 단축키'), style='Heading.TLabel').pack(anchor='w', pady=(0, 10))
        ttk.Label(shortcuts_page, text=tr('키 칸을 누른 뒤 원하는 키를 입력하세요. 같은 기능에 키를 두 개까지 지정할 수 있습니다.'),
                  wraplength=630, style='Muted.TLabel').pack(anchor='w', pady=(0, 12))
        shortcut_table = ttk.Frame(shortcuts_page)
        shortcut_table.pack(fill='x')
        shortcut_table.columnconfigure(0, weight=1)
        ttk.Style(self).configure('ShortcutKey.TButton', padding=(8, 3))
        for column, title in enumerate(('기능', '키 1', '키 2')):
            ttk.Label(shortcut_table, text=tr(title), style='Muted.TLabel').grid(row=0, column=column, sticky='w', padx=(0, 12), pady=(0, 5))
        def draft_shortcuts():
            return {command: [variable.get() for variable in values]
                    for command, values in shortcut_vars.items()}
        def assign_shortcut(command, index, key):
            key = normalize_key(key)
            draft = draft_shortcuts()
            draft[command][index] = key
            normalized = validate_shortcuts(draft)
            # Keep the selected slot stable, including an empty first slot.
            shortcut_vars[command][index].set(key if key else '')
            return normalized
        dialog.settings_assign_shortcut = assign_shortcut
        def capture_shortcut(command, index):
            existing_capture = getattr(dialog, 'shortcut_capture', None)
            if existing_capture is not None and existing_capture.winfo_exists():
                existing_capture.lift()
                return
            capture = dialog.shortcut_capture = tk.Toplevel(dialog)
            capture.withdraw()
            capture.title(tr('단축키 할당 · {action}').format(action=tr(labels[command])))
            capture.transient(dialog)
            capture.resizable(False, False)
            capture.configure(bg=self.palette['panel'])
            frame = ttk.Frame(capture, padding=20)
            frame.pack(fill='both', expand=True)
            ttk.Label(frame, text=tr('할당할 키를 누르세요.'), style='Heading.TLabel').pack(anchor='w')
            ttk.Label(frame, text=tr('Ctrl·Alt·Shift·Command와 다른 키를 함께 누를 수 있습니다.'),
                      wraplength=440, style='Muted.TLabel').pack(anchor='w', pady=(8, 12))
            capture.key_var = tk.StringVar(capture, value='')
            capture.error_var = tk.StringVar(capture, value='')
            capture.key_entry = ttk.Entry(frame, textvariable=capture.key_var, state='readonly', justify='center', width=34)
            capture.key_entry.pack(fill='x', pady=(0, 10))
            ttk.Label(frame, textvariable=capture.error_var, wraplength=440, foreground=self.palette['accent']).pack(fill='x', pady=(0, 12))
            def close_capture():
                capture.destroy()
                if dialog.winfo_exists():
                    dialog.grab_set()
                    dialog.shortcut_buttons[command][index].focus_set()
            def accept_capture():
                key = capture.key_var.get()
                if not key:
                    capture.error_var.set(tr('사용할 단축키를 먼저 입력해 주세요.'))
                    return
                try:
                    assign_shortcut(command, index, key)
                except ValueError as exc:
                    capture.error_var.set(tr(str(exc)))
                    messagebox.showerror(tr('중복 단축키'), tr(str(exc)), parent=capture)
                    return
                close_capture()
            def clear_capture():
                assign_shortcut(command, index, '')
                close_capture()
            def key_pressed(event):
                key = event_key(event)
                if key == 'Escape':
                    close_capture()
                    return 'break'
                if key:
                    try:
                        validate_shortcuts({command: [key]})
                    except ValueError as exc:
                        capture.error_var.set(tr(str(exc)))
                    else:
                        capture.key_var.set(key)
                        capture.error_var.set('')
                return 'break'
            actions = ttk.Frame(frame)
            actions.pack(fill='x')
            ttk.Button(actions, text=tr('할당 해제'), command=clear_capture).pack(side='left')
            ttk.Button(actions, text=tr('할당'), command=accept_capture).pack(side='right')
            ttk.Button(actions, text=tr('취소'), command=close_capture).pack(side='right', padx=8)
            capture.settings_accept = accept_capture
            capture.settings_clear = clear_capture
            capture.settings_cancel = close_capture
            capture.protocol('WM_DELETE_WINDOW', close_capture)
            capture.bind('<KeyPress>', key_pressed)
            style_settings(capture)
            center_dialog(capture, dialog)
            capture.deiconify()
            capture.grab_set()
            capture.after_idle(capture.key_entry.focus_force)
        dialog.settings_capture_shortcut = capture_shortcut
        for row_index, (command, label) in enumerate(labels.items(), start=1):
            ttk.Label(shortcut_table, text=tr(label)).grid(row=row_index, column=0, sticky='w', padx=(0, 18), pady=2)
            buttons_for_command = []
            for index, variable in enumerate(shortcut_vars[command]):
                button = ttk.Button(shortcut_table, width=16, style='ShortcutKey.TButton',
                                    command=lambda command=command, index=index: capture_shortcut(command, index))
                button.grid(row=row_index, column=index + 1, sticky='ew', padx=(0, 8) if index == 0 else 0, pady=2)
                def show_key(*_, variable=variable, button=button):
                    button.configure(text=variable.get() or tr('없음'))
                    change()
                variable.trace_add('write', show_key)
                button.configure(text=variable.get() or tr('없음'))
                buttons_for_command.append(button)
            dialog.shortcut_buttons[command] = buttons_for_command
        shortcut_status = tk.StringVar(dialog, value='')
        dialog.shortcut_status = shortcut_status
        def reset_shortcuts():
            defaults = default_shortcuts()
            for command, values in shortcut_vars.items():
                for index, variable in enumerate(values):
                    variable.set(defaults[command][index] if index < len(defaults[command]) else '')
            shortcut_status.set(tr('기본 단축키를 불러왔습니다. 적용을 누르면 저장됩니다.'))
        dialog.settings_reset_shortcuts = reset_shortcuts
        ttk.Button(shortcuts_page, text=tr('기본값 복원'), command=reset_shortcuts).pack(anchor='w', pady=(12, 5))
        ttk.Label(shortcuts_page, textvariable=shortcut_status, wraplength=630, style='Muted.TLabel').pack(anchor='w')
        ttk.Label(shortcuts_page, text=tr('파일 작업은 썸네일 영역에서, 폴더 패널·창 맞춤은 메인 창에서 동작합니다. 입력창과 설정창에서는 화면 전환 키가 동작하지 않습니다.'),
                  wraplength=630, style='Muted.TLabel').pack(anchor='w', pady=(10, 0))
        options = ttk.Frame(content)
        options.pack(fill='x', pady=(16, 0))
        ttk.Checkbutton(options, text=tr('전체 탭에서 하위 폴더까지 모아 보기'), variable=recursive).pack(anchor='w')
        buttons = ttk.Frame(dialog, padding=(22, 10))
        buttons.pack(fill='x')
        def apply():
            try:
                self.commit_preferences(theme.get(), action.get(), honey.get().strip(), custom.get().strip(), recursive.get(), {key: value.get() for key, value in display.items()},
                                        dict(family='' if family_choice.get() == automatic_font else family_choice.get(), size=size_choice.get()),
                                        language=next(code for code, label in LANGUAGES.items() if label == language.get()),
                                        shortcuts=draft_shortcuts())
            except ValueError as exc:
                messagebox.showerror(tr('설정 확인'), tr(str(exc)), parent=dialog)
                return
            dialog.destroy()
        dialog.settings_apply = apply
        ttk.Button(buttons, text=tr('적용'), command=apply).pack(side='right')
        ttk.Button(buttons, text=tr('취소'), command=dialog.destroy).pack(side='right', padx=8)
        dialog.bind('<Escape>', lambda e: dialog.destroy())
        for choice in choices:
            choice.bind('<<ComboboxSelected>>', change)
        self.apply_theme()
        # Keep the settings controls compact; the font sample retains the selected size.
        settings_style = ttk.Style(self)
        def style_settings(widget):
            kind = widget.winfo_class()
            if kind.startswith('T') and kind not in ('Toplevel', 'TFrame'):
                original = widget.cget('style') or kind
                name = 'Settings.' + original
                settings_style.configure(name, font=(self.ui_font, min(self.font_size, 12) + (3 if original == 'Heading.TLabel' else 0), 'bold' if original == 'Heading.TLabel' else 'normal'))
                widget.configure(style=name)
            for child in widget.winfo_children():
                style_settings(child)
        style_settings(dialog)
        settings_style.configure('Settings.TNotebook.Tab', font=(self.ui_font, min(self.font_size, 12)))
        localize_widgets(dialog)
        change()
        dialog.after_idle(fit_dialog)
