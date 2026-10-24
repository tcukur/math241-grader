@echo off
REM Double-click to start MATH241 Grader on Windows.
REM The app is copied to this computer and runs from there, so nothing is ever written into this folder
REM (safe to keep it in Google Drive or share it). The first start downloads what the app needs.
set "SRC=%~dp0"
set "BASE=%LOCALAPPDATA%\MATH241Grader"
set "APP=%BASE%\app"
set "VENV=%BASE%\venv"
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
set "PYTHONDONTWRITEBYTECODE=1"

REM leftovers of older versions that ran inside this folder
if exist "%SRC%.venv\pyvenv.cfg" rmdir /s /q "%SRC%.venv"
for /d /r "%SRC%grader_app" %%P in (__pycache__) do if exist "%%P" rmdir /s /q "%%P"

echo Copying the app to this computer...
if not exist "%APP%" mkdir "%APP%"
if exist "%APP%\packs" rmdir /s /q "%APP%\packs"
for %%D in (grader_app docs) do (
  robocopy "%SRC%%%D" "%APP%\%%D" /MIR /XD __pycache__ /NFL /NDL /NJH /NJS /NP >nul
  if errorlevel 8 goto copyfail
)
copy /y "%SRC%run_grader.py" "%APP%\" >nul || goto copyfail
copy /y "%SRC%requirements-run.txt" "%APP%\" >nul || goto copyfail
cd /d "%APP%"

where uv >nul 2>nul
if errorlevel 1 (
  echo First start: setting up MATH241 Grader. This happens only once and takes a few minutes.
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex" >nul 2>nul
)
where uv >nul 2>nul
if errorlevel 1 goto fail
set "NEED=0"
fc /b requirements-run.txt "%VENV%\.ready" >nul 2>nul || set "NEED=1"
"%VENV%\Scripts\python.exe" -c "import PySide6, pymupdf" >nul 2>nul || set "NEED=1"
if "%NEED%"=="1" (
  echo Preparing the app, one time...
  uv venv --quiet --clear --python 3.12 "%VENV%" || goto fail
  uv pip install --quiet --python "%VENV%\Scripts\python.exe" -r requirements-run.txt || goto fail
  copy /y requirements-run.txt "%VENV%\.ready" >nul
)
start "" "%VENV%\Scripts\pythonw.exe" run_grader.py
exit /b 0
:copyfail
echo.
echo Could not copy the app from this folder. If it is in Google Drive, wait until it has finished syncing and try again.
pause
exit /b 1
:fail
echo.
echo Setup did not finish. Check the internet connection and double-click this file again.
pause
exit /b 1
