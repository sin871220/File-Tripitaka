"""Private bundled CJK font registration; no system font installation required."""
import ctypes
import logging
from pathlib import Path
import sys
from tkinter import font

BUNDLED_FAMILY = 'Noto Sans CJK KR'
_REGISTERED = False


def resource_font():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'fonts' / 'NotoSansCJKkr-Regular.otf'


def register_font():
    global _REGISTERED
    if sys.platform != 'win32' or _REGISTERED:
        return
    file = resource_font()
    if not file.is_file():
        logging.error('Bundled CJK font missing: %s', file)
        return
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    gdi.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
    gdi.AddFontResourceExW.restype = ctypes.c_int
    if gdi.AddFontResourceExW(str(file), 0x10, None):
        _REGISTERED = True
    else:
        logging.error('Private CJK font registration failed: %s', ctypes.get_last_error())


def select_family(families):
    available = {name.casefold(): name for name in families}
    for choice in (BUNDLED_FAMILY, 'Noto Sans CJK JP', 'Noto Sans JP', 'Yu Gothic UI',
                   'Yu Gothic', 'Meiryo', 'Microsoft YaHei UI', 'Malgun Gothic',
                   'Apple SD Gothic Neo', 'Hiragino Sans', 'Segoe UI'):
        if choice.casefold() in available:
            return available[choice.casefold()]
    return None


def configure_fonts(root, preferred='', size=10):
    available = {name.casefold(): name for name in font.families(root)}
    family = available.get(preferred.casefold()) if preferred else None
    family = family or select_family(available.values()) or font.nametofont('TkDefaultFont', root=root).actual('family')
    for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont',
                 'TkCaptionFont', 'TkSmallCaptionFont', 'TkTooltipFont', 'TkIconFont'):
        try:
            font.nametofont(name, root=root).configure(family=family, size=size)
        except Exception:
            logging.exception('Unable to configure named font: %s', name)
    root.option_add('*Font', 'TkDefaultFont')
    root.option_add('*TCombobox*Listbox.font', 'TkDefaultFont')
    logging.info('UI font: %s; bundled registered: %s', family, _REGISTERED)
    return family
