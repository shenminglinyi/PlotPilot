# PlotPilot startup menu
# 墨枢 - AI driven long novel creation platform

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptDir) {
    $ScriptDir = $PSScriptRoot
}
Set-Location $ScriptDir
$env:PYTHONIOENCODING = "utf-8"

$ErrorActionPreference = "Continue"
$Script:LastError = $null
$Script:HasError = $false

function Pause-OnError {
    if ($Script:HasError) {
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Red
        Write-Host "  [ERROR] Script execution paused" -ForegroundColor Red
        Write-Host "========================================" -ForegroundColor Red
        if ($Script:LastError) {
            Write-Host "Error: $Script:LastError" -ForegroundColor Red
        }
        Write-Host ""
        Write-Host "Press Enter to continue or Ctrl+C to exit..." -ForegroundColor Yellow
        Read-Host
        $Script:HasError = $false
        $Script:LastError = $null
    }
}

function Ensure-Uv {
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCmd) {
        $uvVersion = & uv --version 2>$null
        Write-Host "[OK] uv installed: $uvVersion" -ForegroundColor Green
        return $true
    }

    Write-Host "[*] uv not found, installing..." -ForegroundColor Yellow

    try {
        $installScript = Invoke-WebRequest -Uri "https://astral.sh/uv/install.sh" -UseBasicParsing -TimeoutSec 30
        if ($LASTEXITCODE -eq 0 -or $installScript) {
            $tempScript = "$env:TEMP\uv_install.ps1"
            $installScript.Content | Out-File -FilePath $tempScript -Encoding UTF8
            & powershell -ExecutionPolicy Bypass -File $tempScript
            Remove-Item $tempScript -Force -ErrorAction SilentlyContinue

            if (Get-Command uv -ErrorAction SilentlyContinue) {
                Write-Host "[OK] uv installed: $(& uv --version)" -ForegroundColor Green
                return $true
            }
        }
    }
    catch {
        $Script:LastError = $_.Exception.Message
        $Script:HasError = $true
        Write-Host "[*] Official install script failed, trying pip..." -ForegroundColor Yellow
    }

    $pipCmd = Get-Command pip -ErrorAction SilentlyContinue
    if (-not $pipCmd) {
        $pipCmd = Get-Command pip3 -ErrorAction SilentlyContinue
    }

    if ($pipCmd) {
        & pip install uv
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] uv installed via pip" -ForegroundColor Green
            return $true
        }
    }

    Write-Host "[!] Cannot install uv, please install manually: https://astral.sh/uv/install.sh" -ForegroundColor Red
    return $false
}

function Free-Port {
    param([int]$Port)

    Write-Host "[INFO] Checking port $Port..." -ForegroundColor Cyan

    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue

    $listeningConn = $connections | Where-Object { $_.State -eq 'Listen' }
    $timeWaitConn = $connections | Where-Object { $_.State -eq 'TimeWait' }

    if ($timeWaitConn) {
        Write-Host "[*] Port $Port has TIME_WAIT connections (will auto-clean)" -ForegroundColor Cyan
    }

    if ($listeningConn) {
        Write-Host "[*] Port $Port is in use (Listen)" -ForegroundColor Yellow

        foreach ($conn in $listeningConn) {
            $procId = $conn.OwningProcess

            if ($procId -eq 0) {
                Write-Host "  PID=0 reserved, skipped" -ForegroundColor Gray
                continue
            }

            if ($procId -eq 4) {
                Write-Host "  PID=4 System, cannot terminate" -ForegroundColor Gray
                continue
            }

            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) {
                $procName = $proc.ProcessName
                Write-Host "  PID=$procId ($procName)" -ForegroundColor Yellow
            }
            else {
                Write-Host "  PID=$procId (process not found, may be zombie)" -ForegroundColor Yellow
            }

            $confirm = Read-Host "  Kill this process? [y/N]"
            if ($confirm -match '^[Yy]$') {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Write-Host "  [OK] Terminated PID=$procId" -ForegroundColor Green
            }
            else {
                Write-Host "  [*] Skipped" -ForegroundColor Gray
            }
        }
        Start-Sleep -Milliseconds 500
    }
    else {
        Write-Host "[OK] Port $Port is free" -ForegroundColor Green
    }
}

