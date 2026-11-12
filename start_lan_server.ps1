# ==============================================================================
# Thamarayyath Employee Portal — Windows Workstation LAN Production Launcher
# ==============================================================================

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  THAMARAYYATH EMPLOYEE PORTAL — WORKSTATION LAN LAUNCHER" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$Waitress = Join-Path $ScriptDir ".venv\Scripts\waitress-serve.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[ERROR] Virtual environment not found at .venv. Please initialize first." -ForegroundColor Red
    Exit 1
}

# 1. Apply any pending database migrations
Write-Host "`n[1/3] Checking database schema & migrations..." -ForegroundColor Yellow
& $VenvPython manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Database migrations failed." -ForegroundColor Red
    Exit 1
}

# 2. Detect Workstation LAN IP Address
Write-Host "`n[2/3] Detecting LAN Workstation IP Address..." -ForegroundColor Yellow
$LocalIPs = Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Wi-Fi", "Ethernet*" -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notmatch "^127\." -and $_.IPAddress -notmatch "^169\.254\." } | Select-Object -ExpandProperty IPAddress

$Port = 8000
Write-Host "`n======================================================================" -ForegroundColor Green
Write-Host "  PORTAL READY TO SERVE LAN CLIENTS" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  Local Workstation Access:    http://127.0.0.1:$Port/" -ForegroundColor White

if ($LocalIPs) {
    foreach ($ip in $LocalIPs) {
        Write-Host "  LAN Network Client Access:   http://${ip}:${Port}/" -ForegroundColor Cyan
    }
} else {
    Write-Host "  Network Access:              http://<WORKSTATION-LAN-IP>:$Port/" -ForegroundColor Cyan
}

Write-Host "----------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  Default Demo Credentials:" -ForegroundColor White
Write-Host "  * Superadmin:            admin      / AdminPass123!" -ForegroundColor White
Write-Host "  * Office Administration: accountant / AccountPass123!" -ForegroundColor White
Write-Host "  * Owner:                 owner      / OwnerPass123!" -ForegroundColor White
Write-Host "======================================================================`n" -ForegroundColor Green

# 3. Launch Waitress Production WSGI Server
Write-Host "[3/3] Starting Waitress Production WSGI Server (Binding 0.0.0.0:$Port)..." -ForegroundColor Yellow
& $Waitress --listen="0.0.0.0:$Port" --threads=8 --channel-timeout=120 config.wsgi:application
