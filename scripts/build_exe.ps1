Param(
  [string]$Name = "NetLens"
)

$ErrorActionPreference = "Stop"

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
  if (-not (Test-Path "requirements.txt")) {
    throw "No se encontró requirements.txt en $(Get-Location)"
  }

  Write-Host "[1/3] Instalando dependencias..."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  python -m pip install pyinstaller

  Write-Host "[2/3] Limpiando builds anteriores..."
  if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
  if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist" }
  if (Test-Path "$Name.spec") { Remove-Item -Force "$Name.spec" }

  Write-Host "[3/3] Construyendo $Name.exe (onefile, windowed)..."
  pyinstaller --noconfirm --clean --onefile --windowed --name $Name `
    --add-data "filter_hosts.conf;." `
    --add-data "payloads;payloads" `
    main.py

  Write-Host "OK: dist\\$Name.exe"
}
finally {
  Pop-Location
}
