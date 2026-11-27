@echo off
REM One-click start for Windows. Run from the project folder.
cd /d "%~dp0backend"
if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
if not exist .env (
  copy .env.example .env >nul
  echo.
  echo Created backend\.env - set NEO4J_PASSWORD in it, save, then run this file again.
  notepad .env
  pause
  exit /b
)
python app.py
pause
