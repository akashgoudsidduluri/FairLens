# Start the FairLens sandbox and dashboard on Windows PowerShell.
# Demo path: Model 2 -> Model 7 -> Model 5.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$apiPort = if ($env:FAIRLENS_API_PORT) { [int]$env:FAIRLENS_API_PORT } else { 8010 }
$uiPort = if ($env:FAIRLENS_UI_PORT) { [int]$env:FAIRLENS_UI_PORT } else { 8501 }
$apiUrl = "http://127.0.0.1:$apiPort"

$api = Start-Process -FilePath $py `
    -ArgumentList "-m","sandbox.serve","--host","127.0.0.1","--port",$apiPort,"--log-level","warning" `
    -PassThru -NoNewWindow
try {
    $ready = $false
    for ($i = 0; $i -lt 80; $i++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "$apiUrl/health" -TimeoutSec 1
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch { }
        if ($api.HasExited) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $ready) {
        throw "Sandbox failed to start on $apiUrl. Try another port: `$env:FAIRLENS_API_PORT=8020; .\run.ps1"
    }

    Write-Host "FairLens sandbox: $apiUrl"
    Write-Host "FairLens dashboard: http://127.0.0.1:$uiPort"
    Write-Host "Demo path: Model 2 (gender) -> Model 7 (confounded) -> Model 5 (intersectional)."
    # The dashboard reads this so a FAIRLENS_API_PORT override also moves the
    # URL the UI probes, not just the sandbox process.
    $env:FAIRLENS_API_URL = $apiUrl
    & $py -m streamlit run ui/app.py --server.address 127.0.0.1 --server.port $uiPort
} finally {
    Stop-Process -Id $api.Id -ErrorAction SilentlyContinue
}
