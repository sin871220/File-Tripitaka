"""Run large-image codecs outside the GUI process with RSS/time monitoring."""
import os
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import psutil
from PIL import Image

LARGE_DECODER = threading.Semaphore(1)
RSS_LIMIT = 512 * 1024 * 1024
TIME_LIMIT = 45
MAX_PREVIEW_EDGE = 4096


def validate_options(max_size, box=None):
    """Bound output allocations and reject malformed normalized selections."""
    if (not isinstance(max_size, (tuple, list)) or len(max_size) != 2 or
            any(isinstance(value, bool) or not isinstance(value, int) or
                not 1 <= value <= MAX_PREVIEW_EDGE for value in max_size)):
        raise ValueError('미리보기 크기가 올바르지 않습니다.')
    size = tuple(max_size)
    if box is None:
        return size, None
    if (not isinstance(box, (tuple, list)) or len(box) != 4 or
            any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in box)):
        raise ValueError('썸네일 영역이 올바르지 않습니다.')
    try:
        coordinates = tuple(float(value) for value in box)
    except (OverflowError, ValueError):
        raise ValueError('썸네일 영역이 올바르지 않습니다.') from None
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError('썸네일 영역이 올바르지 않습니다.')
    left, top, right, bottom = coordinates
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError('썸네일 영역이 올바르지 않습니다.')
    return size, (left, top, right, bottom)


def crop_pixels(width, height, box):
    """Return integral bounds in the already oriented, full-resolution image."""
    left, top, right, bottom = box
    return (max(0, min(width - 1, math.floor(left * width))),
            max(0, min(height - 1, math.floor(top * height))),
            max(1, min(width, math.ceil(right * width))),
            max(1, min(height, math.ceil(bottom * height))))


def thumbnail(data, max_size=(320, 340), box=None):
    max_size, box = validate_options(max_size, box)
    with LARGE_DECODER, tempfile.TemporaryDirectory(prefix='archiveshelf-thumb-') as tmp:
        source = Path(tmp) / 'input.image'
        target = Path(tmp) / 'thumbnail.png'
        source.write_bytes(data)
        if getattr(sys, 'frozen', False):
            args = [sys.executable, '--thumbnail-worker', str(source), str(target)]
        else:
            args = [sys.executable, str(Path(__file__).with_name('thumbnail_worker.py')), str(source), str(target)]
        args.extend(['--width', str(max_size[0]), '--height', str(max_size[1])])
        if box is not None:
            args.extend(['--crop', ','.join(format(value, '.17g') for value in box)])
        with (Path(tmp) / 'decoder.log').open('w+b') as errors:
            process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=errors,
                                       creationflags=0x08000000 if os.name == 'nt' else 0)
            try:
                watcher = psutil.Process(process.pid)
                start = time.monotonic()
                while process.poll() is None:
                    if time.monotonic() - start > TIME_LIMIT:
                        raise ValueError('큰 이미지 축소 시간이 45초를 초과했습니다.')
                    try:
                        if watcher.memory_info().rss > RSS_LIMIT:
                            raise ValueError('큰 이미지 축소 메모리가 512MB를 초과하여 해당 미리보기를 중단했습니다.')
                    except psutil.NoSuchProcess:
                        break
                    time.sleep(.05)
                process.wait(timeout=5)
                if process.returncode != 0 or not target.is_file():
                    errors.seek(0)
                    detail = errors.read(2000).decode('utf-8', 'replace')
                    raise ValueError('큰 이미지 축소 실패: ' + (detail or f'디코더 종료 코드 {process.returncode}'))
                with Image.open(target) as image:
                    image.thumbnail(max_size, Image.Resampling.LANCZOS)
                    return image.convert('RGB')
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
