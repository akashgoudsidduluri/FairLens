# Start the FairLens sandbox and dashboard on Windows PowerShell.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$api = Start-Process -FilePath $py -ArgumentList "-m","uvicorn","sandbox.api:app","--host","127.0.0.1","--port","8010" -PassThru -NoNewWindow
try {
    Start-Sleep -Seconds 2
    & $py -m streamlit run ui/app.py --server.port 8501
} finally {
    Stop-Process -Id $api.Id -ErrorAction SilentlyContinue
}
