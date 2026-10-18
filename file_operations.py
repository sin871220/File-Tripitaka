"""Rename archive files without replacement, or move them to the native trash.

The UI confirms trash operations and supplies a *stem* for rename operations.
Neither operation follows a leaf symlink. No permanent-delete fallback is used.
"""
import ctypes
import errno
import os
from pathlib import Path
import re
import stat
import sys

try:
    if sys.platform == 'win32':
        # The legacy SHFileOperation backend may permanently delete files on
        # volumes without a Recycle Bin. Require the IFileOperation backend,
        # whose Windows 10/11 flags include FOFX_RECYCLEONDELETE.
        if sys.getwindowsversion().major < 10:
            raise ImportError('Safe Recycle Bin support requires Windows 10 or later.')
        from send2trash.win.modern import send2trash as _send2trash
    else:
        from send2trash import send2trash as _send2trash
except (ImportError, OSError):
    _send2trash = None


class FileOperationError(Exception):
    """An operation failed; ``code`` is stable for localized UI messages."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


_INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_RESERVED_NAME = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])$', re.I)


def _file_path(path):
    """Validate a regular file without resolving a leaf symlink."""
    path = Path(path).expanduser().absolute()
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as error:
        raise FileOperationError('missing', 'The file no longer exists.') from error
    except PermissionError as error:
        raise FileOperationError('permission', 'The file cannot be accessed.') from error
    except OSError as error:
        raise FileOperationError('not_file', 'The file cannot be accessed.') from error
    if stat.S_ISLNK(mode):
        raise FileOperationError('symlink', 'Symbolic links cannot be changed here.')
    if not stat.S_ISREG(mode):
        raise FileOperationError('not_file', 'Only regular files can be changed here.')
    return path


def _validate_stem(new_stem):
    # Apply Windows restrictions on both platforms so renamed files remain
    # usable when a library is shared between Windows and macOS.
    if (not isinstance(new_stem, str) or not new_stem.strip()
            or new_stem in ('.', '..') or new_stem.endswith(('.', ' '))
            or _INVALID_NAME.search(new_stem)
            or _RESERVED_NAME.fullmatch(new_stem.split('.', 1)[0].rstrip(' '))
            or any(0xD800 <= ord(character) <= 0xDFFF for character in new_stem)):
        raise FileOperationError('invalid_name', 'The file name is not valid.')


def _rename_no_replace(source, destination):
    """Use an atomic OS rename that fails if another item owns the name."""
    if sys.platform == 'win32':
        # Unlike POSIX rename(), Windows os.rename() never replaces a target.
        os.rename(source, destination)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        rename = getattr(libc, 'renamex_np', None)
        if rename is None:
            raise OSError(errno.ENOSYS, 'Exclusive rename is unavailable.')
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(os.fsencode(source), os.fsencode(destination), 0x00000004)  # RENAME_EXCL
    elif sys.platform.startswith('linux'):
        rename = getattr(libc, 'renameat2', None)
        if rename is None:
            raise OSError(errno.ENOSYS, 'Exclusive rename is unavailable.')
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                           ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1)  # AT_FDCWD, RENAME_NOREPLACE
    else:
        raise OSError(errno.ENOSYS, 'Exclusive rename is unavailable.')
    if result:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(source))


def _operation_error(error, fallback):
    if isinstance(error, FileNotFoundError):
        code, message = 'missing', 'The file no longer exists.'
    elif isinstance(error, FileExistsError) or error.errno in (errno.EEXIST, errno.ENOTEMPTY):
        code, message = 'exists', 'An item with that name already exists.'
    elif isinstance(error, PermissionError) or error.errno in (errno.EACCES, errno.EPERM):
        code, message = 'permission', 'Permission to change the file was denied.'
    elif error.errno in (errno.ENAMETOOLONG, errno.EINVAL):
        code, message = 'invalid_name', 'The file name is not valid for this volume.'
    elif error.errno in (errno.ENOSYS, errno.ENOTSUP):
        code, message = 'unavailable', 'This volume does not support this operation safely.'
    else:
        code, message = fallback, 'The file operation failed.'
    return FileOperationError(code, message)


def rename_archive(path: Path, new_stem: str) -> Path:
    """Rename a file in its current folder, preserving its final extension.

    ``new_stem`` does not include the extension. Existing destinations are never
    replaced. The returned path is absolute; an unchanged name is a no-op.
    """
    source = _file_path(path)
    _validate_stem(new_stem)
    destination = source.with_name(new_stem + source.suffix)
    # WindowsPath equality ignores case; compare spelling to allow case edits.
    if destination.name == source.name:
        return source
    try:
        _rename_no_replace(source, destination)
    except OSError as error:
        raise _operation_error(error, 'rename_failed') from error
    return destination


def trash_archive(path: Path) -> None:
    """Move one regular file to the operating system's Trash/Recycle Bin.

    If native trash support is unavailable or the volume refuses the operation,
    an error is raised. The file is never unlinked as a fallback.
    """
    source = _file_path(path)
    if _send2trash is None:
        raise FileOperationError('unavailable', 'Native trash support is unavailable.')
    try:
        _send2trash(str(source))
    except OSError as error:
        raise _operation_error(error, 'trash_failed') from error
    except Exception as error:
        # COM setup can raise a pywin32 exception before the backend converts
        # failures to OSError. Keep that failure inside the same UI boundary.
        raise FileOperationError('trash_failed', 'The native trash operation failed.') from error
