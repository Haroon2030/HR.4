@echo off
title HR - تثبيت وكيل فرع
cd /d "%~dp0"
echo.
echo  تثبيت وكيل البصمة للفرع
echo  - يثبت Python تلقائيا اذا لم يكن موجودا (winget)
echo  - يضيف Python الى PATH
echo  - يسحب من جهاز البصمة ويرفع للسيرفر عبر API
echo.
echo  شغّل كمسؤول: Right-click - Run as administrator
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_branch.ps1" %*
echo.
pause
