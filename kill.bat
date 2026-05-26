@echo off
for %%p in (pro_comm_msg nmsd dbatchs dsq xtop) do (
    taskkill /F /IM %%p.exe /T >nul 2>&1
)