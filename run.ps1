$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Run .\setup.ps1 first.' }
$backendProcess = Start-Process -FilePath "$PSScriptRoot\.venv\Scripts\python.exe" -ArgumentList '-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
Write-Host 'Open http://localhost:3000. Press Ctrl+C to stop.'
Push-Location frontend
try { npm.cmd run start } finally { Pop-Location; Stop-Process -Id $backendProcess.Id -ErrorAction SilentlyContinue }
