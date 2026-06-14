@echo off
setlocal EnableExtensions

REM If xtop is still running, wait up to 30s for it to exit before force-kill.
set "_xtopWaitSec=0"
:wait_xtop
tasklist /FI "IMAGENAME eq xtop.exe" 2>nul | find /I "xtop.exe" >nul
if errorlevel 1 goto do_kill
if %_xtopWaitSec% GEQ 30 goto do_kill
timeout /t 2 /nobreak >nul
set /a _xtopWaitSec+=2
goto wait_xtop

:do_kill
for %%p in (pro_comm_msg nmsd dbatchs dbatchc dsq xtop) do (
    taskkill /F /IM %%p.exe /T >nul 2>&1
)

endlocal
