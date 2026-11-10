@echo off
cd /d "%~dp0"
echo ========================================================
echo  Starting Student Management System (IIT JU)
echo ========================================================
venv\Scripts\python.exe manage.py runserver
pause
