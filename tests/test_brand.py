import unittest
from PIL import Image
from brand import APP_NAME, APP_TITLE, APP_VERSION, asset_path


class BrandChecks(unittest.TestCase):
    def test_application_name(self):
        self.assertEqual(APP_NAME, '파일만대장경')
        self.assertEqual(APP_TITLE, f'{APP_NAME} v{APP_VERSION}')

    def test_icon_transparency_and_windows_sizes(self):
        with Image.open(asset_path('app.png')) as image:
            self.assertEqual(image.mode, 'RGBA')
            self.assertEqual(image.getextrema()[-1], (0, 255))
        with Image.open(asset_path('app.ico')) as image:
            self.assertTrue({(16,16), (32,32), (48,48), (256,256)} <= image.info['sizes'])