function Show-Menu {
    Clear-Host
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  PlotPilot (PlotPilot) Startup Menu" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  1. Start both services (backend+frontend)"
    Write-Host "  2. Backend (Start or Kill)"
    Write-Host "  3. Frontend (Start or Kill)"
    Write-Host "  4. Qdrant (Start or Kill)"
    Write-Host "  5. Run tests"
    Write-Host "  6. Lazy install (one-click setup)"
    Write-Host ""
    Write-Host "  0. Exit"
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
}

function Ask-Reinstall {
    param($DirName, $DirPath)

    Write-Host "[*] Detected existing $DirName`: $DirPath" -ForegroundColor Yellow
    Write-Host "  Enter) Skip and keep existing"
    Write-Host "  9) Delete and recreate"
    $choice = Read-Host "Please choose [skip/9]"

    switch ($choice) {
        "9" {
            Write-Host "[*] Deleting $DirPath..." -ForegroundColor Yellow
            Remove-Item -Path $DirPath -Recurse -Force -ErrorAction SilentlyContinue
            return $true
        }
        default {
            Write-Host "[OK] Skipped $DirName installation" -ForegroundColor Green
            return $false
        }
    }
}

function Check-BackendReady {
    $maxAttempts = 30
    $attempt = 1

    Write-Host "[INFO] Checking backend service status..." -ForegroundColor Cyan

    while ($attempt -le $maxAttempts) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8005/docs" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                Write-Host "[OK] Backend service is ready!" -ForegroundColor Green
                return $true
            }
        }
        catch {
            try {
                $response = Invoke-WebRequest -Uri "http://127.0.0.1:8005/" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($response.StatusCode -eq 200) {
                    Write-Host "[OK] Backend service is ready!" -ForegroundColor Green
                    return $true
                }
            }
            catch { }
        }

        Write-Host "[*] Waiting for backend... ($attempt/$maxAttempts)" -ForegroundColor Yellow
        Start-Sleep -Seconds 2
        $attempt++
    }

    Write-Host "[!] Backend startup timeout, check backend.log" -ForegroundColor Red
    return $false
}

