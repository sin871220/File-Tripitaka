<p align="center">
  <img src="assets/app.png" width="112" alt="파일만대장경 아이콘">
</p>

<h1 align="center">파일만대장경 · File Tripitaka</h1>

<p align="center"><strong>압축파일 안의 사진을, 한눈에.</strong></p>

<p align="center">
  여러 폴더에 흩어진 압축파일을 썸네일로 훑어보고,<br>
  마음에 드는 파일을 모아 원하는 뷰어로 여는 Windows·macOS 프로그램입니다.
</p>

<p align="center">
  <a href="https://github.com/sin871220/File-Tripitaka/releases/tag/v1.2.0-beta.1"><strong>베타 다운로드</strong></a>
  &nbsp;·&nbsp;
  <a href="#처음-사용하기">사용 방법</a>
  &nbsp;·&nbsp;
  <a href="https://github.com/sin871220/File-Tripitaka/issues">오류 신고·기능 제안</a>
</p>

<p align="center"><sub>Archive thumbnail browser for Windows and macOS · 한국어 / English</sub></p>

![파일만대장경 라이브러리 화면](docs/images/library-overview.png)

*예시 자료를 사용한 Mac 베타 화면입니다. 개인 파일과 개인 폴더 이름은 포함하지 않았습니다.*

## 다운로드

