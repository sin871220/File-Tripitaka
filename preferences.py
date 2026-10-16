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
from viewer import (ACTIONS, KEY_ACTIONS, CUSTOM_VIEWER_ACTION, DEFAULT_APP_ACTION,
                    HONEYVIEW_ACTION, available_actions, default_action,
                    normalize_action, is_viewer, launch_viewer, choose_viewer)

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

    def commit_preferences(self, theme, action, honey, custom, recursive, display=None, typography=None, key_actions=None, language=None):
        if language is not None and language not in LANGUAGES:
            raise ValueError('지원하지 않는 언어입니다.')
        previous_language = self.settings.get('language', 'ko')
        if theme not in PALETTES or action not in available_actions():
            raise ValueError('테마와 더블클릭 동작을 선택해 주세요.')
        keys = key_actions or dict(enter=self.settings.get('enter_action', action), space=self.settings.get('space_action', action))
        if any(keys.get(key) not in available_actions(keyboard=True) for key in ('enter', 'space')):
            raise ValueError('Enter와 Space 동작을 선택해 주세요.')
        selected_actions = {action, keys['enter'], keys['space']}
        for selected, path in ((HONEYVIEW_ACTION, honey), (CUSTOM_VIEWER_ACTION, custom)):
            if selected in selected_actions and path and not is_viewer(path):
                raise ValueError('선택한 프로그램 파일을 찾을 수 없습니다.')
        if CUSTOM_VIEWER_ACTION in selected_actions and not custom:
            raise ValueError('다른 뷰어 프로그램의 실행 파일을 선택해 주세요.')
        font_view = None
        previous_size = getattr(self, 'font_size', 10)
        if typography is not None:
            try:
                size = int(typography['size'])
            except (ValueError, TypeError):
                raise ValueError('글자 크기는 8~24 사이의 정수로 입력해 주세요.')
            if not 8 <= size <= 24:
                raise ValueError('글자 크기는 8~24 사이로 선택해 주세요.')
            family = typography.get('family', '')
            if family and family not in font.families(self):
                raise ValueError('설치된 글꼴 목록에서 선택해 주세요.')
            self.remember_position()
            font_view = self.views.get(self.current_folder, {}).copy()
            self.settings.update(font_family=family, font_size=size)
            self.font_size = size
            self.ui_font = configure_fonts(self, family, size)
        changed = recursive != self.recursive.get()
        self.settings.update(theme=theme, double_click=action, enter_action=keys['enter'], space_action=keys['space'], viewer=honey, custom_viewer=custom)
        if display is not None:
            self.settings.update({key: bool(display[key]) for key in ('show_filename', 'show_extension', 'show_size', 'show_date')})
        if language is not None:
            self.settings['language'] = language
        self.recursive.set(recursive)
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
        dialog.title(tr('설정 · {name}'.format(name=tr(APP_NAME))))
        dialog.geometry('640x560')
        dialog.minsize(600, 540)
        dialog.transient(self)
        dialog.grab_set()
        language = tk.StringVar(dialog, value=LANGUAGES.get(self.settings.get('language', 'ko'), '한국어'))
        self.language_choice = language
        theme = tk.StringVar(dialog, value=self.settings.get('theme', '라이트'))
        action = tk.StringVar(dialog, value=normalize_action(self.settings.get('double_click', default_action())))
        honey = tk.StringVar(dialog, value=self.settings.get('viewer') or detect_honeyview())
        custom = tk.StringVar(dialog, value=self.settings.get('custom_viewer', ''))
        recursive = tk.BooleanVar(dialog, value=self.recursive.get())
        enter_action = tk.StringVar(dialog, value=normalize_action(self.settings.get('enter_action', action.get()), keyboard=True))
        space_action = tk.StringVar(dialog, value=normalize_action(self.settings.get('space_action', action.get()), keyboard=True))
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
        def fit_dialog():
            if not dialog.winfo_exists():
                return
            dialog.update_idletasks()
            width = max(640, dialog.winfo_reqwidth())
            height = max(560, dialog.winfo_reqheight())
            dialog.minsize(width, height)
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
        for label, variable, values in [('더블클릭', action, available_actions()), ('Enter', enter_action, available_actions(keyboard=True)), ('Space', space_action, available_actions(keyboard=True))]:
            row = ttk.Frame(opening)
            row.pack(fill='x', pady=5)
            ttk.Label(row, text=label, width=12).pack(side='left')
            box = ttk.Combobox(row, state='readonly', textvariable=variable, values=values)
            box.pack(side='left', fill='x', expand=True)
            choices.append(box)
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
            selected = {action.get(), enter_action.get(), space_action.get()}
            for index, mode in enumerate(path_boxes):
                path_boxes[mode].grid_forget()
                if mode in selected:
                    path_boxes[mode].grid(row=0, column=index, sticky='new', padx=(0, 12) if index < len(path_boxes) - 1 else 0)
            dialog.after_idle(fit_dialog)
        options = ttk.Frame(content)
        options.pack(fill='x', pady=(16, 0))
        ttk.Checkbutton(options, text=tr('전체 탭에서 하위 폴더까지 모아 보기'), variable=recursive).pack(anchor='w')
        buttons = ttk.Frame(dialog, padding=(22, 10))
        buttons.pack(fill='x')
        def apply():
            try:
                self.commit_preferences(theme.get(), action.get(), honey.get().strip(), custom.get().strip(), recursive.get(), {key: value.get() for key, value in display.items()},
                                        dict(family='' if family_choice.get() == automatic_font else family_choice.get(), size=size_choice.get()),
                                        dict(enter=enter_action.get(), space=space_action.get()),
                                        language=next(code for code, label in LANGUAGES.items() if label == language.get()))
            except ValueError as exc:
                messagebox.showerror(tr('설정 확인'), tr(str(exc)), parent=dialog)
                return
            dialog.destroy()
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
        localize_widgets(dialog)
        change()
        dialog.after_idle(fit_dialog)
