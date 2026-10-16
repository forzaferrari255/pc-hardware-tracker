@echo off
REM Windows: run one collection (use after venv + config.json ready)
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat (
  call .venv\Scripts\activate.bat
) else (
  echo Create venv first: python -m venv .venv ^&^& .venv\Scripts\activate ^&^& pip install -r requirements-local.txt
  exit /b 1
)
python collect_once.py -c config.json %*