function Start-Both {
    Write-Host ""
    Write-Host "[OK] Starting both services (backend+frontend)..." -ForegroundColor Green

    Write-Host ""
    Write-Host "[0/2] Vector database configuration..." -ForegroundColor Cyan
    $qdrantConn = Get-NetTCPConnection -LocalPort 6333 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
    if ($qdrantConn) {
        $prevPid = $qdrantConn[0].OwningProcess
        $proc = Get-Process -Id $prevPid -ErrorAction SilentlyContinue
        $procName = if ($proc) { $proc.ProcessName } else { "Unknown" }
        Write-Host "[OK] Qdrant already running (PID=$prevPid, $procName)" -ForegroundColor Green
        $startQdrant = "2"
    }
    else {
        $startQdrant = Read-Host "Qdrant not running. Start Qdrant? [1]"
        if ($startQdrant -ne "1") {
            Write-Host "[OK] Skipping Qdrant" -ForegroundColor Green
        }
    }

    if ($startQdrant -eq "1") {
        Write-Host "[*] Starting Qdrant..." -ForegroundColor Yellow
        $null = Start-Qdrant
        Start-Sleep -Seconds 2
    }

    Write-Host ""
    Write-Host "[1/2] Starting backend..." -ForegroundColor Cyan
    Free-Port -Port 8005

    if (-not (Ensure-Uv)) {
        $Script:LastError = "uv installation failed"
        $Script:HasError = $true
        Write-Host "[!] uv install failed, cannot continue" -ForegroundColor Red
        Pause-OnError
        return
    }

    $venvPath = Join-Path $ScriptDir ".venv"
    if (Test-Path $venvPath) {
        Write-Host "[INFO] Detected venv, activating..." -ForegroundColor Cyan
        & "$venvPath\Scripts\Activate.ps1" 2>$null
    }

    $uvicornCmd = Get-Command uvicorn -ErrorAction SilentlyContinue
    if (-not $uvicornCmd) {
        $Script:LastError = "uvicorn not found"
        $Script:HasError = $true
        Write-Host "[!] uvicorn not found, install deps: uv pip install -r requirements.txt" -ForegroundColor Red
        Pause-OnError
        return
    }

    Write-Host "[OK] Backend starting (http://localhost:8005)..." -ForegroundColor Green

    $backendLog = Join-Path $ScriptDir "backend.log"
    $backendJob = Start-Job -ScriptBlock {
        param($ScriptDir, $BackendLog)
        Set-Location $ScriptDir
        $env:PYTHONIOENCODING = "utf-8"
        uvicorn interfaces.main:app --host 0.0.0.0 --port 8005 --reload 2>&1 | Out-File -FilePath $BackendLog -Encoding UTF8
    } -ArgumentList $ScriptDir, $backendLog

    Write-Host "[INFO] Backend Job ID: $($backendJob.Id)" -ForegroundColor Cyan

    Write-Host ""
    Write-Host "[2/2] Starting frontend..." -ForegroundColor Cyan
    Free-Port -Port 3000

    $frontendDir = Join-Path $ScriptDir "frontend"
    if (-not (Test-Path $frontendDir)) {
        $Script:LastError = "Frontend directory not found: $frontendDir"
        $Script:HasError = $true
        Write-Host "[!] Frontend directory not found: $frontendDir" -ForegroundColor Red
        Stop-Job -Job $backendJob -ErrorAction SilentlyContinue
        Pause-OnError
        return
    }

    Set-Location $frontendDir

    if (-not (Test-Path "$frontendDir\node_modules")) {
        Write-Host "[*] node_modules not found, installing..." -ForegroundColor Yellow
        npm install
        if ($LASTEXITCODE -ne 0) {
            $Script:LastError = "npm install failed with exit code $LASTEXITCODE"
            $Script:HasError = $true
            Write-Host "[!] npm install failed" -ForegroundColor Red
            Stop-Job -Job $backendJob -ErrorAction SilentlyContinue
            Set-Location $ScriptDir
            Pause-OnError
            return
        }
    }

    if (-not (Check-BackendReady)) {
        $continueFrontend = Read-Host "Backend not ready, continue starting frontend? [y/N]"
        if ($continueFrontend -notmatch '^[Yy]$') {
            Stop-Job -Job $backendJob -ErrorAction SilentlyContinue
            Set-Location $ScriptDir
            return
        }
    }

    Write-Host "[OK] Frontend dev server starting..." -ForegroundColor Green
    Write-Host "[INFO] Press Ctrl+C to stop" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[OK] Backend: http://localhost:8005" -ForegroundColor Green
    Write-Host "[OK] Frontend: http://localhost:3000" -ForegroundColor Green
    if ($startQdrant -match '^[Yy]$') {
        Write-Host "[OK] Qdrant: http://localhost:6333" -ForegroundColor Green
    }
    Write-Host ""
    Write-Host "[*] Note: Backend is running in background" -ForegroundColor Yellow
    Write-Host ""

    Set-Location $frontendDir

    $viteExe = Join-Path $frontendDir "node_modules\.bin\vite.cmd"
    if (-not (Test-Path $viteExe)) {
        $Script:LastError = "vite not found in node_modules, run npm install first"
        $Script:HasError = $true
        Write-Host "[!] vite not found, please run 'npm install' in frontend directory" -ForegroundColor Red
        Set-Location $ScriptDir
        Pause-OnError
        return
    }

    npm run dev

    Set-Location $ScriptDir
}

