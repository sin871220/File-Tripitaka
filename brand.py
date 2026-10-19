"""Application display identity; legacy settings folder stays compatible."""
from pathlib import Path
import sys

APP_NAME = '파일만대장경'
APP_VERSION = '1.2.3'
APP_TITLE = f'{APP_NAME} v{APP_VERSION}'
EXE_NAME = 'FileManDaejanggyeong'


def asset_path(name):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets' / name
