from localization import translate as tr, set_language, localize_widgets, LANGUAGES
"""Theme and viewer preferences UI shared by the browser."""
import os
from datetime import datetime
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font, colorchooser
from ui_fonts import configure_fonts, select_family
from brand import APP_NAME, APP_VERSION
from dialog_geometry import center_dialog
from gallery_card import GalleryCard
from thumbnail_overlays import (normalize_overlay_settings, normalize_overlay_order, OVERLAY_POSITIONS,
                                POSITION_LABELS, OVERLAY_SIZES, SIZE_LABELS,
                                PAGE_FONT_MIN, PAGE_FONT_MAX, PAGE_FONT_DEFAULT)
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
        style.configure('OverlayRow.TFrame', background=p['panel'], borderwidth=1,
                        relief='solid', bordercolor=p['panel'], lightcolor=p['panel'], darkcolor=p['panel'])
        style.map('OverlayRow.TFrame', background=[('alternate', p['hover'])],
                  bordercolor=[('alternate', p['accent'])], lightcolor=[('alternate', p['accent'])],
                  darkcolor=[('alternate', p['accent'])])
        style.configure('OverlayRow.TLabel', background=p['panel'], foreground=p['fg'])
        style.map('OverlayRow.TLabel', background=[('alternate', p['hover'])],
                  foreground=[('alternate', p['fg'])])
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
        elif getattr(self, 'item_kinds', {}).get(path) == 'folder':
            self.open_folder_image(path, action)
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

    def commit_preferences(self, theme, action, honey, custom, recursive, display=None, typography=None, key_actions=None, language=None, shortcuts=None, overlays=None, overlay_order=None):
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
        if isinstance(overlays, dict) and isinstance(overlays.get('pages'), dict):
            alpha = overlays['pages'].get('background_alpha', 100)
            if isinstance(alpha, bool) or not isinstance(alpha, int) or not 0 <= alpha <= 100:
                raise ValueError('배경 알파는 0~100 사이의 정수로 입력해 주세요.')
            if 'font_size' in overlays['pages']:
                page_font = overlays['pages']['font_size']
                if (isinstance(page_font, bool) or not isinstance(page_font, int)
                        or not PAGE_FONT_MIN <= page_font <= PAGE_FONT_MAX):
                    raise ValueError('페이지 글자 크기는 4~72 사이의 정수로 입력해 주세요.')
        overlay_values = normalize_overlay_settings(overlays, ui_font_size=getattr(self, 'font_size', 10)) if overlays is not None else None
        ordered_overlays = normalize_overlay_order(overlay_order) if overlay_order is not None else None
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
        if overlay_values is not None:
            self.settings['thumbnail_overlays'] = overlay_values
        if ordered_overlays is not None:
            self.settings['thumbnail_overlay_order'] = ordered_overlays
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
        ttk.Label(display_page, text=tr('썸네일 카드 표시'), style='Heading.TLabel').pack(anchor='w', pady=(0, 12))
        details = ttk.Frame(display_page)
        details.pack(fill='x')
        extension = ttk.Checkbutton(details, text=tr('파일명에 확장자 표시'), variable=display['show_extension'])
        def filename_changed():
            extension.configure(state='normal' if display['show_filename'].get() else 'disabled')
        ttk.Checkbutton(details, text=tr('파일명'), variable=display['show_filename'], command=filename_changed).grid(row=0, column=0, sticky='w', pady=5, padx=(0, 24))
        extension.grid(row=0, column=1, sticky='w', pady=5)
        ttk.Checkbutton(details, text=tr('용량'), variable=display['show_size']).grid(row=1, column=0, sticky='w', pady=5, padx=(0, 24))
        ttk.Checkbutton(details, text=tr('날짜 (수정한 날짜)'), variable=display['show_date']).grid(row=1, column=1, sticky='w', pady=5)
        ttk.Label(display_page, text=tr('체크한 항목만 카드에 표시합니다. 전체 경로와 파일 정보는 그대로 확인할 수 있습니다.'), wraplength=630, style='Muted.TLabel').pack(anchor='w', pady=(8, 12))
        filename_changed()
        ttk.Separator(display_page).pack(fill='x', pady=(0, 12))
        ttk.Label(display_page, text=tr('썸네일 위 표시'), style='Heading.TLabel').pack(anchor='w', pady=(0, 10))
        overlay_values = normalize_overlay_settings(self.settings.get('thumbnail_overlays'), ui_font_size=self.font_size)
        overlay_order = normalize_overlay_order(self.settings.get('thumbnail_overlay_order'))
        overlay_selected = tk.StringVar(dialog, value=overlay_order[0])
        overlay_visible = {key: tk.BooleanVar(dialog, value=value['visible'])
                           for key, value in overlay_values.items()}
        overlay_position = {key: tk.StringVar(dialog, value=value['position'])
                            for key, value in overlay_values.items()}
        overlay_size = {key: tk.StringVar(dialog, value=overlay_values[key].get('size', 'large'))
                        for key in ('favorite', 'folder')}
        page_font_size = tk.StringVar(dialog, value=str(overlay_values['pages'].get('font_size', PAGE_FONT_DEFAULT)))
        last_valid_page_font_size = [int(page_font_size.get())]
        page_colors = {field: tk.StringVar(dialog, value=overlay_values['pages'].get(field, default))
                       for field, default in (('text_color', '#FFFFFF'), ('background_color', '#242830'))}
        page_alpha = tk.StringVar(dialog, value=str(overlay_values['pages'].get('background_alpha', 100)))
        last_valid_page_alpha = [int(page_alpha.get())]
        page_color_images = {}
        page_color_buttons = {}
        dialog.settings_overlay_visible = overlay_visible
        dialog.settings_overlay_position = overlay_position
        dialog.settings_overlay_combos = {}
        dialog.settings_overlay_controls = dialog.settings_overlay_combos
        dialog.settings_overlay_size = overlay_size
        dialog.settings_overlay_size_controls = {}
        dialog.settings_overlay_order = overlay_order
        dialog.settings_overlay_selected = overlay_selected
        dialog.settings_overlay_rows = {}
        dialog.settings_overlay_labels = {}
        dialog.settings_overlay_checks = {}
        dialog.settings_overlay_handles = {}
        dialog.settings_page_text_color = page_colors['text_color']
        dialog.settings_page_background_color = page_colors['background_color']
        dialog.settings_page_alpha = page_alpha
        dialog.settings_page_font_size = page_font_size
        overlay_section = ttk.Frame(display_page)
        overlay_section.pack(fill='x')
        overlay_controls = ttk.Frame(overlay_section)
        overlay_controls.pack(side='left', fill='both', expand=True, padx=(0, 16))
        overlay_preview = ttk.Frame(overlay_section)
        overlay_preview.pack(side='right', anchor='n')
        ttk.Label(overlay_preview, text=tr('미리보기'), style='Muted.TLabel').pack(anchor='w', pady=(0, 5))
        preview_canvas = tk.Canvas(overlay_preview, width=166, height=216,
                                   highlightthickness=0, bd=0, bg=self.palette['field'])
        preview_canvas.pack()
        preview_card = GalleryCard(preview_canvas, Path('preview'), 0, 0, 166, 216,
                                   self.palette, (self.ui_font, min(self.font_size, 11)))
        preview_card.set_favorite(True)
        preview_card.set_folder(True)
        preview_card.set_page_count(30)
        # A neutral sample makes all four corners visible without using a file.
        from PIL import Image, ImageDraw
        sample = Image.new('RGB', (150, 200), '#DAE5ED')
        drawing = ImageDraw.Draw(sample)
        drawing.polygon(((0, 200), (0, 150), (52, 95), (100, 160), (150, 110), (150, 200)), fill='#8AA9B3')
        preview_card.thumbnail.show_image(sample, (150, 200))
        dialog.settings_overlay_preview = preview_card
        overlay_traces = []
        overlay_drag = {}
        def dispose_preview(event):
            if event.widget is dialog:
                for variable, trace_id in overlay_traces:
                    try:
                        variable.trace_remove('write', trace_id)
                    except tk.TclError:
                        pass
                overlay_traces.clear()
                overlay_drag.clear()
                for button in page_color_buttons.values():
                    try:
                        button.configure(image='')
                    except tk.TclError:
                        pass
                page_color_images.clear()
                preview_card.destroy()
        dialog.bind('<Destroy>', dispose_preview, add='+')
        def read_page_alpha(strict=False):
            try:
                value = int(page_alpha.get().strip())
                if not 0 <= value <= 100:
                    raise ValueError
            except (ValueError, tk.TclError):
                if strict:
                    raise ValueError('배경 알파는 0~100 사이의 정수로 입력해 주세요.')
                return last_valid_page_alpha[0]
            last_valid_page_alpha[0] = value
            return value
        def read_page_font_size(strict=False):
            try:
                value = int(page_font_size.get().strip())
                if not PAGE_FONT_MIN <= value <= PAGE_FONT_MAX:
                    raise ValueError
            except (ValueError, tk.TclError):
                if strict:
                    raise ValueError('페이지 글자 크기는 4~72 사이의 정수로 입력해 주세요.')
                return last_valid_page_font_size[0]
            last_valid_page_font_size[0] = value
            return value
        def draft_overlays(strict=False):
            values = {key: dict(visible=overlay_visible[key].get(), position=overlay_position[key].get())
                      for key in overlay_values}
            for key, choice in overlay_size.items():
                values[key]['size'] = choice.get()
            values['pages'].update({field: variable.get() for field, variable in page_colors.items()})
            values['pages']['background_alpha'] = read_page_alpha(strict)
            values['pages']['font_size'] = read_page_font_size(strict)
            return values
        def update_overlay_preview(*_):
            if not preview_card.alive:
                return
            preview_palette = PALETTES.get(theme.get(), self.palette)
            preview_overlays = normalize_overlay_settings(draft_overlays(), ui_font_size=self.font_size)
            preview_card.set_overlays(preview_overlays)
            preview_card.set_overlay_order(overlay_order)
            preview_card.set_theme(preview_palette, (self.ui_font, min(self.font_size, 11)))
            preview_canvas.configure(bg=preview_palette['field'])
            for key, choice in dialog.settings_overlay_combos.items():
                choice.configure(state='readonly' if overlay_visible[key].get() else 'disabled')
            for key, choice in dialog.settings_overlay_size_controls.items():
                choice.configure(state='readonly' if overlay_visible[key].get() else 'disabled')
            page_state = ['!disabled'] if overlay_visible['pages'].get() else ['disabled']
            for field, button in page_color_buttons.items():
                color = preview_overlays['pages'].get(field, '#FFFFFF' if field == 'text_color' else '#242830')
                button.configure(text=color)
                page_color_images[field].put(color, to=(0, 0, 14, 14))
                button.state(page_state)
            if hasattr(dialog, 'settings_page_alpha_control'):
                dialog.settings_page_alpha_control.state(page_state)
            if hasattr(dialog, 'settings_page_font_size_control'):
                dialog.settings_page_font_size_control.state(page_state)
        def start_overlay_drag(event, key):
            overlay_selected.set(key)
            overlay_drag.update(key=key, start_y=event.y_root, active=False)
        def drag_overlay(event):
            key = overlay_drag.get('key')
            if key is None:
                return
            if not overlay_drag['active']:
                if abs(event.y_root - overlay_drag['start_y']) < 6:
                    return
                overlay_drag['active'] = True
            # Flush geometry only: processing Tk events here would re-enter a
            # drag handler while the same row order is being changed.
            overlay_controls.update_idletasks()
            target = min(range(len(overlay_order)), key=lambda index: abs(
                event.y_root - (dialog.settings_overlay_rows[overlay_order[index]].winfo_rooty()
                                + dialog.settings_overlay_rows[overlay_order[index]].winfo_height() / 2)))
            move_overlay_to(key, target)
        def finish_overlay_drag(event):
            overlay_drag.clear()
        def bind_overlay_drag(widget, key):
            widget.bind('<ButtonPress-1>', lambda event, key=key: start_overlay_drag(event, key))
            widget.bind('<B1-Motion>', drag_overlay)
            widget.bind('<ButtonRelease-1>', finish_overlay_drag)
        for key, label in (('favorite', '즐겨찾기 별'), ('folder', '폴더 아이콘'), ('pages', '페이지 수')):
            row = ttk.Frame(overlay_controls, style='OverlayRow.TFrame', padding=(3, 1), takefocus=True)
            row.grid(row=overlay_order.index(key), column=0, sticky='ew')
            dialog.settings_overlay_rows[key] = row
            bind_overlay_drag(row, key)
            row.bind('<FocusIn>', lambda event, key=key: overlay_selected.set(key))
            handle = ttk.Label(row, text='≡', style='OverlayRow.TLabel', padding=(5, 7),
                               cursor='sb_v_double_arrow')
            handle.grid(row=0, column=0, sticky='ns')
            bind_overlay_drag(handle, key)
            dialog.settings_overlay_handles[key] = handle
            check = ttk.Checkbutton(row, text=tr('표시'), variable=overlay_visible[key],
                                    command=lambda key=key: overlay_selected.set(key))
            check.grid(row=0, column=2, sticky='w', padx=(5, 10), pady=5)
            dialog.settings_overlay_checks[key] = check
            name = ttk.Label(row, text=tr(label), style='OverlayRow.TLabel', padding=(8, 7),
                             cursor='sb_v_double_arrow')
            name.grid(row=0, column=1, sticky='nsew')
            bind_overlay_drag(name, key)
            dialog.settings_overlay_labels[key] = name
            choice = ttk.Combobox(row, state='readonly', width=12,
                                  textvariable=overlay_position[key], values=OVERLAY_POSITIONS)
            choice._display_labels = POSITION_LABELS
            choice.grid(row=0, column=3, sticky='ew', pady=5)
            choice.bind('<FocusIn>', lambda event, key=key: overlay_selected.set(key), add='+')
            choice.bind('<Button-1>', lambda event, key=key: overlay_selected.set(key), add='+')
            row.columnconfigure(1, weight=1)
            dialog.settings_overlay_combos[key] = choice
            if key in overlay_size:
                size_combo = ttk.Combobox(row, state='readonly', width=7,
                                          textvariable=overlay_size[key], values=OVERLAY_SIZES)
                size_combo._display_labels = SIZE_LABELS
                size_combo.grid(row=0, column=4, sticky='ew', padx=(6, 0), pady=5)
                size_combo.bind('<FocusIn>', lambda event, key=key: overlay_selected.set(key), add='+')
                size_combo.bind('<Button-1>', lambda event, key=key: overlay_selected.set(key), add='+')
                dialog.settings_overlay_size_controls[key] = size_combo
                overlay_traces.append((overlay_size[key], overlay_size[key].trace_add('write', update_overlay_preview)))
            else:
                page_font_row = ttk.Frame(row)
                page_font_row.grid(row=0, column=4, sticky='ew', padx=(6, 0), pady=5)
                page_font_control = ttk.Spinbox(page_font_row, from_=PAGE_FONT_MIN, to=PAGE_FONT_MAX,
                                                increment=1, width=4, textvariable=page_font_size)
                page_font_control.pack(side='left', fill='x', expand=True)
                ttk.Label(page_font_row, text='pt').pack(side='left', padx=(4, 0))
                page_font_control.bind('<FocusIn>', lambda event, key=key: overlay_selected.set(key), add='+')
                page_font_control.bind('<Button-1>', lambda event, key=key: overlay_selected.set(key), add='+')
                dialog.settings_page_font_size_control = page_font_control
            for variable in (overlay_visible[key], overlay_position[key]):
                overlay_traces.append((variable, variable.trace_add('write', update_overlay_preview)))
        def align_overlay_columns():
            if dialog.winfo_exists():
                widths = [choice.winfo_reqwidth() for choice in dialog.settings_overlay_size_controls.values()]
                widths.append(dialog.settings_page_font_size_control.master.winfo_reqwidth())
                width = max(widths) + 6
                for row in dialog.settings_overlay_rows.values():
                    row.columnconfigure(4, minsize=width)
        dialog.after_idle(align_overlay_columns)
        overlay_controls.columnconfigure(0, weight=1)
        order_buttons = ttk.Frame(overlay_controls)
        order_buttons.grid(row=3, column=0, sticky='w', pady=(9, 6))
        def update_order_controls(*_):
            selected = overlay_selected.get()
            index = overlay_order.index(selected) if selected in overlay_order else 0
            dialog.settings_overlay_up.state(['disabled'] if index == 0 else ['!disabled'])
            dialog.settings_overlay_down.state(['disabled'] if index == len(overlay_order) - 1 else ['!disabled'])
            for key, row in dialog.settings_overlay_rows.items():
                state = ['alternate'] if key == selected else ['!alternate']
                row.state(state)
                dialog.settings_overlay_labels[key].state(state)
                dialog.settings_overlay_handles[key].state(state)
        def move_overlay_to(selected, target):
            if selected not in overlay_order or not 0 <= target < len(overlay_order):
                return
            index = overlay_order.index(selected)
            if index == target:
                return
            overlay_order.insert(target, overlay_order.pop(index))
            for row_number, key in enumerate(overlay_order):
                dialog.settings_overlay_rows[key].grid_configure(row=row_number)
            update_order_controls()
            update_overlay_preview()
        def move_overlay(delta):
            selected = overlay_selected.get()
            if delta not in (-1, 1) or selected not in overlay_order:
                return
            move_overlay_to(selected, overlay_order.index(selected) + delta)
        dialog.settings_move_overlay = move_overlay
        dialog.settings_overlay_up = ttk.Button(order_buttons, text=tr('위로'), width=9,
                                                 command=lambda: move_overlay(-1))
        dialog.settings_overlay_up.pack(side='left')
        dialog.settings_overlay_down = ttk.Button(order_buttons, text=tr('아래로'), width=9,
                                                   command=lambda: move_overlay(1))
        dialog.settings_overlay_down.pack(side='left', padx=(5, 10))
        overlay_traces.append((overlay_selected, overlay_selected.trace_add('write', update_order_controls)))
        def reset_overlays():
            overlay_order[:] = normalize_overlay_order()
            for row_number, key in enumerate(overlay_order):
                dialog.settings_overlay_rows[key].grid_configure(row=row_number)
            overlay_selected.set(overlay_order[0])
            defaults = normalize_overlay_settings()
            for key, value in defaults.items():
                overlay_visible[key].set(value['visible'])
                overlay_position[key].set(value['position'])
                if key in overlay_size:
                    overlay_size[key].set(value.get('size', 'large'))
            for field, variable in page_colors.items():
                variable.set(defaults['pages'].get(field, '#FFFFFF' if field == 'text_color' else '#242830'))
            page_alpha.set(str(defaults['pages'].get('background_alpha', 100)))
            page_font_size.set(str(defaults['pages'].get('font_size', PAGE_FONT_DEFAULT)))
            update_overlay_preview()
        dialog.settings_reset_overlays = reset_overlays
        ttk.Button(order_buttons, text=tr('표시 기본값 복원'), command=reset_overlays).pack(side='left')
        ttk.Label(overlay_controls, text=tr('손잡이나 항목 이름을 드래그하거나 위로·아래로 버튼으로 순서를 바꾸세요. 같은 위치에서는 목록의 위에서 아래 순서로 표시합니다.'),
                  style='Muted.TLabel', wraplength=385).grid(row=4, column=0, sticky='w', pady=(3, 0))
        ttk.Label(overlay_controls, text=tr('아이콘 크기: 크게 100% · 보통 2/3 · 작게 1/2. 페이지 수는 pt로 설정합니다.'),
                  style='Muted.TLabel', wraplength=385).grid(row=5, column=0, sticky='w', pady=(5, 0))
        ttk.Label(display_page, text=tr('별은 즐겨찾기 탭에서 숨깁니다. 페이지 수는 전체 이미지 수이며, 폴더는 바로 안의 이미지만 셉니다.'),
                  wraplength=630, style='Muted.TLabel').pack(anchor='w', pady=(10, 0))
        page_style_controls = ttk.Frame(display_page)
        page_style_controls.pack(fill='x', pady=(10, 0))
        def choose_page_color(field):
            if field not in page_colors or not overlay_visible['pages'].get():
                return
            title = '페이지 글씨 색 선택' if field == 'text_color' else '페이지 배경 색 선택'
            result = colorchooser.askcolor(color=page_colors[field].get(), title=tr(title), parent=dialog)
            color = result[1] if result and len(result) > 1 else None
            if (isinstance(color, str) and len(color) == 7 and color.startswith('#')
                    and all(character in '0123456789abcdefABCDEF' for character in color[1:])):
                page_colors[field].set(color.upper())
        dialog.settings_choose_page_color = choose_page_color
        for column, (field, label) in enumerate((('text_color', '페이지 글씨 색'),
                                                  ('background_color', '페이지 배경 색'))):
            group = ttk.Frame(page_style_controls)
            group.grid(row=0, column=column, sticky='ew', padx=(0, 12))
            page_style_controls.columnconfigure(column, weight=1, uniform='page-style-controls')
            ttk.Label(group, text=tr(label)).pack(anchor='w', pady=(0, 4))
            swatch = tk.PhotoImage(master=dialog, width=14, height=14)
            swatch.put(page_colors[field].get(), to=(0, 0, 14, 14))
            page_color_images[field] = swatch
            button = ttk.Button(group, text=page_colors[field].get(), image=swatch, compound='left',
                                command=lambda field=field: choose_page_color(field))
            button.pack(fill='x')
            page_color_buttons[field] = button
        dialog.settings_page_text_color_button = page_color_buttons['text_color']
        dialog.settings_page_background_color_button = page_color_buttons['background_color']
        alpha_group = ttk.Frame(page_style_controls)
        alpha_group.grid(row=0, column=2, sticky='ew')
        page_style_controls.columnconfigure(2, weight=1, uniform='page-style-controls')
        ttk.Label(alpha_group, text=tr('배경 알파')).pack(anchor='w', pady=(0, 4))
        alpha_entry = ttk.Frame(alpha_group)
        alpha_entry.pack(fill='x')
        alpha_control = ttk.Spinbox(alpha_entry, from_=0, to=100, increment=1, width=5,
                                    textvariable=page_alpha)
        alpha_control.pack(side='left', fill='x', expand=True)
        ttk.Label(alpha_entry, text='%').pack(side='left', padx=(5, 0))
        dialog.settings_page_alpha_control = alpha_control
        ttk.Label(display_page, text=tr('배경 알파: 0%는 투명, 100%는 불투명입니다.'),
                  style='Muted.TLabel', wraplength=630).pack(anchor='w', pady=(6, 0))
        for variable in (*page_colors.values(), page_alpha, page_font_size):
            overlay_traces.append((variable, variable.trace_add('write', update_overlay_preview)))
        overlay_traces.append((theme, theme.trace_add('write', update_overlay_preview)))
        update_order_controls()
        update_overlay_preview()
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
                                        shortcuts=draft_shortcuts(), overlays=draft_overlays(strict=True), overlay_order=overlay_order)
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
