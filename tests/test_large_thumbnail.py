import unittest
from unittest.mock import Mock, patch
from large_thumbnail import thumbnail, RSS_LIMIT


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