[v1.2.0-beta.1 다운로드 페이지](https://github.com/sin871220/File-Tripitaka/releases/tag/v1.2.0-beta.1)에서 내 컴퓨터에 맞는 ZIP을 받으세요. Python을 따로 설치할 필요가 없습니다.

이번 베타의 [Tcl/Tk 추가 고지문](https://github.com/sin871220/File-Tripitaka/releases/download/v1.2.0-beta.1/THIRD-PARTY-NOTICES.txt)도 함께 받아 앱 배포물과 보관해 주세요. 기존 앱 ZIP은 변경하지 않았습니다.

| 내 컴퓨터 | 받을 파일 | 실행 방법 |
|---|---|---|
| Windows 10/11 · 64비트 | [Windows-x64.zip](https://github.com/sin871220/File-Tripitaka/releases/download/v1.2.0-beta.1/File-Tripitaka-v1.2.0-beta.1-Windows-x64.zip) | 압축을 풀고 `FileManDaejanggyeong.exe` 실행 |
| Mac · Apple Silicon(M1 이상) | [macOS-arm64.zip](https://github.com/sin871220/File-Tripitaka/releases/download/v1.2.0-beta.1/File-Tripitaka-v1.2.0-beta.1-macOS-arm64.zip) | 압축을 풀고 `File Tripitaka.app`을 응용 프로그램 폴더로 이동 |
| Mac · Intel | [macOS-x86_64.zip](https://github.com/sin871220/File-Tripitaka/releases/download/v1.2.0-beta.1/File-Tripitaka-v1.2.0-beta.1-macOS-x86_64.zip) | 압축을 풀고 `File Tripitaka.app`을 응용 프로그램 폴더로 이동 |

Mac 버전은 **macOS 15 이상**을 지원합니다. Mac의 칩 종류는  → **이 Mac에 관하여**에서 확인할 수 있습니다.

현재는 **배포자 코드 서명·Apple 공증이 없는 베타**라서 운영체제의 실행 경고나 차단이 나타날 수 있습니다. 자세한 실행 조건은 [베타 안내](BETA-RELEASE.md)를 확인하세요. 이전 버전과 변경 사항은 [전체 Releases](https://github.com/sin871220/File-Tripitaka/releases)에 모아 둡니다.

## 이렇게 둘러보세요

| 기능 | 할 수 있는 일 |
|---|---|
| **폴더 전체를 한 화면에** | 선택한 폴더와 하위 폴더의 압축파일을 모아 보고, 파일명 검색과 이름·수정 날짜 정렬로 좁혀 갑니다. |
| **표지와 본문을 함께** | 기본 1장 보기에서 2장·3장 보기로 바꾸면 여러 이미지를 나란히 확인할 수 있습니다. |
| **파일별 즐겨찾기** | 폴더가 달라도 즐겨찾기 탭에서 한꺼번에 확인합니다. 전체 탭에서는 오른쪽 위 노란 별로 구분합니다. |
| **끊김을 줄인 탐색** | 페이지를 넘기지 않고 계속 스크롤합니다. 화면 근처의 카드만 생성하며, 탭마다 스크롤 위치를 기억합니다. |
| **내 화면에 맞게** | 사이드바 접기, 창 너비 맞춤, 네 가지 테마와 글꼴·글자 크기, 카드 표시 항목을 설정합니다. |

## 처음 사용하기

1. **폴더 선택**을 눌러 압축파일이 있는 폴더를 고르세요. 하위 폴더까지 모아 보는 옵션은 기본으로 켜져 있습니다.
2. **전체** 탭에서 썸네일을 둘러보세요. 파일명으로 검색하거나 이름·수정 날짜 순으로 정렬할 수 있습니다.
3. 자주 찾는 파일은 **오른쪽 클릭 → 즐겨찾기 추가**로 모아 두세요. **즐겨찾기** 탭은 현재 폴더와 관계없이 모든 파일 즐겨찾기를 보여 줍니다.
4. **설정 → 열기 동작**에서 더블클릭·Enter·Space가 각각 할 일을 고르세요. Windows에서는 꿀뷰나 다른 뷰어를, Mac에서는 기본 앱이나 다른 뷰어를 연결할 수 있습니다.

Mac의 기본 더블클릭 동작은 **Finder에서 파일 위치 열기**입니다. **기본 앱으로 열기**는 macOS의 파일 연결을 따르므로 압축 해제 프로그램이 열릴 수도 있습니다. 외부 뷰어와 Windows용 꿀뷰는 포함하지 않으며, 따로 설치해야 합니다.

### 마우스와 키보드

| 조작 | 동작 |
|---|---|
| 왼쪽 폴더 이름 한 번 클릭 | 해당 폴더의 썸네일 표시 |
| 폴더 탐색에서 더블클릭 / 화살표 클릭 | 하위 폴더 펼치기·접기 |
| 썸네일 한 번 클릭 → 방향키 | 파일 선택 후 그리드 안에서 이동 |
| 더블클릭 / Enter / Space | 각자 설정한 동작 실행 |
| 오른쪽 클릭 | 파일 위치·즐겨찾기 등 메뉴 열기. Mac은 보조 클릭·Control-click도 지원 |

Enter·Space에는 **즐겨찾기 추가/해제**, **없음**도 지정할 수 있습니다. 즐겨찾기 탭에서 키보드로 해제하면 스크롤을 유지하며 다음 파일을 선택하고, 마지막 파일이면 이전 파일을 선택합니다.

### 1장·2장·3장 미리보기

기본은 **1장 보기**입니다. 2장·3장 보기는 카드의 폭을 넓혀 이미지를 작은 간격으로 나란히 배치합니다.

| 선택 | 순차 보기에서 고르는 이미지 | 비율 보기에서 고르는 이미지 | 화면의 왼쪽 → 오른쪽 |
|---|---|---|---|
| 1장 | 맨 앞 | 맨 앞 | `1` |
| 2장 | 1·2번째 | 맨 앞 · 1/2 위치 | `2 → 1` |
| 3장 | 1·2·3번째 | 맨 앞 · 1/3 · 2/3 위치 | `3 → 2 → 1` |

화면 순서의 숫자는 선택된 이미지의 순서입니다. 맨 앞 이미지가 오른쪽에 옵니다. 이미지가 부족하면 실제 장수만 표시하고 같은 이미지를 중복하지 않습니다.

### 화면 꾸미기

- **창에 맞춤 ON/OFF:** 현재 4열이면 4열, 5열이면 5열을 유지하면서 창 너비를 채웁니다. 슬라이더를 움직이면 OFF로 돌아옵니다.
- **폴더 패널 접기:** 사이드바 전체를 접어 썸네일 영역을 넓힙니다. 즐겨찾는 폴더와 폴더 탐색도 각각 접을 수 있습니다.
- **테마:** 라이트 · 다크 · 네이비 · 블루.
- **카드 표시:** 파일명, 확장자, 용량, 수정 날짜 중 필요한 항목만 표시합니다.
- **글꼴·언어:** 글꼴과 글자 크기를 바꾸고, 한국어 / English를 선택할 수 있습니다. 제목·메뉴·설정이 함께 바뀌며 파일명은 그대로 유지합니다.

## 어떤 파일을 볼 수 있나요?

| 종류 | 지원 |
|---|---|
| 압축파일 | ZIP · CBZ 기본 지원 / RAR · CBR · 7Z · CB7은 별도 7-Zip 필요 |
| 압축파일 안의 이미지 | JPG · JPEG · PNG · WebP · BMP · GIF · TIFF |

**7-Zip은 배포 파일에 포함하지 않습니다.** 설치된 `7z`·`7zz`를 PATH와 일반적인 설치 경로에서 찾으며 Mac의 Homebrew 경로도 확인합니다. 내부 이미지 이름은 자연 정렬합니다.

암호가 걸렸거나 손상·분할·중첩된 압축파일은 미리보기가 제한될 수 있습니다. 미리보기를 만들 수 없는 파일은 파일 위치를 열어 직접 확인할 수 있습니다. 원본 압축파일은 수정하지 않으며, 즐겨찾기는 파일 경로 기준으로 저장합니다.

## 문제를 발견했나요?

[Issues](https://github.com/sin871220/File-Tripitaka/issues)에 **운영체제 버전, Mac 칩 종류 또는 Windows CPU, 파일 형식, 문제가 생긴 순서**를 적어 주세요. 화면을 첨부한다면 개인 이미지와 민감한 경로는 가려 주세요.

<details>
<summary><strong>설정·캐시·로그 위치와 미리보기 제한</strong></summary>

| 운영체제 | 저장 위치 |
|---|---|
| Windows | `%LOCALAPPDATA%\ArchiveShelf` |
| macOS | `~/Library/Application Support/File Tripitaka` |

`settings.json`에는 설정과 즐겨찾기, `cache/`에는 썸네일이 저장됩니다. 오류를 살펴볼 때는 `error.log`와 `crash.log`를 확인하세요. 로그를 공개하기 전에는 개인 경로와 민감한 내용이 들어 있는지 확인해 주세요.

Mac에서 이전 소스 실행으로 만든 `~/.local/share/ArchiveShelf/settings.json`이 있으면 새 저장 위치로 한 번 가져옵니다. Windows의 기존 설정 위치는 유지합니다. Windows에서 언어를 바꾸면 현재 EXE를 가리키는 기존 바탕화면 바로가기 이름도 변경합니다.

대표 이미지 데이터는 압축 해제 후 64MB까지 처리합니다. 큰 이미지 디코더는 별도 프로세스에서 한 장씩 실행하며 메모리(RSS 512MB)와 시간(45초) 제한을 적용합니다. 미리보기 실패 항목은 설정한 열기 동작 대신 파일 위치를 엽니다. **없음·즐겨찾기 전환**은 예외입니다.

</details>

<details>
<summary><strong>소스로 실행하거나 직접 빌드하기</strong></summary>

Python 3.12 이상과 Tcl/Tk가 필요합니다.

```sh
python -m pip install -r requirements.txt
python app.py
```

- Windows: 소스 실행은 `run-windows.bat`, 배포 빌드는 `build-windows.bat`.
- macOS: `build-macos.sh`. Apple Silicon과 Intel은 해당 CPU용 Python 환경에서 각각 빌드합니다.
- GitHub Actions: 베타 태그를 푸시하면 Windows·Mac의 테스트, 빌드, 패키징 점검을 통과한 파일을 prerelease로 배포합니다. 수동 실행은 빌드 산출물을 만듭니다.

```sh
python -m unittest discover -s tests -v
python tests/gui_smoke.py
python tests/language_smoke.py
```

패키징된 앱은 `--self-test --report <JSON 경로>`로 ZIP 처리·네이티브 디코더·Tk GUI·언어 전환을 점검할 수 있습니다. 자동 점검이 모든 기기에서의 실사용 검증을 대신하지는 않습니다.

</details>

<details>
<summary><strong>포함 자료와 고지</strong></summary>

- 앱 아이콘: `assets/app.png`. Windows용 `assets/app.ico`를 포함하며 Mac 아이콘은 같은 이미지로 빌드합니다.
- Noto Sans CJK KR 글꼴: `fonts/SOURCE.txt`에 출처, `fonts/OFL.txt`에 라이선스를 포함합니다.
- 배포 패키지에는 사용한 라이브러리 버전과 이용 가능한 라이선스 고지문을 함께 담습니다.

</details>
