# File Tripitaka 1.2.0-beta.1 / 파일만대장경

Windows와 macOS용 첫 베타 배포입니다. / First Windows and macOS beta release.

## 다운로드 / Downloads

- **Windows-x64.zip**: 압축을 풀고 EXE를 실행합니다. Python 설치는 필요 없습니다.
- **macOS-arm64.zip**: Apple Silicon(M1 이상)용입니다. 압축을 풀고 File Tripitaka.app을 응용 프로그램 폴더로 옮깁니다.
- **macOS-x86_64.zip**: Intel Mac용입니다. Apple Silicon용 파일과 구분해 주세요.
- `SHA256SUMS.txt`로 각 ZIP의 다운로드 무결성을 확인할 수 있습니다.

Unzip the package and run the EXE on Windows, or copy the app into Applications on macOS. Python is bundled. Choose arm64 for Apple Silicon and x86_64 for Intel Macs.

## 이번 베타 / In this beta

- macOS Finder에서 파일 위치 열기, 기본 앱·선택한 .app 뷰어로 열기
- Mac의 볼륨 탐색, Control-click·보조 클릭과 스크롤 지원
- Windows의 기존 꿀뷰·다른 뷰어 연동 유지
- 한국어 / English, 즐겨찾기, 키보드 동작, 1·2·3장 미리보기 및 창 너비 맞춤
- 운영체제별 빌드에서 테스트 및 패키징된 앱 자체 점검

## 실행 환경과 제한 / Requirements and limitations

- Windows는 64비트 Windows 10/11, Mac은 **macOS 15 이상**을 대상으로 빌드합니다.
- macOS 패키지는 **Developer ID 서명·Apple 공증을 하지 않은 베타**입니다. 조직 정책이나 Gatekeeper 설정에 따라 실행이 차단될 수 있으며, 보안 기능을 끄도록 요구하지 않습니다.
- Windows EXE도 배포자 코드 서명이 없는 베타입니다. SmartScreen 또는 Smart App Control에서 경고·차단될 수 있습니다.
- Mac의 자동 맞춤·미리보기·ZIP 처리는 앱 자체에서 동작합니다. RAR·7Z 계열 미리보기에는 별도 **7-Zip(7zz/7z)** 설치가 필요합니다. Mac에서는 Homebrew 설치 경로도 찾습니다.
- Mac의 기본 더블클릭은 Finder에서 파일 위치 열기입니다. 설정에서 다른 뷰어 `.app`을 지정하거나 기본 앱 열기를 선택할 수 있습니다. 기본 앱은 macOS의 파일 연결을 따르므로 압축 해제 프로그램일 수도 있습니다.
- 꿀뷰 및 다른 외부 뷰어는 포함하지 않습니다.
- 암호·손상·분할·중첩 압축은 미리보기가 제한될 수 있습니다. 대표 이미지 데이터는 64MB까지 처리하며, 큰 이미지 디코더는 시간·메모리 제한을 적용합니다.
- 자동 점검 결과는 모든 Windows/Mac 기기에서의 실사용 검증을 뜻하지 않습니다. 베타에서 발견한 문제는 저장소 Issues로 알려주세요.

The Mac beta is ad-hoc signed for execution integrity, not Developer ID signed or Apple-notarized. The Windows beta has no publisher code-signing certificate. OS security policies may block these builds. External archive viewers and 7-Zip are not bundled. The default Mac action reveals the file in Finder; opening with the default app follows your file associations and may launch an archive extractor.

## 설정과 피드백 / Settings and feedback

- Windows: `%LOCALAPPDATA%\ArchiveShelf`
- macOS: `~/Library/Application Support/File Tripitaka` (이전 Mac 소스 실행 설정이 있으면 한 번 가져옵니다.)
- 기존 즐겨찾기와 설정은 유지합니다. 원본 압축파일을 수정하지 않습니다.
- 오류 신고 시 OS 버전, CPU 종류, 파일 형식과 재현 단계를 알려주세요. 실제 이미지·토큰·민감한 파일 경로는 공개 Issues에 올리지 마세요.
