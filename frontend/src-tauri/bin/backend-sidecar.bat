@echo off
:: PlotPilot Backend Sidecar
:: 由 Tauri 自动调用，不要手动运行
::
:: 用法: backend-sidecar.bat <port>
::   Tauri 会传入动态分配的端口号

set PORT=%1
if "%PORT%"=="" set PORT=8005

:: 查找 Python（优先内嵌 > venv > 系统）
set "PYTHON_EXE="

if exist "%~dp0..\..\tools\python_embed\python.exe" (
    set "PYTHON_EXE=%~dp0..\..\tools\python_embed\python.exe"
) else if exist "%~dp0..\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"
) else (
    where python >nul 2>&1 && set "PYTHON_EXE=python"
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python not found
    exit /b 1
)

:: 启动 uvicorn
cd /d "%~dp0..\.."
"%PYTHON_EXE%" -m uvicorn interfaces.main:app --host 127.0.0.1 --port %PORT% --log-level info
