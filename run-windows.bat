@echo off
setlocal DisableDelayedExpansion
rem PUSHD also supports a shared folder opened through a UNC path.
pushd "%~dp0"
if errorlevel 1 goto location_fail
set "APP_DIR=%CD%"
set "APP_PYTHON=%APP_DIR%\.venv\Scripts\python.exe"
if not exist "%APP_DIR%\app.py" goto incomplete
if not exist "%APP_DIR%\brand.py" goto incomplete
if not exist "%APP_DIR%\requirements.txt" goto incomplete
if exist "%APP_PYTHON%" goto check_python
py -3 -m venv "%APP_DIR%\.venv"
if errorlevel 1 goto fail
:check_python
"%APP_PYTHON%" -E -s -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
if errorlevel 1 goto python_fail
echo Source folder: "%APP_DIR%"
"%APP_PYTHON%" -E -s -B "%APP_DIR%\app.py" --version
if errorlevel 1 goto fail
"%APP_PYTHON%" -E -s -m pip install -r "%APP_DIR%\requirements.txt"
if errorlevel 1 goto fail
"%APP_PYTHON%" -E -s -B "%APP_DIR%\app.py"
if errorlevel 1 goto fail
popd
exit /b 0
:incomplete
echo Source files are missing. Extract the complete latest Source ZIP first.
goto fail
:python_fail
echo Python 3.12 or newer is required. This folder's .venv may need to be recreated.
goto fail
:fail
echo Launch failed. See the error above. No other version will be opened.
popd
pause
exit /b 1
:location_fail
echo Cannot open the source folder: "%~dp0"
pause
exit /b 1
