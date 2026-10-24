"""Pure, persistent identities for independently browsable folder tabs.

Loading these records never probes the filesystem. A disconnected drive can
remain a saved tab; the application checks availability when opening it.
"""
import os
from pathlib import Path
import re
from uuid import uuid4


MAX_FOLDER_TABS = 512
_ID_PATTERN = re.compile(r'folder:[0-9a-f]{32}')


def _path(path):
    try:
        value = os.fspath(path)
    except TypeError as exc:
        raise ValueError('A folder tab needs a valid path.') from exc
    if (not isinstance(value, str) or not value.strip() or '\0' in value
            or len(value) > 32768):
        raise ValueError('A folder tab needs a valid path.')
    return os.path.abspath(os.path.expanduser(value))


def tab_path_key(path):
    """Compare native paths lexically, including Windows case folding."""
    return os.path.normcase(_path(path))


def _valid_id(value):
    return isinstance(value, str) and _ID_PATTERN.fullmatch(value) is not None


def _new_id(used):
    while True:
        identity = 'folder:' + uuid4().hex
        if identity not in used:
            return identity


def normalize_folder_tabs(saved):
    """Keep distinct valid paths, repairing missing or duplicate identities."""
    if not isinstance(saved, list):
        return []
    records, paths, identities = [], set(), set()
    for item in saved:
        if not isinstance(item, dict):
            continue
        try:
            path = _path(item.get('path'))
        except ValueError:
            continue
        key = os.path.normcase(path)
        if key in paths:
            continue
        identity = item.get('id')
        if not _valid_id(identity) or identity in identities:
            identity = _new_id(identities)
        records.append({'id': identity, 'path': path})
        paths.add(key)
        identities.add(identity)
        if len(records) >= MAX_FOLDER_TABS:
            break
    return records


def new_folder_tab(path, existing):
    """Return a tab to focus or append, without changing the caller's list.

    ``existing`` normally comes from ``normalize_folder_tabs``. Duplicate
    paths reuse their identity, so one folder cannot accidentally have two
    independent tabs with indistinguishable names.
    """
    path = _path(path)
    key = os.path.normcase(path)
    identities, count = set(), 0
    for item in existing if isinstance(existing, (list, tuple)) else ():
        if not isinstance(item, dict) or not _valid_id(item.get('id')):
            continue
        try:
            existing_path = _path(item.get('path'))
        except ValueError:
            continue
        identities.add(item['id'])
        count += 1
        if os.path.normcase(existing_path) == key:
            return {'id': item['id'], 'path': existing_path}, False
    if count >= MAX_FOLDER_TABS:
        raise ValueError('Too many folder tabs are open.')
    return {'id': _new_id(identities), 'path': path}, True


def tab_label(path):
    """Use the literal folder name; roots retain a useful drive/root label."""
    folder = Path(os.path.normpath(os.fspath(path)))
    return folder.name or folder.anchor or str(folder)


def normalize_active_tab(value, records, only_favorites=False):
    """Restore a known identity while retaining legacy favorites selection."""
    if value in ('all', 'favorites'):
        return value
    if isinstance(value, str):
        for item in records if isinstance(records, (list, tuple)) else ():
            if isinstance(item, dict) and _valid_id(item.get('id')) and item['id'] == value:
                return value
    return 'favorites' if only_favorites is True else 'all'
