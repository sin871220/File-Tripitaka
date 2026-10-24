"""Stable settings for the optional markers drawn over thumbnail groups."""

OVERLAY_POSITIONS = ('top_left', 'top_right', 'bottom_left', 'bottom_right')
POSITION_LABELS = dict(zip(OVERLAY_POSITIONS,
                          ('왼쪽 위', '오른쪽 위', '왼쪽 아래', '오른쪽 아래')))
OVERLAY_ORDER = ('favorite', 'folder', 'pages')
OVERLAY_SIZES = ('large', 'medium', 'small')
SIZE_LABELS = dict(zip(OVERLAY_SIZES, ('크게', '보통', '작게')))
SIZE_SCALES = {'large': 1.0, 'medium': 2 / 3, 'small': 1 / 2}
DEFAULT_OVERLAYS = {
    'favorite': {'visible': True, 'position': 'top_right', 'size': 'large'},
    'folder': {'visible': True, 'position': 'top_left', 'size': 'large'},
    'pages': {'visible': True, 'position': 'bottom_right'},
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


def normalize_overlay_settings(value=None):
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
    return result
