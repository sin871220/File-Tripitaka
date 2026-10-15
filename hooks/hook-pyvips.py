"""Include native libraries from the self-contained pyvips-binary wheel."""
from importlib.metadata import distribution
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('pyvips') + ['_libvips', '_cffi_backend']
binaries = []
datas = []
wheel = distribution('pyvips-binary')
for entry in wheel.files or []:
    name = str(entry).lower()
    if name.endswith(('.dll', '.dylib', '.so', '.pyd')) or '.so.' in name:
        binaries.append((str(wheel.locate_file(entry)), str(Path(entry).parent)))
    elif 'license' in name or 'copying' in name:
        datas.append((str(wheel.locate_file(entry)), str(Path(entry).parent)))
