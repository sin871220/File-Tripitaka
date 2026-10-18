"""Offline, isolated smoke checks for source and packaged desktop builds.

Run ``FileManDaejanggyeong --self-test --report report.json``. The JSON report
is the contract used by release builds; a windowed executable needs no console.
No viewer is launched, and all app settings, archives and cache live in a
TemporaryDirectory rather than in the current user's library.
"""
import argparse
import io
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import traceback
import zipfile


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _archive_checks(directory, report):
    from PIL import Image
    from archive_core import cover, image_entries, preview_indices

    library = directory / 'library'
    library.mkdir()
    archive = library / '미리보기-画像.zip'
    colors = [(220, 42, 50), (42, 170, 70), (40, 75, 215),
              (225, 170, 35), (170, 50, 195), (35, 180, 185),
              (160, 90, 40), (100, 120, 190), (190, 100, 145)]
    jpeg_data = None
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as target:
        for index, color in enumerate(colors):
            kind, extension = (('PNG', 'png'), ('JPEG', 'jpg'), ('WEBP', 'webp'))[index % 3]
            output = io.BytesIO()
            image = Image.new('RGB', (96, 144), color)
            image.save(output, format=kind, **({'lossless': True} if kind == 'WEBP' else {}))
            data = output.getvalue()
            target.writestr(f'画像{index + 1:02d}.{extension}', data)
            if kind == 'JPEG' and jpeg_data is None:
                jpeg_data = data
    _require(len(image_entries(archive)) == 9, 'Mixed-format archive listing failed')
    cache = directory / 'cache'
    for sampling in ('순차 보기', '비율 보기'):
        for count in (1, 2, 3):
            result = cover(archive, cache, count, sampling)
            indices = preview_indices(len(colors), count, sampling)
            _require(result.height == 144 and result.width >= 96 * count,
                     f'Unexpected {count}-page thumbnail dimensions: {result.size}')
            gap = 0 if count == 1 else (result.width - 96 * count) // (count - 1)
            for position, index in enumerate(reversed(indices)):
                actual = result.getpixel((position * (96 + gap) + 48, 72))[:3]
                _require(max(abs(a - b) for a, b in zip(actual, colors[index])) <= 5,
                         f'Incorrect {count}-page thumbnail sample or order')
            cached = cover(archive, cache, count, sampling)
            _require(cached.size == result.size and cached.tobytes() == result.tobytes(),
                     'Cached thumbnail does not match original')
    report['checks'].append('mixed_png_jpeg_webp_archive_and_cached_1_2_3_page_sampling')
    return archive, jpeg_data


def _native_checks(jpeg_data, report):
    import pyvips
    from large_thumbnail import thumbnail

    # Call the isolated decoder directly: even this small fixture must exercise
    # the packaged worker entry point and its native libvips dependency loader.
    reduced = thumbnail(jpeg_data)
    _require(reduced.mode == 'RGB' and reduced.width > 0 and reduced.height > 0,
             'Native worker did not produce an RGB thumbnail')
    _require(reduced.width <= 320 and reduced.height <= 340,
             'Native worker did not honor thumbnail bounds')
    report['libvips'] = '.'.join(str(pyvips.version(i)) for i in range(3))
    report['checks'].append('native_libvips_loader_and_isolated_thumbnail_worker')


def _cancel_callbacks(app):
    for identifier in app.tk.call('after', 'info'):
        app.after_cancel(identifier)


