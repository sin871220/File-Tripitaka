import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from PIL import Image
from large_thumbnail import thumbnail, RSS_LIMIT
from thumbnail_worker import main as worker_main


class DecoderLimits(unittest.TestCase):
    def run_limit(self, memory, times, message):
        process = Mock()
        process.pid = 123
        process.poll.return_value = None
        watcher = Mock()
        watcher.memory_info.return_value.rss = memory
        with patch('large_thumbnail.subprocess.Popen', return_value=process), \
             patch('large_thumbnail.psutil.Process', return_value=watcher), \
             patch('large_thumbnail.time.monotonic', side_effect=times):
            with self.assertRaisesRegex(ValueError, message):
                thumbnail(b'test')
        process.kill.assert_called_once()
        process.wait.assert_called_once()

    def test_memory_excess_kills_decoder(self):
        self.run_limit(RSS_LIMIT + 1, [0, 1], '512MB')

    def test_timeout_kills_decoder(self):
        self.run_limit(0, [0, 46], '45초')

    def test_preview_size_and_crop_are_sent_to_both_worker_entry_points(self):
        for frozen in (False, True):
            captured = []

            def start(arguments, **unused):
                captured.extend(arguments)
                Image.new('RGB', (50, 70), 'blue').save(Path(arguments[3]), 'PNG')
                process = Mock(pid=123, returncode=0)
                process.poll.return_value = 0
                return process

            with self.subTest(frozen=frozen), \
                    patch('large_thumbnail.sys.frozen', frozen, create=True), \
                    patch('large_thumbnail.subprocess.Popen', side_effect=start), \
                    patch('large_thumbnail.psutil.Process'):
                result = thumbnail(b'test', (800, 700), (.1, .2, .8, .9))
                self.assertEqual(result.size, (50, 70))
                self.assertEqual(captured[captured.index('--width') + 1], '800')
                self.assertEqual(captured[captured.index('--height') + 1], '700')
                self.assertIn('--crop', captured)
                self.assertEqual('--thumbnail-worker' in captured, frozen)

    def test_invalid_preview_options_do_not_spawn_a_process(self):
        with patch('large_thumbnail.subprocess.Popen') as start:
            with self.assertRaises(ValueError):
                thumbnail(b'test', (999999, 10))
            with self.assertRaises(ValueError):
                thumbnail(b'test', box=(0, 0, float('nan'), 1))
        start.assert_not_called()


class WorkerArguments(unittest.TestCase):
    def test_old_positional_paths_and_frozen_prefix_are_accepted(self):
        for prefix in ([], ['--thumbnail-worker']):
            vips = Mock()
            with self.subTest(prefix=prefix), patch.dict('sys.modules', {'pyvips': vips}):
                self.assertEqual(worker_main(prefix + ['input.image', 'thumbnail.png']), 0)
            vips.Image.thumbnail.assert_called_once_with('input.image', 320, height=340,
                                                        size='down', auto_rotate=True)
            vips.Image.thumbnail.return_value.pngsave.assert_called_once_with('thumbnail.png', strip=True)

    def test_crop_uses_oriented_original_before_thumbnail(self):
        vips = Mock()
        oriented = vips.Image.new_from_file.return_value.autorot.return_value
        oriented.width, oriented.height = 100, 200
        with patch.dict('sys.modules', {'pyvips': vips}):
            status = worker_main(['in.jpg', 'out.png', '--width', '800', '--height', '600',
                                  '--crop', '.25,.25,.75,.75'])
        self.assertEqual(status, 0)
        oriented.crop.assert_called_once_with(25, 50, 50, 100)
        oriented.crop.return_value.thumbnail_image.assert_called_once_with(800, height=600, size='down')
        vips.Image.thumbnail.assert_not_called()

    def test_invalid_sizes_or_crop_fail_before_native_decoder(self):
        for arguments in [ ['--width', '0'], ['--height', '1000000'],
                           ['--crop', '0,0,1,NaN'], ['--crop', '0,1,0,1'],
                           ['--crop', 'broken'] ]:
            vips = Mock()
            with self.subTest(arguments=arguments), \
                    patch.dict('sys.modules', {'pyvips': vips}), patch('sys.stderr'):
                self.assertEqual(worker_main(['in.jpg', 'out.png'] + arguments), 1)
            vips.Image.new_from_file.assert_not_called()
            vips.Image.thumbnail.assert_not_called()
