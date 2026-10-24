"""Persist thumbnail crops by verified archive or image-folder content.

Looking up an unrelated archive never reads its whole contents: size and a
bounded prefix/suffix fingerprint first narrow the candidates. A full SHA-256
then confirms any match. All public methods are safe to call from worker
threads; this module has no dependency on Tk or image decoders.
"""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import threading


QUICK_BYTES = 64 * 1024
_HASH_CHUNK = 1024 * 1024
_LOCKS = {}
_LOCKS_LOCK = threading.Lock()
_IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tif', '.tiff'}


class ThumbnailEditDatabaseError(ValueError):
    """The existing database cannot safely be replaced."""


class ThumbnailFileChangedError(OSError):
    """An archive changed while its identity was being read."""


class ThumbnailEditCancelledError(OSError):
    """Identity lookup was cancelled because the application is closing."""


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise ThumbnailEditCancelledError('Thumbnail edit lookup cancelled')


def _path_key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _signature(info):
    return (info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_dev, info.st_ino)


def _file_signature(path):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise IsADirectoryError(str(path))
    return _signature(info)


def _digest(path, expected, full, cancel=None, reject_symlink=False):
    """Check both the opened file and its current directory entry around I/O."""
    _check_cancel(cancel)
    before = _file_signature(path)
    if expected != before:
        raise ThumbnailFileChangedError('Archive changed before fingerprinting')
    digest = hashlib.sha256()
    if reject_symlink:
        if path.is_symlink():
            raise ThumbnailFileChangedError('Image was replaced by a symbolic link')
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0)
                             | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        stream = os.fdopen(descriptor, 'rb')
    else:
        stream = path.open('rb')
    with stream:
        opened = _signature(os.fstat(stream.fileno()))
        # Windows Python can report creation time from stat(path), but metadata
        # change time from fstat(fd). Compare ctime only within the same API;
        # size, modification time and full device/file IDs must still agree.
        if opened[:2] + opened[3:] != before[:2] + before[3:]:
            raise ThumbnailFileChangedError('Archive was replaced before reading')
        if full:
            for chunk in iter(lambda: stream.read(_HASH_CHUNK), b''):
                _check_cancel(cancel)
                digest.update(chunk)
        else:
            digest.update(str(before[0]).encode('ascii') + b'\0')
            digest.update(stream.read(QUICK_BYTES))
            _check_cancel(cancel)
            if before[0] > QUICK_BYTES:
                stream.seek(max(QUICK_BYTES, before[0] - QUICK_BYTES))
                digest.update(stream.read(QUICK_BYTES))
        after = _signature(os.fstat(stream.fileno()))
    _check_cancel(cancel)
    if (after != opened or _file_signature(path) != before
            or reject_symlink and path.is_symlink()):
        raise ThumbnailFileChangedError('Archive changed while fingerprinting')
    return digest.hexdigest()


def _quick_fingerprint(path, expected, cancel=None):
    return _digest(path, expected, full=False, cancel=cancel)


def _full_digest(path, expected, cancel=None):
    return _digest(path, expected, full=True, cancel=cancel)


def _folder_signature(path, cancel=None):
    """Snapshot only direct, regular image children, never linked images.

    Stat details invalidate location hints; they are not part of the persisted
    identity, so renamed/moved folders and identical copies can share edits.
    """
    _check_cancel(cancel)
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise NotADirectoryError(str(path))
    entries = []
    with os.scandir(path) as listing:
        for child in listing:
            _check_cancel(cancel)
            if Path(child.name).suffix.casefold() not in _IMAGE_SUFFIXES:
                continue
            try:
                # Windows DirEntry.stat may use cached enumeration metadata
                # whose device/file IDs are zero. Fingerprinting rechecks the
                # path and open handle, so gather the same full path identity
                # here instead of comparing those different stat APIs later.
                # lstat still excludes linked images from the snapshot.
                info = (path / child.name).lstat()
            except FileNotFoundError as error:
                raise ThumbnailFileChangedError('Image disappeared while listing folder') from error
            if stat.S_ISREG(info.st_mode):
                entries.append((child.name, _signature(info)))
    entries.sort(key=lambda item: (
        [int(part) if part.isdigit() else part.casefold()
         for part in re.split(r'(\d+)', item[0])], item[0]))
    return sum(info[0] for _, info in entries), 'folder-v1', tuple(entries)


def _source_signature(path, cancel=None):
    return (_folder_signature(path, cancel) if path.is_dir()
            else _file_signature(path))


def _source_kind(signature):
    return 'folder' if signature[1] == 'folder-v1' else 'archive'


