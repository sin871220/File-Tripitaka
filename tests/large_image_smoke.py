"""Opt-in real decoding check; streams large fixtures without allocating a full bitmap."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import zipfile
import pyvips
from archive_core import cover

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
