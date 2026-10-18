import ast
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
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
    @contextmanager
    def publication(self, version, existing=None):
        """Exercise the real asset gate while replacing all remote gh calls."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'dist' / 'releases'
            directory.mkdir(parents=True)
            (root / 'BETA-RELEASE.md').write_text('Release notes\n', encoding='utf-8')
            for label in build_release.TARGETS.values():
                archive = directory / f'File-Tripitaka-v{version}-{label}.zip'
                archive.write_bytes(label.encode())
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                archive.with_suffix('.zip.sha256').write_text(
                    f'{digest}  {archive.name}\n', encoding='ascii')
            lookup = subprocess.CompletedProcess(
                [], 1 if existing is None else 0,
                stdout='' if existing is None else json.dumps(existing), stderr='')
            responses = [lookup] + [subprocess.CompletedProcess([], 0)] * 4
            environment = {'FILETRIPITAKA_RELEASE_TAG': f'v{version}',
                           'GITHUB_REPOSITORY': 'example/File-Tripitaka',
                           'GH_TOKEN': 'mock-repository-token'}
            with patch.object(publish_release, 'ROOT', root), \
                 patch.object(publish_release, 'identity', return_value=(version, 'File Tripitaka')), \
                 patch.dict(publish_release.os.environ, environment), \
                 patch.object(publish_release.subprocess, 'run', side_effect=responses) as run:
                yield root, run

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

    def test_stable_publication_is_latest_and_not_a_prerelease(self):
        with self.publication('1.2.1') as (root, run):
            publish_release.main()
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual([command[2] for command in commands],
                             ['view', 'create', 'upload', 'edit', 'view'])
            for command in (commands[1], commands[3]):
                self.assertIn('--prerelease=false', command)
                self.assertIn('--latest=true', command)
                self.assertIn('File Tripitaka v1.2.1', command)
                self.assertIn(str(root / 'BETA-RELEASE.md'), command)
            self.assertIn('--draft', commands[1])
            self.assertIn('--verify-tag', commands[1])
            self.assertIn('--draft=false', commands[3])
            uploads = commands[2]
            for label in build_release.TARGETS.values():
                self.assertIn(str(root / 'dist' / 'releases' /
                                  f'File-Tripitaka-v1.2.1-{label}.zip'), uploads)
            self.assertIn(str(root / 'dist' / 'releases' / 'SHA256SUMS.txt'), uploads)

    def test_beta_publication_stays_prerelease_and_never_latest(self):
        with self.publication('1.2.2-beta.1') as (_, run):
            publish_release.main()
            commands = [call.args[0] for call in run.call_args_list]
            for command in (commands[1], commands[3]):
                self.assertIn('--prerelease=true', command)
                self.assertIn('--latest=false', command)
                self.assertNotIn('--latest=true', command)

    def test_draft_rerun_can_finish_a_stable_release(self):
        with self.publication('1.2.1', {'isDraft': True, 'isPrerelease': True}) as (_, run):
            publish_release.main()
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual([command[2] for command in commands],
                             ['view', 'upload', 'edit', 'view'])
            self.assertIn('--clobber', commands[1])
            self.assertIn('--prerelease=false', commands[2])
            self.assertIn('--latest=true', commands[2])

    def test_published_stable_and_beta_assets_are_never_overwritten(self):
        for version in ('1.2.1', '1.2.2-beta.1'):
            with self.subTest(version=version), \
                 self.publication(version, {'isDraft': False, 'isPrerelease': '-beta.' in version}) as (_, run):
                with self.assertRaisesRegex(RuntimeError, 'already published'):
                    publish_release.main()
                run.assert_called_once()
                self.assertEqual(run.call_args.args[0][2], 'view')

    def test_invalid_checksum_blocks_publication_before_any_remote_call(self):
        with self.publication('1.2.1') as (root, run):
            checksum = next((root / 'dist' / 'releases').glob('*.sha256'))
            checksum.write_text('incorrect\n', encoding='ascii')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                publish_release.main()
            run.assert_not_called()

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
