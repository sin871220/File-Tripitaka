import sys
if __name__ == '__main__' and '--version' in sys.argv:
    from brand import APP_TITLE
    print(APP_TITLE)
    raise SystemExit(0)
if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == '--thumbnail-worker':
    from thumbnail_worker import main
    raise SystemExit(main())
if __name__ == '__main__' and '--self-test' in sys.argv:
    from runtime_check import main
    raise SystemExit(main())

from localization import translate as tr, set_language, localize_widgets, LANGUAGES
import json
import logging
import faulthandler
import sys
import os
from datetime import datetime
from pathlib import Path
import queue
import subprocess
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont
from windows_shell import reveal_file, logical_drive_roots, set_titlebar_theme
from brand import APP_NAME, APP_TITLE, APP_VERSION, asset_path
from tree_icons import navigation_icons
from ui_fonts import register_font, configure_fonts
from preferences import Preferences, detect_honeyview, card_text
from viewer import (default_action, normalize_action, launch_default, choose_viewer as select_viewer,
                    REVEAL_ACTION, HONEYVIEW_ACTION, DEFAULT_APP_ACTION, CUSTOM_VIEWER_ACTION)
from archive_core import ARCHIVES, cover, render_edited_cover, natural, visible_indices, sort_archives
from file_operations import FileOperationError, rename_archive, trash_archive
from dialog_geometry import center_dialog, _workarea
from thumbnail_edits import (ThumbnailEditStore, ThumbnailEditDatabaseError,
                             ThumbnailEditCancelledError, ThumbnailFileChangedError)
from thumbnail_editor import ThumbnailEditor
from shortcuts import migrate as migrate_shortcuts, validate as validate_shortcuts, legacy_actions, command_for_key, event_key
from smooth_scroll import SmoothScroller, wheel_pixels
from gallery_card import GalleryCard

DATA = (Path(os.environ['LOCALAPPDATA']) / 'ArchiveShelf' if os.environ.get('LOCALAPPDATA') else
        Path.home() / 'Library/Application Support/File Tripitaka' if sys.platform == 'darwin' else
        Path.home() / '.local/share/ArchiveShelf')
DATA.mkdir(parents=True, exist_ok=True)
CONFIG = DATA / 'settings.json'
if sys.platform == 'darwin' and not os.environ.get('LOCALAPPDATA') and not CONFIG.exists():
    legacy = Path.home() / '.local/share/ArchiveShelf/settings.json'
    if legacy.is_file():
        import shutil
        shutil.copy2(legacy, CONFIG)
logging.basicConfig(filename=DATA / 'error.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')
FAULT_LOG = open(DATA / 'crash.log', 'a', encoding='utf-8')
faulthandler.enable(FAULT_LOG)
sys.excepthook = lambda *args: logging.critical('Unhandled exception', exc_info=args)


