@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Emergency only: stop creo-batch PowerShell runners first, then Creo, then nmsd.
rem Do not use this from the batch runner — runners call kill.bat instead.
rem Use when the app is frozen or leftover runners keep relaunching Creo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$procs = Get-CimInstance Win32_Process | Where-Object { ($_.Name -ieq 'powershell.exe' -or $_.Name -ieq 'pwsh.exe') -and $_.CommandLine -and ($_.CommandLine -match 'creo-batch-.*\.ps1') }; foreach ($p in @($procs)) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {} }" >nul 2>&1

call "%~dp0kill.bat"
taskkill /F /IM nmsd.exe /T >nul 2>&1

endlocal
