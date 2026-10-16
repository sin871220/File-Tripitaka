# 파일만대장경 · File Tripitaka

압축파일 안의 사진을 썸네일로 모아 보고 외부 뷰어로 여는 Windows·macOS 프로그램입니다. 한국어 / English를 지원합니다.

Archive thumbnail browser for Windows and macOS. Browse images inside archives, collect favorites, and open files with an external viewer. Korean and English UI are included.

## 베타 다운로드 / Beta downloads

GitHub의 **Releases**에서 운영체제와 CPU에 맞는 ZIP을 받으세요. Python은 설치하지 않아도 됩니다.

| 패키지 | 대상 |
|---|---|
| Windows-x64 | 64비트 Windows 10/11 |
| macOS-arm64 | Apple Silicon Mac(M1 이상), macOS 15 이상 |
| macOS-x86_64 | Intel Mac, macOS 15 이상 |

Windows는 압축을 풀고 EXE를 실행합니다. Mac은 압축을 풀고 `.app`을 응용 프로그램 폴더로 옮깁니다. 베타의 서명·공증 제한, 외부 프로그램 요구 사항과 변경 사항은 [BETA-RELEASE.md](BETA-RELEASE.md)를 확인하세요.

Download a ZIP for your OS and CPU from Releases. Run the EXE on Windows, or copy the `.app` into Applications on macOS. See [the beta notes](BETA-RELEASE.md) for signing limitations and prerequisites.

## 주요 기능

- ZIP·CBZ 대표 이미지 표시. RAR·CBR·7Z·CB7은 별도 7-Zip 설치 후 지원합니다.
- 하위 폴더 전체 수집, 파일명 검색, 이름·수정 날짜 오름/내림차순 정렬.
- 수천 개 파일도 화면 근처의 카드만 생성하는 연속 스크롤.
- 전체 / 전역 즐겨찾기 탭과 각 탭의 스크롤 위치 기억.
- 즐겨찾기 추가 시 노란 별만 변경하고, 해제 시 항목만 제거하며 현재 스크롤을 유지합니다.
- 방향키 선택 이동, 더블클릭 / Enter / Space의 독립 동작 설정. Enter·Space에는 없음 및 즐겨찾기 전환도 있습니다.
- 즐겨찾기 탭에서 키보드로 해제하면 다음 항목을 선택하며 마지막 항목은 이전 항목을 선택합니다.
- 기본 1장, 선택 2장 / 3장 미리보기. 순차 또는 비율 샘플을 왼쪽부터 2·1 / 3·2·1 순서로 좁은 간격을 두어 나열합니다.
- 창에 맞춤 ON/OFF: 현재 열 수를 유지하면서 창 너비를 채웁니다. 슬라이더 조작 시 OFF로 바뀝니다.
- 즐겨찾는 폴더·폴더 탐색의 개별 접기와 사이드바 전체 접기.
- 폴더 한 번 클릭으로 썸네일 표시, 트리 더블클릭 또는 화살표로 펼치기·접기.
- 라이트 / 다크 / 네이비 / 블루 테마, 파일명·확장자·용량·날짜 표시 설정, 글꼴·글자 크기 설정.
- 한국어 / English 선택에 따라 제목·메뉴·설정·상태 문구가 바뀝니다. 파일명·폴더명은 번역하지 않습니다.

## 운영체제별 열기 동작

**Windows:** 파일 위치 열기 / 꿀뷰 / 다른 뷰어. 꿀뷰는 별도 설치합니다. 언어를 바꾸면 현재 EXE를 가리키는 기존 바탕화면 바로가기 이름도 바꿉니다.

**macOS:** Finder에서 파일 위치 열기 / 기본 앱 / 다른 `.app` 또는 실행 파일. 기본 동작은 Finder에서 위치 열기이며, 기본 앱 열기는 OS 파일 연결을 따릅니다. 압축 해제 앱이 기본으로 연결되어 있을 수도 있습니다. 보조 클릭과 Control-click 메뉴를 지원합니다.

## 압축·이미지 지원

지원 이미지: JPG·JPEG·PNG·WebP·BMP·GIF·TIFF. 내부 파일명을 자연 정렬합니다.

- 순차 2장: 1·2번째, 순차 3장: 1·2·3번째.
- 비율 2장: 맨 앞과 1/2 위치, 비율 3장: 맨 앞과 1/3·2/3 위치.
- 이미지 수가 부족하면 실제 장수만 표시하고 중복시키지 않습니다.
- 7-Zip의 `7z`/`7zz`를 PATH에서 찾습니다. Windows 설치 경로와 Mac Homebrew의 `/opt/homebrew/bin`, `/usr/local/bin`도 확인합니다.
- 이미지 데이터는 압축 해제 후 64MB까지 처리합니다. 큰 이미지 디코더는 별도 프로세스에서 한 번에 한 장씩 실행하며 RSS 512MB·45초 제한을 감시합니다.
- 암호·손상·분할·중첩 압축은 미리보기가 제한될 수 있습니다. 미리보기 실패 항목은 기본적으로 파일 위치를 엽니다(동작 없음·즐겨찾기 전환은 예외).
- 원본 압축파일을 수정하지 않습니다. 즐겨찾기는 파일 경로 기준입니다.

## 설정과 로그

- Windows: `%LOCALAPPDATA%\ArchiveShelf`
- macOS: `~/Library/Application Support/File Tripitaka`
- Mac에서 이전 소스 실행 시 사용한 `~/.local/share/ArchiveShelf/settings.json`이 있으면 새 저장 위치에 한 번 가져옵니다.
- `settings.json`: 설정·즐겨찾기. `cache/`: 썸네일 캐시. `error.log`, `crash.log`: 진단 로그.

오류 신고 시 OS 버전·CPU·파일 형식·재현 단계를 함께 알려주세요. 실제 이미지·토큰·민감한 파일 경로는 공개 Issues에 올리지 마세요.

## 소스 실행과 빌드

Python 3.12 이상과 Tcl/Tk가 필요합니다. `pip install -r requirements.txt` 후 `python app.py`로 실행합니다.

- Windows: `run-windows.bat` 또는 `build-windows.bat`.
- macOS: `build-macos.sh`.
- GitHub Actions: 베타 태그를 푸시하면 OS별 테스트·빌드·패키징 점검을 통과한 파일을 prerelease로 배포합니다. 수동 실행은 빌드 산출물을 생성합니다.
- 테스트: `python -m unittest discover -s tests -v`. GUI 회귀 검사: `python tests/gui_smoke.py`, `python tests/language_smoke.py`.
- 패키징된 앱 자체 검사: `--self-test --report <JSON 경로>`. ZIP 처리·네이티브 디코더·Tk GUI·언어 전환을 검증합니다.

Source code builds require Python with Tcl/Tk. Release packages include the Python runtime. Beta tag builds publish a GitHub prerelease only after platform build checks pass.

## 포함 자료

- 승인된 앱 아이콘: `assets/app.png`, Windows 아이콘: `assets/app.ico`. Mac 아이콘은 빌드 시 같은 이미지로 생성합니다.
- Noto Sans CJK KR 글꼴: `fonts/SOURCE.txt`, `fonts/OFL.txt`에 출처와 라이선스를 포함합니다.
- 배포 패키지에 사용한 라이브러리 버전과 이용 가능한 라이선스 고지문을 함께 포함합니다.