function Start-Backend {
    Write-Host ""
    Write-Host "[OK] Backend (Start or Kill)..." -ForegroundColor Green

    $backendConn = Get-NetTCPConnection -LocalPort 8005 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
    $runningBackend = $null
    if ($backendConn) {
        $prevPid = $backendConn[0].OwningProcess
        $proc = Get-Process -Id $prevPid -ErrorAction SilentlyContinue
        if ($proc) {
            $runningBackend = @{Pid=$prevPid; Name=$proc.ProcessName}
        }
    }

    Write-Host "  1) Start backend"
    if ($runningBackend) {
        Write-Host "  2) Kill backend (PID=$($runningBackend.Pid), $($runningBackend.Name))"
    }
    $choice = Read-Host "Choose [1]"
    if ($choice -eq "2" -and $runningBackend) {
        Stop-Process -Id $runningBackend.Pid -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Backend process terminated" -ForegroundColor Green
        Start-Sleep -Milliseconds 500
    }
    if ($choice -ne "1" -and -not ($choice -eq "2" -and $runningBackend)) {
        Write-Host "[*] Cancelled" -ForegroundColor Yellow
        return
    }

    Free-Port -Port 8005

    if (-not (Ensure-Uv)) {
        Write-Host "[!] uv install failed, cannot continue" -ForegroundColor Red
        return
    }

    $venvPath = Join-Path $ScriptDir ".venv"
    if (Test-Path $venvPath) {
        Write-Host "[INFO] Detected venv, activating..." -ForegroundColor Cyan
        & "$venvPath\Scripts\Activate.ps1" 2>$null
    }

    $uvicornCmd = Get-Command uvicorn -ErrorAction SilentlyContinue
    if (-not $uvicornCmd) {
        $Script:LastError = "uvicorn not found"
        $Script:HasError = $true
        Write-Host "[!] uvicorn not found, install deps: uv pip install -r requirements.txt" -ForegroundColor Red
        Pause-OnError
        return
    }

    Write-Host "[OK] Backend starting (http://localhost:8005)..." -ForegroundColor Green
    Write-Host "[INFO] Press Ctrl+C to stop" -ForegroundColor Gray
    Write-Host ""

    Set-Location $ScriptDir
    $env:PYTHONIOENCODING = "utf-8"

    try {
        uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload
    }
    catch {
        $Script:LastError = $_.Exception.Message
        $Script:HasError = $true
        Write-Host "[!] Backend error: $_" -ForegroundColor Red
        Pause-OnError
    }
}

function Start-Frontend {
    Write-Host ""
    Write-Host "[OK] Frontend (Start or Kill)..." -ForegroundColor Green

    $frontendConn = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
    $runningFrontend = $null
    if ($frontendConn) {
        $prevPid = $frontendConn[0].OwningProcess
        $proc = Get-Process -Id $prevPid -ErrorAction SilentlyContinue
        if ($proc) {
            $runningFrontend = @{Pid=$prevPid; Name=$proc.ProcessName}
        }
    }

    Write-Host "  1) Start frontend"
    if ($runningFrontend) {
        Write-Host "  2) Kill frontend (PID=$($runningFrontend.Pid), $($runningFrontend.Name))"
    }
    $choice = Read-Host "Choose [1]"
    if ($choice -eq "2" -and $runningFrontend) {
        Stop-Process -Id $runningFrontend.Pid -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Frontend process terminated" -ForegroundColor Green
        Start-Sleep -Milliseconds 500
    }
    if ($choice -ne "1" -and -not ($choice -eq "2" -and $runningFrontend)) {
        Write-Host "[*] Cancelled" -ForegroundColor Yellow
        return
    }

    Free-Port -Port 3000

    $frontendDir = Join-Path $ScriptDir "frontend"
    if (-not (Test-Path $frontendDir)) {
        $Script:LastError = "Frontend directory not found: $frontendDir"
        $Script:HasError = $true
        Write-Host "[!] Frontend directory not found: $frontendDir" -ForegroundColor Red
        Pause-OnError
        return
    }

    Set-Location $frontendDir

    if (-not (Test-Path "$frontendDir\node_modules")) {
        Write-Host "[*] node_modules not found, installing..." -ForegroundColor Yellow
        npm install
        if ($LASTEXITCODE -ne 0) {
            $Script:LastError = "npm install failed with exit code $LASTEXITCODE"
            $Script:HasError = $true
            Write-Host "[!] npm install failed" -ForegroundColor Red
            Set-Location $ScriptDir
            Pause-OnError
            return
        }
    }

    Write-Host "[OK] Frontend dev server starting..." -ForegroundColor Green
    Write-Host "[INFO] Press Ctrl+C to stop" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[OK] Frontend: http://localhost:3000" -ForegroundColor Green
    Write-Host ""

    $viteExe = Join-Path $frontendDir "node_modules\.bin\vite.cmd"
    if (-not (Test-Path $viteExe)) {
        $Script:LastError = "vite not found in node_modules"
        $Script:HasError = $true
        Write-Host "[!] vite not found, please run 'npm install' in frontend directory" -ForegroundColor Red
        Set-Location $ScriptDir
        Pause-OnError
        return
    }

    npm run dev

    Set-Location $ScriptDir
}

