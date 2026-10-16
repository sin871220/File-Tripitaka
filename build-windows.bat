@echo off
cd /d "%~dp0"
py -3.12 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto fail
.venv\Scripts\python scripts\build_release.py --platform windows --arch x64
if errorlevel 1 goto fail
echo Release ZIP and SHA-256: %CD%\dist\releases
pause
exit /b 0
:fail
echo Build failed. See the error above.
pause
exit /b 1
