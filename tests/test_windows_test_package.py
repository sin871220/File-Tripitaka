"""A Windows test delivery must keep its own code when the ZIP is moved."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from scripts.package_windows_test import REQUIRED, package


class WindowsTestPackage(unittest.TestCase):
    def make_source(self, root):
        for relative in REQUIRED:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'fixture')
        (root / 'brand.py').write_text("APP_VERSION = '1.2.0-beta.3'\nEXE_NAME = 'FileManDaejanggyeong'\n", 'utf-8')
        (root / 'app.py').write_text('from brand import APP_VERSION\nprint(APP_VERSION)\n', 'utf-8')
        (root / 'run-windows.bat').write_bytes(b'@echo off\npushd "%~dp0"\n')
        (root / 'uncommitted_feature.py').write_text('# not in any Git index\n', 'utf-8')
        (root / '.venv').mkdir()
        (root / '.venv' / 'old-brand.py').write_text('1.1.0', 'utf-8')
        (root / '.git').mkdir()
        (root / '.git' / 'private-config').write_text('exclude me', 'utf-8')

    def test_moved_zip_contains_current_uncommitted_code_and_no_local_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            original = base / 'source'
            original.mkdir()
            self.make_source(original)
            archive = package(original, base / 'delivery.zip')
            moved = base / '다른 컴퓨터 공유 폴더'
            moved.mkdir()
            with zipfile.ZipFile(archive) as bundle:
                names = bundle.namelist()
                self.assertEqual(len({name.split('/')[0] for name in names}), 1)
                self.assertFalse(any('/.venv/' in name or '/.git/' in name for name in names))
                self.assertTrue(any(name.endswith('/uncommitted_feature.py') for name in names))
                bundle.extractall(moved)
            shutil.rmtree(original)
            extracted = next(moved.iterdir())
            renamed = moved / '폴더 이름도 바꿈'
            extracted.rename(renamed)
            result = subprocess.run([sys.executable, '-E', '-s', '-S', str(renamed / 'app.py'), '--version'],
                                    cwd=base, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), '1.2.0-beta.3')
            info = json.loads((renamed / 'PACKAGE-INFO.json').read_text('utf-8'))
            for relative, digest in info['files'].items():
                self.assertEqual(hashlib.sha256((renamed / relative).read_bytes()).hexdigest(), digest)
            self.assertEqual((renamed / 'run-windows.bat').read_bytes().count(b'\r\n'), 2)

    def test_incomplete_source_cannot_produce_a_successful_test_zip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_source(root)
            (root / 'shortcuts.py').unlink()
            with self.assertRaisesRegex(FileNotFoundError, 'shortcuts.py'):
                package(root, root / 'incomplete.zip')
            self.assertFalse((root / 'incomplete.zip').exists())


if __name__ == '__main__':
    unittest.main()
