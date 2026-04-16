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

    Write-Host "[INFO] 检查端口 $Port..." -ForegroundColor Cyan

    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue

    $listeningConn = $connections | Where-Object { $_.State -eq 'Listen' }
    $timeWaitConn = $connections | Where-Object { $_.State -eq 'TimeWait' }

    if ($timeWaitConn) {
        Write-Host "[*] 端口 $Port 有 TIME_WAIT 连接（会自动清理）" -ForegroundColor Cyan
    }

    if ($listeningConn) {
        Write-Host "[*] 端口 $Port 已被占用（监听中）" -ForegroundColor Yellow

        foreach ($conn in $listeningConn) {
            $procId = $conn.OwningProcess

            if ($procId -eq 0) {
                Write-Host "  PID=0 系统保留，跳过" -ForegroundColor Gray
                continue
            }

            if ($procId -eq 4) {
                Write-Host "  PID=4 系统进程，无法终止" -ForegroundColor Gray
                continue
            }

            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) {
                $procName = $proc.ProcessName
                Write-Host "  PID=$procId ($procName)" -ForegroundColor Yellow
            }
            else {
                Write-Host "  PID=$procId (进程不存在，可能是僵尸连接)" -ForegroundColor Yellow
            }

            $confirm = Read-Host "  确认终止？[y/N]"
            if ($confirm -match '^[Yy]$') {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Write-Host "  [OK] 已终止 PID=$procId" -ForegroundColor Green
            }
            else {
                Write-Host "  [*] 已跳过" -ForegroundColor Gray
            }
        }
        Start-Sleep -Milliseconds 500
    }
    else {
        Write-Host "[OK] 端口 $Port 可用" -ForegroundColor Green
    }
}

function Show-Menu {
    Clear-Host
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  PlotPilot (PlotPilot) Startup Menu" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  1. Start both services (backend+frontend)"
    Write-Host "  2. Start backend service"
    Write-Host "  3. Start frontend dev server"
    Write-Host "  4. Start Qdrant via Docker"
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
    $startQdrant = Read-Host "Qdrant vector DB for semantic search, start? [y/N]"

    if ($startQdrant -match '^[Yy]$') {
        Write-Host "[*] Starting Qdrant..." -ForegroundColor Yellow
        $null = Start-Qdrant
        Start-Sleep -Seconds 2
    }
    else {
        Write-Host "[OK] Skipping Qdrant" -ForegroundColor Green
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
    Write-Host "[OK] Starting backend service..." -ForegroundColor Green

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
    Write-Host "[OK] Starting frontend dev server..." -ForegroundColor Green

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
    Write-Host "[OK] Starting Qdrant vector database..." -ForegroundColor Green

    $dockerCmd = $null

    $dockerExe = Get-Command docker -ErrorAction SilentlyContinue
    if ($dockerExe) {
        $dockerInfo = & docker info 2>$null
        if ($LASTEXITCODE -eq 0) {
            $dockerCmd = "docker"
        }
    }

    if (-not $dockerCmd) {
        $Script:LastError = "Cannot access Docker"
        $Script:HasError = $true
        Write-Host "[!] Cannot access Docker, check Docker installation" -ForegroundColor Red
        Write-Host "[*] Tip: Try 'sudo usermod -aG docker $USER'" -ForegroundColor Yellow
        Pause-OnError
        return $false
    }

    Write-Host "[INFO] Checking Docker service status..." -ForegroundColor Cyan
    $dockerCheck = & docker info 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[*] Docker not running, trying to start..." -ForegroundColor Yellow

        $serviceCmd = Get-Command systemctl -ErrorAction SilentlyContinue
        if ($serviceCmd) {
            Write-Host "[*] Using systemctl to start Docker..." -ForegroundColor Yellow
            sudo systemctl start docker
        }
        else {
            $serviceCmd = Get-Command service -ErrorAction SilentlyContinue
            if ($serviceCmd) {
                Write-Host "[*] Using service to start Docker..." -ForegroundColor Yellow
                sudo service docker start
            }
            else {
                $Script:LastError = "Cannot auto-start Docker"
                $Script:HasError = $true
                Write-Host "[!] Cannot auto-start Docker, please start manually" -ForegroundColor Red
                Write-Host "[*] Run 'sudo systemctl start docker' or 'sudo service docker start'" -ForegroundColor Yellow
                Pause-OnError
                return $false
            }
        }

        Start-Sleep -Seconds 3

        $dockerCheck = & docker info 2>$null
        if ($LASTEXITCODE -ne 0) {
            $Script:LastError = "Docker start failed"
            $Script:HasError = $true
            Write-Host "[!] Docker start failed, please start manually" -ForegroundColor Red
            Pause-OnError
            return $false
        }
    }

    $composeFile = Join-Path $ScriptDir "docker-compose.yml"
    if (Test-Path $composeFile) {
        Write-Host "[OK] Starting Qdrant..." -ForegroundColor Green
        & docker compose up -d
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Qdrant started at http://localhost:6333" -ForegroundColor Green
        }
        else {
            $Script:LastError = "Qdrant start failed, check Docker logs"
            $Script:HasError = $true
            Write-Host "[!] Qdrant start failed, check Docker logs" -ForegroundColor Red
            Pause-OnError
            return $false
        }
    }
    else {
        Write-Host "[*] docker-compose.yml not found, skipping Qdrant" -ForegroundColor Yellow
    }

    return $true
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
