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
REQUIRED = ('app.py', 'brand.py', 'archive_core.py', 'library_items.py', 'preferences.py', 'localization.py',
            'viewer.py', 'windows_shell.py', 'file_operations.py', 'shortcuts.py',
            'runtime_check.py', 'thumbnail_worker.py', 'large_thumbnail.py',
            'thumbnail_editor.py', 'thumbnail_edits.py', 'thumbnail_overlays.py', 'smooth_scroll.py', 'gallery_card.py',
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

썸네일 위 표시 설정
- 설정 → 표시 설정 → 썸네일 위 표시에서 즐겨찾기 별 / 폴더 아이콘 / 페이지 수를 각각 표시하거나 숨기고 네 모서리 중 위치를 고르세요.
- 별·폴더 아이콘은 크게 / 보통(2/3) / 작게(1/2) 중 고릅니다. 페이지 수는 숫자로 글자 크기 4~72pt를 지정하며 기본값은 10pt입니다. 앱 전체 글자 크기와 독립적으로 저장하고, 미리보기와 실제 카드에 같은 크기를 적용합니다.
- 페이지 수는 글씨 색·배경색·배경 알파(0~100%)도 설정합니다. 알파 0%는 배경 완전 투명, 100%는 불투명입니다. 글씨는 별도 색으로 선명하게 표시합니다. 기본값은 흰 글씨·어두운 배경·알파 100%입니다.
- 손잡이나 항목 이름을 위아래로 드래그해 순서를 바꾸세요. 행을 클릭해 선택하고 위로 / 아래로 버튼을 사용해도 됩니다. 체크박스와 위치 드롭다운은 순서를 바꾸지 않습니다.
- 같은 위치에서는 목록의 위에서 아래 순서로 쌓입니다. 아래쪽도 묶음 전체를 아래에 맞춰 이 순서를 유지하며, 숨긴 표시는 빈칸을 남기지 않습니다.
- 기본값은 별 오른쪽 위, 폴더 왼쪽 위, 페이지 오른쪽 아래로 모두 표시합니다. 즐겨찾기 탭에서는 별이 숨겨집니다.
- 페이지 수는 지원 이미지 전체 개수이며 폴더는 바로 안의 이미지 개수입니다. 2장·3장 보기에서도 그룹당 하나만 표시하고, 확인할 수 없는 개수는 표시하지 않습니다.
- 설정 미리보기와 표시 기본값 복원을 사용할 수 있습니다. 기본값 복원은 순서를 별 → 폴더 → 페이지로, 아이콘 크기를 크게로, 페이지 글자 크기를 10pt로, 색과 배경 알파도 기본값으로 돌립니다. 적용하면 카드와 스크롤 위치를 유지하며 바로 바뀌고 다시 실행해도 설정을 기억합니다.

정렬 표시와 그룹 배치
- 정렬 목록은 이름 / 수정 날짜 / 용량 각각 ▲·▼로 표시합니다. ▲는 작은 값부터, ▼는 큰 값부터입니다. 날짜는 ▲가 오래된 순, ▼가 최신 순입니다.
- 용량은 카드에 표시하는 용량입니다. 폴더는 바로 안의 이미지 용량 합계입니다.
- 페이지 수 정렬과 전체 목록의 페이지 수를 계산하는 작업은 제거했습니다. 이전에 저장한 페이지 수 정렬은 이름 ▲로 전환합니다. 썸네일의 페이지 수 표시는 그대로 사용할 수 있습니다.
- 배치는 섞어서 / 폴더 먼저 / 파일 먼저 중에서 고르세요. 기본값은 섞어서입니다.
- 그룹 순서는 ▲·▼를 바꿔도 그대로 유지하고, 각 그룹 안에서 선택한 이름·날짜와 방향대로 정렬합니다.
- 종류가 압축파일만 또는 폴더만이면 배치 선택은 비활성화됩니다. 전체로 돌아오면 선택했던 배치를 유지합니다.
- 배치와 정렬은 전체·즐겨찾기 탭별로 기억하고 다시 실행해도 유지합니다. 기존 정렬 설정도 그대로 가져옵니다.

이미지 폴더 썸네일
- 폴더를 선택하면 압축파일과 이미지가 직접 들어 있는 폴더를 함께 모아 보여줍니다. 하위 폴더 포함 옵션이 켜져 있으면 하위 폴더도 탐색합니다.
- 상단의 종류에서 전체 / 압축파일 / 폴더를 선택하세요. 검색과 정렬을 함께 사용할 수 있고 탭별 필터와 스크롤 위치를 기억합니다.
- 폴더 카드 왼쪽 위의 작은 폴더 표시로 구분합니다. 1장·2장·3장 미리보기와 순차·비율 보기 모두 지원합니다.
- 카드의 폴더 즐겨찾기는 기존 파일 즐겨찾기와 함께 즐겨찾기 탭에서 볼 수 있습니다. 왼쪽의 즐겨찾는 탐색 폴더 목록과는 별개입니다.
- 폴더도 썸네일 영역 편집 버튼·우클릭·지정한 단축키로 이미지와 영역을 고르고 적용·복원할 수 있습니다. 원본 이미지는 변경하지 않습니다.
- 폴더 이름·위치가 바뀌어도 내부 이미지 이름과 내용이 같으면 편집이 복원됩니다. 이미지 추가·삭제·이름·내용 변경 시에는 새 구성으로 인식합니다.
- 뷰어 열기 동작은 폴더 안의 대표 이미지(편집한 1번 이미지 또는 첫 이미지)를 엽니다. 파일 위치 열기는 해당 폴더를 엽니다.
- 폴더 용량 표시는 바로 안의 이미지 파일 용량 합계입니다. 하위 폴더와 다른 종류 파일은 합산하지 않습니다.
- 폴더 카드의 이름 변경·휴지통 이동은 비활성화되어 있습니다. 기존 압축파일의 이름 변경·삭제는 그대로 사용할 수 있습니다.

썸네일 영역 편집 단축키
- 설정 → 단축키에 '썸네일 영역 편집'을 추가했습니다. 기본값은 미할당이며 키를 두 개까지 지정할 수 있습니다.
- 기존 단축키·Enter·Space·더블클릭 설정은 유지합니다. 중복 키 안내와 기본값 복원도 적용됩니다.
- 파일을 선택하고 썸네일 영역에서 지정한 키를 누르면 기존 편집기가 열립니다. 검색·이름 입력 중이나 다른 대화상자에서는 실행하지 않습니다.
- 우클릭 메뉴에도 현재 지정한 키가 표시됩니다. 편집기를 열 때 선택과 스크롤 위치를 유지하고 남은 휠 이동은 멈춥니다.

드롭다운과 영역별 휠 수정
- 미리보기 장수·이미지 선택 방식·정렬 드롭다운을 펼친 상태에서 휠을 돌릴 때 발생하던 KeyError: 'popdown' 오류를 수정했습니다.
- 스크롤바 휠이 3.0·0.025 같은 소수 이동량을 전달해도 ValueError 없이 픽셀 위치로 변환합니다. 화살표·페이지 이동·직접 끌기도 유지합니다.
- 갤러리 휠 입력은 썸네일 영역 안에서만 처리합니다. 폴더 탐색·즐겨찾는 폴더·설정의 목록·이름 변경창에서는 각 영역의 기본 스크롤을 사용합니다.
- 갤러리에서 마우스가 벗어나거나 포커스가 이동하고 팝업·대화상자가 열리면 남은 휠 애니메이션을 멈춥니다.
- 썸네일 편집기에서는 이미지 위의 휠만 확대·축소하며, 드롭다운을 사용하는 동안에는 이미지와 뒤쪽 갤러리를 움직이지 않습니다.
- 확인할 곳: 갤러리·양쪽 폴더 목록·스크롤바·메인 드롭다운·설정 5개 탭과 글꼴 목록·이름 변경창의 원래 파일명·썸네일 편집기와 그 안의 드롭다운.

스크롤 개선
- 썸네일·글자·테두리·즐겨찾기 별을 같은 Canvas에 직접 그립니다. 스크롤 중 각 썸네일 칸을 별도 창으로 이동시키지 않도록 바꿔, 이미지 조각이 가로로 겹쳐 남는 현상에 대응했습니다.
- 휠 이동을 픽셀 단위 애니메이션으로 표시합니다. 빠르게 돌리면 이동량이 누적되고 반대로 돌리면 바로 방향을 바꿉니다.
- 스크롤 중에는 기존 카드의 위치와 크기를 불필요하게 다시 설정하지 않습니다.
- 스크롤바·방향키·탭 전환 등 다른 탐색 동작을 사용하면 남은 휠 애니메이션을 멈춥니다.

썸네일 편집기
- 편집기는 자유 비율로 시작합니다. '썸네일 비율 (127:180)'을 선택하면 1270×1800 비율로 고정합니다.
- 썸네일 크기·슬라이더·창에 맞춤·미리보기·편집 버튼을 같은 줄 오른쪽에 한 묶음으로 배치했습니다.
- 파일을 선택한 뒤 오른쪽 묶음의 '썸네일 영역 편집' 버튼으로도 열 수 있습니다.
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
