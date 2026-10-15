@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto fail
.venv\Scripts\python -m unittest discover -s tests -v
if errorlevel 1 goto fail
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed --name FileManDaejanggyeong --icon assets/app.ico --additional-hooks-dir hooks --add-data "fonts;fonts" --add-data "assets;assets" app.py
if errorlevel 1 goto fail
echo EXE: %CD%\dist\FileManDaejanggyeong.exe
pause
exit /b 0
:fail
echo Build failed. See the error above.
pause
exit /b 1
