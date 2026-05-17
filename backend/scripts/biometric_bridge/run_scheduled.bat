@echo off
cd /d "%~dp0"
python agent.py --once >> agent_scheduled.log 2>&1
