@echo off
REM ===================================================================
REM  Spin up all four WoW-timers Discord bots.
REM  Double-click this file, or run it from a terminal.
REM  Each bot opens in its own minimized window and logs to logs\.
REM ===================================================================

setlocal
cd /d "%~dp0"

REM Anaconda Python 3.12 (has discord.py). Edit here if the path changes.
set "PY=C:\Users\david\anaconda3\python.exe"

REM Force UTF-8 so emoji / circled-number nicknames don't crash logging.
set "PYTHONUTF8=1"

if not exist logs mkdir logs

if not exist "%PY%" (
    echo [ERROR] Python not found at: %PY%
    echo Edit the PY variable in this script to point at your python.exe
    pause
    exit /b 1
)

echo Launching WoW-timers bots...

start "WoW-STV" /min cmd /c ""%PY%" bot_stv.py > logs\stv.log 2>&1"
start "WoW-AGM" /min cmd /c ""%PY%" bot_agm.py > logs\agm.log 2>&1"
start "WoW-DMF" /min cmd /c ""%PY%" bot_dmf.py > logs\dmf.log 2>&1"
start "WoW-BG"  /min cmd /c ""%PY%" bot_bg.py  > logs\bg.log  2>&1"

echo.
echo All four bots launched (STV, AGM, DMF, BG).
echo Each runs in its own minimized window. Close a window to stop that bot.
echo Logs: %cd%\logs\
echo.
timeout /t 3 >nul
