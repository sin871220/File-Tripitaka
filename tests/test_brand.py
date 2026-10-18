import unittest
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from PIL import Image
from brand import APP_NAME, APP_TITLE, APP_VERSION, asset_path


class BrandChecks(unittest.TestCase):
    def test_application_name(self):
        self.assertEqual(APP_NAME, '파일만대장경')
        self.assertEqual(APP_TITLE, f'{APP_NAME} v{APP_VERSION}')

    def test_source_version_check_needs_no_gui_or_installed_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / 'unused-settings'
            result = subprocess.run(
                [sys.executable, '-S', str(Path(__file__).resolve().parents[1] / 'app.py'), '--version'],
                cwd=temporary, env=dict(os.environ, LOCALAPPDATA=str(data), PYTHONIOENCODING='utf-8'),
                capture_output=True, text=True, encoding='utf-8', check=True)
            self.assertEqual(result.stdout.strip(), APP_TITLE)
            self.assertFalse(data.exists())

    def test_icon_transparency_and_windows_sizes(self):
        with Image.open(asset_path('app.png')) as image:
            self.assertEqual(image.mode, 'RGBA')
            self.assertEqual(image.getextrema()[-1], (0, 255))
        with Image.open(asset_path('app.ico')) as image:
            self.assertTrue({(16,16), (32,32), (48,48), (256,256)} <= image.info['sizes'])
