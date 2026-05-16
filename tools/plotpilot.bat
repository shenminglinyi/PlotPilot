@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0.."

:: ============================================================
::  PlotPilot（墨枢）- AI 小说创作平台 启动器
::  ============================================================
::  双击即用，全自动流程：
::    ① 自动解压 Python（无需安装）
::    ② 自动安装 pip / 创建虚拟环境 / 安装依赖
::    ③ 启动后端服务 + 打开浏览器
::
::  用法:
::    双击本文件          → 自动模式
::    plotpilot.bat pack     → 打包分享
::    plotpilot.bat force    → 强制重启
::  ============================================================

set "MODE=auto"
if not "%~1"=="" (
    if /i "%~1"=="pack"     set "MODE=pack"
    if /i "%~1"=="p"        set "MODE=pack"
    if /i "%~1"=="force"    set "MODE=force"
    if /i "%~1"=="f"        set "MODE=force"
)

:: ════════════════════════════════════
:: Step 0: 确保内嵌 Python 已解压（零配置核心！）
:: ════════════════════════════════════
if not exist "tools\python_embed\python.exe" (
    if exist "tools\python-3.11.9-embed-amd64.zip" (
        echo.
        echo   ┌────────────────────────────────────┐
        echo   │  首次启动：正在准备 Python 环境...   │
        echo   └────────────────────────────────────┘
        echo.

        :: 用 PowerShell 解压（单行命令，避免 ^ 续行符解析问题）
        powershell -NoProfile -Command "Expand-Archive -Path 'tools\python-3.11.9-embed-amd64.zip' -DestinationPath 'tools\python_embed' -Force"
        if errorlevel 1 (
            echo   [ERROR] 解压失败！请手动解压 tools\python-3.11.9-embed-amd64.zip 到 tools\python_embed\
            pause
            exit /b 1
        )
        echo   Python 环境就绪 ✓
    ) else (
        echo   [WARN] 未找到内嵌 Python 包，将使用系统 Python
    )
)

:: ════════════════════════════════════
:: Step 0.5: 为内嵌 Python 自动安装 pip（embeddable 版默认无 pip）
:: ════════════════════════════════════
if exist "tools\python_embed\python.exe" (
    "tools\python_embed\python.exe" -m pip --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo   ┌────────────────────────────────────┐
        echo   │  首次启动：正在为内嵌 Python 安装 pip... │
        echo   └────────────────────────────────────┘
        echo.

        :: 下载 get-pip.py（如果不存在）
        if not exist "tools\python_embed\get-pip.py" (
            echo   正在下载 get-pip.py...
            "tools\python_embed\python.exe" -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', r'tools\python_embed\get-pip.py'); print('OK')" >nul 2>&1
        )

        :: 安装 pip
        if exist "tools\python_embed\get-pip.py" (
            "tools\python_embed\python.exe" "tools\python_embed\get-pip.py" --no-warn-script-location -q
            if errorlevel 1 (
                echo   [WARN] pip 自动安装失败，将尝试继续...
            ) else (
                echo   pip 安装完成 ✓
                :: 清理临时文件
                del /f "tools\python_embed\get-pip.py" 2>nul
            )
        ) else (
            echo   [WARN] get-pip.py 下载失败，请检查网络连接
        )
    )
)

:: ════════════════════════════════════
:: Step 1: 查找 Python（优先级：venv > 内嵌 > 系统）
:: ════════════════════════════════════
set "PYTHON_EXE="

:: A) 虚拟环境
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    goto :python_found
)

:: B) 内嵌 Python（已解压）
if exist "tools\python_embed\python.exe" (
    set "PYTHON_EXE=tools\python_embed\python.exe"
    :: 设置 Tcl/Tk 环境变量（嵌入版需要）
    set "TCL_LIBRARY=%CD%\tools\python_embed\tcl\tcl8.6"
    set "TK_LIBRARY=%CD%\tools\python_embed\tcl\tk8.6"
    goto :python_found
)

:: C) 系统 PATH
for /f "delims=" %%i in ('where python 2^>nul') do (
    set "PYTHON_EXE=%%i"
    goto :python_found
)

:: D) 都没有 → 引导安装
:python_not_found
echo.
echo   +======================================================+
echo   |                                                      |
echo   |     [X]  Python NOT found                             |
echo   |                                                      |
echo   +------------------------------------------------------+
echo   |  请选择以下任一方式：                                  |
echo   |                                                      |
echo   |  方式 A (推荐): 将 python-3.11.9-embed-amd64.zip      |
echo   |            放到 tools/ 目录下，然后重新双击           |
echo   |                                                      |
echo   |  方式 B: 安装 Python 3.10+ (勾选 Add to PATH)         |
echo   |          https://www.python.org/downloads/            |
echo   |                                                      |
echo   +======================================================+
echo.
pause
exit /b 1

:python_found

:: ════════════════════════════════════
:: Step 2: 验证 Python 可用
:: ════════════════════════════════════
"%PYTHON_EXE%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] Python 存在但无法运行: %PYTHON_EXE%
    pause
    exit /b 1
)

:: ════════════════════════════════════
:: Step 3: 确保目录存在
:: ════════════════════════════════════
if not exist "logs"          mkdir logs
if not exist "data\chromadb"  mkdir data\chromadb
if not exist "data\logs"     mkdir data\logs

:: ════════════════════════════════════
:: Step 3.5: 清理残留进程（防止端口占用）
:: ════════════════════════════════════
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8005 .*LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8006 .*LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

:: ════════════════════════════════════
:: Step 4: 启动独立的 GUI 窗口（核心魔法！）
:: ════════════════════════════════════
::  ① 用 pythonw.exe（无控制台版）启动 Tkinter
::  ② 用 start "" 把 GUI 进程彻底分离，bat 不等待
::  ③ bat 立即 exit，黑框消失，GUI 独立存活

:: 安全提取目录（%~dpI 处理带空格/特殊字符的路径极其稳健）
for %%I in ("%PYTHON_EXE%") do set "PYTHON_DIR=%%~dpI"
set "PYTHONW_EXE=%PYTHON_DIR%pythonw.exe"

:: 检查 pythonw 是否存在，不存在则回退 python.exe
if not exist "%PYTHONW_EXE%" (
    echo   [WARN] 未找到 pythonw.exe，将使用 python.exe（可能附带终端窗口）
    set "PYTHONW_EXE=%PYTHON_EXE%"
)

echo.
echo   ┌────────────────────────────────────┐
echo   │  正在启动 PlotPilot（墨枢）...      │
echo   └────────────────────────────────────┘
echo.

:: ★ 核心魔法：start "" 分离进程 ★
:: 第一个 "" 是 start 的窗口标题（必须留空！否则路径会被误解析为标题）
:: start 之后 bat 立即 exit，不再等待 GUI 关闭
start "" "%PYTHONW_EXE%" -u scripts\install\hub.py %MODE% 2>logs\hub_error.log

:: bat 在这里就结束了，用户只会看到独立的 Tkinter 窗口
exit /b 0
