# Forge3D.Ai

![Forge3D.Ai Icon](assets/forge3d-icon.png)

Forge3D.Ai is a local Windows launcher for running `Hunyuan3D-2` on your own machine without paying per-generation credits. It wraps the upstream Hunyuan API with a custom control panel, local queue management, model preview, run history, and a packaging path for sharing the app with other Windows users.

## What it does

- Checks local machine readiness
- Bootstraps and manages the upstream `Hunyuan3D-2` repo locally
- Starts and stops the upstream Hunyuan API server
- Queues image-to-3D jobs against the local API
- Saves generated `.glb` files into local workspaces
- Shows in-browser 3D preview, compare view, and generation history
- Tracks CPU, RAM, GPU, VRAM, and temperature
- Supports multiple visual themes in the launcher UI
- Packages into a Windows-shareable app folder with icon and installer script

## Current design

- `app.py`: FastAPI launcher backend and static file host
- `static/`: setup and generation UI
- `scripts/setup_hunyuan.ps1`: Windows bootstrap for the upstream Hunyuan environment
- `scripts/build_windows_release.ps1`: PyInstaller build script
- `packaging/Forge3DAi.iss`: Inno Setup installer script
- `assets/`: Forge3D.Ai icon assets

## Recommended local path for this machine

This machine has an `RTX 4060 8 GB`, so start with:

- `Hunyuan3D-2mini`
- shape generation first
- texture generation only after the base pipeline is stable

## Run

1. Install launcher dependencies:

```powershell
python -m pip install -r requirements.txt
```

2. Bootstrap upstream Hunyuan using Python 3.11 if available:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_hunyuan.ps1
```

3. Start the launcher:

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 7861
```

4. Open `http://127.0.0.1:7861`

## One-click start

After the upstream bootstrap has completed, you can start both the Hunyuan API and the launcher UI with:

```bat
start_hunyuan_launcher.bat
```

For first-time setup and launch in one step, use:

```bat
setup_and_start_hunyuan.bat
```

## Build a Windows app

You can package the launcher as a Windows distributable folder and optional installer:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_release.ps1
```

That build:

- creates `dist\Forge3DAi\Forge3DAi.exe`
- bundles the web UI into the app
- copies `scripts\setup_hunyuan.ps1` for first-run Hunyuan setup
- compiles `dist\Forge3DAi-Setup.exe` too if Inno Setup 6 is installed

Notes for sharing:

- share the installer or the entire `dist\Forge3DAi\` folder
- friends still need a compatible NVIDIA GPU and first-run model downloads
- the Hunyuan community license still applies

## Notes

- This project is designed for local/self-hosted use on Windows.
- `Hunyuan3D-2mini` is the safest starting point for `8 GB VRAM` GPUs.
- Texture generation is heavier and may be unstable on lower-VRAM cards.
- The upstream Tencent license is not a standard permissive OSS license. Read it before commercial use or redistribution.
- The bootstrap script installs CUDA-enabled PyTorch from the official PyTorch wheel index.
- If Python 3.11 is not installed, adjust `-PythonSelector` in the bootstrap script invocation.
