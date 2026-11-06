# Start the local read-only dashboard (Windows).
#   ./serve-dashboard.ps1              # http://localhost:8000, auto-reload
#   ./serve-dashboard.ps1 -Lan         # bind 0.0.0.0 so your phone on the same Wi-Fi can reach it
#   ./serve-dashboard.ps1 -Port 8123
param([int]$Port = 8000, [switch]$Lan)
Set-Location $PSScriptRoot
$PY = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
$HostIp = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
Write-Host "Dashboard: http://localhost:$Port  (Ctrl+C to stop)"
& $PY -m uvicorn dashboard.app:app --reload --host $HostIp --port $Port
