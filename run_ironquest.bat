@echo off
setlocal

cd /d "%~dp0"

set "IRONQUEST_PY=%~dp0ironquest_env\Scripts\python.exe"
set "FITQUEST_WORKER_URL=https://fitquest-garmin.merazmilton9.workers.dev"

if not exist "%IRONQUEST_PY%" (
  echo FitQuest could not find ironquest_env\Scripts\python.exe.
  echo Create or restore the project virtual environment before running this launcher.
  pause
  exit /b 1
)

"%IRONQUEST_PY%" -m ironquest run --web --no-show %*
