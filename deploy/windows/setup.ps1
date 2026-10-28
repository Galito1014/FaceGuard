# FaceGuard AI - configuracion automatica del entorno en Windows 10/11 (PowerShell)
# Uso (desde la carpeta raiz del repositorio):
#   powershell -ExecutionPolicy Bypass -File .\deploy\windows\setup.ps1
# Crea backend\.venv, instala las dependencias, descarga y verifica los modelos
# y crea backend\.env a partir de backend\.env.example (si no existe).
$ErrorActionPreference = "Stop"

$Root    = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Backend = Join-Path $Root "backend"
$Venv    = Join-Path $Backend ".venv"
$VenvPy  = Join-Path $Venv "Scripts\python.exe"

function Find-Python {
    # En PowerShell 5.1, redirigir stderr de un programa con "Stop" lanza una excepcion.
    $ErrorActionPreference = "Continue"
    # 1) Lanzador "py" de python.org (versiones compatibles, de la preferida a la menos preferida)
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in @("3.12", "3.11", "3.13")) {
            & py "-$v" -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) { return @("py", "-$v") }
        }
    }
    # 2) "python" en el PATH
    if (Get-Command python -ErrorAction SilentlyContinue) { return @("python") }
    return $null
}

Write-Host "==> Buscando Python 3.11 - 3.13 (64 bits)"
$Py = Find-Python
if (-not $Py) {
    Write-Host "No se encontro Python. Instale Python 3.12 (64 bits) desde https://www.python.org/downloads/windows/" -ForegroundColor Red
    Write-Host "y marque 'Add python.exe to PATH' durante la instalacion." -ForegroundColor Red
    exit 1
}
$PyExe  = $Py[0]
$PyArgs = @($Py | Select-Object -Skip 1)
$check = & $PyExe @PyArgs -c "import sys,struct; ok=(3,11)<=sys.version_info[:2]<=(3,13) and struct.calcsize('P')==8; print(sys.version.split()[0], struct.calcsize('P')*8); sys.exit(0 if ok else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Version no compatible: Python $check bits. Se requiere Python 3.11, 3.12 o 3.13 de 64 bits." -ForegroundColor Red
    exit 1
}
Write-Host "    Python $check bits"

if (-not (Test-Path $VenvPy)) {
    Write-Host "==> Creando entorno virtual en backend\.venv"
    & $PyExe @PyArgs -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno virtual" }
}

Write-Host "==> Instalando dependencias (backend\requirements.txt)"
& $VenvPy -m pip install --upgrade pip
& $VenvPy -m pip install -r (Join-Path $Backend "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Fallo la instalacion de dependencias" }

Write-Host "==> Modelos de reconocimiento facial"
Push-Location $Backend
try {
    & $VenvPy -m scripts.download_models
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron descargar los modelos" }
} finally { Pop-Location }

$EnvFile = Join-Path $Backend ".env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $Backend ".env.example") $EnvFile
    Write-Host "==> Se creo backend\.env (edite FACEGUARD_ADMIN_PASSWORD antes del primer arranque)"
} else {
    Write-Host "==> backend\.env ya existe; no se modifica"
}

if (-not (Test-Path (Join-Path $Root "frontend\dist\index.html"))) {
    Write-Host "!! No se encontro frontend\dist. Compilelo con: cd frontend; npm ci; npm run build" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Listo. Para iniciar FaceGuard AI:" -ForegroundColor Green
Write-Host "   .\deploy\windows\run.ps1"
Write-Host "y abra http://localhost:8000 (usuario: admin)."
