# Empaqueta DraftMind LoL para Windows con PyInstaller.
# Uso (desde la carpeta del proyecto):  powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1
# Resultado: dist\DraftMindLoL\DraftMindLoL.exe
#
# El ejecutable NO incluye ningun .env ni API key. Para usar la Riot API,
# crea un archivo .env junto a DraftMindLoL.exe (ver .env.example).
#
# Los archivos intermedios van a %TEMP%: si el proyecto esta dentro de
# OneDrive, la sincronizacion bloquea la carpeta build\ y PyInstaller falla.
# (Los mensajes van sin tildes porque Windows PowerShell 5.1 lee mal los
# scripts UTF-8 sin BOM.)

# PyInstaller escribe sus mensajes informativos en stderr; en Windows PowerShell 5.1
# eso no debe detener el script. Los fallos se detectan con $LASTEXITCODE.
$ErrorActionPreference = "Continue"
$root = (Resolve-Path "$PSScriptRoot\..").Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$work = Join-Path $env:TEMP "draftmind-build"

Push-Location $root
try {
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Las pruebas fallan: no se empaqueta." }

    # OneDrive marca dist\ como solo lectura y el borrado de PyInstaller falla;
    # Remove-Item -Force si quita ese atributo.
    $old = Join-Path $root "dist\DraftMindLoL"
    if (Test-Path $old) {
        Remove-Item -Recurse -Force $old -ErrorAction Stop
    }

    & $python -m PyInstaller `
        --noconfirm --clean --windowed `
        --name DraftMindLoL `
        --workpath $work `
        --specpath $work `
        --distpath (Join-Path $root "dist") `
        --paths (Join-Path $root "src") `
        --add-data "$(Join-Path $root 'src\draftmind\resources');draftmind/resources" `
        --exclude-module PySide6.QtWebEngineCore `
        --exclude-module PySide6.QtWebEngineWidgets `
        --exclude-module PySide6.Qt3DCore `
        --exclude-module tkinter `
        (Join-Path $root "main.py")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller fallo (codigo $LASTEXITCODE)." }

    Copy-Item (Join-Path $root ".env.example") (Join-Path $root "dist\DraftMindLoL\.env.example") -Force
    Write-Host "Listo: dist\DraftMindLoL\DraftMindLoL.exe"
}
finally {
    Pop-Location
}
