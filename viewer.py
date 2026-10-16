"""Platform-aware viewer actions, selection and shell-free launching."""
import os
from pathlib import Path
import subprocess
import sys
from tkinter import filedialog

from localization import translate as tr


REVEAL_ACTION = '파일 위치 열기'
HONEYVIEW_ACTION = '꿀뷰 열기'
DEFAULT_APP_ACTION = '기본 앱으로 열기'
CUSTOM_VIEWER_ACTION = '다른 뷰어 프로그램 열기'
ACTIONS = [REVEAL_ACTION, HONEYVIEW_ACTION, CUSTOM_VIEWER_ACTION]
KEY_ACTIONS = ACTIONS + ['즐겨찾기 추가/해제', '없음']


def default_action(platform=None):
    return REVEAL_ACTION if (platform or sys.platform) == 'darwin' else HONEYVIEW_ACTION


def available_actions(keyboard=False, platform=None):
    actions = ([REVEAL_ACTION, DEFAULT_APP_ACTION, CUSTOM_VIEWER_ACTION]
               if (platform or sys.platform) == 'darwin' else list(ACTIONS))
    return actions + (['즐겨찾기 추가/해제', '없음'] if keyboard else [])


def normalize_action(action, keyboard=False, platform=None):
    """Use a supported action when settings move between operating systems."""
    return action if action in available_actions(keyboard, platform) else default_action(platform)


def is_viewer(path, platform=None):
    if not path:
        return False
    candidate = Path(path).expanduser()
    if (platform or sys.platform) == 'darwin':
        if candidate.suffix.casefold() == '.app' and candidate.is_dir():
            return (candidate / 'Contents' / 'Info.plist').is_file()
        return candidate.is_file() and os.access(candidate, os.X_OK)
    return candidate.is_file()


def launch_viewer(viewer, path):
    if not is_viewer(viewer):
        raise FileNotFoundError('선택한 프로그램 파일을 찾을 수 없습니다.')
    candidate = Path(viewer).expanduser()
    archive = str(Path(path).resolve())
    if sys.platform == 'darwin' and candidate.suffix.casefold() == '.app':
        return subprocess.Popen(['/usr/bin/open', '-a', str(candidate.resolve()), archive])
    return subprocess.Popen([str(candidate), archive])


def launch_default(path):
    archive = str(Path(path).resolve())
    if sys.platform == 'darwin':
        return subprocess.Popen(['/usr/bin/open', archive])
    if os.name == 'nt':
        return os.startfile(archive)
    raise OSError('Unsupported operating system')


def choose_viewer(parent=None):
    options = dict(parent=parent, title=tr('뷰어 실행 파일 선택'))
    if sys.platform == 'darwin':
        options['filetypes'] = [(tr('응용 프로그램'), '*.app'), (tr('모든 파일'), '*')]
        options['initialdir'] = '/Applications'
    else:
        options['filetypes'] = [(tr('실행 파일'), '*.exe'), (tr('모든 파일'), '*')]
    return filedialog.askopenfilename(**options)
