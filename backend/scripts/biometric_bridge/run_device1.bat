@echo off
cd /d "%~dp0"
python agent.py --once --device 1 %*
