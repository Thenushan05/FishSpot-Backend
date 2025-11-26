#!/usr/bin/env pwsh
<#
Start script for Windows PowerShell.
Activates local .venv (if present) and runs uvicorn from project root so imports like
`import app` resolve correctly.
#>

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $projectRoot

if (Test-Path ".venv\Scripts\Activate.ps1") {
    Write-Host "Activating virtual environment..."
    . .\.venv\Scripts\Activate.ps1
}
else {
    Write-Host "No .venv found; ensure dependencies are installed or create a venv first." -ForegroundColor Yellow
}

Write-Host "Starting uvicorn (app.main:app) on http://127.0.0.1:8000"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
