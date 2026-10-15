"""Isolated streaming thumbnail decoder; also used by the frozen EXE."""
import os
import sys


def main():
    os.environ['VIPS_CONCURRENCY'] = '1'
    import pyvips
    pyvips.cache_set_max(0)
    pyvips.cache_set_max_mem(16 * 1024 * 1024)
    try:
        image = pyvips.Image.thumbnail(sys.argv[-2], 320, height=340, size='down')
        image.pngsave(sys.argv[-1])
    except Exception as exc:
        sys.stderr.write(str(exc)[:2000])
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
