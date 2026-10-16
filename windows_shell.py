"""Native file reveal and drive enumeration; legacy module name is retained."""
import ctypes
import logging
import os
from pathlib import Path
import subprocess
import sys


def _select_item(path, shell, ole):
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole.CoInitializeEx.restype = ctypes.c_int32
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole.CoTaskMemFree.restype = None
    shell.SHParseDisplayName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p,
                                        ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint32,
                                        ctypes.POINTER(ctypes.c_uint32)]
    shell.SHParseDisplayName.restype = ctypes.c_int32
    shell.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                               ctypes.c_void_p, ctypes.c_uint32]
    shell.SHOpenFolderAndSelectItems.restype = ctypes.c_int32
    initialized = ole.CoInitializeEx(None, 2)
    # RPC_E_CHANGED_MODE means COM is already initialized in a different apartment.
    if initialized < 0 and initialized != -2147417850:
        raise OSError(f'COM 초기화 실패: 0x{initialized & 0xffffffff:08X}')
    pidl = ctypes.c_void_p()
    try:
        result = shell.SHParseDisplayName(str(path), None, ctypes.byref(pidl), 0, None)
        if result < 0 or not pidl.value:
            raise OSError(f'파일 경로 확인 실패: 0x{result & 0xffffffff:08X}')
        result = shell.SHOpenFolderAndSelectItems(pidl, 0, None, 0)
        if result < 0:
            raise OSError(f'탐색기 선택 실패: 0x{result & 0xffffffff:08X}')
    finally:
        if pidl.value:
            ole.CoTaskMemFree(pidl)
        if initialized >= 0:
            ole.CoUninitialize()


def reveal_file(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f'파일을 찾을 수 없습니다. 새로고침 후 다시 시도해 주세요.\n{path}')
    if sys.platform == 'darwin':
        try:
            subprocess.run(['/usr/bin/open', '-R', str(path)], check=True,
                           capture_output=True, timeout=15)
        except subprocess.SubprocessError as exc:
            raise OSError(str(exc)) from exc
        return True
    if os.name != 'nt':
        raise OSError('Unsupported operating system')
    try:
        _select_item(path, ctypes.WinDLL('shell32'), ctypes.WinDLL('ole32'))
    except OSError:
        logging.exception('Explorer selection failed: %s; opening parent folder', path)
        os.startfile(str(path.parent))
        return False
    return True


def logical_drive_roots(kernel=None):
    """List Windows drive letters or macOS mounted volumes without scanning files."""
    if kernel is None:
        if sys.platform == 'darwin':
            return _mac_volume_roots()
        if os.name != 'nt':
            return []
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetLogicalDrives.argtypes = []
    kernel.GetLogicalDrives.restype = ctypes.c_uint32
    mask = kernel.GetLogicalDrives()
    if not mask:
        logging.warning('Windows drive list unavailable')
        return []
    return [chr(65 + index) + ':\\' for index in range(26) if mask & (1 << index)]


def _mac_volume_roots():
    roots = ['/']
    try:
        volumes = sorted(Path('/Volumes').iterdir(), key=lambda path: path.name.casefold())
    except OSError:
        return roots
    for volume in volumes:
        try:
            if volume.is_dir() and volume.is_mount() and volume.resolve() != Path('/'):
                roots.append(str(volume))
        except OSError:
            logging.debug('Volume unavailable: %s', volume, exc_info=True)
    return roots


def set_titlebar_theme(widget_id, background, foreground, dark):
    """Apply supported DWM colors; unsupported Windows versions keep native chrome."""
    if os.name != 'nt':
        return
    try:
        user = ctypes.WinDLL('user32')
        user.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        user.GetAncestor.restype = ctypes.c_void_p
        hwnd = user.GetAncestor(widget_id, 2) or widget_id
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_int32
        def apply(attribute, value):
            color = ctypes.c_uint32(value)
            return dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(color), ctypes.sizeof(color))
        apply(20, int(dark))
        def colorref(hex_color):
            red, green, blue = bytes.fromhex(hex_color.lstrip('#'))
            return red | green << 8 | blue << 16
        apply(35, colorref(background))
        apply(36, colorref(foreground))
    except (OSError, AttributeError):
        logging.debug('Native title bar theming unavailable', exc_info=True)
