"""Korean stable settings values with independently translated UI labels."""
import re
import tkinter as tk
from tkinter import ttk

LANGUAGES = {'ko': '한국어', 'en': 'English'}
_language = 'ko'
EN = {
'파일만대장경':'File Tripitaka', '설정':'Settings', '일반':'General', '표시 설정':'Display', '글꼴':'Font', '열기 동작':'Actions',
'← 뒤로':'← Back','폴더 선택':'Choose folder','새로고침':'Refresh','즐겨찾는 폴더':'Favorite folders','폴더 탐색':'Folders',
'현재 폴더 추가':'Add current folder','제거':'Remove','전체':'All','★ 즐겨찾기':'★ Favorites','파일명 검색':'Search name','정렬':'Sort',
'이름 오름차순':'Name ascending','이름 내림차순':'Name descending','수정한 날짜 오름차순':'Modified oldest first','수정한 날짜 내림차순':'Modified newest first',
'맨 위로 ↑':'Top ↑','썸네일 크기':'Thumbnail size','창에 맞춤 ON':'Fit width ON','창에 맞춤 OFF':'Fit width OFF','미리보기':'Preview',
'1장':'1 image','2장':'2 images','3장':'3 images','순차 보기':'Sequential','비율 보기':'Proportional',
'▶ 폴더 패널 펼치기':'▶ Show folders','◀ 폴더 패널 접기':'◀ Hide folders',
'파일 위치 열기':'Show in Explorer','꿀뷰 열기':'Open in Honeyview','꿀뷰로 열기':'Open in Honeyview',
'다른 뷰어 프로그램 열기':'Open in another viewer','즐겨찾기 추가/해제':'Toggle favorite','없음':'None',
'라이트':'Light','다크':'Dark','네이비':'Navy','블루':'Blue','날짜 없음':'No date',
'파일 정보':'File information','경로 복사':'Copy path','★ 즐겨찾기 해제':'★ Remove favorite','☆ 즐겨찾기 추가':'☆ Add favorite',
'폴더 확인':'Check folder','이전 폴더가 없습니다.':'No previous folder.', '불러오는 중…':'Loading…','접근할 수 없는 폴더':'Folder unavailable','표지 읽는 중…':'Loading preview…',
'압축파일을 찾고 있습니다…':'Searching for archives…','오류':'Error',
'폴더를 선택해 주세요. ZIP은 바로, RAR·7Z는 7-Zip 설치 후 미리볼 수 있습니다.':'Choose a folder. ZIP works directly; RAR and 7Z previews require 7-Zip.',
'파일 선택에 실패하여 해당 폴더를 열었습니다. 자세한 내용은 error.log에 기록했습니다.':'Opened the containing folder because file selection failed. See error.log for details.',
'존재하는 폴더를 선택해 주세요.':'Choose an existing folder.', '꿀뷰 설정':'Honeyview settings','꿀뷰 실행 실패':'Honeyview failed','탐색기 실행 실패':'Explorer failed',
'꿀뷰 Honeyview.exe 선택':'Select Honeyview.exe','꿀뷰 실행 파일(Honeyview.exe)을 선택해 주세요.':'Select the Honeyview executable (Honeyview.exe).',
'뷰어 설정':'Viewer settings','설정에서 다른 뷰어 실행 파일을 지정해 주세요.':'Choose another viewer executable in Settings.', '뷰어 실행 실패':'Viewer failed',
'테마와 더블클릭 동작을 선택해 주세요.':'Select a theme and double-click action.', 'Enter와 Space 동작을 선택해 주세요.':'Select Enter and Space actions.',
'선택한 프로그램 파일을 찾을 수 없습니다.':'The selected executable was not found.', '다른 뷰어 프로그램의 실행 파일을 선택해 주세요.':'Choose the other viewer executable.',
'글자 크기는 8~24 사이의 정수로 입력해 주세요.':'Enter an integer font size from 8 to 24.', '글자 크기는 8~24 사이로 선택해 주세요.':'Choose a font size from 8 to 24.',
'설치된 글꼴 목록에서 선택해 주세요.':'Select an installed font.', '썸네일 카드 표시':'Thumbnail card details','파일명':'File name','파일명에 확장자 표시':'Show file extension',
'용량':'Size','날짜 (수정한 날짜)':'Date modified','체크한 항목만 카드에 표시합니다. 전체 경로와 파일 정보는 그대로 확인할 수 있습니다.':'Only checked details appear on cards. Full paths and file information remain available.',
'자동 선택 (CJK 우선)':'Automatic (prefer CJK)','글꼴과 글자 크기':'Font and text size','글자 크기 (pt · 8~24)':'Text size (pt · 8–24)',
'한글 · 日本語 · 漢字 · ABC 123':'English · 한국어 · 日本語 · 漢字 · ABC 123',
'일본어·한자가 보이지 않으면 자동 선택 또는 Noto Sans CJK KR을 선택하세요. 적용을 누르기 전에는 미리보기에만 반영됩니다.':'If Japanese or Chinese characters are missing, choose Automatic or Noto Sans CJK KR. Changes affect only the preview until you apply.',
'화면 및 파일 열기':'Appearance and opening files','화면 모드':'Theme','카드 실행 동작':'Card actions','더블클릭':'Double-click','꿀뷰 실행 파일 경로':'Honeyview executable',
'다른 뷰어 실행 파일 경로':'Other viewer executable','뷰어 실행 파일 선택':'Select viewer executable','실행 파일':'Executables','모든 파일':'All files','찾아보기':'Browse',
'꿀뷰 자동 찾기':'Find Honeyview','전체 탭에서 하위 폴더까지 모아 보기':'Include subfolders in the All tab','설정 확인':'Check settings','적용':'Apply','취소':'Cancel',
'언어':'Language','지원하지 않는 언어입니다.':'Unsupported language.',
'바탕화면 바로가기':'Desktop shortcut','일부 바로가기 이름을 변경하지 못했습니다.':'Some desktop shortcuts could not be renamed.',
'RAR·7Z 미리보기에는 7-Zip 설치가 필요합니다.':'RAR and 7Z previews require 7-Zip.', '압축파일에 지원하는 이미지가 없습니다.':'No supported images in this archive.',
'대표 이미지가 64MB를 초과합니다.':'The preview image exceeds 64 MB.',
'큰 이미지 축소 시간이 45초를 초과했습니다.':'Large image decoding exceeded 45 seconds.',
'큰 이미지 축소 메모리가 512MB를 초과하여 해당 미리보기를 중단했습니다.':'Large image preview stopped after exceeding 512 MB of memory.',
'파일 위치 열기는 Windows에서 사용할 수 있습니다.':'Show in Explorer is available on Windows.',
}
# Templates translate generated UI prose without changing filenames or paths.
TEMPLATES = [
('설정 · {name}', 'Settings · {name}'),
('현재 위치 · {path}', 'Current location · {path}'),
('폴더를 찾을 수 없습니다.\n{path}', 'Folder not found.\n{path}'),
('파일을 찾을 수 없습니다. 새로고침 후 다시 시도해 주세요.\n{path}', 'File not found. Refresh and try again.\n{path}'),
('즐겨찾기 전체 {count}개 · 검색 결과 {found}개 · 더블클릭: 설정한 동작 · 우클릭: 파일 위치', 'Favorites: {count} · Matches: {found} · Double-click: configured action · Right-click: file actions'),
('전체 {count}개 · 검색 결과 {found}개 · 더블클릭: 설정한 동작 · 우클릭: 파일 위치', 'All: {count} · Matches: {found} · Double-click: configured action · Right-click: file actions'),
('미리보기 불가\n{error}', 'Preview unavailable\n{error}'),
('{name}\n\n전체 경로: {path}\n\n크기: {size} 바이트 ({mb} MB)\n수정: {date}', '{name}\n\nFull path: {path}\n\nSize: {size} bytes ({mb} MB)\nModified: {date}'),
('{error}\n\n로그: {path}', '{error}\n\nLog: {path}'),
('큰 이미지 축소 실패: {error}', 'Large image decoding failed: {error}'),
('COM 초기화 실패: 0x{code}', 'COM initialization failed: 0x{code}'),
('파일 경로 확인 실패: 0x{code}', 'File path lookup failed: 0x{code}'),
('탐색기 선택 실패: 0x{code}', 'Explorer selection failed: 0x{code}'),
('디코더 종료 코드 {code}', 'Decoder exit code {code}'),
]

