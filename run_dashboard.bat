@echo off
setlocal EnableExtensions
title CEM Dashboard

set "PYTHON_EXE="
where python >nul 2>nul
if not errorlevel 1 set "PYTHON_EXE=python"

if "%PYTHON_EXE%"=="" (
  for /d %%D in ("%LocalAppData%\Python\pythoncore-*-64") do (
    if exist "%%~fD\python.exe" set "PYTHON_EXE=%%~fD\python.exe"
  )
)

if "%PYTHON_EXE%"=="" (
  echo ERROR: Python was not found.
  pause
  exit /b 1
)

cd /d "%~dp0"
echo Starting dashboard at http://localhost:5050
start "" http://localhost:5050
"%PYTHON_EXE%" app.py
pause
