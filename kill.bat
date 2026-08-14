@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Safe for runners and the app to call mid-batch: Creo/dbatch only.
rem Do not kill nmsd.exe — Name Service is shared by all Dist BATCH / Creo on this PC.
rem To also stop creo-batch PowerShell runners (frozen app / manual cleanup), use emergency_kill.bat.

for %%p in (pro_comm_msg dbatchs dbatchc dsq xtop) do (
    taskkill /F /IM %%p.exe /T >nul 2>&1
)

endlocal
