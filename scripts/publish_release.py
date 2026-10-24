#!/usr/bin/env python3
"""Publish only a complete, checksum-verified three-platform release build."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

from build_release import ROOT, TARGETS, check_tag, identity


def release_assets(directory, version):
    expected = sorted(f'File-Tripitaka-v{version}-{label}.zip' for label in TARGETS.values())
    actual = sorted(item.name for item in directory.glob('*.zip'))
    if actual != expected:
        raise ValueError(f'Expected all three platform ZIPs: {expected}; received: {actual}')
    lines = []
    assets = []
    for name in expected:
        archive = directory / name
        sidecar = archive.with_suffix('.zip.sha256')
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        expected_line = f'{digest}  {name}'
        if not sidecar.is_file() or sidecar.read_text(encoding='ascii').strip() != expected_line:
            raise ValueError(f'Missing or incorrect SHA-256 checksum: {name}')
        lines.append(expected_line)
        assets.append(archive)
    checksums = directory / 'SHA256SUMS.txt'
    checksums.write_text('\n'.join(lines) + '\n', encoding='ascii')
    return assets + [checksums]


def main():
    version, _ = identity()
    tag = os.environ['FILETRIPITAKA_RELEASE_TAG']
    check_tag(version, tag)
    prerelease = '-beta.' in version
    release_flags = [f'--prerelease={str(prerelease).lower()}',
                     f'--latest={str(not prerelease).lower()}']
    repository = os.environ['GITHUB_REPOSITORY']
    if not os.environ.get('GH_TOKEN'):
        raise ValueError('The publishing job requires its repository-scoped GITHUB_TOKEN.')
    notes = ROOT / 'RELEASE-NOTES.md'
    if not notes.is_file():
        notes = ROOT / 'BETA-RELEASE.md'
    if not notes.is_file():
        raise FileNotFoundError('Release notes are required before publishing.')
    assets = release_assets(ROOT / 'dist' / 'releases', version)
    base = ['gh', 'release']
    common = ['--repo', repository]
    existing = subprocess.run(base + ['view', tag, *common, '--json', 'isDraft,isPrerelease'],
                              capture_output=True, text=True, check=False)
    title = f'File Tripitaka v{version}'
    if existing.returncode == 0:
        state = json.loads(existing.stdout)
        if not state['isDraft']:
            # Published packages remain immutable. A rerun is a verification,
            # rather than silently replacing executables downloaded by users.
            raise RuntimeError('This release is already published. Use a new version/tag.')
    else:
        subprocess.run(base + ['create', tag, *common, '--draft', '--verify-tag', *release_flags,
                              '--title', title, '--notes-file', str(notes)], check=True)
    subprocess.run(base + ['upload', tag, *common, *map(str, assets), '--clobber'], check=True)
    subprocess.run(base + ['edit', tag, *common, '--draft=false', *release_flags,
                          '--title', title, '--notes-file', str(notes)], check=True)
    subprocess.run(base + ['view', tag, *common, '--json', 'url,isPrerelease,assets'], check=True)


if __name__ == '__main__':
    main()