def _folder_digest(path, expected, full, cancel=None):
    """Hash ordered image names, lengths and verified individual content.

    Prefix/suffix hashes of at most the first/last images cheaply reject
    same-size unrelated folders, reading at most 256 KiB regardless of page
    count. Full digests of every image confirm a match before crops are
    restored. Enumeration, replacement and content changes during either pass
    invalidate the entire identity.
    """
    if _folder_signature(path, cancel) != expected:
        raise ThumbnailFileChangedError('Image folder changed before fingerprinting')
    digest = hashlib.sha256(b'File Tripitaka image folder v1\0')
    entries = expected[2]
    for name, signature in entries:
        _check_cancel(cancel)
        digest.update(json.dumps([name, signature[0]], ensure_ascii=True,
                                 separators=(',', ':')).encode('ascii') + b'\0')
    selected = entries if full else entries[:1] + (entries[-1:] if len(entries) > 1 else ())
    for name, signature in selected:
        _check_cancel(cancel)
        digest.update(_digest(path / name, signature, full, cancel,
                              reject_symlink=True).encode('ascii') + b'\0')
    if _folder_signature(path, cancel) != expected:
        raise ThumbnailFileChangedError('Image folder changed while fingerprinting')
    return digest.hexdigest()


def _source_digest(path, signature, full, cancel=None):
    if _source_kind(signature) == 'folder':
        return _folder_digest(path, signature, full, cancel)
    return (_full_digest(path, signature, cancel) if full
            else _quick_fingerprint(path, signature, cancel))


def _slot(slot):
    if type(slot) is not int or not 0 <= slot <= 2:
        raise ValueError('Thumbnail slot must be 0, 1 or 2')
    return str(slot)


def _recipe(entry, box):
    if not isinstance(entry, str) or not entry or '\0' in entry:
        raise ValueError('An archive image entry is required')
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        raise ValueError('Crop must contain four normalized coordinates')
    if any(type(value) not in (int, float) or not math.isfinite(value)
           for value in box):
        raise ValueError('Crop coordinates must be finite numbers')
    left, top, right, bottom = map(float, box)
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError('Crop must have positive size and lie within the image')
    return {'entry': entry, 'box': [left, top, right, bottom]}


def _hex_digest(value):
    return (isinstance(value, str) and len(value) == 64
            and all(char in '0123456789abcdef' for char in value))


def _validated_database(value):
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or value['version'] != 1 or not isinstance(value.get('edits'), dict)):
        raise ValueError('Unsupported thumbnail edit database')
    result = {}
    for digest, record in value['edits'].items():
        if (not _hex_digest(digest) or not isinstance(record, dict)
                or type(record.get('size')) is not int or record['size'] < 0
                or not _hex_digest(record.get('quick'))
                or not isinstance(record.get('slots'), dict)
                or not record['slots']):
            raise ValueError('Invalid archive identity in thumbnail edit database')
        kind = record.get('kind', 'archive')
        if kind not in ('archive', 'folder'):
            raise ValueError('Unsupported thumbnail source kind')
        slots = {}
        for slot, recipe in record['slots'].items():
            if slot not in ('0', '1', '2') or not isinstance(recipe, dict):
                raise ValueError('Invalid thumbnail slot in database')
            slots[slot] = _recipe(recipe.get('entry'), recipe.get('box'))
        result[digest] = {'size': record['size'], 'quick': record['quick'],
                          'slots': slots}
        if kind == 'folder':
            result[digest]['kind'] = 'folder'
    return result