function Run-Tests {
    Write-Host ""
    Write-Host "[OK] Running tests..." -ForegroundColor Green

    $testsDir = Join-Path $ScriptDir "tests"
    if (-not (Test-Path $testsDir)) {
        Write-Host "[*] tests directory not found: $testsDir" -ForegroundColor Yellow
        Write-Host "[*] Checking for other test files..." -ForegroundColor Cyan

        $pytestCmd = Get-Command pytest -ErrorAction SilentlyContinue
        if ($pytestCmd) {
            Write-Host "[OK] pytest found, running..." -ForegroundColor Green
            pytest -v
        }
        else {
            Write-Host "[!] pytest not found, install: uv pip install pytest" -ForegroundColor Red
        }
        return
    }

    $venvPath = Join-Path $ScriptDir ".venv"
    if (Test-Path $venvPath) {
        & "$venvPath\Scripts\Activate.ps1" 2>$null
    }

    Write-Host "[OK] Running unit and integration tests..." -ForegroundColor Green
    pytest "$testsDir\unit" "$testsDir\integration" -v
}

function Start-Qdrant {
    Write-Host ""
    Write-Host "[OK] Qdrant (Start or Kill)..." -ForegroundColor Green

    $qdrantConn = Get-NetTCPConnection -LocalPort 6333 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
    $runningQdrant = $null
    if ($qdrantConn) {
        $prevPid = $qdrantConn[0].OwningProcess
        $proc = Get-Process -Id $prevPid -ErrorAction SilentlyContinue
        if ($proc) {
            $runningQdrant = @{Pid=$prevPid; Name=$proc.ProcessName}
        }
    }

    Write-Host "  1) Start Qdrant"
    if ($runningQdrant) {
        Write-Host "  2) Kill Qdrant (PID=$($runningQdrant.Pid), $($runningQdrant.Name))"
    }
    $choice = Read-Host "Choose [1]"
    if ($choice -eq "2" -and $runningQdrant) {
        Stop-Process -Id $runningQdrant.Pid -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Qdrant process terminated" -ForegroundColor Green
        Start-Sleep -Milliseconds 500
    }
    if ($choice -ne "1" -and -not ($choice -eq "2" -and $runningQdrant)) {
        Write-Host "[*] Cancelled" -ForegroundColor Yellow
        return $false
    }

    $qdrantDir = Join-Path $ScriptDir "qdrant"
    $qdrantExe = Join-Path $qdrantDir "qdrant.exe"
    $qdrantConfig = Join-Path $qdrantDir "config.yaml"
    $zipUrl = "https://github.com/qdrant/qdrant/releases/download/v1.17.1/qdrant-x86_64-pc-windows-msvc.zip"
    $zipFile = Join-Path $qdrantDir "qdrant-x86_64-pc-windows-msvc.zip"

    if (-not (Test-Path $qdrantDir)) {
        New-Item -ItemType Directory -Path $qdrantDir -Force | Out-Null
    }

    if (-not (Test-Path $qdrantConfig)) {
        Write-Host "[*] Creating config.yaml..." -ForegroundColor Yellow
        @"
host: 0.0.0.0
port: 6333

service:
  http_port: 6333
  grpc_port: 6334

cluster:
  enabled: false

storage:
  snapshots_path: qdrant/snapshots
  storage_path: qdrant/storage
  temp_path: qdrant/tmp
"@ | Out-File -FilePath $qdrantConfig -Encoding UTF8
    }

    if (-not (Test-Path $qdrantExe)) {
        Write-Host "[*] Qdrant not found..." -ForegroundColor Yellow
        if (-not (Test-Path $zipFile)) {
            Write-Host "[*] Downloading Qdrant from GitHub..." -ForegroundColor Yellow
            try {
                Invoke-WebRequest -Uri $zipUrl -OutFile $zipFile -UseBasicParsing -TimeoutSec 300
            }
            catch {
                $Script:LastError = "Failed to download Qdrant: " + $_.Exception.Message
                $Script:HasError = $true
                Write-Host "[!] Failed to download Qdrant: $_" -ForegroundColor Red
                Pause-OnError
                return $false
            }
        }
        Write-Host "[*] Extracting Qdrant..." -ForegroundColor Yellow
        Expand-Archive -Path $zipFile -DestinationPath $qdrantDir -Force

        if (-not (Test-Path $qdrantExe)) {
            $extractedFiles = Get-ChildItem -Path $qdrantDir -Recurse -Filter "qdrant.exe" -ErrorAction SilentlyContinue
            if ($extractedFiles) {
                Move-Item -Path $extractedFiles[0].FullName -Destination $qdrantExe -Force
            }
        }
        Write-Host "[OK] Qdrant downloaded and extracted" -ForegroundColor Green
    }

    $confirm = Read-Host "Start Qdrant? [y/N]"
    if (-not ($confirm -match '^[Yy]$')) {
        Write-Host "[*] Qdrant start cancelled" -ForegroundColor Yellow
        return $false
    }

    Write-Host "[*] Starting Qdrant..." -ForegroundColor Yellow
    $qdrantLog = Join-Path $qdrantDir "qdrant.log"
    $qdrantProcess = Start-Process -FilePath $qdrantExe -ArgumentList "--config-path", $qdrantConfig -PassThru -RedirectStandardError $qdrantLog -WindowStyle Hidden
    Start-Sleep -Seconds 5

    if ($qdrantProcess -and -not $qdrantProcess.HasExited) {
        Write-Host "[OK] Qdrant started at http://localhost:6333" -ForegroundColor Green
        return $true
    }
    else {
        $Script:LastError = "Qdrant failed to start"
        $Script:HasError = $true
        Write-Host "[!] Qdrant failed to start" -ForegroundColor Red
        if (Test-Path $qdrantLog) {
            $errorContent = Get-Content $qdrantLog -Raw -ErrorAction SilentlyContinue
            if ($errorContent) {
                Write-Host "[!] Error details: $errorContent" -ForegroundColor Red
            }
        }
        Write-Host "[*] Check $qdrantLog for details" -ForegroundColor Yellow
        Pause-OnError
        return $false
    }
}

