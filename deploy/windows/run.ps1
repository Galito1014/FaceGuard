# FaceGuard AI - inicio en Windows 10/11 (PowerShell)
# Uso (desde la carpeta raiz del repositorio):
#   powershell -ExecutionPolicy Bypass -File .\deploy\windows\run.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy\windows\run.ps1 --host 0.0.0.0 --port 8000
# Los argumentos se pasan a "python -m scripts.run".
$ErrorActionPreference = "Continue"  # uvicorn escribe sus registros en stderr

$Backend = (Resolve-Path (Join-Path $PSScriptRoot "..\..\backend")).Path
$VenvPy  = Join-Path $Backend ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPy)) {
    Write-Host "No existe backend\.venv. Ejecute primero .\deploy\windows\setup.ps1" -ForegroundColor Red
    exit 1
}

Push-Location $Backend
try {
    & $VenvPy -m scripts.run @args
} finally { Pop-Location }
