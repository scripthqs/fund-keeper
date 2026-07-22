param(
    [ValidateSet("frontend", "backend", "all", "deps")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"

# === Config ===
$CHINA_SERVER    = "root@1.14.152.133"
$OVERSEAS_SERVER = "root@23.95.169.175"
$REMOTE_BASE     = "/opt/fund-keeper"
$LOCAL_BASE      = "d:\Work\fund-keeper"
$SERVICE_NAME    = "fund-keeper"
$UseProxyJump    = $false

# === Utilities ===
function Write-Step {
    param([string]$Msg)
    Write-Host "`n>>> " -NoNewline -ForegroundColor Cyan
    Write-Host $Msg -ForegroundColor White
}

function Write-OK {
    param([string]$Msg)
    Write-Host "  " -NoNewline
    Write-Host "[OK] " -NoNewline -ForegroundColor Green
    Write-Host $Msg -ForegroundColor Green
}

function Write-FAIL {
    param([string]$Msg)
    Write-Host "  " -NoNewline
    Write-Host "[FAIL] " -NoNewline -ForegroundColor Red
    Write-Host $Msg -ForegroundColor Red
}

function Invoke-Overseas {
    param([string]$Cmd)
    if ($UseProxyJump) {
        ssh -J $CHINA_SERVER $OVERSEAS_SERVER $Cmd
    } else {
        ssh -t $CHINA_SERVER "ssh -t $OVERSEAS_SERVER '$Cmd'"
    }
    if ($LASTEXITCODE -ne 0) { throw "SSH failed: $Cmd" }
}

function Send-ToOverseas {
    param([string]$LocalPath, [string]$RemoteRelPath)
    $chinaPath   = "${CHINA_SERVER}:$REMOTE_BASE/$RemoteRelPath"
    $overseasPath = "${OVERSEAS_SERVER}:$REMOTE_BASE/$RemoteRelPath"
    if ($UseProxyJump) {
        Write-Step "scp directly to overseas..."
        scp -o "ProxyJump $CHINA_SERVER" -r $LocalPath $overseasPath
    } else {
        Write-Step "scp to jump server..."
        scp -r $LocalPath $chinaPath
        if ($LASTEXITCODE -ne 0) { throw "scp to jump server failed" }
        Write-Step "scp from jump to overseas..."
        ssh -t $CHINA_SERVER "scp -r $REMOTE_BASE/$RemoteRelPath $overseasPath"
        if ($LASTEXITCODE -ne 0) { throw "scp to overseas failed" }
    }
    Write-OK "Transfer done"
}

function Restart-Service {
    Write-Step "Restarting backend service..."
    Invoke-Overseas "sudo systemctl restart $SERVICE_NAME"
    Start-Sleep -Seconds 2
    Write-Step "Checking service status..."
    Invoke-Overseas "sudo systemctl is-active $SERVICE_NAME"
    Write-OK "Service restarted"
}

# === Deploy Frontend ===
function Deploy-Frontend {
    Write-Step "======== Deploy Frontend ========"
    Write-Step "1/3  Build frontend..."
    Push-Location "$LOCAL_BASE\frontend"
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Build failed" }
    } finally {
        Pop-Location
    }
    Write-OK "Build done"

    Write-Step "2/3  Clean old dist on overseas..."
    Invoke-Overseas "rm -rf $REMOTE_BASE/dist/*"
    Write-OK "Cleaned"

    Write-Step "3/3  Upload dist..."
    Send-ToOverseas -LocalPath "$LOCAL_BASE\frontend\dist\*" -RemoteRelPath "dist/"
    Write-OK "======== Frontend deployed ========"
}

# === Deploy Backend ===
function Deploy-Backend {
    Write-Step "======== Deploy Backend ========"
    Write-Step "Clean local __pycache__..."
    Get-ChildItem -Path "$LOCAL_BASE\backend" -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Step "Upload backend code..."
    Send-ToOverseas -LocalPath "$LOCAL_BASE\backend\app\*" -RemoteRelPath "backend/app/"
    Write-OK "======== Backend deployed ========"
}

# === Deploy Deps ===
function Deploy-Deps {
    Write-Step "======== Update Python Deps ========"
    Write-Step "Upload requirements.txt..."
    Send-ToOverseas -LocalPath "$LOCAL_BASE\backend\requirements.txt" -RemoteRelPath "backend/requirements.txt"
    Write-Step "Install dependencies on overseas..."
    Invoke-Overseas "cd $REMOTE_BASE/backend && source venv/bin/activate && pip install -r requirements.txt"
    Write-OK "======== Deps updated ========"
}

# === Main ===
Write-Host ""
Write-Host "========================================"
Write-Host "  Fund Keeper Auto Deploy"
Write-Host "========================================"
Write-Host "  Target : $Target"
Write-Host "  Jump   : $CHINA_SERVER"
Write-Host "  Server : $OVERSEAS_SERVER"
Write-Host "========================================"

try {
    if ($Target -eq "frontend") {
        Deploy-Frontend
    } elseif ($Target -eq "backend") {
        Deploy-Backend
        Restart-Service
    } elseif ($Target -eq "all") {
        Deploy-Frontend
        Deploy-Backend
        Restart-Service
    } elseif ($Target -eq "deps") {
        Deploy-Deps
        Restart-Service
    }
    Write-Host "========================================"
    Write-Host "  All Done!"
    Write-Host "========================================"
} catch {
    Write-FAIL $_.Exception.Message
    exit 1
}
