"""Archive cover loading. Archive members are never extracted onto user folders."""
import hashlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile
from PIL import Image, ImageOps

ARCHIVES = {'.zip', '.cbz', '.rar', '.cbr', '.7z', '.cb7'}
IMAGES = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tif', '.tiff'}
MAX_IMAGE = 64 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000


def natural(value):
    return [int(p) if p.isdigit() else p.casefold() for p in re.split(r'(\d+)', str(value))]


def sevenzip():
    for p in [shutil.which('7z'), shutil.which('7zz'),
              str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / '7-Zip/7z.exe'),
              str(Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / '7-Zip/7z.exe')]:
        if p and Path(p).is_file():
            return p
    raise ValueError('RAR·7Z 미리보기에는 7-Zip 설치가 필요합니다.')


def command(args):
    return subprocess.run(args, capture_output=True, timeout=30, check=True,
                          creationflags=0x08000000 if os.name == 'nt' else 0)


def image_entries(path):
    if path.suffix.lower() in {'.zip', '.cbz'}:
        with zipfile.ZipFile(path) as archive:
            entries = [(i.filename, i.file_size) for i in archive.infolist()
                       if not i.is_dir() and Path(i.filename).suffix.lower() in IMAGES
                       and not i.filename.startswith('__MACOSX/')]
    else:
        listing = command([sevenzip(), 'l', '-slt', '-sccUTF-8', '-p', '--', str(path)]).stdout.decode('utf-8', 'replace').replace('\r\n', '\n')
        entries = []
        for block in listing.split('\n\n'):
            fields = dict(line.split(' = ', 1) for line in block.splitlines() if ' = ' in line)
            name = fields.get('Path', '')
            if Path(name).suffix.lower() in IMAGES and fields.get('Folder') != '+':
                entries.append((name, int(fields.get('Size', '0'))))
    if not entries:
        raise ValueError('압축파일에 지원하는 이미지가 없습니다.')
    return sorted(entries, key=lambda e: natural(e[0]))


def read_image_entry(path, entry):
    name, size = entry
    if size > MAX_IMAGE:
        raise ValueError('대표 이미지가 64MB를 초과합니다.')
    if path.suffix.lower() in {'.zip', '.cbz'}:
        with zipfile.ZipFile(path) as archive, archive.open(name) as stream:
            return stream.read(MAX_IMAGE + 1)
    return command([sevenzip(), 'e', '-so', '-spd', '-p', '--', str(path), name]).stdout


def first_image(path, index=0):
    return read_image_entry(path, image_entries(path)[index])


def preview_indices(length, count, sampling='순차 보기'):
    count = min(length, max(1, min(3, int(count))))
    if count == 0:
        return []
    if sampling == '비율 보기':
        return [i * length // count for i in range(count)]
    return list(range(count))


def cover(path, cache, preview_count=1, sampling='순차 보기'):
    preview_count = max(1, min(3, int(preview_count)))
    path = Path(path).resolve()
    stat = path.stat()
    key = hashlib.sha256(f'v7:{sampling}:{preview_count}:{path}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()
    target = Path(cache) / (key + '.png')
    if target.exists():
        with Image.open(target) as im:
            return im.copy()
    entries = image_entries(path)
    images = []
    for index in preview_indices(len(entries), preview_count, sampling):
        try:
            data = read_image_entry(path, entries[index])
            if len(data) > MAX_IMAGE:
                raise ValueError('대표 이미지가 64MB를 초과합니다.')
            images.append(decode_thumbnail(data))
        except Exception:
            if not images:
                raise
            # Preserve a usable front cover if a secondary sampled page fails.
            continue
    im = side_by_side_thumbnail(images) if len(images) > 1 else images[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.png', delete=False) as stream:
        temp = Path(stream.name)
    try:
        im.save(temp, format='PNG')
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return im


def decode_thumbnail(data):
    try:
        source = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError:
        source = None
    if source is None:
        from large_thumbnail import thumbnail
        im = thumbnail(data)
    else:
        with source:
            large = source.width * source.height > 20_000_000
            if not large:
                source.thumbnail((320, 340))
                im = ImageOps.exif_transpose(source).convert('RGB')
                im.thumbnail((320, 340))
        if large:
            from large_thumbnail import thumbnail
            im = thumbnail(data)
    return im


def side_by_side_thumbnail(images):
    """Pack actual page widths with a small gap, in reverse sample order."""
    pages = []
    for source in reversed(images):
        page = source.copy().convert('RGBA')
        page.thumbnail((320, 340), Image.Resampling.LANCZOS)
        pages.append(page)
    height = max(page.height for page in pages)
    # Scale the gap with the images so smaller source pages stay close as well.
    gap = max(2, round(height * 6 / 340))
    canvas = Image.new('RGBA', (sum(page.width for page in pages) + gap * (len(pages) - 1), height))
    x = 0
    for page in pages:
        canvas.alpha_composite(page, (x, (height - page.height) // 2))
        x += page.width + gap
    return canvas


def visible_indices(count, columns, top, height, row_height=290, overscan=2):
    """Only create rows in/near the viewport, independent of the collection size."""
    columns = max(1, columns)
    rows = (count + columns - 1) // columns
    first = max(0, int(max(0, top) // row_height) - overscan)
    last = min(rows, int((max(0, top) + max(1, height)) // row_height) + 1 + overscan)
    return range(min(count, first * columns), min(count, last * columns))


def sort_archives(files, order, modified):
    # Path is a stable tie-breaker for same-name files in different folders.
    ordered = sorted(files, key=lambda p: (natural(p.name), natural(str(p))))
    if order.startswith('수정한 날짜'):
        return sorted(ordered, key=lambda p: modified.get(p, 0), reverse=order.endswith('내림차순'))
    return ordered[::-1] if order.endswith('내림차순') else ordered