class ThumbnailEditStore:
    """Read and atomically save per-slot crops for byte-identical archives.

    ``get`` returns a deep copy of ``{'0': {'entry': ..., 'box': [...]}, ...}``
    or ``None``. Corrupt/unsupported database files are left untouched: reads
    return no edits and writes raise ``ThumbnailEditDatabaseError``. File I/O
    failures propagate. A disappeared archive never removes its saved crops.
    """

    def __init__(self, path):
        self.path = Path(path)
        with _LOCKS_LOCK:
            self._lock = _LOCKS.setdefault(_path_key(self.path), threading.RLock())
        self._records = {}
        self._index = {}
        self._path_cache = {}
        self._generation = 0
        self._cancel = threading.Event()
        self._db_signature = object()
        self._corrupt_reason = None
        # Read lazily in worker-side get/set calls. Unavailable metadata must not
        # prevent the browser from starting or block its Tk thread on disk I/O.

    def _refresh(self):
        try:
            signature = _file_signature(self.path)
        except FileNotFoundError:
            signature = None
        if signature == self._db_signature:
            return
        self._generation += 1
        self._records = {}
        self._corrupt_reason = None
        if signature is not None:
            try:
                with self.path.open('r', encoding='utf-8') as stream:
                    self._records = _validated_database(json.load(stream))
            except (ValueError, UnicodeError, TypeError, OverflowError) as error:
                self._corrupt_reason = str(error)
            # Refuse to attribute a parsed document to a concurrently replaced
            # file. A subsequent call can safely load the new file again.
            if _file_signature(self.path) != signature:
                raise ThumbnailEditDatabaseError('Thumbnail edit database changed while reading')
        self._db_signature = signature
        self._reindex()

    def _reindex(self):
        self._index = {}
        for digest, record in self._records.items():
            key = record.get('kind', 'archive'), record['size']
            self._index.setdefault(key, {}).setdefault(record['quick'], set()).add(digest)

    def _writable(self):
        if self._corrupt_reason is not None:
            raise ThumbnailEditDatabaseError(
                'Existing thumbnail edit database is invalid; preserved without changes: '
                + self._corrupt_reason)

    def _identify(self, archive, create=False):
        _check_cancel(self._cancel)
        path = Path(archive)
        key = _path_key(path)
        try:
            signature = _source_signature(path, self._cancel)
        except FileNotFoundError:
            with self._lock:
                self._path_cache.pop(key, None)
            if create:
                raise
            return None
        kind = _source_kind(signature)
        if create and kind == 'folder' and not signature[2]:
            raise ValueError('폴더에 지원하는 이미지가 없습니다.')
        with self._lock:
            self._refresh()
            if create:
                self._writable()
            elif self._corrupt_reason is not None:
                return None
            generation = self._generation
            cached = self._path_cache.get(key)
            if cached is not None and cached[0] == signature:
                digest = cached[1]
                if digest in self._records:
                    return digest, signature, self._records[digest]['quick']
                if not create and cached[2] == generation:
                    return None
            candidates = {quick: frozenset(digests) for quick, digests in
                          self._index.get((kind, signature[0]), {}).items()}
            if not create and not candidates:
                self._path_cache[key] = (signature, None, generation)
                return None
        # File reads can be slow on network drives. Do them outside the database
        # lock so unrelated thumbnail workers and already-known files can proceed.
        quick = _source_digest(path, signature, full=False, cancel=self._cancel)
        if not create and quick not in candidates:
            with self._lock:
                self._path_cache[key] = (signature, None, generation)
            return None
        digest = _source_digest(path, signature, full=True, cancel=self._cancel)
        with self._lock:
            self._path_cache[key] = (signature, digest, generation)
        if create or digest in candidates.get(quick, ()):
            return digest, signature, quick
        return None

    def _write(self, records):
        # Once a commit starts it finishes atomically even if close() arrives.
        _check_cancel(self._cancel)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                             dir=self.path.parent, prefix=self.path.name + '.',
                                             suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({'version': 1, 'edits': records}, stream,
                          ensure_ascii=True, allow_nan=False, separators=(',', ':'))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self._db_signature = _file_signature(self.path)
            self._records = records
            self._generation += 1
            self._reindex()
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def get(self, archive):
        _check_cancel(self._cancel)
        with self._lock:
            self._refresh()
            if self._corrupt_reason is not None or not self._records:
                return None
        identity = self._identify(archive)
        with self._lock:
            self._refresh()
            record = self._records.get(identity[0]) if identity else None
            return deepcopy(record['slots']) if record else None

    def set(self, archive, slot, entry, box):
        slot = _slot(slot)
        recipe = _recipe(entry, box)
        digest, signature, quick = self._identify(archive, create=True)
        if (_source_kind(signature) == 'folder'
                and entry not in {name for name, _ in signature[2]}):
            raise ValueError('폴더 안의 이미지 파일을 선택해 주세요.')
        with self._lock:
            self._refresh()
            self._writable()
            records = deepcopy(self._records)
            record = records.setdefault(digest, {'size': signature[0], 'quick': quick, 'slots': {}})
            if _source_kind(signature) == 'folder':
                record['kind'] = 'folder'
            if record['slots'].get(slot) == recipe:
                return
            record['slots'][slot] = recipe
            self._write(records)

    def reset(self, archive, slot=None):
        _check_cancel(self._cancel)
        slot = _slot(slot) if slot is not None else None
        with self._lock:
            self._refresh()
            self._writable()
        identity = self._identify(archive)
        with self._lock:
            self._refresh()
            self._writable()
            if identity is None or identity[0] not in self._records:
                return False
            digest = identity[0]
            records = deepcopy(self._records)
            if slot is None:
                del records[digest]
            elif slot in records[digest]['slots']:
                del records[digest]['slots'][slot]
                if not records[digest]['slots']:
                    del records[digest]
            else:
                return False
            self._write(records)
            return True

    def relocate(self, old, new):
        """Forget location hints after a rename, without reading either file.

        Content records need no migration. The next worker lookup verifies the
        new location, including a move across volumes, before restoring edits.
        """
        with self._lock:
            self._path_cache.pop(_path_key(old), None)
            self._path_cache.pop(_path_key(new), None)

    def close(self):
        """Cancel pending identity reads without interrupting an atomic commit."""
        self._cancel.set()
