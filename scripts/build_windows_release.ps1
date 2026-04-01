param(
  [string]$AppName = "Forge3DAi",
  [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$distDir = Join-Path $root "dist"
$buildDir = Join-Path $root "build"
$releaseDir = Join-Path $distDir $AppName
$iconPath = Join-Path $root "assets\forge3d-icon.ico"
$specDir = Join-Path $root "build"
$innoScript = Join-Path $root "packaging\Forge3DAi.iss"

Write-Host "Project root: $root"
Write-Host "Installing build dependencies ..."
python -m pip install --upgrade pyinstaller

if (Test-Path $buildDir) {
  Remove-Item -Recurse -Force $buildDir -ErrorAction SilentlyContinue
}

if (Test-Path $releaseDir) {
  Remove-Item -Recurse -Force $releaseDir -ErrorAction SilentlyContinue
}

Write-Host "Building $AppName ..."
pyinstaller `
  --noconfirm `
  --clean `
  --onedir `
  --name $AppName `
  --icon $iconPath `
  --distpath $distDir `
  --workpath $buildDir `
  --specpath $specDir `
  --add-data "$root\static;static" `
  app.py

Write-Host "Copying runtime support files ..."
Copy-Item (Join-Path $root "scripts") (Join-Path $releaseDir "scripts") -Recurse -Force
Copy-Item (Join-Path $root "assets") (Join-Path $releaseDir "assets") -Recurse -Force
Copy-Item (Join-Path $root "README.md") (Join-Path $releaseDir "README.md") -Force
Copy-Item (Join-Path $root "requirements.txt") (Join-Path $releaseDir "requirements.txt") -Force

$portableNotes = @"
Forge3D.Ai $Version

Portable folder:
- Run $AppName.exe to start the local launcher.
- The app will open your browser automatically.
- First-time Hunyuan setup can be started from inside the app or with scripts\setup_hunyuan.ps1.

Notes:
- A compatible NVIDIA GPU is still required.
- Model weights download on first run.
- Share the whole folder, not just the .exe, unless you also build the installer.
"@

Set-Content -Path (Join-Path $releaseDir "PORTABLE.txt") -Value $portableNotes -Encoding UTF8

$isccCandidates = @(
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)

$whereIscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if ($whereIscc) {
  $isccCandidates += $whereIscc
}

$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc -and (Test-Path $innoScript)) {
  Write-Host "Compiling installer with Inno Setup ..."
  & $iscc "/DAppVersion=$Version" $innoScript
} else {
  Write-Host "Inno Setup not found. Portable build is ready at $releaseDir"
}

Write-Host "Done."
