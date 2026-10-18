"""Function-based gallery shortcuts, independent of Tk widgets and user files.

Keys are stored in a portable, display-ready form, e.g. ``Ctrl+Shift+A``.
The caller scopes dispatch to the gallery so editing a filename never invokes
an archive action.  Legacy Enter/Space preferences are imported only once.
"""
import re
import sys

from localization import translate as tr
import viewer


COMMANDS = ('reveal', 'viewer', 'custom_viewer', 'favorite', 'rename', 'trash',
            'sidebar', 'fit')
_MODIFIERS = {'ctrl': 'Ctrl', 'control': 'Ctrl', 'cmd': 'Cmd',
              'command': 'Cmd', 'meta': 'Cmd', 'alt': 'Alt', 'option': 'Alt',
              'shift': 'Shift'}
_ORDER = ('Ctrl', 'Alt', 'Shift', 'Cmd')
_ALIASES = {
    'return': 'Enter', 'enter': 'Enter', 'kp_enter': 'Enter', 'keypadenter': 'Enter',
    'space': 'Space', 'spacebar': 'Space', 'delete': 'Delete', 'del': 'Delete',
    'kp_delete': 'Delete', 'backspace': 'Backspace', 'back_space': 'Backspace',
    'insert': 'Insert', 'ins': 'Insert', 'escape': 'Escape', 'esc': 'Escape',
    'tab': 'Tab', 'iso_left_tab': 'Tab', 'left': 'Left', 'right': 'Right',
    'up': 'Up', 'down': 'Down', 'home': 'Home', 'end': 'End',
    'prior': 'PageUp', 'pageup': 'PageUp', 'page_up': 'PageUp',
    'next': 'PageDown', 'pagedown': 'PageDown', 'page_down': 'PageDown',
}
_PUNCTUATION = {
    'minus': '-', 'equal': '=', 'comma': ',', 'period': '.', 'slash': '/',
    'backslash': '\\', 'semicolon': ';', 'apostrophe': "'", 'quotedbl': '"',
    'bracketleft': '[', 'bracketright': ']', 'grave': '`', 'plus': '+',
}
_SHIFTED = dict(zip('!@#$%^&*()_+{}|:"<>?~', '1234567890-=[]\\;\',./`'))
_SHIFTED_NAMES = dict(zip(
    ('exclam', 'at', 'numbersign', 'dollar', 'percent', 'asciicircum', 'ampersand',
     'asterisk', 'parenleft', 'parenright', 'underscore', 'braceleft',
     'braceright', 'bar', 'colon', 'less', 'greater', 'question', 'asciitilde'),
    '!@#$%^&*()_{}|:<>?~'))
_NAVIGATION = {'Left', 'Right', 'Up', 'Down', 'Home', 'End', 'PageUp', 'PageDown',
               'Tab', 'Escape'}
_MODIFIER_KEYSYMS = {
    'Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R',
    'Meta_L', 'Meta_R', 'Super_L', 'Super_R', 'Command', 'Option', 'Caps_Lock',
    'Num_Lock', 'Scroll_Lock', 'ISO_Level3_Shift', 'Mode_switch', 'Fn',
}


def command_labels(platform=None):
    """Stable Korean action names; translate these at the UI boundary."""
    return dict(reveal=viewer.REVEAL_ACTION,
                viewer=(viewer.DEFAULT_APP_ACTION if (platform or sys.platform) == 'darwin'
                        else viewer.HONEYVIEW_ACTION),
                custom_viewer=viewer.CUSTOM_VIEWER_ACTION,
                favorite='즐겨찾기 추가/해제', rename='파일 이름 바꾸기',
                trash='휴지통으로 보내기', sidebar='폴더 패널 접기/펴기',
                fit='창에 맞춤 ON/OFF')


def _empty():
    return {command: [] for command in COMMANDS}


def defaults(platform=None):
    mapping = _empty()
    command = 'reveal' if viewer.default_action(platform) == viewer.REVEAL_ACTION else 'viewer'
    mapping[command] = ['Enter', 'Space']
    mapping['rename'] = ['F2']
    mapping['trash'] = ['Delete', 'Cmd+Backspace'] if (platform or sys.platform) == 'darwin' else ['Delete']
    return mapping


def normalize_key(text):
    """Canonicalize a key chord, raising ValueError for unsupported keys."""
    if text == ' ':
        return 'Space'
    if text is None or str(text).strip().casefold() in ('', 'none', '없음'):
        return ''
    if not isinstance(text, str):
        raise ValueError(tr('지원하지 않는 단축키입니다: {key}').format(key=text))
    chord = text.strip()
    if chord == '+':
        chord = 'Plus'
    elif chord.endswith('++'):
        chord = chord[:-1] + 'Plus'
    parts = [part.strip() for part in chord.split('+')]
    modifiers = set()
    for part in parts[:-1]:
        modifier = _MODIFIERS.get(part.casefold())
        if not modifier:
            raise ValueError(tr('지원하지 않는 단축키입니다: {key}').format(key=text))
        modifiers.add(modifier)
    raw = parts[-1]
    key = _ALIASES.get(raw.casefold())
    if key is None:
        symbol = _SHIFTED_NAMES.get(raw.casefold(), _PUNCTUATION.get(raw.casefold(), raw))
        if symbol in _SHIFTED:
            symbol = _SHIFTED[symbol]
            modifiers.add('Shift')
        if len(symbol) == 1 and (symbol.isascii() and symbol.isalnum() or symbol in "-=[]\\;',./`"):
            key = symbol.upper()
        elif re.fullmatch(r'f(?:[1-9]|1[0-9]|2[0-4])', raw, re.IGNORECASE):
            key = raw.upper()
    if key is None:
        raise ValueError(tr('지원하지 않는 단축키입니다: {key}').format(key=text))
    return '+'.join([modifier for modifier in _ORDER if modifier in modifiers] + [key])


