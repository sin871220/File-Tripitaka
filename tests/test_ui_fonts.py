import unittest
from ui_fonts import select_family, resource_font


class UIFontChecks(unittest.TestCase):
    def test_bundled_family_preferred(self):
        self.assertEqual(select_family(['Segoe UI', 'Yu Gothic', 'Noto Sans CJK KR']), 'Noto Sans CJK KR')

    def test_cjk_fallback_and_case(self):
        self.assertEqual(select_family(['segoe ui', 'MEIRYO']), 'MEIRYO')
        self.assertIsNone(select_family(['Other']))

    def test_font_and_license_packaged(self):
        file = resource_font()
        self.assertTrue(file.is_file())
        self.assertEqual(file.read_bytes()[:4], b'OTTO')
        self.assertIn('SIL OPEN FONT LICENSE', file.with_name('OFL.txt').read_text())
