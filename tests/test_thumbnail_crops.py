import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image, ImageDraw

from archive_core import cover, decode_preview, render_edited_cover
from large_thumbnail import validate_options


def image_bytes(image, **options):
    output = io.BytesIO()
    image.save(output, 'PNG', **options)
    return output.getvalue()


class PreviewDecoding(unittest.TestCase):
    def test_orientation_is_applied_before_normalized_crop(self):
        image = Image.new('RGB', (200, 100), 'red')
        ImageDraw.Draw(image).rectangle((100, 0, 199, 99), fill='blue')
        exif = Image.Exif()
        exif[274] = 6
        data = image_bytes(image, exif=exif)
        whole = decode_preview(data)
        self.assertEqual(whole.size, (100, 200))
        result = decode_preview(data, (1600, 1600), (0, .5, 1, 1))
        self.assertEqual(result.mode, 'RGB')
        self.assertEqual(result.size, (100, 100))
        self.assertEqual(result.getpixel((50, 50)), (0, 0, 255))

    def test_crops_original_resolution_before_reduction(self):
        image = Image.new('RGB', (4000, 1000), 'red')
        ImageDraw.Draw(image).rectangle((2000, 0, 2399, 399), fill='green')
        result = decode_preview(image_bytes(image), (320, 340), (.5, 0, .6, .4))
        self.assertEqual(result.size, (320, 320))
        self.assertEqual(result.getpixel((160, 160)), (0, 128, 0))

    def test_output_is_bounded_without_upscaling(self):
        data = image_bytes(Image.new('RGBA', (50, 100), 'red'))
        self.assertEqual(decode_preview(data, (20, 20)).size, (10, 20))
        self.assertEqual(decode_preview(data, (1600, 1600)).size, (50, 100))

    def test_invalid_sizes_and_crop_values_are_rejected(self):
        for size in [(0, 20), (4097, 20), (20,), (20.0, 20), (True, 20), None]:
            with self.subTest(size=size), self.assertRaises(ValueError):
                validate_options(size)
        for box in [(0, 0, 0, 1), (-.1, 0, 1, 1), (0, 0, 1.1, 1),
                    (0, .8, 1, .2), (0, 0, float('nan'), 1),
                    (0, 0, float('inf'), 1), (0, 0, 1), ('0', 0, 1, 1),
                    (0, 0, 10 ** 1000, 1)]:
            with self.subTest(box=box), self.assertRaises(ValueError):
                validate_options((320, 340), box)

    def test_large_source_is_isolated_with_crop_options(self):
        class Source:
            width, height = 6000, 4000

            def __enter__(self):
                return self

            def __exit__(self, *unused):
                pass

        expected = Image.new('RGB', (80, 80))
        with patch('archive_core.Image.open', return_value=Source()), \
                patch('large_thumbnail.thumbnail', return_value=expected) as worker:
            self.assertIs(decode_preview(b'header', (800, 700), (.2, .3, .8, .9)), expected)
        worker.assert_called_once_with(b'header', max_size=(800, 700), box=(.2, .3, .8, .9))


class EditedCovers(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / 'pages.zip'
        with zipfile.ZipFile(self.archive, 'w') as target:
            for index, color in enumerate(['red', 'green', 'blue', 'yellow', 'purple', 'orange']):
                target.writestr(f'{index + 1}.png', image_bytes(Image.new('RGB', (100, 100), color)))
        self.cache = self.root / 'cache'

    def colors(self, image, count):
        return [image.getpixel((index * 102 + 50, 50))[:3] for index in range(count)]

    def test_slot_overrides_keep_pair_and_triple_reverse_order(self):
        recipes = {'0': {'entry': '4.png', 'box': [0, 0, 1, 1]}}
        pair = render_edited_cover(self.archive, self.cache, recipes, 2)
        self.assertEqual(self.colors(pair, 2), [(0, 128, 0), (255, 255, 0)])
        triple = render_edited_cover(self.archive, self.cache, recipes, 3, '비율 보기')
        self.assertEqual(self.colors(triple, 3), [(128, 0, 128), (0, 0, 255), (255, 255, 0)])

    def test_cache_changes_with_recipe_and_is_reused_for_same_recipe(self):
        recipe = {'0': {'entry': '4.png', 'box': [0, 0, 1, 1]}}
        first = render_edited_cover(self.archive, self.cache, recipe)
        with patch('archive_core.decode_preview', side_effect=AssertionError('Cache miss')):
            cached = render_edited_cover(self.archive, self.cache, recipe)
        self.assertEqual(first.tobytes(), cached.tobytes())
        recipe['0']['entry'] = '5.png'
        changed = render_edited_cover(self.archive, self.cache, recipe)
        self.assertNotEqual(first.tobytes(), changed.tobytes())
        recipe['0']['box'] = [0, 0, .5, 1]
        cropped = render_edited_cover(self.archive, self.cache, recipe)
        self.assertEqual(cropped.size, (50, 100))
        self.assertEqual(len(list(self.cache.glob('*.png'))), 3)

    def test_missing_or_malformed_recipe_falls_back_and_reset_uses_automatic(self):
        for recipe in [{'0': {'entry': 'missing.png', 'box': [0, 0, 1, 1]}},
                       {'0': {'entry': '4.png', 'box': [0, 0, 0, 0]}}]:
            image = render_edited_cover(self.archive, self.cache, recipe)
            self.assertEqual(image.getpixel((50, 50)), (255, 0, 0))
        automatic = cover(self.archive, self.cache, 3)
        reset = render_edited_cover(self.archive, self.cache, {}, 3)
        self.assertEqual(reset.tobytes(), automatic.tobytes())

    def test_list_recipes_and_partial_slots(self):
        result = render_edited_cover(self.archive, self.cache,
                                     [None, {'entry': '6.png', 'box': None}], 3)
        self.assertEqual(self.colors(result, 3), [(0, 0, 255), (255, 165, 0), (255, 0, 0)])


if __name__ == '__main__':
    unittest.main()
