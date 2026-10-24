#!/usr/bin/env python3
"""Build on the target OS, verify the frozen app, then package only release files."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import sysconfig
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MAC_NAME = 'File Tripitaka'
TARGETS = {('windows', 'x64'): 'Windows-x64',
           ('macos', 'arm64'): 'macOS-arm64',
           ('macos', 'x86_64'): 'macOS-x86_64'}


def identity(root=ROOT):
    """Read constants without importing the GUI or any runtime dependencies."""
    tree = ast.parse((root / 'brand.py').read_text(encoding='utf-8'))
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = node.value.value
    version = values['APP_VERSION']
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-beta\.\d+)?', version):
        raise ValueError(f'Unsupported release version: {version!r}')
    return version, values['EXE_NAME']


def check_tag(version, tag):
    if tag and tag != 'v' + version:
        raise ValueError(f'Tag {tag!r} does not match brand.py version v{version}')


def native_target(requested_platform=None, requested_arch=None):
    host = {'win32': 'windows', 'darwin': 'macos'}.get(sys.platform)
    machine = platform.machine().lower()
    arch = {'amd64': 'x64', 'x86_64': 'x64' if host == 'windows' else 'x86_64',
            'aarch64': 'arm64', 'arm64': 'arm64'}.get(machine, machine)
    target = requested_platform or host
    wanted = requested_arch or arch
    if (target, wanted) not in TARGETS:
        raise ValueError('Supported builds: Windows x64, macOS arm64, macOS x86_64.')
    if host != target or arch != wanted or struct.calcsize('P') != 8:
        raise ValueError(f'Use a native 64-bit {target}/{wanted} Python; '
                         f'this interpreter is {host}/{arch}.')
    return target, wanted


def run(args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), cwd=ROOT, check=True, **kwargs)


def make_icns(destination):
    from PIL import Image, ImageOps
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(ROOT / 'assets' / 'app.png') as source:
        # Format conversion only: keep the approved artwork and transparency.
        icon = ImageOps.pad(source.convert('RGBA'), (1024, 1024),
                            method=Image.Resampling.LANCZOS, color=(0, 0, 0, 0))
        icon.save(destination, format='ICNS')
    return destination


def windows_version(version, executable, destination):
    parts = tuple(map(int, version.split('-')[0].split('.'))) + (0,)
    strings = {'CompanyName': 'sin871220', 'FileDescription': 'File Tripitaka',
               'FileVersion': version, 'ProductName': 'File Tripitaka',
               'ProductVersion': version, 'OriginalFilename': executable + '.exe'}
    fields = ',\n'.join(f'StringStruct({key!r}, {value!r})' for key, value in strings.items())
    destination.write_text(
        f'VSVersionInfo(ffi=FixedFileInfo(filevers={parts!r}, prodvers={parts!r}, '
        'mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)), '
        "kids=[StringFileInfo([StringTable('040904B0', [" + fields +
        '])]), VarFileInfo([VarStruct(\'Translation\', [1033, 1200])])])\n', encoding='utf-8')


def mac_spec(version, arch, icon, destination):
    core_version = version.split('-')[0]
    build_version = version.replace('-beta.', 'b')
    info = dict(CFBundleDisplayName=MAC_NAME, CFBundleShortVersionString=core_version,
                CFBundleVersion=build_version, FileTripitakaVersion=version,
                LSMinimumSystemVersion='15.0', NSHighResolutionCapable=True)
    destination.write_text(f'''
a = Analysis([{str(ROOT / 'app.py')!r}], pathex=[{str(ROOT)!r}],
    binaries=[], datas=[({str(ROOT / 'fonts')!r}, 'fonts'), ({str(ROOT / 'assets')!r}, 'assets')],
    hiddenimports=[], hookspath=[{str(ROOT / 'hooks')!r}], runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name={MAC_NAME!r},
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    argv_emulation=False, target_arch={arch!r}, codesign_identity=None, entitlements_file=None)
collect = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name={MAC_NAME!r})
app = BUNDLE(collect, name={MAC_NAME + '.app'!r}, icon={str(icon)!r},
    bundle_identifier='io.github.sin871220.file-tripitaka', info_plist={info!r})
'''.lstrip(), encoding='utf-8')


def freeze(target, arch, version, executable, work):
    output = ROOT / 'dist' / 'frozen' / TARGETS[target, arch]
    common = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
              '--distpath', output, '--workpath', work / 'pyinstaller']
    if target == 'macos':
        spec = work / 'File-Tripitaka.spec'
        mac_spec(version, arch, make_icns(work / 'app.icns'), spec)
        run(common + [spec])
        artifact = output / (MAC_NAME + '.app')
        binary = artifact / 'Contents' / 'MacOS' / MAC_NAME
        run(['/usr/bin/lipo', binary, '-verify_arch', arch])
        run(['/usr/bin/codesign', '--verify', '--deep', '--strict', artifact])
        with (artifact / 'Contents' / 'Info.plist').open('rb') as stream:
            if plistlib.load(stream).get('FileTripitakaVersion') != version:
                raise ValueError('Built macOS bundle has the wrong version.')
    else:
        resource = work / 'windows-version.txt'
        windows_version(version, executable, resource)
        run(common + ['--onefile', '--windowed', '--noupx', '--name', executable,
                      '--icon', ROOT / 'assets' / 'app.ico', '--version-file', resource,
                      '--specpath', work, '--additional-hooks-dir', ROOT / 'hooks',
                      '--add-data', str(ROOT / 'fonts') + os.pathsep + 'fonts',
                      '--add-data', str(ROOT / 'assets') + os.pathsep + 'assets', ROOT / 'app.py'])
        artifact = binary = output / (executable + '.exe')
    if not binary.is_file():
        raise FileNotFoundError(f'The build did not produce {binary}')
    return artifact, binary


def frozen_check(binary, target):
    """The report proves a windowed process really ran, rather than merely launched."""
    with tempfile.TemporaryDirectory(prefix='file-tripitaka-check-') as temporary:
        report = Path(temporary) / 'report.json'
        if target == 'windows':
            environment = dict(os.environ, FILETRIPITAKA_CHECK_BINARY=str(binary),
                               FILETRIPITAKA_CHECK_REPORT=str(report))
            powershell = r'''
$ErrorActionPreference = 'Stop'
$arguments = @('--self-test', '--report', ('"' + $env:FILETRIPITAKA_CHECK_REPORT + '"'))
$process = Start-Process -FilePath $env:FILETRIPITAKA_CHECK_BINARY -ArgumentList $arguments -Wait -PassThru
exit $process.ExitCode
'''
            run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', powershell],
                env=environment, timeout=180)
        else:
            run([binary, '--self-test', '--report', report], timeout=180)
        if not report.is_file():
            raise RuntimeError('Frozen app did not produce its self-test report.')
        result = json.loads(report.read_text(encoding='utf-8'))
        if result.get('ok') is not True:
            raise RuntimeError(f'Frozen application check failed: {result}')
        print('Frozen application check passed.', flush=True)


def copy_notices(destination):
    destination.mkdir(parents=True, exist_ok=True)
    installed = {}
    for name in ('Pillow', 'pyvips', 'pyvips-binary', 'psutil', 'cffi', 'pycparser', 'PyInstaller', 'Send2Trash', 'pywin32'):
        try:
            package = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        installed[name] = package.version
        for entry in package.files or ():
            if any(word in entry.name.lower() for word in ('license', 'licence', 'copying', 'notice')):
                source = Path(package.locate_file(entry))
                if source.is_file():
                    # RECORD paths sometimes include '..'; retain only a safe relative layout.
                    relative = Path(*[part for part in entry.parts if part not in ('.', '..')])
                    target = destination / name / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    font_notice = ROOT / 'fonts' / 'OFL.txt'
    shutil.copy2(font_notice, destination / 'Noto-Sans-CJK-OFL.txt')
    # Some Python distributions omit Tcl/Tk license.terms beside their scripts.
    # Keep the notices for the Tcl/Tk versions shipped in this beta regardless.
    shutil.copytree(ROOT / 'third_party' / 'tcltk', destination / 'Tcl-Tk', dirs_exist_ok=True)
    python_candidates = [Path(sys.base_prefix) / 'LICENSE.txt',
                         Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt',
                         Path(sys.base_prefix) / 'Resources' / 'English.lproj' / 'License.rtf']
    for source in python_candidates:
        if source.is_file():
            shutil.copy2(source, destination / ('Python-' + source.name))
            break
    import tkinter
    library = Path(tkinter.Tcl().eval('info library'))
    for label, source in [('Tcl', library / 'license.terms'),
                          ('Tk', library.parent / library.name.replace('tcl', 'tk') / 'license.terms')]:
        if source.is_file():
            shutil.copy2(source, destination / (label + '-license.terms'))
    (destination / 'VERSIONS.json').write_text(json.dumps(installed, indent=2) + '\n', encoding='utf-8')
    return installed


def write_zip(source, archive, target):
    if target == 'macos':
        # ditto preserves .app symlinks, modes, and bundle metadata.
        run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', source, archive])
    else:
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for item in sorted(source.rglob('*')):
                if item.is_file():
                    bundle.write(item, item.relative_to(source.parent).as_posix())


def package_release(artifact, target, arch, version, work, output):
    stem = f'File-Tripitaka-v{version}-{TARGETS[target, arch]}'
    staging = work / stem
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    if artifact.is_dir():
        shutil.copytree(artifact, staging / artifact.name, symlinks=True)
    else:
        shutil.copy2(artifact, staging / artifact.name)
    for name in ('README.md', 'BETA-RELEASE.md', 'LICENSE', 'LICENSE.txt'):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, staging / name)
    for relative in ('assets/app.png', 'docs/images/library-overview.png'):
        source = ROOT / relative
        if source.is_file():
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    packages = copy_notices(staging / 'THIRD-PARTY')
    instructions = f'''File Tripitaka v{version} / 파일만대장경
{TARGETS[target, arch]}

Windows: Extract the ZIP and run {identity()[1]}.exe. Python is not required.
macOS: Extract the ZIP and drag File Tripitaka.app to Applications.
Use the arm64 build for Apple Silicon, or x86_64 for Intel Macs (macOS 15+).
This build has no verified publisher signature or Apple notarization.
Read BETA-RELEASE.md for release notes and execution requirements.
ZIP/CBZ work directly; RAR/7Z previews require a separate 7-Zip installation.
External image viewers are installed separately.

윈도우: 압축을 풀고 EXE를 실행하세요. Python 설치는 필요 없습니다.
맥: 압축을 풀고 File Tripitaka.app을 응용 프로그램으로 옮기세요.
Apple Silicon은 arm64, Intel Mac은 x86_64 버전을 사용하세요 (macOS 15 이상).
이 배포 파일은 배포자 서명·Apple 공증을 받지 않았습니다. BETA-RELEASE.md를 읽어 주세요.
RAR·7Z 미리보기용 7-Zip과 외부 뷰어는 별도 설치가 필요합니다.
'''
    (staging / 'START-HERE.txt').write_text(instructions, encoding='utf-8')
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                            capture_output=True, text=True, check=False)
    changes = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT,
                             capture_output=True, text=True, check=False)
    info = dict(version=version, target=TARGETS[target, arch],
                built_at=datetime.now(timezone.utc).isoformat(),
                source_commit=commit.stdout.strip() if commit.returncode == 0 else None,
                source_worktree_dirty=bool(changes.stdout.strip()) if changes.returncode == 0 else None,
                python=platform.python_version(), build_os=platform.platform(),
                dependencies=packages, frozen_self_test='passed',
                publisher_signed=False, apple_notarized=False)
    (staging / 'BUILD-INFO.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (stem + '.zip')
    write_zip(staging, archive, target)
    with zipfile.ZipFile(archive) as bundle:
        bad = bundle.testzip()
        if bad:
            raise ValueError(f'Damaged file in release ZIP: {bad}')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(f'Release ZIP: {archive}', flush=True)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=['windows', 'macos'])
    parser.add_argument('--arch', choices=['x64', 'x86_64', 'arm64'])
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist' / 'releases')
    parser.add_argument('--skip-tests', action='store_true', help='Skip source unit tests, never the frozen self-test.')
    args = parser.parse_args()
    target, arch = native_target(args.platform, args.arch)
    version, executable = identity()
    check_tag(version, os.environ.get('FILETRIPITAKA_RELEASE_TAG', ''))
    work = ROOT / 'build' / 'packaging' / TARGETS[target, arch]
    work.mkdir(parents=True, exist_ok=True)
    if not args.skip_tests:
        run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
        run([sys.executable, ROOT / 'tests' / 'file_actions_smoke.py'], timeout=300)
        run([sys.executable, ROOT / 'tests' / 'shortcuts_smoke.py'], timeout=300)
        run([sys.executable, ROOT / 'tests' / 'thumbnail_editor_smoke.py'], timeout=300)
        run([sys.executable, ROOT / 'tests' / 'scroll_smoke.py'], timeout=300)
        run([sys.executable, ROOT / 'tests' / 'wheel_routing_smoke.py'], timeout=300)
        run([sys.executable, ROOT / 'tests' / 'folder_gallery_smoke.py'], timeout=300)
        run([sys.executable, ROOT / 'tests' / 'gallery_card_smoke.py'], timeout=300)
    artifact, binary = freeze(target, arch, version, executable, work)
    frozen_check(binary, target)
    package_release(artifact, target, arch, version, work, args.output_dir.resolve())


if __name__ == '__main__':
    main()
