"""Discover archives and direct-image folders without decoding images."""
import os
from pathlib import Path
import stat

from archive_core import ARCHIVES, IMAGES, natural, sort_archives

KIND_FILTERS = ('전체', '압축파일', '폴더')
ARRANGEMENTS = ('섞어서', '폴더 먼저', '파일 먼저')
SORT_LABELS = {
    '이름 오름차순': '이름 ▲', '이름 내림차순': '이름 ▼',
    '수정한 날짜 오름차순': '수정 날짜 ▲', '수정한 날짜 내림차순': '수정 날짜 ▼',
    '용량 오름차순': '용량 ▲', '용량 내림차순': '용량 ▼',
}


def normalize_sort_order(value):
    """Migrate retired or invalid saved choices to the default name sort."""
    return value if isinstance(value, str) and value in SORT_LABELS else '이름 오름차순'


def item_metadata(path):
    """Return kind, modification time and display size/date on a worker."""
    path = Path(path)
    info = path.stat()
    if stat.S_ISDIR(info.st_mode):
        size, modified = 0, info.st_mtime_ns
        with os.scandir(path) as entries:
            for entry in entries:
                if Path(entry.name).suffix.lower() not in IMAGES or not entry.is_file(follow_symlinks=False):
                    continue
                try:
                    child = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                size += child.st_size
                modified = max(modified, child.st_mtime_ns)
        return 'folder', modified, (size, modified / 1_000_000_000)
    return 'archive', info.st_mtime_ns, (info.st_size, info.st_mtime)


def scan_items(root, recursive=True, cancel=None):
    """One walk: archives plus folders containing at least one direct image.

    Folder size is the sum of direct images, excluding child folders and other
    files. Directory links are not followed. Cancellation never opens a file.
    """
    root = Path(root)
    files, modified, metadata, kinds = [], {}, {}, {}
    for current, directories, names in os.walk(root, followlinks=False):
        if cancel is not None and cancel():
            break
        directories[:] = [name for name in directories
                          if not (Path(current) / name).is_symlink() and name != '__MACOSX']
        folder = Path(current)
        image_size, latest, has_image = 0, 0, False
        for name in names:
            if cancel is not None and cancel():
                break
            path = folder / name
            suffix = path.suffix.lower()
            if suffix not in ARCHIVES and suffix not in IMAGES:
                continue
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode):
                    continue
            except OSError:
                continue
            if suffix in ARCHIVES:
                files.append(path)
                kinds[path] = 'archive'
                modified[path] = info.st_mtime_ns
                metadata[path] = (info.st_size, info.st_mtime)
            if suffix in IMAGES:
                has_image = True
                image_size += info.st_size
                latest = max(latest, info.st_mtime_ns)
        if has_image:
            try:
                latest = max(latest, folder.stat().st_mtime_ns)
            except OSError:
                pass
            files.append(folder)
            kinds[folder] = 'folder'
            modified[folder] = latest
            metadata[folder] = (image_size, latest / 1_000_000_000)
        if not recursive:
            break
    return sorted(files, key=natural), modified, metadata, kinds


def filter_items(candidates, query, kind_filter, kinds):
    query = query.casefold()
    kind = {'압축파일': 'archive', '폴더': 'folder'}.get(kind_filter)
    return [path for path in candidates if query in path.name.casefold()
            and (kind is None or kinds.get(path, 'archive') == kind)]


def sort_items(candidates, order, modified, kinds, arrangement='섞어서', metadata=None):
    """Sort cached metadata within groups, leaving unknown numeric values last.

    This function never reads candidate files. Numeric ties keep natural name
    and path order in either direction, and descending never reverses groups.
    """
    order = normalize_sort_order(order)
    if order in ('용량 오름차순', '용량 내림차순'):
        values = metadata if metadata is not None else {}
        ordered = sort_archives(candidates, '이름 오름차순', {})
        known, unknown, numbers = [], [], {}
        for path in ordered:
            value = values.get(path)
            try:
                value = value[0]
            except (IndexError, TypeError, KeyError):
                value = None
            valid = (isinstance(value, int) and not isinstance(value, bool)
                     and value >= 0)
            if valid:
                known.append(path)
                numbers[path] = value
            else:
                unknown.append(path)
        ordered = sorted(known, key=numbers.__getitem__,
                         reverse=order.endswith('내림차순')) + unknown
    else:
        ordered = sort_archives(candidates, order, modified)
    if arrangement not in ('폴더 먼저', '파일 먼저'):
        return ordered
    folder_first = arrangement == '폴더 먼저'
    first, last = [], []
    for path in ordered:
        folder = kinds.get(path, 'archive') == 'folder'
        (first if folder == folder_first else last).append(path)
    return first + last