def set_language(language):
    global _language
    if language not in LANGUAGES:
        raise ValueError('Unsupported language')
    _language = language


def _match(template, text):
    parts = re.split(r'(\{\w+\})', template)
    pattern = ''.join('(?P<' + p[1:-1] + '>.*?)' if p.startswith('{') else re.escape(p) for p in parts)
    return re.fullmatch(pattern, text, re.S)


def translate(text, language=None):
    if not isinstance(text, str):
        return text
    language = language or _language
    if language == 'en' and text in EN:
        return EN[text]
    if language == 'ko':
        for korean, english in EN.items():
            if text == english:
                return korean
    for prefix in ('▶  ', '▼  '):
        if text.startswith(prefix):
            return prefix + translate(text[len(prefix):], language)
    for korean, english in TEMPLATES:
        source, target = (korean, english) if language == 'en' else (english, korean)
        match = _match(source, text)
        if match:
            values = match.groupdict()
            if 'error' in values:
                values['error'] = translate(values['error'], language)
            return target.format(**values)
    return text


def localize_widgets(widget):
    """Translate presentation only. Combobox model variables retain Korean IDs."""
    if isinstance(widget, ttk.Combobox):
        if not hasattr(widget, '_localization'):
            values = tuple(widget.cget('values'))
            if any(value in EN for value in values):
                original = str(widget.cget('textvariable'))
                if original:
                    model = tk.StringVar(master=widget, name=original)
                    display = tk.StringVar(master=widget)
                    widget._localization = (values, model, display)
                    busy = [False]
                    def sync_model(*_):
                        if busy[0]: return
                        busy[0] = True
                        try: display.set(translate(model.get()))
                        finally: busy[0] = False
                    def sync_display(*_):
                        if busy[0]: return
                        for value in values:
                            if display.get() == translate(value):
                                busy[0] = True
                                try: model.set(value)
                                finally: busy[0] = False
                                break
                    model.trace_add('write', sync_model)
                    display.trace_add('write', sync_display)
                    widget.configure(textvariable=display)
        if hasattr(widget, '_localization'):
            values, model, display = widget._localization
            widget.configure(values=[translate(value) for value in values])
            display.set(translate(model.get()))
    elif isinstance(widget, ttk.Notebook):
        for tab in widget.tabs():
            widget.tab(tab, text=translate(widget.tab(tab, 'text')))
    elif isinstance(widget, tk.Menu):
        end = widget.index('end')
        for index in range((end if end is not None else -1) + 1):
            if widget.type(index) != 'separator':
                widget.entryconfigure(index, label=translate(widget.entrycget(index, 'label')))
    elif isinstance(widget, ttk.Treeview):
        if getattr(widget, '_is_folder_tree', False):
            def visit(parent=''):
                for node in widget.get_children(parent):
                    text = widget.item(node, 'text')
                    if node not in widget._folder_paths:
                        widget.item(node, text=translate(text))
                    visit(node)
            visit()
    elif not getattr(widget, '_literal_user_text', False):
        try:
            # StringVar-backed status is translated separately; filenames remain literal.
            if not widget.cget('textvariable'):
                widget.configure(text=translate(widget.cget('text')))
        except tk.TclError:
            try: widget.configure(text=translate(widget.cget('text')))
            except tk.TclError: pass
    for child in widget.winfo_children():
        localize_widgets(child)
