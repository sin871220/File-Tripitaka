#!/usr/bin/env python3
"""Make one movable Windows source-test ZIP, with no machine-specific launcher."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

try:
    from .build_release import identity
except ImportError:
    from build_release import identity

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ('app.py', 'brand.py', 'archive_core.py', 'preferences.py', 'localization.py',
            'viewer.py', 'windows_shell.py', 'file_operations.py', 'shortcuts.py',
            'runtime_check.py', 'thumbnail_worker.py', 'large_thumbnail.py',
            'thumbnail_editor.py', 'thumbnail_edits.py',
            'desktop_shortcuts.py', 'tree_icons.py', 'ui_fonts.py', 'dialog_geometry.py',
            'run-windows.bat', 'requirements.txt', 'assets/app.ico', 'assets/app.png',
            'fonts/NotoSansCJKkr-Regular.otf', 'fonts/OFL.txt', 'fonts/SOURCE.txt')


def package(root=ROOT, output=None):
    root = Path(root)
    version, _ = identity(root)
    stem = f'File-Tripitaka-v{version}-Windows-Test'
    output = Path(output) if output is not None else root / 'dist' / 'releases' / (stem + '.zip')
    for relative in REQUIRED:
        if not (root / relative).is_file():
            raise FileNotFoundError(f'Missing Windows test package file: {relative}')
    # Include new runtime modules even before they have been committed to Git.
    files = sorted(set(REQUIRED) | {path.name for path in root.glob('*.py') if path.is_file()})
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix='.zip', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        hashes = {}
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for relative in files:
                source = root / relative
                if source.is_symlink():
                    raise ValueError(f'Symlink cannot be included in the test package: {relative}')
                data = source.read_bytes()
                if source.suffix == '.bat':
                    data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
                hashes[relative] = hashlib.sha256(data).hexdigest()
                info = zipfile.ZipInfo.from_file(source, stem + '/' + relative)
                info.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(info, data)
            bundle.writestr(stem + '/PACKAGE-INFO.json', json.dumps(
                dict(version=version, kind='windows-source-test', files=hashes),
                ensure_ascii=False, indent=2) + '\n')
            bundle.writestr(stem + '/실행방법.txt', f'''파일만대장경 v{version} — Windows 테스트용

1. 이 ZIP 하나를 Windows 컴퓨터로 옮기세요.
2. 새 폴더에 압축을 전부 푸세요. 예전 버전 폴더에 덮어 풀지 마세요.
3. 압축을 푼 폴더 안의 run-windows.bat을 실행하세요.
4. 제목 표시줄의 v{version}을 확인하세요.

썸네일 편집기
- 편집기는 자유 비율로 시작합니다. '썸네일 비율 (127:180)'을 선택하면 1270×1800 비율로 고정합니다.
- 파일을 선택한 뒤 썸네일 크기·창에 맞춤·미리보기와 같은 줄 오른쪽의 '썸네일 영역 편집' 버튼으로도 열 수 있습니다.
- Windows에서 정상 파일을 변경된 파일로 오인해 저장하지 못하던 문제를 수정했습니다.
- 적용·복원한 썸네일은 일반 탐색용 작업 대기열과 별도로 갱신합니다.
- 파일을 오른쪽 클릭하고 '썸네일 영역 편집'을 여세요.
- 압축파일 안의 이미지를 고르고 드래그로 영역을 지정한 뒤 '적용'을 누르세요.
- 2장·3장 보기에서는 썸네일 위치를 바꿔 각각 따로 편집할 수 있습니다. 1번은 오른쪽입니다.
- '자동 썸네일로 복원'은 현재 위치에 저장한 편집만 지웁니다.
- 압축파일과 원본 이미지는 변경하지 않습니다.
- 파일 이름을 바꾸거나 이동해도 내용이 같으면 편집이 복원됩니다.
- 압축파일 내용을 바꾸거나 다시 압축하면 새 파일로 인식할 수 있습니다.
- 편집 정보는 LOCALAPPDATA/ArchiveShelf/thumbnail_edits.json에 저장됩니다.
  다른 컴퓨터에서도 편집을 유지하려면 앱을 종료하고 이 파일도 같은 설정 위치로 옮겨 주세요.

폴더를 통째로 옮기거나 폴더 이름을 바꿔도 그 안의 배치로 실행합니다.
Mac의 완료 폴더 경로나 외부의 '최신 버전' 배치는 사용하지 않습니다.
예전 EXE를 실행하면 예전 버전이 열립니다. 이 묶음은 소스로 실행하는 테스트본입니다.

Windows용 Python 3.12 이상이 필요합니다. 첫 실행 시 필요한 라이브러리를 설치합니다.
.venv는 ZIP에 포함하지 않으며 실행한 Windows에서 준비합니다.
이름 변경·휴지통 삭제·기능별 단축키 설정과 대화상자 중앙 배치가 포함되어 있습니다.
이름 변경창 위쪽의 원래 파일명은 드래그하여 선택한 뒤 Ctrl+C로 복사할 수 있습니다. 원래 이름 표시는 읽기 전용입니다.
이름 변경창은 크기를 조절할 수 있고, 원래 파일명은 창 너비에 맞춰 줄바꿈합니다. 입력칸·버튼이 가려지지 않도록 최소 크기가 적용됩니다.
이름 변경창의 처음 너비는 원래 파일명이 한 줄에 들어가도록 자동으로 맞춥니다. 화면 너비를 넘는 이름만 줄바꿈합니다.
설정 → 단축키에서 폴더 패널 접기/펴기와 창에 맞춤 ON/OFF도 지정할 수 있습니다. 두 기능의 기본 키는 미할당입니다.
두 화면 전환 키는 폴더 탐색·버튼 등에서도 바로 쓸 수 있으며, 입력창·설정창에서는 동작하지 않습니다.
설정과 즐겨찾기는 Windows의 기존 LOCALAPPDATA/ArchiveShelf 위치를 유지합니다.
''')
        with zipfile.ZipFile(temporary) as bundle:
            if bundle.testzip() is not None:
                raise ValueError('The test ZIP is damaged.')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    output.with_suffix('.zip.sha256').write_text(
        f'{hashlib.sha256(output.read_bytes()).hexdigest()}  {output.name}\n', encoding='ascii')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(package(output=args.output))
