param(
  [string]$RepoPath = "hunyuan-upstream",
  [string]$PythonSelector = "",
  [string]$RepoUrl = "https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git"
)

$ErrorActionPreference = "Stop"

$repoRoot = Join-Path (Get-Location) $RepoPath

if (-not (Test-Path $repoRoot)) {
  Write-Host "Upstream repo not found. Cloning from $RepoUrl ..."
  git clone $RepoUrl $repoRoot
}

$repo = Resolve-Path $repoRoot
$venv = Join-Path $repo ".venv"

if (-not $PythonSelector) {
  foreach ($candidate in @("py -3.11", "py -3.10", "py -3.12", "python")) {
    try {
      $null = Invoke-Expression "$candidate --version" 2>&1
      if ($LASTEXITCODE -eq 0) {
        $PythonSelector = $candidate
        break
      }
    } catch {
    }
  }
}

if (-not $PythonSelector) {
  throw "No usable Python interpreter was found."
}

Write-Host "Repo: $repo"
Write-Host "Creating venv with: $PythonSelector"

Invoke-Expression "$PythonSelector -m venv `"$venv`""

$python = Join-Path $venv "Scripts\python.exe"

& $python -m pip install --upgrade pip wheel setuptools
& $python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
& $python -m pip install -r (Join-Path $repo "requirements.txt")
& $python -m pip install -e $repo

Push-Location (Join-Path $repo "hy3dgen\texgen\custom_rasterizer")
& $python setup.py install
Pop-Location

Push-Location (Join-Path $repo "hy3dgen\texgen\differentiable_renderer")
& $python setup.py install
Pop-Location

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Next:"
Write-Host "  1. .\.venv\Scripts\Activate.ps1"
Write-Host "  2. python api_server.py --host 127.0.0.1 --port 8080 --model_path tencent/Hunyuan3D-2mini"
Write-Host ""
Write-Host "Note: Python 3.11 or 3.10 is preferred for ML package compatibility. 3.12 may still work, but it is the riskier path."