def validate(mapping, platform=None):
    """Return a clean mapping, rejecting ambiguous or reserved assignments."""
    if not isinstance(mapping, dict) or any(command not in COMMANDS for command in mapping):
        raise ValueError(tr('단축키 설정을 확인해 주세요.'))
    result, used = _empty(), {}
    labels = command_labels(platform)
    for command in COMMANDS:
        keys = mapping.get(command, [])
        if not isinstance(keys, (list, tuple)) or len(keys) > 2:
            raise ValueError(tr('기능마다 단축키는 최대 2개까지 지정할 수 있습니다.'))
        for value in keys:
            key = normalize_key(value)
            if not key:
                continue
            if key in _NAVIGATION:
                raise ValueError(tr('{key}는 탐색에 사용하는 키입니다. 다른 키를 선택해 주세요.').format(key=key))
            if (platform or sys.platform) != 'darwin' and 'Cmd' in key.split('+')[:-1]:
                raise ValueError(tr('Cmd 키는 macOS에서만 사용할 수 있습니다.'))
            if key in used:
                raise ValueError(tr('{key} 키가 중복되었습니다: {first}, {second}').format(
                    key=key, first=tr(labels[used[key]]), second=tr(labels[command])))
            used[key] = command
            result[command].append(key)
    return result


def migrate(settings, platform=None):
    """Import legacy choices without changing double-click or the input dict.

    A saved mapping remains authoritative, including deliberately empty rows.
    If a mapping is damaged or copied between OSes, retain its usable bindings
    instead of silently restoring commands that the user had disabled.
    """
    stored = settings.get('shortcuts')
    if isinstance(stored, dict):
        result, used = _empty(), set()
        for command in COMMANDS:
            values = stored.get(command, [])
            if not isinstance(values, (list, tuple)):
                continue
            for value in values[:2]:
                try:
                    clean = validate({command: [value]}, platform)[command]
                except ValueError:
                    continue
                if clean and clean[0] not in used:
                    result[command].extend(clean)
                    used.add(clean[0])
        return result
    result = defaults(platform)
    for command in COMMANDS:
        result[command] = [key for key in result[command] if key not in ('Enter', 'Space')]
    for field, key in (('enter_action', 'Enter'), ('space_action', 'Space')):
        action = settings.get(field, viewer.default_action(platform))
        if action is None or action == '없음':
            continue
        action = viewer.normalize_action(action, keyboard=True, platform=platform)
        command = next((command for command, label in command_labels(platform).items() if label == action), None)
        if command:
            result[command].append(key)
    return result


def command_for_key(mapping, key):
    if not key:
        return None
    try:
        key = normalize_key(key)
    except ValueError:
        return None
    return next((command for command in COMMANDS if key in mapping.get(command, ())), None)


def legacy_actions(mapping, platform=None):
    labels = command_labels(platform)
    # Older versions cannot dispatch view commands from legacy action strings.
    # Keep Enter/Space disabled there rather than falling back to a file action.
    labels = {command: label for command, label in labels.items()
              if command not in ('sidebar', 'fit')}
    return {field: labels.get(command_for_key(mapping, key), '없음')
            for field, key in (('enter_action', 'Enter'), ('space_action', 'Space'))}


def event_key(event, platform=None):
    """Read Tk state masks without treating lock/Fn/keypad bits as modifiers.

    Tk's macOS setupXEvent uses Mod1=Command and Mod2=Option. Windows uses
    Mod1=NumLock and Mod2/ALT_MASK=Alt. Source: tcltk/tk core-8-6-branch,
    macosx/tkMacOSXKeyEvent.c and win/tkWinKey.c (plus X11/X.h masks).
    """
    raw = getattr(event, 'keysym', '')
    if not raw or raw in _MODIFIER_KEYSYMS:
        return None
    state = int(getattr(event, 'state', 0) or 0)
    modifiers = []
    if state & 0x4:
        modifiers.append('Ctrl')
    if state & (0x10 if (platform or sys.platform) == 'darwin' else 0x20010):
        modifiers.append('Alt')
    if state & 0x1:
        modifiers.append('Shift')
    if (platform or sys.platform) == 'darwin' and state & 0x8:
        modifiers.append('Cmd')
    try:
        return normalize_key('+'.join(modifiers + [raw]))
    except ValueError:
        return None
