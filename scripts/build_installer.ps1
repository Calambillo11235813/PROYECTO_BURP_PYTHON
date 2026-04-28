Param(
  [string]$IssPath = "installer\\NetLens.iss"
)

$ErrorActionPreference = "Stop"

function Resolve-IsccPath {
  # 1) Explicit override
  if ($Env:INNO_SETUP_ISCC -and (Test-Path $Env:INNO_SETUP_ISCC)) {
    return $Env:INNO_SETUP_ISCC
  }

  # 2) Available on PATH
  $cmd = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) {
    return $cmd.Source
  }

  # 3) Common install locations
  $candidates = @(
    "$Env:ProgramFiles(x86)\\Inno Setup 6\\ISCC.exe",
    "$Env:ProgramFiles\\Inno Setup 6\\ISCC.exe",
    "$Env:ProgramFiles(x86)\\Inno Setup 5\\ISCC.exe",
    "$Env:ProgramFiles\\Inno Setup 5\\ISCC.exe"
  ) | Where-Object { $_ -and $_.Trim().Length -gt 0 }

  foreach ($p in $candidates) {
    if (Test-Path $p) { return $p }
  }

  # 4) Registry (InstallLocation)
  $uninstallRoots = @(
    "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
    "HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
  )

  foreach ($root in $uninstallRoots) {
    try {
      $keys = Get-ChildItem $root -ErrorAction Stop
      foreach ($k in $keys) {
        try {
          $p = Get-ItemProperty $k.PSPath -ErrorAction Stop
          if ($p.DisplayName -and ($p.DisplayName -like "Inno Setup*")) {
            $loc = $p.InstallLocation
            if ($loc) {
              $maybe = Join-Path $loc "ISCC.exe"
              if (Test-Path $maybe) { return $maybe }
            }
          }
        } catch { }
      }
    } catch { }
  }

  return $null
}

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
  if (-not (Test-Path $IssPath)) {
    throw "No se encontró el script .iss: $IssPath"
  }
  if (-not (Test-Path "dist\\NetLens.exe")) {
    throw "No se encontró dist\\NetLens.exe. Ejecuta primero scripts\\build_exe.ps1"
  }

  $iscc = Resolve-IsccPath
  if (-not $iscc) {
    throw (
      "No se encontro ISCC.exe (Inno Setup Compiler). " +
      "Instala Inno Setup 6 o agrega ISCC.exe al PATH. " +
      "Opcional: define INNO_SETUP_ISCC con la ruta completa a ISCC.exe."
    )
  }

  New-Item -ItemType Directory -Force -Path "dist\\installer" | Out-Null

  & $iscc $IssPath

  Write-Host "OK: dist\\installer\\NetLens_Setup.exe"
}
finally {
  Pop-Location
}
