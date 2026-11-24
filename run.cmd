@echo off
rem 电力王启动器：优先使用无控制台的 pythonw.exe
setlocal
cd /d "%~dp0"

where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw.exe "PeripheralBattery.pyw"
    exit /b 0
)

where python.exe >nul 2>nul
if %errorlevel%==0 (
    start "" /min python.exe "PeripheralBattery.pyw"
    exit /b 0
)

echo 没有找到 Python，请先安装 Python 3.10 或更高版本：https://www.python.org/downloads/
pause