class App(Preferences, tk.Tk):
    def __init__(self):
        register_font()
        super().__init__()
        self.title(tr(APP_TITLE))
        try:
            if os.name == 'nt':
                self.iconbitmap(str(asset_path('app.ico')))
            else:
                self.app_icon = tk.PhotoImage(master=self, file=str(asset_path('app.png')))
                self.iconphoto(True, self.app_icon)
        except tk.TclError:
            logging.exception('Unable to load application icon')
        self.geometry('1120x760')
        self.minsize(980, 600)
        try:
            self.settings = json.loads(CONFIG.read_text('utf-8'))
        except (OSError, ValueError):
            self.settings = {}
        set_language(self.settings.get('language', 'ko'))
        self.font_size = max(8, min(24, int(self.settings.get('font_size', 10))))
        self.ui_font = configure_fonts(self, self.settings.get('font_family', ''), self.font_size)
        if os.name == 'nt' and not self.settings.get('viewer'):
            self.settings['viewer'] = detect_honeyview()
        self.settings['double_click'] = normalize_action(self.settings.get('double_click', default_action()))
        for key in ('enter_action', 'space_action'):
            self.settings.setdefault(key, self.settings['double_click'])
        self.settings['shortcuts'] = migrate_shortcuts(self.settings)
        self.refresh_shortcuts()
        self.history = []
        self.current_folder = self.settings.get('folder', '')
        self.views = self.settings.get('views', {})
        self.tab_views = self.settings.get('tab_views', {})
        self.active_tab = 'favorites' if self.settings.get('only_favorites', False) else 'all'
        self.favorites = set(self.settings.get('file_favorites', []))
        self.folder_favorites = self.settings.get('folder_favorites', [])
        self.metadata = {}
        self.tree_paths = {}
        self.tree_requests = set()
        self.pending_restore = None
        self.pool = ThreadPoolExecutor(max_workers=3)
        self.folder_pool = ThreadPoolExecutor(max_workers=1)
        self.thumbnail_edit_pool = ThreadPoolExecutor(max_workers=1)
        self.thumbnail_edits = ThumbnailEditStore(DATA / 'thumbnail_edits.json')
        self.closing = False
        self.thumbnail_metadata_error_logged = False
        self.thumbnail_editor_window = None
        self.thumbnail_revisions = {}
        self.results = queue.Queue()
        self.generation = 0
        self.scan_generation = 0
        self.file_revision = 0
        self.file_changes = []
        self.files = []
        self.filtered = []
        self.modified = {}
        self.refresh_job = None
        self.search_job = None
        self.pending = []
        self.active = 0
        self.cards = {}
        self.selected_path = None
        self.photos = {}
        self.preview_errors = set()
        self.folder = tk.StringVar(value=self.settings.get('folder', ''))
        self.recursive = tk.BooleanVar(value=self.settings.get('recursive', True))
        self.query = tk.StringVar()
        self.only_favorites = tk.BooleanVar(value=self.settings.get('only_favorites', False))
        self.thumb_size = tk.IntVar(value=max(120, min(320, int(self.settings.get('thumb_size', 190)))))
        self.sort_order = tk.StringVar(value=self.settings.get('sort', '이름 오름차순'))
        self.fit_columns = None
        self.display_size = self.thumb_size.get()
        self.preview_count = tk.StringVar(value=str(self.settings.get('preview_count', 1)) + '장')
        self.preview_sampling = tk.StringVar(value=self.settings.get('preview_sampling', '순차 보기'))
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill='x')
        ttk.Button(bar, text=tr('← 뒤로'), command=self.go_back).pack(side='left', padx=(0, 6))
        self.sidebar_hidden = bool(self.settings.get('sidebar_hidden', False))
        self.sidebar_toggle = ttk.Button(bar, text=tr('▶ 폴더 패널 펼치기' if self.sidebar_hidden else '◀ 폴더 패널 접기'), command=self.toggle_sidebar)
        self.sidebar_toggle.pack(side='left', padx=(0, 6))
        ttk.Button(bar, text=tr('폴더 선택'), command=self.choose_folder).pack(side='left')
        folder_entry = ttk.Entry(bar, textvariable=self.folder)
        folder_entry.pack(side='left', fill='x', expand=True, padx=8)
        folder_entry.bind('<Return>', lambda e: self.navigate(self.folder.get()))
        ttk.Button(bar, text=tr('새로고침'), command=self.scan).pack(side='left')
        ttk.Button(bar, text=tr('설정'), command=self.open_settings).pack(side='left', padx=8)
        panes = self.panes = ttk.Panedwindow(self, orient='horizontal')
        panes.pack(fill='both', expand=True)
        sidebar = self.sidebar = ttk.Frame(panes, padding=8, width=220)
        sidebar.pack_propagate(False)
        panes.add(sidebar, weight=0)
        self.sidebar_sections = {}
        self.tree_icons = navigation_icons(self)
        favorite_section = ttk.Frame(sidebar)
        favorite_section.pack(fill='x')
        favorite_header = ttk.Button(favorite_section, text=tr('즐겨찾는 폴더'), style='Section.TButton',
                                     command=lambda: self.toggle_sidebar_section('favorites'))
        favorite_header.pack(fill='x')
        favorite_body = ttk.Frame(favorite_section)
        self.favorite_list = ttk.Treeview(favorite_body, height=5, show='tree', selectmode='browse')
        self.favorite_list.column('#0', width=180, minwidth=40)
        self.favorite_list.pack(fill='x', pady=5)
        self.favorite_list.bind('<ButtonRelease-1>', self.open_favorite_folder)
        self.favorite_list.bind('<Return>', self.open_favorite_folder)
        self.favorite_list.bind('<Motion>', self.show_favorite_folder_path)
        folder_buttons = ttk.Frame(favorite_body)
        folder_buttons.pack(fill='x')
        ttk.Button(folder_buttons, text=tr('현재 폴더 추가'), command=self.favorite_folder).pack(side='left')
        ttk.Button(folder_buttons, text=tr('제거'), command=self.remove_favorite_folder).pack(side='left')
        tree_section = ttk.Frame(sidebar)
        tree_section.pack(fill='both', expand=True, pady=(14, 0))
        tree_header = ttk.Button(tree_section, text=tr('폴더 탐색'), style='Section.TButton',
                                 command=lambda: self.toggle_sidebar_section('tree'))
        tree_header.pack(fill='x')
        tree_body = ttk.Frame(tree_section)
        self.tree_drive_nodes = set()
        self.tree = ttk.Treeview(tree_body, show='tree', selectmode='browse')
        self.tree._is_folder_tree = True
        self.tree._folder_paths = self.tree_paths
        tree_scroll = ttk.Scrollbar(tree_body, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewOpen>>', self.expand_tree)
        self.tree.bind('<<TreeviewClose>>', self.collapse_tree)
        self.tree.bind('<ButtonRelease-1>', self.open_tree_folder)
        self.tree.bind('<Double-Button-1>', self.toggle_tree_folder)
        self.tree.bind('<Return>', self.open_tree_folder)
        collapsed = self.settings.get('sidebar_collapsed', {})
        self.sidebar_sections = {
            'favorites': dict(body=favorite_body, header=favorite_header, title=tr('즐겨찾는 폴더'), collapsed=bool(collapsed.get('favorites', False))),
            'tree': dict(body=tree_body, header=tree_header, title=tr('폴더 탐색'), collapsed=bool(collapsed.get('tree', False))),
        }
        for key in self.sidebar_sections:
            self.render_sidebar_section(key)
        body = ttk.Frame(panes)
        panes.add(body, weight=1)
        if self.sidebar_hidden:
            panes.forget(sidebar)
        self.tabs = ttk.Notebook(body, height=1)
        self.tabs.add(ttk.Frame(self.tabs), text=tr('전체'))
        self.tabs.add(ttk.Frame(self.tabs), text=tr('★ 즐겨찾기'))
        self.tabs.select(1 if self.active_tab == 'favorites' else 0)
        self.tabs.pack(fill='x', padx=10, pady=(0, 5))
        self.tabs.bind('<<NotebookTabChanged>>', self.switch_tab)
        filters = ttk.Frame(body, padding=(10, 0, 10, 10))
        filters.pack(fill='x')
        ttk.Label(filters, text=tr('파일명 검색')).pack(side='left', padx=(25, 6))
        ttk.Entry(filters, textvariable=self.query, style='Search.TEntry').pack(side='left', fill='x', expand=True)
        self.query.trace_add('write', self.search_changed)
        ttk.Label(filters, text=tr('정렬')).pack(side='left', padx=(16, 6))
        sorter = ttk.Combobox(filters, textvariable=self.sort_order, state='readonly', width=22,
                              values=['이름 오름차순', '이름 내림차순', '수정한 날짜 오름차순', '수정한 날짜 내림차순'])
        sorter.pack(side='left')
        sorter.bind('<<ComboboxSelected>>', lambda e: self.apply_search())
        tools = ttk.Frame(body, padding=(10, 0, 10, 8))
        tools.pack(fill='x')
        tools.columnconfigure(1, weight=1)
        ttk.Button(tools, text=tr('맨 위로 ↑'), style='Toolbar.TButton',
                   command=lambda: self.scroll_view('moveto', 0)).grid(row=0, column=0, padx=(0, 6))
        controls = self.thumbnail_controls = ttk.Frame(tools)
        controls.grid(row=0, column=1, sticky='e')
        controls.columnconfigure(1, weight=1, minsize=44)
        ttk.Label(controls, text=tr('썸네일 크기')).grid(row=0, column=0)
        self.thumbnail_scale = ttk.Scale(controls, from_=120, to=320, variable=self.thumb_size, command=self.size_changed, length=140)
        self.thumbnail_scale.grid(row=0, column=1, sticky='w', padx=6)
        self.fit_enabled = tk.BooleanVar(value=False)
        self.fit_button = ttk.Checkbutton(controls, text=tr('창에 맞춤 OFF'), style='Toolbar.Fit.Toolbutton', variable=self.fit_enabled, command=self.toggle_fit)
        self.fit_button.grid(row=0, column=2, padx=(0, 4))
        ttk.Label(controls, text=tr('미리보기')).grid(row=0, column=3, padx=(6, 4))
        previews = ttk.Combobox(controls, state='readonly', textvariable=self.preview_count,
                               values=['1장', '2장', '3장'], width=4, style='Toolbar.TCombobox')
        previews.grid(row=0, column=4)
        previews.bind('<<ComboboxSelected>>', self.change_preview_count)
        sampling = self.sampling_control = ttk.Combobox(controls, state='readonly', textvariable=self.preview_sampling,
                                                      values=['순차 보기', '비율 보기'], width=8, style='Toolbar.TCombobox')
        sampling.grid(row=0, column=5, padx=(4, 0))
        sampling.configure(state='disabled' if self.preview_count.get() == '1장' else 'readonly')
        sampling.bind('<<ComboboxSelected>>', self.change_preview_count)
        self.thumbnail_edit_button = ttk.Button(controls, text=tr('썸네일 영역 편집'),
                                               style='Toolbar.TButton', command=self.edit_thumbnail, state='disabled')
        self.thumbnail_edit_button.grid(row=0, column=6, sticky='e', padx=(6, 0))
        gallery = ttk.Frame(body)
        gallery.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(gallery, bg='#edf0f5', highlightthickness=0)
        self.scroll = ttk.Scrollbar(gallery, orient='vertical', command=self.scroll_view)
        self.canvas.configure(yscrollcommand=self.view_changed, yscrollincrement=1)
        self.smooth_scroll = SmoothScroller(
            position=lambda: self.canvas.canvasy(0), limit=self.scroll_limit,
            move=self.move_scroll_pixel, schedule=self.after, cancel=self.after_cancel)
        self.scroll.pack(side='right', fill='y')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.configure(takefocus=True)
        self.canvas.bind('<Button-1>', lambda e: self.canvas.focus_set())
        self.canvas.bind('<KeyPress>', self.gallery_keypress)
        self.canvas.bind('<Configure>', self.resize)
        self.canvas.bind_all('<MouseWheel>', self.wheel)
        self.canvas.bind_all('<Button-4>', self.wheel)
        self.canvas.bind_all('<Button-5>', self.wheel)
        self.status = tk.StringVar(value='폴더를 선택해 주세요. ZIP은 바로, RAR·7Z는 7-Zip 설치 후 미리볼 수 있습니다.')
        ttk.Label(self, textvariable=self.status, padding=10).pack(fill='x')
        self.bind('<Map>', lambda event: self.apply_titlebar_theme() if event.widget is self else None, add='+')
        self.view_shortcut_tag = f'FileTripitakaViewShortcuts_{id(self)}'
        self.bind_class(self.view_shortcut_tag, '<KeyPress>', self.window_keypress)
        self.bind('<Map>', self.install_view_shortcuts, add='+')
        self.install_view_shortcuts()
        self.apply_theme()
        self.apply_language()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)
        self.refresh_favorite_folders()
        self.load_favorite_metadata()
        if self.folder.get():
            self.pending_restore = self.views.get(self.current_folder)
            self.populate_tree(Path(self.current_folder))
            self.scan()
        else:
            self.populate_tree(Path.home())
            if self.only_favorites.get():
                self.apply_search()

    def apply_language(self):
        set_language(self.settings.get('language', 'ko'))
        self.title(f"{tr(APP_NAME)} v{APP_VERSION}")
        localize_widgets(self)
        self.status.set(tr(self.status.get()))
        self.refresh_card_labels()
        for _, _, thumbnail, _ in self.cards.values():
            if thumbnail.text:
                thumbnail.show_error(tr(thumbnail.text))
        # Folder names and paths are literal; only the nearby-location prefix changes.
        for node, path in self.tree_paths.items():
            text = self.tree.item(node, 'text') if self.tree.exists(node) else ''
            if text.startswith(('현재 위치 · ', 'Current location · ')):
                self.tree.item(node, text=tr('현재 위치 · {path}'.format(path=path)))

    def update_shortcut_language(self):
        from desktop_shortcuts import rename_desktop_shortcuts
        language = self.settings.get('language', 'ko')
        def update():
            result = rename_desktop_shortcuts(language)
            self.results.put(('shortcut', None, result, None))
        self.folder_pool.submit(update)

    def apply_titlebar_theme(self):
        if os.name == 'nt':
            set_titlebar_theme(self.winfo_id(), self.palette['panel'], self.palette['fg'],
                               self.settings.get('theme', '라이트') != '라이트')

    def change_preview_count(self, event=None):
        if getattr(self, 'size_job', None) is not None:
            self.after_cancel(self.size_job)
            self.size_job = None
        self.fit_columns = None
        self.fit_enabled.set(False)
        self.fit_button.configure(text=tr('창에 맞춤 OFF'))
        self.thumbnail_scale.configure(from_=120, to=320)
        self.thumb_size.set(max(120, min(320, self.thumb_size.get())))
        self.display_size = self.thumb_size.get()
        self.sampling_control.configure(state='disabled' if self.preview_count.get() == '1장' else 'readonly')
        self.remember_position()
        view = self.views.get(self.current_folder, {}).copy()
        self.settings['preview_count'] = int(self.preview_count.get()[0])
        self.settings['preview_sampling'] = self.preview_sampling.get()
        self.apply_search()
        self.restore_position(view)
        self.canvas.focus_set()

    def select_card(self, path):
        if path not in self.filtered:
            return
        self.smooth_scroll.stop()
        self.selected_path = path
        self.canvas.focus_set()
        self.paint_selection()

    def paint_selection(self):
        self.update_thumbnail_edit_button()
        for path, frame, _, _ in self.cards.values():
            frame.set_selected(path == self.selected_path)

    def update_thumbnail_edit_button(self):
        self.thumbnail_edit_button.state(['!disabled'] if self.selected_path in self.filtered else ['disabled'])

    def move_selection(self, event):
        self.smooth_scroll.stop()
        if not self.filtered:
            return 'break'
        try:
            index = self.filtered.index(self.selected_path)
        except ValueError:
            index = 0
        else:
            delta = {'Left': -1, 'Right': 1, 'Up': -self.columns(), 'Down': self.columns()}[event.keysym]
            index = max(0, min(len(self.filtered) - 1, index + delta))
        self.selected_path = self.filtered[index]
        row = index // self.columns()
        top = self.canvas.canvasy(0)
        y = row * self.row_height()
        height = self.canvas.winfo_height()
        if y < top or y + self.row_height() > top + height:
            target = y if y < top else y + self.row_height() - height
            total = max(height, ((len(self.filtered) + self.columns() - 1) // self.columns()) * self.row_height())
            self.canvas.yview_moveto(max(0, target) / max(1, total))
        self.refresh_visible()
        self.paint_selection()
        return 'break'

    def refresh_shortcuts(self):
        self.settings['shortcuts'] = validate_shortcuts(self.settings['shortcuts'])
        self.settings.update(legacy_actions(self.settings['shortcuts']))

    def gallery_keypress(self, event):
        if self.tk.call('grab', 'current', self._w):
            return 'break'
        key = event_key(event)
        command = command_for_key(self.settings['shortcuts'], key) if key else None
        if command is not None:
            return self.activate_command(command)
        if key in ('Left', 'Right', 'Up', 'Down'):
            return self.move_selection(event)

    def install_view_shortcuts(self, event=None):
        # Put view shortcuts before widget/class bindings. In particular, a
        # configured Space must not also press the button that currently has focus.
        pending = [getattr(event, 'widget', None)] if event is not None else [self]
        while pending:
            widget = pending.pop()
            if not isinstance(widget, tk.Misc) or widget.winfo_toplevel() is not self:
                continue
            tags = widget.bindtags()
            if self.view_shortcut_tag not in tags:
                widget.bindtags((self.view_shortcut_tag,) + tags)
            if event is None:
                pending.extend(widget.winfo_children())

    def window_keypress(self, event):
        widget = getattr(event, 'widget', None)
        if not isinstance(widget, tk.Misc) or widget.winfo_toplevel() is not self:
            return
        if widget.winfo_class() in ('Entry', 'TEntry', 'Text', 'Spinbox', 'TSpinbox',
                                     'Combobox', 'TCombobox'):
            return
        # Tcl-created controls, such as a combo popdown, need not have a Python
        # widget object. Query the grab directly rather than resolving that object.
        if self.tk.call('grab', 'current', self._w):
            return 'break'
        key = event_key(event)
        command = command_for_key(self.settings['shortcuts'], key) if key else None
        if command not in ('sidebar', 'fit'):
            return
        self.activate_command(command)
        if command == 'sidebar' and self.sidebar_hidden:
            path = str(widget)
            if path == str(self.sidebar) or path.startswith(str(self.sidebar) + '.'):
                self.canvas.focus_set()
        return 'break'

    def shortcut_label(self, command):
        return ', '.join(self.settings['shortcuts'].get(command, []))

    def activate_selection(self, key):
        # Compatibility entry point for callers; the function map is authoritative.
        command = command_for_key(self.settings['shortcuts'], {'enter': 'Enter', 'space': 'Space'}.get(key, key))
        return self.activate_command(command)

    def activate_command(self, command):
        # View commands also work in an empty gallery or before selecting a file.
        if command == 'sidebar':
            self.toggle_sidebar()
            return 'break'
        if command == 'fit':
            # invoke() flips the Checkbutton variable before its existing callback.
            self.fit_button.invoke()
            return 'break'
        if self.selected_path in self.filtered:
            path = self.selected_path
            if command == 'rename':
                return self.rename_file()
            if command == 'trash':
                return self.delete_file()
            action = {
                'reveal': REVEAL_ACTION,
                'viewer': DEFAULT_APP_ACTION if sys.platform == 'darwin' else HONEYVIEW_ACTION,
                'custom_viewer': CUSTOM_VIEWER_ACTION,
                'favorite': '즐겨찾기 추가/해제',
            }.get(command)
            if action is None:
                return 'break'
            index = self.filtered.index(path)
            advance = self.active_tab == 'favorites' and command == 'favorite'
            self.execute_action(path, action)
            if advance and path not in self.filtered:
                # Reconciliation preserves the viewport; selection must not scroll it.
                self.selected_path = self.filtered[min(index, len(self.filtered) - 1)] if self.filtered else None
                self.paint_selection()
                self.remember_position()
        return 'break'

    def toggle_sidebar(self):
        if self.sidebar_hidden:
            self.panes.insert(0, self.sidebar, weight=0)
            self.panes.update_idletasks()
            self.panes.sashpos(0, self.settings.get('sidebar_width', 220))
        else:
            self.settings['sidebar_width'] = self.panes.sashpos(0)
            self.panes.forget(self.sidebar)
        self.sidebar_hidden = not self.sidebar_hidden
        self.settings['sidebar_hidden'] = self.sidebar_hidden
        self.sidebar_toggle.configure(text=tr('▶ 폴더 패널 펼치기' if self.sidebar_hidden else '◀ 폴더 패널 접기'))
        self.save()

    def render_sidebar_section(self, key):
        section = self.sidebar_sections[key]
        collapsed = section['collapsed']
        section['header'].configure(text=('▶  ' if collapsed else '▼  ') + tr(section['title']))
        section['body'].pack_forget()
        if not collapsed:
            section['body'].pack(fill='both' if key == 'tree' else 'x', expand=key == 'tree', pady=(6, 0))

    def toggle_sidebar_section(self, key):
        section = self.sidebar_sections[key]
        section['collapsed'] = not section['collapsed']
        self.render_sidebar_section(key)
        self.settings['sidebar_collapsed'] = {name: item['collapsed'] for name, item in self.sidebar_sections.items()}
        self.save()

    def load_favorite_metadata(self):
        paths = list(self.favorites)
        revision = self.file_revision
        def load():
            modified, metadata = {}, {}
            for name in paths:
                path = Path(name)
                try:
                    stat = path.stat()
                    modified[path] = stat.st_mtime_ns
                    metadata[path] = (stat.st_size, stat.st_mtime)
                except OSError:
                    modified[path] = 0
                    metadata[path] = (0, 0)
            self.results.put(('favorite_meta', revision, (modified, metadata), None))
        self.folder_pool.submit(load)

    def cell_width(self):
        if self.fit_columns:
            return max(1, self.canvas.winfo_width() // self.fit_columns)
        return self.display_size * self.settings.get('preview_count', 1) + 35

    def row_height(self):
        return self.display_size + 120 + max(0, self.font_size - 10) * 6

    def remember_position(self):
        self.smooth_scroll.stop()
        if not self.current_folder or not self.filtered:
            return
        index = min(len(self.filtered) - 1, max(0, int(self.canvas.canvasy(0) // self.row_height()) * self.columns()))
        self.views[self.current_folder] = dict(anchor=str(self.filtered[index]),
            fraction=self.canvas.yview()[0], query=self.query.get(), sort=self.sort_order.get(),
            favorites=self.only_favorites.get(), selected=str(self.selected_path) if self.selected_path else None)
        self.tab_views.setdefault('__global_favorites__' if self.active_tab == 'favorites' else self.current_folder, {})[self.active_tab] = self.views[self.current_folder].copy()

    def switch_tab(self, event=None):
        target = 'favorites' if self.tabs.index(self.tabs.select()) == 1 else 'all'
        if target == self.active_tab:
            return
        self.remember_position()
        self.active_tab = target
        self.only_favorites.set(target == 'favorites')
        if target == 'favorites':
            self.load_favorite_metadata()
        view = self.tab_views.get('__global_favorites__' if target == 'favorites' else self.current_folder, {}).get(target, {})
        if view:
            self.query.set(view.get('query', ''))
            self.sort_order.set(view.get('sort', self.sort_order.get()))
        if self.search_job is not None:
            self.after_cancel(self.search_job)
            self.search_job = None
        self.apply_search()
        self.restore_position(view)
        self.remember_position()
        self.save()

    def restore_position(self, view):
        self.smooth_scroll.stop()
        selected = view.get('selected')
        self.selected_path = next((p for p in self.filtered if str(p) == selected), None)
        anchor = view.get('anchor')
        index = next((i for i, p in enumerate(self.filtered) if str(p) == anchor), None)
        if index is not None:
            rows = max(1, (len(self.filtered) + self.columns() - 1) // self.columns())
            fraction = (index // self.columns()) / rows
        else:
            fraction = view.get('fraction', 0)
        self.canvas.yview_moveto(fraction)
        self.refresh_visible()
        self.paint_selection()

    def navigate(self, folder, push=True, update_tree=True):
        target = Path(folder).expanduser()
        if not target.is_dir():
            messagebox.showerror(tr('폴더 확인'), tr(f'폴더를 찾을 수 없습니다.\n{target}'))
            return
        target = str(target.resolve())
        self.remember_position()
        if push and self.current_folder and self.current_folder != target:
            self.history.append(self.current_folder)
        self.current_folder = target
        self.folder.set(target)
        if self.active_tab == 'favorites':
            self.pending_restore = dict(self.tab_views.get('__global_favorites__', {}).get('favorites', {}), favorites=True)
        else:
            view = self.tab_views.get(target, {}).get('all', self.views.get(target, {}))
            self.pending_restore = dict(view, favorites=False)
        if update_tree:
            self.populate_tree(Path(target))
        self.scan()

    def go_back(self):
        if self.history:
            self.navigate(self.history.pop(), push=False)
        else:
            self.status.set(tr('이전 폴더가 없습니다.'))

    def size_changed(self, *_):
        if not hasattr(self, 'canvas'):
            return
        self.fit_columns = None
        self.fit_enabled.set(False)
        self.fit_button.configure(text=tr('창에 맞춤 OFF'))
        self.thumbnail_scale.configure(from_=120, to=320)
        self.thumb_size.set(max(120, min(320, self.thumb_size.get())))
        if getattr(self, 'size_job', None) is not None:
            self.after_cancel(self.size_job)
        self.size_job = self.after(180, self.apply_size)

    def toggle_fit(self):
        if self.fit_enabled.get():
            self.fit_thumbnails()
        else:
            self.size_changed()
            self.after_cancel(self.size_job)
            self.apply_size()
            self.save()

    def fit_thumbnails(self):
        self.fit_enabled.set(True)
        self.fit_button.configure(text=tr('창에 맞춤 ON'))
        self.update_idletasks()
        self.remember_position()
        columns = self.columns()
        self.fit_columns = columns
        count = self.settings.get('preview_count', 1)
        size = max(1, (self.canvas.winfo_width() // columns - 35) // count)
        if getattr(self, 'size_job', None) is not None:
            self.after_cancel(self.size_job)
            self.size_job = None
        self.thumbnail_scale.configure(from_=min(120, size), to=max(320, size))
        self.thumb_size.set(size)
        self.apply_size()
        self.save()

    def apply_size(self):
        self.size_job = None
        self.remember_position()
        view = self.views.get(self.current_folder, {})
        self.display_size = self.thumb_size.get()
        self.apply_search()
        self.restore_position(view)

    def refresh_favorite_folders(self):
        for node in self.favorite_list.get_children():
            self.favorite_list.delete(node)
        for index, folder in enumerate(self.folder_favorites):
            path = Path(folder)
            self.favorite_list.insert('', 'end', iid=str(index), text=path.name or str(path), image=self.tree_icons['folder'])

    def favorite_folder(self):
        if self.current_folder and self.current_folder not in self.folder_favorites:
            self.folder_favorites.append(self.current_folder)
            self.refresh_favorite_folders()
            self.save()

    def remove_favorite_folder(self):
        selection = self.favorite_list.selection()
        if selection:
            self.folder_favorites.pop(int(selection[0]))
            self.refresh_favorite_folders()
            self.save()

    def show_favorite_folder_path(self, event):
        node = self.favorite_list.identify_row(event.y)
        if node:
            self.status.set(tr(self.folder_favorites[int(node)]))

    def open_favorite_folder(self, event=None):
        if event is not None and hasattr(event, 'y'):
            node = self.favorite_list.identify_row(event.y)
            if not node:
                return
            self.favorite_list.selection_set(node)
        selection = self.favorite_list.selection()
        if selection:
            self.tabs.select(0)
            self.switch_tab()
            self.navigate(self.folder_favorites[int(selection[0])])

    def populate_tree(self, root):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree_paths.clear()
        self.tree_drive_nodes.clear()
        self.tree_requests.clear()
        # Drive nodes are lazy: disconnected/network disks cannot block the UI.
        roots = [Path(name) for name in logical_drive_roots()]
        for drive in roots:
            node = self.tree.insert('', 'end', text=str(drive), image=self.tree_icons['drive'])
            self.tree_drive_nodes.add(node)
            self.tree_paths[node] = drive
            self.tree.insert(node, 'end', text=tr('불러오는 중…'))
        # Retain a nearby shortcut, including UNC paths outside mapped drives.
        base = root.parent if root.parent != root else root
        if base not in roots:
            node = self.tree.insert('', 0, text=tr(('현재 위치 · ' if roots else '') + str(base)), open=True, image=self.tree_icons['folder_open'])
            self.tree_paths[node] = base
            self.request_tree(node)

    def request_tree(self, node):
        if node in self.tree_requests or node not in self.tree_paths:
            return
        self.tree_requests.add(node)
        folder = self.tree_paths[node]
        def load():
            try:
                children = sorted((p for p in folder.iterdir() if p.is_dir()), key=lambda p: natural(p.name))
                self.results.put(('tree', node, children, None))
            except OSError as exc:
                self.results.put(('tree', node, [], str(exc)))
        self.folder_pool.submit(load)

    def finish_tree(self, node, children, error):
        self.tree_requests.discard(node)
        if not self.tree.exists(node):
            return
        for child in self.tree.get_children(node):
            self.tree.delete(child)
        if error:
            self.tree.insert(node, 'end', text=tr('접근할 수 없는 폴더'))
            return
        for folder in children:
            child = self.tree.insert(node, 'end', text=folder.name, image=self.tree_icons['folder'])
            self.tree_paths[child] = folder
            self.tree.insert(child, 'end', text=tr('불러오는 중…'))

    def collapse_tree(self, event=None):
        node = self.tree.focus()
        if node in self.tree_paths and node not in self.tree_drive_nodes:
            self.tree.item(node, image=self.tree_icons['folder'])

    def expand_tree(self, event=None):
        node = self.tree.focus()
        if node in self.tree_paths and node not in self.tree_drive_nodes:
            self.tree.item(node, image=self.tree_icons['folder_open'])
        children = self.tree.get_children(node)
        if children and children[0] not in self.tree_paths:
            self.request_tree(node)

    def toggle_tree_folder(self, event):
        # The first click already navigated. The second click only toggles children.
        self.tree_skip_release = True
        node = self.tree.identify_row(event.y)
        if node not in self.tree_paths or self.tree.identify_element(event.x, event.y).endswith('indicator'):
            return 'break'
        self.tree.focus(node)
        opened = bool(self.tree.item(node, 'open'))
        self.tree.item(node, open=not opened)
        if opened:
            self.collapse_tree()
        else:
            self.expand_tree()
        return 'break'

    def open_tree_folder(self, event=None):
        if event is not None and hasattr(event, 'x') and getattr(self, 'tree_skip_release', False):
            self.tree_skip_release = False
            return 'break'
        # Single-click names/icons to navigate; disclosure arrows only expand/collapse.
        if event is not None and hasattr(event, 'x'):
            if self.tree.identify_element(event.x, event.y).endswith('indicator'):
                return
            node = self.tree.identify_row(event.y)
        else:
            node = self.tree.focus()
        if node in self.tree_paths:
            self.tree.selection_set(node)
            self.tree.focus(node)
            self.tabs.select(0)
            self.switch_tab()
            self.navigate(self.tree_paths[node], update_tree=False)
            return 'break'

    def toggle_favorite(self, path):
        key = str(path)
        if key in self.favorites:
            self.favorites.remove(key)
        else:
            self.favorites.add(key)
        if self.active_tab == 'all':
            for card_path, frame, _, _ in self.cards.values():
                if card_path == path:
                    self.update_badge(frame, path)
            self.save()
        else:
            candidates = [Path(name) for name in self.favorites]
            self.reconcile_favorites(candidates)
            self.remember_position()
            self.save()

    def reconcile_favorites(self, candidates):
        self.reconcile_cards(candidates)

    def reconcile_cards(self, candidates):
        # Keep surviving card/PhotoImage/worker objects, changing their positions only.
        self.smooth_scroll.stop()
        top = max(0, self.canvas.canvasy(0))
        self.filtered = sort_archives(
            [p for p in candidates if self.query.get().casefold() in p.name.casefold()],
            self.sort_order.get(), self.modified)
        indices = {path: index for index, path in enumerate(self.filtered)}
        retained = {}
        for card in self.cards.values():
            path, frame, label, window = card
            if path in indices:
                retained[indices[path]] = card
            else:
                self.photos.pop(label, None)
                self.canvas.delete(window)
                frame.destroy()
        self.cards = retained
        self.update_region()
        total_height = max(self.canvas.winfo_height(),
            ((len(self.filtered) + self.columns() - 1) // self.columns()) * self.row_height())
        self.canvas.yview_moveto(top / max(1, total_height))
        self.refresh_visible()
        self.status.set(tr(f'{"즐겨찾기 전체" if self.only_favorites.get() else "전체"} {len(candidates):,}개 · 검색 결과 {len(self.filtered):,}개 · 더블클릭: 설정한 동작 · 우클릭: 파일 위치'))

    def update_saved_file_paths(self, old, new):
        def update(view):
            if not view:
                return
            for key in ('anchor', 'selected'):
                if view.get(key) == str(old):
                    view[key] = str(new) if new is not None else None
        for view in self.views.values():
            update(view)
        for tabs in self.tab_views.values():
            for view in tabs.values():
                update(view)
        update(self.pending_restore)

    def changed_snapshot(self, files, modified, metadata, revision, root=None, recursive=True):
        """Bring background results up to date without resurrecting old file paths."""
        files = list(files)
        modified, metadata = dict(modified), dict(metadata)
        for change_revision, old, new in self.file_changes:
            if change_revision <= revision:
                continue
            present = old in files
            files = [path for path in files if path != old]
            old_modified, old_metadata = modified.pop(old, None), metadata.pop(old, None)
            in_scope = new is not None and root is not None and (
                new.is_relative_to(root) if recursive else new.parent == root)
            if new is not None and (present or in_scope):
                if new not in files:
                    files.append(new)
                if new in self.modified or old_modified is not None:
                    modified[new] = self.modified.get(new, old_modified)
                if new in self.metadata or old_metadata is not None:
                    metadata[new] = self.metadata.get(new, old_metadata)
        return files, modified, metadata

    def apply_file_change(self, old, new):
        """Update the collections only after a successful rename or trash operation."""
        self.remember_position()
        index = self.filtered.index(old) if old in self.filtered else 0
        self.file_revision += 1
        self.file_changes.append((self.file_revision, old, new))
        self.thumbnail_edits.relocate(old, new if new is not None else old)
        revision = self.thumbnail_revisions.pop(str(old), 0)
        if new is not None:
            self.thumbnail_revisions[str(new)] = revision
        self.files = [new if path == old else path for path in self.files if path != old or new is not None]
        if str(old) in self.favorites:
            self.favorites.remove(str(old))
            if new is not None:
                self.favorites.add(str(new))
        for values in (self.modified, self.metadata):
            previous = values.pop(old, None)
            if new is not None and previous is not None:
                values[new] = previous
        if str(old) in self.preview_errors:
            self.preview_errors.remove(str(old))
            if new is not None:
                self.preview_errors.add(str(new))
        self.update_saved_file_paths(old, new)
        # Recreate the changed card, including on case-insensitive Windows paths.
        # Its event callbacks and thumbnail worker still capture the old spelling.
        for card_index, card in list(self.cards.items()):
            if str(card[0]) == str(old):
                _, frame, label, window = self.cards.pop(card_index)
                self.photos.pop(label, None)
                self.canvas.delete(window)
                frame.destroy()
        candidates = [Path(name) for name in self.favorites] if self.only_favorites.get() else self.files
        self.reconcile_cards(candidates)
        self.selected_path = new if new in self.filtered else (
            self.filtered[min(index, len(self.filtered) - 1)] if self.filtered else None)
        self.paint_selection()
        if self.filtered:
            self.remember_position()
        else:
            # remember_position deliberately ignores empty collections.
            key = '__global_favorites__' if self.active_tab == 'favorites' else self.current_folder
            view = dict(anchor=None, selected=None, fraction=0, query=self.query.get(),
                        sort=self.sort_order.get(), favorites=self.only_favorites.get())
            self.tab_views.setdefault(key, {})[self.active_tab] = view
            if self.current_folder:
                self.views[self.current_folder] = view.copy()
        self.save()

    def file_operation_error(self, error, path):
        messages = {
            'invalid_name': '사용할 수 없는 파일 이름입니다. 빈 이름, 예약된 이름, 특수문자와 끝의 점·공백을 확인해 주세요.',
            'missing': '파일을 찾을 수 없습니다. 새로고침 후 다시 시도해 주세요.',
            'not_file': '압축파일만 변경하거나 삭제할 수 있습니다.',
            'symlink': '바로가기나 심볼릭 링크는 변경하거나 삭제할 수 없습니다.',
            'exists': '같은 이름의 파일이 이미 있습니다. 다른 이름을 입력해 주세요.',
            'permission': '파일을 변경할 권한이 없거나 다른 프로그램에서 사용 중입니다.',
            'unavailable': '이 위치 또는 실행 환경에서는 이 작업을 안전하게 수행할 수 없습니다. 파일은 변경하지 않았습니다.',
            'rename_failed': '이름을 변경하지 못했습니다.',
            'trash_failed': '휴지통으로 보내지 못했습니다. 파일 위치와 사용 권한을 확인해 주세요.',
        }
        logging.warning('File operation failed for %s: %s', path, error)
        messagebox.showerror(tr('파일 작업 실패'),
                             tr(messages.get(error.code, '파일 작업을 완료하지 못했습니다.')) + '\n\n' + str(path),
                             parent=getattr(self, 'rename_window', None) or self)

    def edit_thumbnail(self, path=None):
        path = path if path is not None else self.selected_path
        if path not in self.filtered:
            return 'break'
        existing = self.thumbnail_editor_window
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return 'break'
        self.thumbnail_editor_window = ThumbnailEditor(
            self, path, self.palette, self.settings.get('preview_count', 1),
            self.settings.get('preview_sampling', '순차 보기'),
            recipes=lambda: self.thumbnail_recipes(path, strict=True) or {},
            on_apply=lambda slot, entry, box, done: self.save_thumbnail_edit(path, slot, entry, box, done),
            on_reset=lambda slot, done: self.reset_thumbnail_edit(path, slot, done),
        )
        return 'break'

    def thumbnail_recipes(self, path, strict=False):
        try:
            return self.thumbnail_edits.get(path)
        except ThumbnailEditCancelledError:
            raise
        except OSError as error:
            if not self.thumbnail_metadata_error_logged:
                logging.exception('Unable to read thumbnail edit metadata')
                self.thumbnail_metadata_error_logged = True
            if strict:
                raise OSError(tr('썸네일 편집 정보를 읽지 못했습니다. 설정 폴더의 접근 권한을 확인해 주세요.')) from error
            # Browsing still works when optional edit metadata is unavailable.
            return None

    def submit_thumbnail_edit(self, path, operation, done, reset=False):
        window = self.thumbnail_editor_window

        def work():
            if self.closing:
                return
            error = None
            try:
                operation()
            except ThumbnailEditCancelledError:
                return
            except ThumbnailEditDatabaseError:
                logging.exception('Cannot update damaged thumbnail edit database')
                error = tr('저장된 썸네일 편집 정보를 읽을 수 없어 덮어쓰지 않았습니다. 오류 로그를 확인해 주세요.')
            except Exception as exc:
                logging.exception('Cannot save thumbnail edit for %s', path)
                if isinstance(exc, ThumbnailFileChangedError):
                    reason = '읽는 동안 압축파일이 변경되었습니다. 편집기를 다시 열어 적용해 주세요.'
                elif isinstance(exc, PermissionError):
                    reason = '파일을 읽거나 설정을 저장할 수 없습니다. 다른 프로그램의 사용 여부와 접근 권한을 확인해 주세요.'
                elif isinstance(exc, FileNotFoundError):
                    reason = '압축파일 또는 설정 폴더를 찾을 수 없습니다. 파일 위치를 확인해 주세요.'
                else:
                    reason = '썸네일 편집 정보를 저장하지 못했습니다.'
                detail = f'{type(exc).__name__}: {exc}'[:320]
                error = tr(reason) + '\n' + tr(f'오류 정보: {detail}\n로그: {DATA / "error.log"}')
            self.results.put(('thumbnail_edit', None, (path, window, done, reset), error))

        self.thumbnail_edit_pool.submit(work)

    def save_thumbnail_edit(self, path, slot, entry, box, done):
        self.submit_thumbnail_edit(path, lambda: self.thumbnail_edits.set(path, slot, entry, box), done)

    def reset_thumbnail_edit(self, path, slot, done):
        self.submit_thumbnail_edit(path, lambda: self.thumbnail_edits.reset(path, slot), done, reset=True)

    def refresh_thumbnail(self, path):
        """Refresh edits independently of slow gallery jobs, retaining the photo."""
        key = str(path)
        revision = self.thumbnail_revisions[key] = self.thumbnail_revisions.get(key, 0) + 1
        for current, _, label, _ in self.cards.values():
            if str(current) != key:
                continue
            self.pending = [task for task in self.pending if task[2] is not label]
        count = self.settings.get('preview_count', 1)
        sampling = self.settings.get('preview_sampling', '순차 보기')
        scan_generation = self.scan_generation

        def render():
            if self.closing:
                return
            image, error = None, None
            try:
                recipes = self.thumbnail_recipes(path, strict=True)
                if self.closing:
                    return
                image = (render_edited_cover(path, DATA / 'cache', recipes, count, sampling)
                         if recipes else cover(path, DATA / 'cache', count, sampling))
            except ThumbnailEditCancelledError:
                return
            except Exception as exc:
                if self.closing:
                    return
                logging.exception('Edited thumbnail refresh failed: %s', path)
                error = str(exc)
            # This result never consumes/decrements a normal gallery worker slot.
            self.results.put(('thumbnail_refresh', scan_generation,
                              (path, revision, count, sampling, image), error))

        self.thumbnail_edit_pool.submit(render)

    def display_thumbnail(self, label, image, error=None):
        """Replace just the pixels/text inside an existing gallery card."""
        path = getattr(label, 'archive_path', None)
        if error:
            if path is not None:
                self.preview_errors.add(str(path))
            label.show_error(tr('미리보기 불가\n' + error[:110]))
            return
        if path is not None:
            self.preview_errors.discard(str(path))
        label.show_image(image, (self.thumb_size.get() * self.settings.get('preview_count', 1),
                                 self.thumb_size.get() + 20))

    def keep_thumbnail_photo(self, label, photo):
        if photo is None:
            self.photos.pop(label, None)
        else:
            self.photos[label] = photo

    def rename_file(self, path=None):
        path = path if path is not None else self.selected_path
        if path not in self.filtered:
            return 'break'
        existing = getattr(self, 'rename_window', None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return 'break'
        dialog = self.rename_window = tk.Toplevel(self)
        dialog.withdraw()
        dialog.title(tr('파일 이름 바꾸기'))
        dialog.transient(self)
        dialog.resizable(True, True)
        dialog.configure(bg=self.palette['panel'])
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        name_font = tkfont.Font(dialog, family=self.ui_font, size=self.font_size)
        original = tk.Text(body, width=1, height=1, wrap='char', font=name_font,
                           bg=self.palette['panel'], fg=self.palette['fg'],
                           selectbackground=self.palette['accent'], selectforeground='white',
                           inactiveselectbackground=self.palette['accent'],
                           borderwidth=0, highlightthickness=0, padx=0, pady=0,
                           cursor='xterm', exportselection=False, takefocus=True)
        original.insert('1.0', path.name)
        original.configure(state='disabled')
        original.grid(row=0, column=0, sticky='nsew', pady=(0, 12))

        def select_original(event=None):
            original.tag_add('sel', '1.0', 'end-1c')
            return 'break'

        original.bind('<Control-a>', select_original)
        if sys.platform == 'darwin':
            original.bind('<Command-a>', select_original)
        controls = ttk.Frame(body)
        controls.grid(row=1, column=0, sticky='ew')
        ttk.Label(controls, text=tr('새 파일 이름')).pack(anchor='w')
        name = tk.StringVar(value=path.stem)
        entry = ttk.Entry(controls, textvariable=name, width=1)
        entry.pack(fill='x', pady=6)
        ttk.Label(controls, text=tr('확장자 {extension}는 그대로 유지됩니다.'.format(extension=path.suffix))).pack(anchor='w')

        def close():
            self.rename_window = None
            dialog.destroy()
            self.canvas.focus_set()

        def commit(event=None):
            try:
                renamed = rename_archive(path, name.get())
            except FileOperationError as exc:
                self.file_operation_error(exc, path)
                entry.focus_set()
                return 'break'
            if str(renamed) != str(path):
                self.apply_file_change(path, renamed)
                self.status.set(tr('파일 이름을 변경했습니다. {name}'.format(name=renamed.name)))
            close()
            return 'break'

        buttons = ttk.Frame(controls)
        buttons.pack(fill='x', pady=(16, 0))
        ttk.Button(buttons, text=tr('취소'), command=close).pack(side='right')
        ttk.Button(buttons, text=tr('이름 바꾸기'), command=commit).pack(side='right', padx=8)
        dialog.bind('<Return>', commit)
        dialog.bind('<Escape>', lambda e: close())
        dialog.protocol('WM_DELETE_WINDOW', close)
        dialog.update_idletasks()
        line_height = name_font.metrics('linespace')
        fixed_height = controls.winfo_reqheight() + 36 + 12

        def required_height(width):
            # Measure against an explicit pixel width, never an unmapped Text's
            # displaylines: Windows may still report a one-pixel widget there.
            available = max(1, width - 36 - 2)
            lines, line = 1, ''
            for character in path.name:
                if character == '\n':
                    lines, line = lines + 1, ''
                elif line and name_font.measure(line + character) > available:
                    lines, line = lines + 1, character
                else:
                    line += character
            return fixed_height + lines * line_height + 4

        left, top, right, bottom = _workarea(self)
        max_width = max(300, right - left - 40)
        max_height = max(fixed_height + line_height, bottom - top - max(64, 2 * line_height))
        min_width = min(max_width, max(360, controls.winfo_reqwidth() + 36))
        # Keep even the narrowest allowed window wide enough for the complete
        # filename above the fixed controls within this monitor's work area.
        low, high = min_width, max_width
        while low < high:
            middle = (low + high) // 2
            if required_height(middle) <= max_height:
                high = middle
            else:
                low = middle + 1
        min_width = low
        filename_width = max(name_font.measure(line) for line in path.name.split('\n'))
        width = min(max_width, max(min_width, filename_width + 36 + 2))
        height = min(max_height, required_height(width))
        dialog.minsize(min_width, height)
        center_dialog(dialog, self, width, height)

        def reflow(event):
            if event.widget is not dialog:
                return
            width = max(min_width, event.width)
            minimum = min(max_height, required_height(width))
            if dialog.minsize() != (min_width, minimum):
                dialog.minsize(min_width, minimum)
            if event.height < minimum:
                x = max(left, min(dialog.winfo_x(), right - width - 20))
                y = max(top, min(dialog.winfo_y(), bottom - minimum - max(64, 2 * line_height)))
                dialog.geometry(f'{width}x{minimum}+{x}+{y}')

        dialog.deiconify()
        # Ignore provisional sizes emitted while the native window is mapping;
        # they must not replace the width calculated from the full filename.
        dialog.wait_visibility()
        dialog.bind('<Configure>', reflow, add='+')
        dialog.grab_set()
        entry.focus_set()
        entry.selection_range(0, 'end')
        return 'break'

    def delete_file(self, path=None):
        path = path if path is not None else self.selected_path
        if path not in self.filtered:
            return 'break'
        if not messagebox.askyesno(tr('파일 삭제'),
                tr('다음 파일을 휴지통으로 보내시겠습니까?\n{name}\n\n원본 압축파일이 휴지통으로 이동합니다.'.format(name=path.name)),
                parent=self, icon='warning', default='no'):
            return 'break'
        try:
            trash_archive(path)
        except FileOperationError as exc:
            self.file_operation_error(exc, path)
            return 'break'
        self.apply_file_change(path, None)
        self.status.set(tr('휴지통으로 보냈습니다. {name}'.format(name=path.name)))
        self.canvas.focus_set()
        return 'break'

    def update_badge(self, frame, path):
        show = self.active_tab == 'all' and str(path) in self.favorites
        frame.set_favorite(show)

    def update_card_labels(self, frame, path):
        name, details = card_text(path, self.metadata.get(path, (0, 0)), self.settings)
        frame.set_text(name, details)

    def refresh_card_labels(self):
        for path, frame, _, _ in self.cards.values():
            self.update_card_labels(frame, path)

    def file_info(self, path):
        try:
            stat = path.stat()
            messagebox.showinfo(tr('파일 정보'), tr(f'{path.name}\n\n전체 경로: {path}\n\n크기: {stat.st_size:,} 바이트 ({stat.st_size / 1024 ** 2:.2f} MB)\n수정: {datetime.fromtimestamp(stat.st_mtime):%Y-%m-%d %H:%M:%S}'))
        except OSError as exc:
            messagebox.showerror(tr('파일 정보'), tr(str(exc)))

    def save(self):
        self.settings.update(folder=self.current_folder, recursive=self.recursive.get(), sort=self.sort_order.get(),
                             thumb_size=self.thumb_size.get(), only_favorites=self.only_favorites.get(),
                             views=self.views, tab_views=self.tab_views, file_favorites=sorted(self.favorites),
                             folder_favorites=self.folder_favorites)
        temp = CONFIG.with_suffix('.tmp')
        temp.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), 'utf-8')
        temp.replace(CONFIG)

    def choose_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.navigate(folder)

    def choose_viewer(self):
        path = select_viewer(parent=self)
        if path:
            self.settings['viewer' if os.name == 'nt' else 'custom_viewer'] = path
            self.save()


    def scan(self):
        root = Path(self.folder.get()).expanduser()
        if not self.folder.get() or not root.is_dir():
            messagebox.showerror(tr('폴더 확인'), tr('존재하는 폴더를 선택해 주세요.'))
            return
        if str(root.resolve()) != self.current_folder:
            self.navigate(str(root.resolve()))
            return
        root = root.resolve()
        self.smooth_scroll.stop()
        if self.pending_restore is None:
            self.remember_position()
            self.pending_restore = self.views.get(self.current_folder)
        self.save()
        self.generation += 1
        self.scan_generation += 1
        gen = self.scan_generation
        revision = self.file_revision
        self.files = []
        self.filtered = []
        self.pending.clear()
        for _, frame, _, window in self.cards.values():
            self.canvas.delete(window)
            frame.destroy()
        self.cards.clear()
        self.photos.clear()
        self.status.set(tr('압축파일을 찾고 있습니다…'))
        recursive = self.recursive.get()
        def find():
            try:
                paths = root.rglob('*') if recursive else root.iterdir()
                files = sorted((p for p in paths if p.suffix.lower() in ARCHIVES and p.is_file()), key=natural)
                modified = {}
                metadata = {}
                for path in files:
                    try:
                        stat = path.stat()
                        modified[path] = stat.st_mtime_ns
                        metadata[path] = (stat.st_size, stat.st_mtime)
                    except OSError:
                        modified[path] = 0
                self.results.put(('scan', gen, (files, modified, metadata, revision, root, recursive), None))
            except Exception as exc:
                self.results.put(('scan', gen, [], str(exc)))
        self.pool.submit(find)

    def report_callback_exception(self, exc, value, tb):
        logging.error('UI callback failed', exc_info=(exc, value, tb))
        messagebox.showerror(tr('오류'), tr(f'{value}\n\n로그: {DATA / "error.log"}'))

    def search_changed(self, *_):
        if self.search_job is not None:
            self.after_cancel(self.search_job)
        self.search_job = self.after(250, self.apply_search)

    def apply_search(self):
        self.search_job = None
        self.smooth_scroll.stop()
        self.save()
        candidates = [Path(p) for p in self.favorites] if self.only_favorites.get() else self.files
        self.filtered = sort_archives(
            [p for p in candidates if self.query.get().casefold() in p.name.casefold()],
            self.sort_order.get(), self.modified)
        self.generation += 1
        self.pending.clear()
        for _, frame, _, window in self.cards.values():
            self.canvas.delete(window)
            frame.destroy()
        self.cards.clear()
        self.photos.clear()
        self.update_region()
        self.canvas.yview_moveto(0)
        self.refresh_visible()
        self.status.set(tr(f'{"즐겨찾기 전체" if self.only_favorites.get() else "전체"} {len(candidates):,}개 · 검색 결과 {len(self.filtered):,}개 · 더블클릭: 설정한 동작 · 우클릭: 파일 위치'))

    def add_cards(self, result):
        if len(result) > 3:
            result = self.changed_snapshot(*result[:3], *result[3:])
        self.files, modified, metadata = result
        self.modified.update(modified)
        self.metadata.update(metadata)
        logging.info('Scan complete: %s archives', len(self.files))
        restore = self.pending_restore
        self.pending_restore = None
        if restore:
            self.query.set(restore.get('query', ''))
            if self.search_job is not None:
                self.after_cancel(self.search_job)
                self.search_job = None
            self.sort_order.set(restore.get('sort', self.sort_order.get()))
            self.only_favorites.set(restore.get('favorites', False))
        self.active_tab = 'favorites' if self.only_favorites.get() else 'all'
        if self.active_tab == 'favorites':
            restore = self.tab_views.get('__global_favorites__', {}).get('favorites', restore)
        self.tabs.select(1 if self.active_tab == 'favorites' else 0)
        self.apply_search()
        if restore:
            self.restore_position(restore)

    def columns(self):
        if self.fit_columns:
            return self.fit_columns
        return max(1, self.canvas.winfo_width() // self.cell_width())

    def update_region(self):
        self.smooth_scroll.stop()
        rows = (len(self.filtered) + self.columns() - 1) // self.columns()
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(),
                                           max(self.canvas.winfo_height(), rows * self.row_height())))

    def scroll_view(self, *args):
        self.smooth_scroll.stop()
        # Keep scrollbar arrows useful now that the canvas uses single pixels.
        if len(args) == 3 and args[0] == 'scroll' and args[2] == 'units':
            args = ('scroll', int(args[1]) * 30, 'units')
        self.canvas.yview(*args)
        self.schedule_refresh()

    def scroll_height(self):
        region = self.tk.splitlist(self.canvas.cget('scrollregion'))
        return float(region[3]) if region else self.canvas.winfo_height()

    def scroll_limit(self):
        return max(0, self.scroll_height() - self.canvas.winfo_height())

    def move_scroll_pixel(self, top):
        self.canvas.yview_moveto(top / max(1, self.scroll_height()))
        self.schedule_refresh()

    def view_changed(self, first, last):
        self.scroll.set(first, last)
        self.schedule_refresh()

    def wheel(self, event):
        if self.grab_current() is not None:
            return
        if event.widget.winfo_toplevel() != self:
            return
        if event.widget == self.tree or event.widget == self.favorite_list:
            return
        pixels = wheel_pixels(getattr(event, 'delta', 0), getattr(event, 'num', None), sys.platform)
        if pixels:
            self.smooth_scroll.scroll_by(pixels)
            return 'break'

    def schedule_refresh(self):
        if self.refresh_job is None:
            self.refresh_job = self.after(16, self.refresh_visible)

    def refresh_visible(self):
        if self.refresh_job is not None:
            self.after_cancel(self.refresh_job)
            self.refresh_job = None
        self.update_thumbnail_edit_button()
        columns = self.columns()
        width = self.canvas.winfo_width()
        cell_width = self.cell_width()
        row_height = self.row_height()
        wanted = set(visible_indices(len(self.filtered), columns,
                                    self.canvas.canvasy(0), self.canvas.winfo_height(), row_height))
        for index in list(self.cards):
            if index not in wanted:
                _, frame, label, window = self.cards.pop(index)
                self.photos.pop(label, None)
                self.canvas.delete(window)
                frame.destroy()
        live_labels = {card[2] for card in self.cards.values()}
        self.pending = [item for item in self.pending if item[2] in live_labels]
        # Overlap adjacent one-pixel borders so cards share a single grid line.
        for index in sorted(wanted):
            column = index % columns
            if self.fit_columns:
                x = column * width // columns
                card_width = (column + 1) * width // columns - x + 1
            else:
                x = column * cell_width
                card_width = cell_width + 1
            y = (index // columns) * row_height
            geometry = (x, y, card_width, row_height + 1)
            if index in self.cards:
                _, frame, _, window = self.cards[index]
                frame.layout(*geometry)
                continue
            path = self.filtered[index]
            # Images, text and borders share one canvas paint pass. Embedded
            # native child windows can leave stale strips when scrolling on Windows.
            frame = GalleryCard(self.canvas, path, *geometry, self.palette,
                                (self.ui_font, self.font_size), on_photo=self.keep_thumbnail_photo)
            label = frame.thumbnail
            label.show_error(tr('표지 읽는 중…'))
            frame.set_selected(path == self.selected_path)
            self.update_card_labels(frame, path)
            self.update_badge(frame, path)
            frame.bind('<Button-1>', lambda e, p=path: self.select_card(p))
            frame.bind('<Double-Button-1>', lambda e, p=path: self.double_click(p))
            frame.bind('<Button-3>', lambda e, p=path: self.context(e, p))
            if sys.platform == 'darwin':
                frame.bind('<Button-2>', lambda e, p=path: self.context(e, p))
                frame.bind('<Control-Button-1>', lambda e, p=path: self.context(e, p))
            frame.bind('<Enter>', lambda e, p=path: self.status.set(tr(str(p))))
            window = frame.background
            self.cards[index] = (path, frame, label, window)
            self.pending.append((self.generation, path, label))

    def resize(self, event):
        if self.fit_columns:
            if getattr(self, 'size_job', None) is not None:
                self.after_cancel(self.size_job)
            self.size_job = self.after(180, self.fit_thumbnails)
        self.update_region()
        self.schedule_refresh()

    def poll(self):
        for _ in range(40):
            try:
                kind, gen, value, error = self.results.get_nowait()
            except queue.Empty:
                break
            if kind == 'thumbnail_edit':
                path, window, done, reset = value
                if not error:
                    self.refresh_thumbnail(path)
                    self.status.set(tr('썸네일 편집을 초기화했습니다.' if reset else '썸네일 편집을 저장했습니다.'))
                if window is not None and window.winfo_exists():
                    done(error)
                elif error:
                    messagebox.showerror(tr('썸네일 편집'), error, parent=self)
                continue
            if kind == 'thumbnail_refresh':
                path, revision, count, sampling, image = value
                if (gen != self.scan_generation
                        or revision != self.thumbnail_revisions.get(str(path), 0)
                        or count != self.settings.get('preview_count', 1)
                        or sampling != self.settings.get('preview_sampling', '순차 보기')):
                    continue
                # Locate the current card: scrolling/resizing may have replaced
                # its widgets while the priority render was in progress.
                for current, _, label, _ in self.cards.values():
                    if str(current) == str(path):
                        self.pending = [task for task in self.pending if task[2] is not label]
                        self.display_thumbnail(label, image, error)
                continue
            if kind == 'shortcut':
                if value.get('errors'):
                    messagebox.showwarning(tr('바탕화면 바로가기'), tr('일부 바로가기 이름을 변경하지 못했습니다.') + '\n\n' + '\n'.join(value['errors']))
                continue
            if kind == 'favorite_meta':
                _, modified, metadata = self.changed_snapshot(list(value[0]), *value, gen)
                self.modified.update({p: value for p, value in modified.items() if str(p) in self.favorites})
                self.metadata.update({p: value for p, value in metadata.items() if str(p) in self.favorites})
                if self.active_tab == 'favorites':
                    self.reconcile_favorites([Path(name) for name in self.favorites])
                    for path, frame, _, _ in self.cards.values():
                        self.update_card_labels(frame, path)
                continue
            if kind == 'tree':
                self.finish_tree(gen, value, error)
                continue
            if kind == 'cover':
                self.active -= 1
            if gen != (self.scan_generation if kind == 'scan' else self.generation):
                continue
            if kind == 'scan':
                if error:
                    self.status.set(tr(error))
                else:
                    self.add_cards(value)
            else:
                label, im, *revision = value
                if not label.exists():
                    continue
                path = getattr(label, 'archive_path', None)
                if revision and revision[0] != self.thumbnail_revisions.get(str(path), 0):
                    continue
                self.display_thumbnail(label, im, error)
        while self.pending and self.active < 3:
            gen, path, label = self.pending.pop(0)
            self.active += 1
            count = self.settings.get('preview_count', 1)
            sampling = self.settings.get('preview_sampling', '순차 보기')
            revision = self.thumbnail_revisions.get(str(path), 0)
            def load(gen=gen, path=path, label=label, count=count, sampling=sampling, revision=revision):
                try:
                    if self.closing:
                        return
                    recipes = self.thumbnail_recipes(path)
                    if self.closing:
                        return
                    im = (render_edited_cover(path, DATA / 'cache', recipes, count, sampling)
                          if recipes else cover(path, DATA / 'cache', count, sampling))
                    self.results.put(('cover', gen, (label, im, revision), None))
                except ThumbnailEditCancelledError:
                    return
                except Exception as exc:
                    if self.closing:
                        return
                    logging.exception('Cover failed: %s', path)
                    self.results.put(('cover', gen, (label, None, revision), str(exc)))
            self.pool.submit(load)
        self.after(75, self.poll)

    def open_archive(self, path):
        if sys.platform == 'darwin':
            try:
                launch_default(path)
            except OSError as exc:
                messagebox.showerror(tr('뷰어 실행 실패'), str(exc))
            return
        viewer = self.settings.get('viewer')
        if not viewer or not Path(viewer).is_file():
            for base in ('ProgramFiles', 'ProgramFiles(x86)'):
                candidate = Path(os.environ.get(base, 'C:/Program Files')) / 'Honeyview/Honeyview.exe'
                if candidate.is_file():
                    viewer = str(candidate)
                    break
            else:
                messagebox.showinfo(tr('꿀뷰 설정'), tr('꿀뷰 실행 파일(Honeyview.exe)을 선택해 주세요.'))
                self.choose_viewer()
                viewer = self.settings.get('viewer')
        if viewer:
            try:
                subprocess.Popen([viewer, str(path.resolve())])
            except OSError as exc:
                messagebox.showerror(tr('꿀뷰 실행 실패'), tr(str(exc)))

    def context(self, event, path):
        self.select_card(path)
        if getattr(self, 'context_menu', None) is not None:
            self.context_menu.destroy()
        menu = self.context_menu = tk.Menu(self, tearoff=False, bg=self.palette['panel'], fg=self.palette['fg'], activebackground=self.palette['accent'], activeforeground='white')
        menu.add_command(label=tr('★ 즐겨찾기 해제' if str(path) in self.favorites else '☆ 즐겨찾기 추가'), accelerator=self.shortcut_label('favorite'), command=lambda: self.toggle_favorite(path))
        menu.add_command(label=tr('썸네일 영역 편집'), command=lambda: self.edit_thumbnail(path))
        menu.add_command(label=tr('파일 정보'), command=lambda: self.file_info(path))
        menu.add_command(label=tr('기본 앱으로 열기' if sys.platform == 'darwin' else '꿀뷰로 열기'), accelerator=self.shortcut_label('viewer'), command=lambda: self.open_archive(path))
        menu.add_command(label=tr('파일 위치 열기'), accelerator=self.shortcut_label('reveal'), command=lambda: self.reveal(path))
        menu.add_command(label=tr('경로 복사'), command=lambda: (self.clipboard_clear(), self.clipboard_append(str(path))))
        menu.add_separator()
        menu.add_command(label=tr('파일 이름 바꾸기'), accelerator=self.shortcut_label('rename'), command=lambda: self.rename_file(path))
        menu.add_command(label=tr('파일 삭제'), accelerator=self.shortcut_label('trash'), command=lambda: self.delete_file(path))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def reveal(self, path):
        try:
            selected = reveal_file(path)
            if not selected:
                self.status.set(tr('파일 선택에 실패하여 해당 폴더를 열었습니다. 자세한 내용은 error.log에 기록했습니다.'))
        except OSError as exc:
            logging.exception('Reveal failed: %s', path)
            messagebox.showerror(tr('탐색기 실행 실패'), tr(str(exc)))

    def close(self):
        self.closing = True
        self.smooth_scroll.stop()
        self.remember_position()
        self.save()
        self.pending.clear()
        if self.thumbnail_editor_window is not None and self.thumbnail_editor_window.winfo_exists():
            self.thumbnail_editor_window.close()
        self.thumbnail_edits.close()
        # Cancel timers before destroying their Tcl commands, including callbacks
        # registered by child dialogs. Their owning widgets clean up the commands.
        for job in self.tk.splitlist(self.tk.call('after', 'info')):
            self.tk.call('after', 'cancel', job)
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.folder_pool.shutdown(wait=False, cancel_futures=True)
        self.thumbnail_edit_pool.shutdown(wait=False, cancel_futures=True)
        for _, frame, _, _ in self.cards.values():
            frame.destroy()
        self.cards.clear()
        self.photos.clear()
        self.destroy()


if __name__ == '__main__':
    logging.info('ArchiveShelf started, virtual scroll build')
    # Keep the Tcl interpreter owned by the main thread while outstanding
    # archive workers finish, including after the visible window is closed.
    application = App()
    try:
        application.mainloop()
    finally:
        for executor in (application.pool, application.folder_pool, application.thumbnail_edit_pool):
            executor.shutdown(wait=True, cancel_futures=True)
        editor = application.thumbnail_editor_window
        if editor is not None:
            editor._executor.shutdown(wait=True, cancel_futures=True)
