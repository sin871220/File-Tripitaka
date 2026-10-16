import ast
import hashlib
import importlib.util
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import build_release
import publish_release


class ReleasePackagingTests(unittest.TestCase):
    def test_no_cross_architecture_or_version_mislabeling(self):
        with patch.object(build_release.sys, 'platform', 'darwin'), \
             patch.object(build_release.platform, 'machine', return_value='arm64'):
            self.assertEqual(build_release.native_target('macos', 'arm64'), ('macos', 'arm64'))
            with self.assertRaises(ValueError):
                build_release.native_target('macos', 'x86_64')
            with self.assertRaises(ValueError):
                build_release.native_target('windows', 'x64')
        build_release.check_tag('1.2.0-beta.1', 'v1.2.0-beta.1')
        with self.assertRaises(ValueError):
            build_release.check_tag('1.2.0-beta.1', 'v1.1.0')

    def test_mac_spec_preserves_worker_arguments_and_beta_bundle_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            spec = Path(temporary) / 'app.spec'
            build_release.mac_spec('1.2.0-beta.1', 'arm64', Path(temporary) / 'app.icns', spec)
            code = spec.read_text(encoding='utf-8')
            ast.parse(code)
            self.assertIn("CFBundleShortVersionString': '1.2.0'", code)
            self.assertIn("CFBundleVersion': '1.2.0b1'", code)
            self.assertIn('argv_emulation=False', code)
            self.assertIn('codesign_identity=None', code)

    def test_publication_requires_three_matching_platform_checksums(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for label in build_release.TARGETS.values():
                archive = directory / f'File-Tripitaka-v1.2.0-beta.1-{label}.zip'
                archive.write_bytes(label.encode())
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
            assets = publish_release.release_assets(directory, '1.2.0-beta.1')
            self.assertEqual(len(assets), 4)
            self.assertEqual(len((directory / 'SHA256SUMS.txt').read_text().splitlines()), 3)
            assets[0].write_bytes(b'changed-after-checksum')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                publish_release.release_assets(directory, '1.2.0-beta.1')
            assets[0].unlink()
            with self.assertRaisesRegex(ValueError, 'all three'):
                publish_release.release_assets(directory, '1.2.0-beta.1')

    @unittest.skipUnless(sys.platform == 'darwin', 'ditto is provided by macOS')
    def test_mac_zip_preserves_executable_permission_and_framework_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            payload = directory / 'Package'
            executable = payload / 'File Tripitaka.app' / 'Contents' / 'MacOS' / 'File Tripitaka'
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b'native-test-fixture')
            executable.chmod(0o755)
            (executable.parent / 'worker-link').symlink_to(executable.name)
            archive = directory / 'package.zip'
            build_release.write_zip(payload, archive, 'macos')
            with zipfile.ZipFile(archive) as bundle:
                saved = bundle.getinfo(executable.relative_to(directory).as_posix())
                self.assertTrue(saved.external_attr >> 16 & stat.S_IXUSR)
                link = bundle.getinfo((executable.parent / 'worker-link').relative_to(directory).as_posix())
                self.assertTrue(stat.S_ISLNK(link.external_attr >> 16))
                self.assertEqual(bundle.read(link).decode(), executable.name)


if __name__ == '__main__':
    unittest.main()