def _gui_checks(archive, directory, report):
    settings = directory / 'ArchiveShelf' / 'settings.json'
    settings.parent.mkdir(exist_ok=True)
    settings.write_text(json.dumps({'folder': str(archive.parent), 'language': 'ko'}), 'utf-8')
    # Explicit imports also let PyInstaller discover App and all its dependencies.
    from app import App
    import app as app_module
    from brand import APP_NAME, APP_VERSION
    from viewer import available_actions, default_action

    report['version'] = APP_VERSION
    application = None
    errors = []
    blocked_dialogs = {}

    def block_dialog(*args, **kwargs):
        raise RuntimeError('Self-test attempted to open a message dialog: ' + str(args[:2]))

    try:
        for name in ('showinfo', 'showerror', 'showwarning', 'askyesno', 'askokcancel'):
            blocked_dialogs[name] = getattr(app_module.messagebox, name)
            setattr(app_module.messagebox, name, block_dialog)
        application = App()
        application.withdraw()
        application.report_callback_exception = lambda *exc: errors.append(''.join(traceback.format_exception(*exc)))
        _require(application.settings['double_click'] == default_action(),
                 'Double-click default is not appropriate for this platform')
        _require(application.settings['double_click'] in available_actions(),
                 'Double-click default is not an available platform action')
        for key in ('enter_action', 'space_action'):
            _require(application.settings[key] == default_action(),
                     f'{key} default differs from the platform default')
        report['checks'].append('platform_specific_action_defaults')
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            application.update()
            if errors:
                raise RuntimeError(errors[0])
            if application.files == [archive] and application.photos and not application.active:
                break
            time.sleep(.02)
        _require(application.files == [archive] and application.photos,
                 'GUI did not scan and render its temporary archive within 15 seconds')
        _require(not application.preview_errors, 'GUI reported a preview error')
        report['tk'] = application.tk.call('info', 'patchlevel')
        report['checks'].append('tk_app_creation_archive_scan_and_thumbnail_render')
        application.select_card(archive)
        cards = dict(application.cards)
        scroll = application.canvas.yview()
        from shortcuts import command_for_key, validate
        _require(command_for_key(application.settings['shortcuts'], 'Enter') ==
                 ('reveal' if sys.platform == 'darwin' else 'viewer'), 'Legacy Enter default did not migrate')
        original_shortcuts = application.settings['shortcuts']
        double_click = application.settings['double_click']
        custom_shortcuts = {command: list(keys) for command, keys in original_shortcuts.items()}
        custom_shortcuts['favorite'] = ['F8']
        application.settings['shortcuts'] = validate(custom_shortcuts)
        application.refresh_shortcuts()
        application.activate_command(command_for_key(application.settings['shortcuts'], 'F8'))
        _require(str(archive) in application.favorites, 'Assigned favorite shortcut did not run')
        application.activate_command('favorite')
        _require(str(archive) not in application.favorites, 'Assigned favorite shortcut did not toggle off')
        _require(application.settings['double_click'] == double_click, 'Shortcut change altered double-click')
        _require(application.cards == cards and application.canvas.yview() == scroll,
                 'Shortcut action changed unrelated cards or scroll')
        application.settings['shortcuts'] = original_shortcuts
        application.refresh_shortcuts()
        report['checks'].append('function_shortcuts_dispatch_and_independent_double_click')
        for language, title, tab in (('en', 'File Tripitaka', 'All'), ('ko', APP_NAME, '전체')):
            application.settings['language'] = language
            application.apply_language()
            application.update_idletasks()
            _require(application.title() == f'{title} v{APP_VERSION}',
                     f'{language} application title was not localized')
            _require(application.tabs.tab(0, 'text') == tab,
                     f'{language} tab was not localized')
            _require(application.selected_path == archive and application.cards == cards,
                     'Language switch changed card identity or selection')
            _require(application.canvas.yview() == scroll, 'Language switch changed scroll position')
        _require(not errors, 'GUI callback failed: ' + '\n'.join(errors))
        report['checks'].append('english_korean_switch_preserves_cards_selection_and_scroll')
    finally:
        if application is not None:
            # Settle worker threads before removing their temporary files; cancel
            # Tk timers before destroying the root to avoid post-destroy callbacks.
            application.pending.clear()
            application.pool.shutdown(wait=True, cancel_futures=True)
            application.folder_pool.shutdown(wait=True, cancel_futures=True)
            _cancel_callbacks(application)
            application.close()
        for name, original in blocked_dialogs.items():
            setattr(app_module.messagebox, name, original)
    report['checks'].append('clean_gui_and_worker_shutdown')


def _run_checks(directory, report):
    from file_operations import _send2trash, rename_archive, FileOperationError
    _require(_send2trash is not None, 'Native Trash/Recycle Bin support is missing from this build')
    source = directory / 'rename-검사.ZIP'
    source.write_bytes(b'isolated rename fixture')
    renamed = rename_archive(source, 'renamed-画像')
    _require(renamed.name == 'renamed-画像.ZIP' and not source.exists()
             and renamed.read_bytes() == b'isolated rename fixture', 'Archive rename failed')
    source.write_bytes(b'collision fixture')
    try:
        rename_archive(source, 'renamed-画像')
    except FileOperationError as error:
        _require(error.code == 'exists', 'Incorrect rename collision error')
    else:
        raise RuntimeError('Archive rename replaced an existing file')
    _require(renamed.read_bytes() == b'isolated rename fixture', 'Rename collision changed the destination')
    report['checks'].append('native_trash_backend_import_and_no_replace_archive_rename')
    archive, jpeg_data = _archive_checks(directory, report)
    _native_checks(jpeg_data, report)
    _gui_checks(archive, directory, report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args(argv)
    from brand import APP_VERSION
    report = dict(ok=False, status='failed', version=APP_VERSION,
                  platform=sys.platform, arch=platform.machine(), checks=[])
    previous_environment = os.environ.get('LOCALAPPDATA')
    previous_exception_hook = sys.excepthook
    root_logger = __import__('logging').getLogger()
    previous_handlers = set(root_logger.handlers)
    with tempfile.TemporaryDirectory(prefix='file-tripitaka-self-test-') as temporary:
        directory = Path(temporary).resolve()
        os.environ['LOCALAPPDATA'] = str(directory)
        try:
            _run_checks(directory, report)
            report.update(ok=True, status='passed')
        except Exception as exc:
            report.update(error=str(exc), traceback=traceback.format_exc())
        finally:
            sys.excepthook = previous_exception_hook
            if previous_environment is None:
                os.environ.pop('LOCALAPPDATA', None)
            else:
                os.environ['LOCALAPPDATA'] = previous_environment
            # app.py opens fault/log files at import; release the handles before
            # TemporaryDirectory cleanup, particularly on Windows.
            loaded_app = sys.modules.get('app')
            if loaded_app is not None and hasattr(loaded_app, 'FAULT_LOG'):
                __import__('faulthandler').disable()
                loaded_app.FAULT_LOG.close()
            for handler in list(root_logger.handlers):
                if handler not in previous_handlers:
                    handler.close()
                    root_logger.removeHandler(handler)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
