"""Small, theme-independent navigation icons, retained by the owning Tk app."""
from PIL import Image, ImageDraw, ImageTk


def navigation_icons(master, size=20):
    icons = {}
    scale = 4
    for kind in ('drive', 'folder', 'folder_open'):
        image = Image.new('RGBA', (size * scale, size * scale))
        draw = ImageDraw.Draw(image)
        def polygon(points, fill):
            draw.polygon([(round(x * size * scale / 20), round(y * size * scale / 20)) for x, y in points], fill=fill)
        if kind == 'drive':
            polygon([(2, 5), (15, 5), (18, 12), (1, 12)], '#cbd5e1')
            polygon([(1, 12), (18, 12), (18, 17), (1, 17)], '#64748b')
            polygon([(3, 13), (12, 13), (12, 14), (3, 14)], '#e2e8f0')
            polygon([(15, 13), (17, 13), (17, 15), (15, 15)], '#4ade80')
        else:
            polygon([(1, 4), (8, 4), (10, 6), (18, 6), (18, 17), (1, 17)], '#ce8d22')
            if kind == 'folder_open':
                polygon([(4, 9), (20, 9), (16, 17), (1, 17)], '#ffda72')
                polygon([(4, 9), (20, 9), (19, 10), (4, 10)], '#fff0b5')
            else:
                polygon([(1, 8), (18, 8), (18, 17), (1, 17)], '#f5c451')
                polygon([(1, 8), (18, 8), (18, 9), (1, 9)], '#ffe9a2')
        image = image.resize((size, size), Image.Resampling.LANCZOS)
        icons[kind] = ImageTk.PhotoImage(image, master=master)
    return icons
