@echo off
for %%p in (pro_comm_msg nmsd dbatchs dsq) do (
    taskkill /F /IM %%p.exe /T
)