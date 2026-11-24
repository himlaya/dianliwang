@echo off
setlocal
cd /d "%~dp0"

echo Building PeripheralBattery (电力王)...
python -m pip install --disable-pip-version-check --quiet pyinstaller
if errorlevel 1 (
    echo [ERROR] pip install pyinstaller failed.
    pause
    exit /b 1
)

python -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --icon "%~dp0assets\app.ico" ^
  --add-data "%~dp0assets\app.ico;assets" ^
  --version-file "%~dp0build\version_info.txt" ^
  --name 电力王 ^
  --distpath "%~dp0dist" --workpath "%~dp0build\temp" --specpath "%~dp0build" ^
  "%~dp0PeripheralBattery.pyw"

if not exist "%~dp0dist\电力王\电力王.exe" (
    echo [ERROR] build failed.
    pause
    exit /b 1
)
echo.
echo Done: dist\电力王\电力王.exe
echo Run 安装.cmd to install with shortcuts.
pause
