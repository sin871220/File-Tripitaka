import io
from pathlib import Path
import tempfile
import unittest
import zipfile
from PIL import Image
from archive_core import cover, visible_indices, sort_archives, preview_indices


class Covers(unittest.TestCase):
    def test_natural_order_cache_and_invalidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / '한글 파일.zip'
            def write(color):
                with zipfile.ZipFile(archive, 'w') as z:
                    for name, c in [('10.png', 'blue'), ('2.png', color)]:
                        b = io.BytesIO()
                        Image.new('RGB', (600, 800), c).save(b, 'PNG')
                        z.writestr(name, b.getvalue())
            write('red')
            result = cover(archive, root / 'cache')
            self.assertEqual(result.getpixel((0, 0)), (255, 0, 0))
            self.assertLessEqual(max(result.size), 340)
            self.assertEqual(cover(archive, root / 'cache').tobytes(), result.tobytes())
            write('green')
            self.assertEqual(cover(archive, root / 'cache').getpixel((0, 0)), (0, 128, 0))

    def test_virtual_scroll_bounds_and_reachability(self):
        count, columns, height = 7444, 4, 700
        visited = set()
        for top in range(0, ((count + columns - 1) // columns) * 290, 200):
            indices = list(visible_indices(count, columns, top, height))
            self.assertLessEqual(len(indices), 32)
            self.assertTrue(all(0 <= i < count for i in indices))
            visited.update(indices)
        self.assertEqual(visited, set(range(count)))
        self.assertEqual(list(visible_indices(0, 4, 0, 700)), [])
        self.assertIn(7443, visible_indices(count, columns, 539000, 700))

    def test_all_sort_orders(self):
        files = [Path('folder/10.zip'), Path('folder/2.zip'), Path('folder/1.zip')]
        modified = {files[0]: 100, files[1]: 300, files[2]: 200}
        self.assertEqual(sort_archives(files, '이름 오름차순', modified), [files[2], files[1], files[0]])
        self.assertEqual(sort_archives(files, '이름 내림차순', modified), [files[0], files[1], files[2]])
        self.assertEqual(sort_archives(files, '수정한 날짜 오름차순', modified), [files[0], files[2], files[1]])
        self.assertEqual(sort_archives(files, '수정한 날짜 내림차순', modified), [files[1], files[2], files[0]])

    def test_preview_sampling_positions(self):
        self.assertEqual(preview_indices(12, 1), [0])
        self.assertEqual(preview_indices(12, 2), [0, 1])
        self.assertEqual(preview_indices(12, 3), [0, 1, 2])
        self.assertEqual(preview_indices(12, 2, '비율 보기'), [0, 6])
        self.assertEqual(preview_indices(12, 3, '비율 보기'), [0, 4, 8])
        self.assertEqual(preview_indices(11, 3, '비율 보기'), [0, 3, 7])
        self.assertEqual(preview_indices(1, 3, '비율 보기'), [0])
        self.assertEqual(preview_indices(2, 3, '비율 보기'), [0, 1])
        self.assertEqual(preview_indices(0, 3, '비율 보기'), [])

    def test_multi_image_preview_cache_and_fewer_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'pages.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                for i, color in enumerate(['red', 'green', 'blue', 'yellow', 'purple', 'orange']):
                    data = io.BytesIO()
                    Image.new('RGB', (150, 240), color).save(data, 'PNG')
                    z.writestr(f'{i+1}.png', data.getvalue())
            single = cover(archive, root / 'cache')
            sequential = cover(archive, root / 'cache', 3)
            proportional = cover(archive, root / 'cache', 3, '비율 보기')
            self.assertEqual(single.getpixel((0, 0)), (255, 0, 0))
            self.assertEqual(sequential.mode, 'RGBA')
            self.assertEqual(sequential.size, (458, 240))
            self.assertEqual([sequential.getpixel((x, 170))[:3] for x in (75, 229, 383)],
                             [(0, 0, 255), (0, 128, 0), (255, 0, 0)])
            pair = cover(archive, root / 'pair-cache', 2)
            self.assertEqual(pair.size, (304, 240))
            self.assertEqual([pair.getpixel((x, 170))[:3] for x in (75, 229)],
                             [(0, 128, 0), (255, 0, 0)])
            self.assertEqual(sequential.getpixel((151, 120))[3], 0)
            self.assertEqual(sequential.getpixel((149, 120))[3], 255)
            self.assertEqual(sequential.getpixel((154, 120))[3], 255)
            self.assertNotEqual(sequential.tobytes(), proportional.tobytes())
            self.assertEqual(cover(archive, root / 'cache', 3).tobytes(), sequential.tobytes())
            self.assertEqual(len(list((root / 'cache').glob('*.png'))), 3)
            with zipfile.ZipFile(root / 'one.zip', 'w') as z:
                data = io.BytesIO()
                Image.new('RGB', (100, 100), 'red').save(data, 'PNG')
                z.writestr('1.png', data.getvalue())
            only = cover(root / 'one.zip', root / 'cache', 3, '비율 보기')
            self.assertEqual(only.size, (100, 100))

    def test_empty_and_corrupt_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'empty.zip'
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr('note.txt', 'hello')
            with self.assertRaises(ValueError):
                cover(p, Path(tmp) / 'cache')
            p.write_bytes(b'broken')
            with self.assertRaises(zipfile.BadZipFile):
                cover(p, Path(tmp) / 'cache')


if __name__ == '__main__':
    unittest.main()
