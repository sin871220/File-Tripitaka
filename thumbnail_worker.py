"""Isolated streaming thumbnail decoder; also used by the frozen EXE."""
import os
import sys
import argparse


def main(argv=None):
    # The frozen executable enters here with --thumbnail-worker still present.
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == '--thumbnail-worker':
        arguments.pop(0)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('target')
    parser.add_argument('--width', type=int, default=320)
    parser.add_argument('--height', type=int, default=340)
    parser.add_argument('--crop', help='Normalized left,top,right,bottom coordinates')
    options = parser.parse_args(arguments)
    os.environ['VIPS_CONCURRENCY'] = '1'
    try:
        from large_thumbnail import validate_options, crop_pixels
        size, box = validate_options((options.width, options.height),
                                     [float(value) for value in options.crop.split(',')]
                                     if options.crop is not None else None)
        import pyvips
        pyvips.cache_set_max(0)
        pyvips.cache_set_max_mem(16 * 1024 * 1024)
        if box is None:
            image = pyvips.Image.thumbnail(options.source, size[0], height=size[1],
                                          size='down', auto_rotate=True)
        else:
            source = pyvips.Image.new_from_file(options.source, access='sequential').autorot()
            left, top, right, bottom = crop_pixels(source.width, source.height, box)
            source = source.crop(left, top, right - left, bottom - top)
            image = source.thumbnail_image(size[0], height=size[1], size='down')
        # Strip metadata: an already oriented bitmap must not rotate a second time.
        image.pngsave(options.target, strip=True)
    except Exception as exc:
        sys.stderr.write(str(exc)[:2000])
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
