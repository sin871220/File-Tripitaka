"""Stable settings for the optional markers drawn over thumbnail groups."""
import re

OVERLAY_POSITIONS = ('top_left', 'top_right', 'bottom_left', 'bottom_right')
POSITION_LABELS = dict(zip(OVERLAY_POSITIONS,
                          ('왼쪽 위', '오른쪽 위', '왼쪽 아래', '오른쪽 아래')))
OVERLAY_ORDER = ('favorite', 'folder', 'pages')
OVERLAY_SIZES = ('large', 'medium', 'small')
SIZE_LABELS = dict(zip(OVERLAY_SIZES, ('크게', '보통', '작게')))
SIZE_SCALES = {'large': 1.0, 'medium': 2 / 3, 'small': 1 / 2}
PAGE_FONT_MIN = 4
PAGE_FONT_MAX = 72
PAGE_FONT_DEFAULT = 10
DEFAULT_OVERLAYS = {
    'favorite': {'visible': True, 'position': 'top_right', 'size': 'large'},
    'folder': {'visible': True, 'position': 'top_left', 'size': 'large'},
    'pages': {'visible': True, 'position': 'bottom_right', 'font_size': PAGE_FONT_DEFAULT,
              'text_color': '#FFFFFF', 'background_color': '#242830', 'background_alpha': 100},
}


def normalize_overlay_order(value=None):
    """Preserve known markers once each, appending any missing defaults."""
    result = []
    if isinstance(value, (list, tuple)):
        for kind in value:
            if isinstance(kind, str) and kind in OVERLAY_ORDER and kind not in result:
                result.append(kind)
    result.extend(kind for kind in OVERLAY_ORDER if kind not in result)
    return result


def normalize_overlay_settings(value=None, ui_font_size=10):
    """Fill missing or invalid saved values without sharing mutable defaults."""
    source = value if isinstance(value, dict) else {}
    result = {}
    for kind in OVERLAY_ORDER:
        default = DEFAULT_OVERLAYS[kind]
        saved = source.get(kind)
        saved = saved if isinstance(saved, dict) else {}
        visible = saved.get('visible', default['visible'])
        position = saved.get('position', default['position'])
        result[kind] = {
            'visible': visible if isinstance(visible, bool) else default['visible'],
            'position': position if position in OVERLAY_POSITIONS else default['position'],
        }
        if 'size' in default:
            size = saved.get('size', default['size'])
            result[kind]['size'] = size if size in OVERLAY_SIZES else default['size']
        if kind == 'pages':
            points = saved.get('font_size', PAGE_FONT_DEFAULT)
            if 'font_size' not in saved and saved.get('size') in OVERLAY_SIZES:
                try:
                    base = max(10, min(24, abs(int(ui_font_size))))
                except (TypeError, ValueError, OverflowError):
                    base = PAGE_FONT_DEFAULT
                points = int(base * SIZE_SCALES[saved['size']] + .5)
            result[kind]['font_size'] = (points if isinstance(points, int) and not isinstance(points, bool)
                                         and PAGE_FONT_MIN <= points <= PAGE_FONT_MAX else PAGE_FONT_DEFAULT)
            for key in ('text_color', 'background_color'):
                color = saved.get(key)
                result[kind][key] = (color.upper() if isinstance(color, str)
                                     and re.fullmatch(r'#[0-9a-fA-F]{6}', color) else default[key])
            alpha = saved.get('background_alpha', default['background_alpha'])
            result[kind]['background_alpha'] = (alpha if isinstance(alpha, int)
                                                and not isinstance(alpha, bool) and 0 <= alpha <= 100
                                                else default['background_alpha'])
    return result