function Lazy-Install {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Magenta
    Write-Host "  Lazy Install - One-click Setup" -ForegroundColor Magenta
    Write-Host "========================================" -ForegroundColor Magenta

    Set-Location $ScriptDir
    Write-Host "[INFO] Project root: $ScriptDir" -ForegroundColor Cyan

    Write-Host ""
    Write-Host "[2/7] Checking and installing uv..." -ForegroundColor Cyan
    if (-not (Ensure-Uv)) {
        $Script:LastError = "uv installation failed"
        $Script:HasError = $true
        Write-Host "[!] uv install failed, cannot continue" -ForegroundColor Red
        Pause-OnError
        return 1
    }

    Write-Host ""
    Write-Host "[3/7] Creating virtual environment..." -ForegroundColor Cyan
    $venvPath = Join-Path $ScriptDir ".venv"

    if (Test-Path $venvPath) {
        if (-not (Ask-Reinstall -DirName "Virtual Environment" -DirPath $venvPath)) {
            Write-Host "[OK] Using existing venv" -ForegroundColor Green
        }
        else {
            Write-Host "[*] Creating venv with uv..." -ForegroundColor Yellow
            uv venv --clear $venvPath
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[!] venv creation failed, continuing anyway" -ForegroundColor Red
            }
            else {
                Write-Host "[OK] venv created" -ForegroundColor Green
            }
        }
    }
    else {
        Write-Host "[*] Creating venv with uv..." -ForegroundColor Yellow
        uv venv $venvPath
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[!] venv creation failed, continuing anyway" -ForegroundColor Red
        }
        else {
            Write-Host "[OK] venv created" -ForegroundColor Green
        }
    }

    Write-Host "[INFO] Activating venv..." -ForegroundColor Cyan
    & "$venvPath\Scripts\Activate.ps1" 2>$null

    Write-Host ""
    Write-Host "[4/7] Checking env config..." -ForegroundColor Cyan
    $envFile = Join-Path $ScriptDir ".env"
    $envExample = Join-Path $ScriptDir ".env.example"

    if (Test-Path $envFile) {
        Write-Host "[OK] .env exists" -ForegroundColor Green
    }
    else {
        if (Test-Path $envExample) {
            Write-Host "[*] Copying .env.example to .env..." -ForegroundColor Yellow
            Copy-Item -Path $envExample -Destination $envFile
            Write-Host "[OK] .env created, please edit and add API keys!" -ForegroundColor Green
        }
        else {
            Write-Host "[*] .env.example not found, skipping" -ForegroundColor Yellow
        }
    }

    Write-Host ""
    Write-Host "[5/7] Installing Python dependencies..." -ForegroundColor Cyan
    $requirementsFile = Join-Path $ScriptDir "requirements.txt"

    if (Test-Path $requirementsFile) {
        uv pip install -r $requirementsFile
        if ($LASTEXITCODE -ne 0) {
            $Script:LastError = "Python dependencies install failed"
            $Script:HasError = $true
            Write-Host "[!] pip install failed" -ForegroundColor Red
            Pause-OnError
        }
        else {
            Write-Host "[OK] Python dependencies installed" -ForegroundColor Green
        }
    }
    else {
        Write-Host "[*] requirements.txt not found, skipping" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "[6/7] Downloading embedding model..." -ForegroundColor Cyan

    $modelCacheDir = Join-Path $env:USERPROFILE ".cache\huggingface\hub"
    $modelExists = $false

    if (Test-Path $modelCacheDir) {
        $modelDirs = Get-ChildItem -Path $modelCacheDir -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*bge-small-zh*" }
        if ($modelDirs) {
            $modelExists = $true
            Write-Host "[OK] Embedding model already exists, skipping" -ForegroundColor Green
        }
    }

    if (-not $modelExists) {
        Write-Host "[*] Choose model download method:" -ForegroundColor Yellow
        Write-Host "  1) Hugging Face (download_embedding_model.py)"
        Write-Host "  2) ModelScope (download_model_via_modelscope.py) - CN recommended"
        $modelChoice = Read-Host "Choose [1-2]"

        switch ($modelChoice) {
            "1" {
                $modelScript = Join-Path $ScriptDir "scripts\utils\download_embedding_model.py"
                Write-Host "[OK] Using Hugging Face..." -ForegroundColor Green
            }
            default {
                $modelScript = Join-Path $ScriptDir "scripts\utils\download_model_via_modelscope.py"
                Write-Host "[OK] Using ModelScope..." -ForegroundColor Green

                $pipCmd = Get-Command pip -ErrorAction SilentlyContinue
                if (-not $pipCmd) {
                    $pipCmd = Get-Command pip3 -ErrorAction SilentlyContinue
                }

                if (-not $pipCmd) {
                    Write-Host "[*] pip not found in venv, installing..." -ForegroundColor Yellow
                    uv pip install pip
                    if ($LASTEXITCODE -ne 0) {
                        Write-Host "[!] pip install failed, switching to Hugging Face..." -ForegroundColor Red
                        $modelScript = Join-Path $ScriptDir "scripts\utils\download_embedding_model.py"
                        Write-Host "[OK] Using Hugging Face..." -ForegroundColor Green
                    }
                }
            }
        }

        $pythonExe = Join-Path $venvPath "Scripts\python.exe"
        if (Test-Path $pythonExe) {
            if (Test-Path $modelScript) {
                & $pythonExe $modelScript
                if ($LASTEXITCODE -ne 0) {
                    $Script:LastError = "Model download failed, check network"
                    $Script:HasError = $true
                    Write-Host "[!] Model download failed, check network" -ForegroundColor Red
                    Pause-OnError

                    if ($modelScript -like "*modelscope*") {
                        Write-Host "[*] Trying Hugging Face fallback..." -ForegroundColor Yellow
                        $altScript = Join-Path $ScriptDir "scripts\utils\download_embedding_model.py"
                        if (Test-Path $altScript) {
                            & $pythonExe $altScript
                            if ($LASTEXITCODE -eq 0) {
                                Write-Host "[OK] Model downloaded (fallback)" -ForegroundColor Green
                            }
                            else {
                                $Script:LastError = "Model download (Hugging Face fallback) also failed"
                                $Script:HasError = $true
                                Pause-OnError
                            }
                        }
                    }
                }
                else {
                    Write-Host "[OK] Embedding model downloaded" -ForegroundColor Green
                }
            }
            else {
                Write-Host "[!] Model script not found: $modelScript" -ForegroundColor Red

                if ($modelScript -like "*modelscope*") {
                    $altScript = Join-Path $ScriptDir "scripts\utils\download_embedding_model.py"
                    if (Test-Path $altScript) {
                        Write-Host "[*] Trying fallback script: $altScript" -ForegroundColor Yellow
                        & $pythonExe $altScript
                        if ($LASTEXITCODE -eq 0) {
                            Write-Host "[OK] Model downloaded (fallback)" -ForegroundColor Green
                        }
                    }
                }
            }
        }
        else {
            Write-Host "[!] Python not found in venv, skipping model download" -ForegroundColor Red
        }
    }

    Write-Host ""
    Write-Host "[7/7] Installing frontend dependencies..." -ForegroundColor Cyan
    $frontendDir = Join-Path $ScriptDir "frontend"

    if (Test-Path $frontendDir) {
        Set-Location $frontendDir

        if (-not (Test-Path "$frontendDir\node_modules")) {
            Write-Host "[*] Installing frontend dependencies..." -ForegroundColor Yellow
            npm install
            if ($LASTEXITCODE -ne 0) {
                $Script:LastError = "npm install failed"
                $Script:HasError = $true
                Write-Host "[!] npm install failed" -ForegroundColor Red
                Pause-OnError
            }
            else {
                Write-Host "[OK] Frontend dependencies installed" -ForegroundColor Green
            }
        }
        else {
            Write-Host "[OK] Frontend dependencies exist, skipping" -ForegroundColor Green
        }
    }
    else {
        Write-Host "[*] Frontend directory not found, skipping" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Magenta
    Write-Host "  Lazy Install Complete!" -ForegroundColor Magenta
    Write-Host "========================================" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "[OK] Run this script and select option 1 to start services" -ForegroundColor Green

    Set-Location $ScriptDir
}

function Main {
    $exitMenu = $false

    while (-not $exitMenu) {
        Show-Menu
        $choice = Read-Host "Please select"

        $Script:HasError = $false
        $Script:LastError = $null

        switch ($choice) {
            "1" { Start-Both }
            "2" { Start-Backend }
            "3" { Start-Frontend }
            "4" { Start-Qdrant }
            "5" { Run-Tests }
            "6" { Lazy-Install }
            "0" {
                Write-Host "[OK] Exiting" -ForegroundColor Green
                $exitMenu = $true
            }
            default {
                Write-Host "[!] Invalid choice" -ForegroundColor Red
                Start-Sleep -Seconds 1
            }
        }

        if (-not $exitMenu) {
            Pause-OnError
            Write-Host ""
            Write-Host "Press Enter to return to menu..." -ForegroundColor Gray
            Read-Host
        }
    }
}

Main
