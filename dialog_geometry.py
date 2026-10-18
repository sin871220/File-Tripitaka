"""Place a dialog over its parent once, within the available desktop area."""
import ctypes
import sys


class _Rect(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int32) for name in ('left', 'top', 'right', 'bottom')]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [('cbSize', ctypes.c_uint32), ('rcMonitor', _Rect),
                ('rcWork', _Rect), ('dwFlags', ctypes.c_uint32)]


def _windows_workarea(parent):
    """Return the nearest parent's monitor work area, excluding the taskbar."""
    try:
        user = ctypes.WinDLL('user32', use_last_error=True)
        user.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        user.MonitorFromWindow.restype = ctypes.c_void_p
        user.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MonitorInfo)]
        user.GetMonitorInfoW.restype = ctypes.c_int32
        monitor = user.MonitorFromWindow(parent.winfo_id(), 2)  # DEFAULTTONEAREST
        info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
        if monitor and user.GetMonitorInfoW(monitor, ctypes.byref(info)):
            area = info.rcWork
            if area.right > area.left and area.bottom > area.top:
                return area.left, area.top, area.right, area.bottom
    except (AttributeError, OSError):
        pass
    return None


def _workarea(parent):
    if sys.platform == 'win32':
        area = _windows_workarea(parent)
        if area is not None:
            return area
    left, top = parent.winfo_vrootx(), parent.winfo_vrooty()
    width, height = parent.winfo_vrootwidth(), parent.winfo_vrootheight()
    if width <= 0 or height <= 0:
        left, top = 0, 0
        width, height = parent.winfo_screenwidth(), parent.winfo_screenheight()
    return left, top, left + width, top + height


def _center_position(width, height, parent_rect, workarea):
    left, top, parent_width, parent_height = parent_rect
    x = left + (parent_width - width) // 2
    y = top + (parent_height - height) // 2
    area_left, area_top, area_right, area_bottom = workarea
    # Oversized dialogs retain their size, with their top-left still accessible.
    x = min(max(x, area_left), max(area_left, area_right - width))
    y = min(max(y, area_top), max(area_top, area_bottom - height))
    return x, y


def center_dialog(dialog, parent, width=None, height=None):
    """Center once over parent; omitted dimensions preserve natural widget sizing.

    Pass the final width and height when the caller controls the dialog's size.
    Otherwise only the position is set, so later content can still grow. This
    installs no event bindings and does not prevent users moving the window.
    """
    dialog.update_idletasks()
    set_size = width is not None or height is not None
    width = max(1, int(dialog.winfo_reqwidth() if width is None else width))
    height = max(1, int(dialog.winfo_reqheight() if height is None else height))
    # Both windows are Tk/Toplevels: use the parent's window-manager origin.
    # rootx/rooty refer to its client area and would add the title bar twice.
    parent_rect = (parent.winfo_x(), parent.winfo_y(),
                   parent.winfo_width(), parent.winfo_height())
    x, y = _center_position(width, height, parent_rect, _workarea(parent))
    # Tk's leading '-' means right/bottom-relative. '+-123' is absolute -123.
    size = f'{width}x{height}' if set_size else ''
    dialog.geometry(f'{size}+{x}+{y}')
    return x, y
