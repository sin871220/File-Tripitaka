"""The packaged self-test must report failures without a console."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from runtime_check import main, _archive_checks


class RuntimeCheckTests(unittest.TestCase):
    def test_mixed_archive_sampling(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = {'checks': []}
            archive, jpeg = _archive_checks(Path(temporary), report)
            self.assertTrue(archive.is_file())
            self.assertTrue(jpeg.startswith(b'\xff\xd8'))
            self.assertEqual(len(report['checks']), 1)

    def test_report_contract_without_stdout(self):
        previous = os.environ.get('LOCALAPPDATA')
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / 'report.json'
            def check(directory, result):
                self.assertEqual(os.environ['LOCALAPPDATA'], str(directory))
                result['checks'].append('fixture')
            with patch('runtime_check._run_checks', side_effect=check), patch.object(sys, 'stdout', None):
                self.assertEqual(main(['--self-test', '--report', str(report)]), 0)
            result = json.loads(report.read_text('utf-8'))
            self.assertTrue(result['ok'])
            self.assertEqual(result['checks'], ['fixture'])
            self.assertTrue({'version', 'platform', 'arch'} <= result.keys())
        self.assertEqual(os.environ.get('LOCALAPPDATA'), previous)

    def test_failure_is_reported_and_nonzero(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / 'failure.json'
            with patch('runtime_check._run_checks', side_effect=RuntimeError('native decoder failed')):
                self.assertEqual(main(['--self-test', '--report', str(report)]), 1)
            result = json.loads(report.read_text('utf-8'))
            self.assertFalse(result['ok'])
            self.assertEqual(result['error'], 'native decoder failed')
            self.assertIn('RuntimeError', result['traceback'])


if __name__ == '__main__':
    unittest.main()
