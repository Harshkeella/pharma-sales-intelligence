$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) { py -3 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Push-Location frontend
try {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npx.cmd playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Browser installation failed.' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Production build failed.' }
} finally { Pop-Location }
Write-Host 'Setup complete. Run .\run.ps1 to start Pharma Sales Intelligence.'
