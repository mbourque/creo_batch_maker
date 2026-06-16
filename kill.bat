@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Optional: batch runner passes "nowait" after its own 15s xtop grace when outputs finished.
if /I "%~1"=="nowait" goto do_kill

REM Wait up to 15s for xtop to exit before force-kill (Stop button, manual runs).
set "_xtopWaitSec=0"
:wait_xtop
tasklist /FI "IMAGENAME eq xtop.exe" 2>nul | find /I "xtop.exe" >nul
if errorlevel 1 goto do_kill
if !_xtopWaitSec! GEQ 15 goto do_kill
timeout /t 2 /nobreak >nul
set /a _xtopWaitSec+=2
goto wait_xtop

:do_kill
for %%p in (pro_comm_msg nmsd dbatchs dbatchc dsq xtop) do (
    taskkill /F /IM %%p.exe /T >nul 2>&1
)

endlocal
