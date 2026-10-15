"""Run large-image codecs outside the GUI process with RSS/time monitoring."""
import os
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


def thumbnail(data):
    with LARGE_DECODER, tempfile.TemporaryDirectory(prefix='archiveshelf-thumb-') as tmp:
        source = Path(tmp) / 'input.image'
        target = Path(tmp) / 'thumbnail.png'
        source.write_bytes(data)
        if getattr(sys, 'frozen', False):
            args = [sys.executable, '--thumbnail-worker', str(source), str(target)]
        else:
            args = [sys.executable, str(Path(__file__).with_name('thumbnail_worker.py')), str(source), str(target)]
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
                    image.thumbnail((320, 340))
                    return image.convert('RGB')
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
