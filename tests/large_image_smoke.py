"""Opt-in real decoding check; streams large fixtures without allocating a full bitmap."""
import sys
import io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import zipfile
import pyvips
from PIL import Image, ImageDraw
from archive_core import cover, decode_preview
from large_thumbnail import thumbnail

# Exercise the actual worker with an orientation tag, not just a mocked vips API.
fixture = Image.new('RGB', (200, 100), 'red')
ImageDraw.Draw(fixture).rectangle((100, 0, 199, 99), fill='blue')
orientation = Image.Exif()
orientation[274] = 6
output = io.BytesIO()
fixture.save(output, 'JPEG', exif=orientation, quality=100, subsampling=0)
oriented_crop = thumbnail(output.getvalue(), (800, 700), (0, .5, 1, 1))
assert oriented_crop.size == (100, 100)
assert oriented_crop.getpixel((50, 50))[2] > 240
print('PASS native EXIF orientation before crop', flush=True)

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    source = pyvips.Image.black(15000, 15045, bands=3)
    for extension in ('jpg', 'png', 'tif'):
        file = root / ('large.' + extension)
        if extension == 'tif':
            source.tiffsave(str(file), compression='deflate')
        else:
            source.write_to_file(str(file))
        archive = root / (extension + '.zip')
        with zipfile.ZipFile(archive, 'w') as z:
            z.write(file, '01-cover.jpg')
        image = cover(archive, root / 'cache')
        assert image.width <= 320 and image.height <= 340
        assert image.getpixel((0, 0)) == (0, 0, 0)
        print(f'PASS {extension}: 225,675,000 pixels -> {image.size}', flush=True)
        cropped = decode_preview(file.read_bytes(), (800, 700), (.2, .3, .4, .5))
        assert 600 < cropped.width <= 800 and cropped.height == 700
        assert cropped.getpixel((0, 0)) == (0, 0, 0)
        print(f'PASS {extension}: original-resolution crop -> {cropped.size}', flush=True)
