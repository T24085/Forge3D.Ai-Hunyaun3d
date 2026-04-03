from __future__ import annotations

import base64
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from pathlib import Path
from typing import Any

import psutil
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


IS_FROZEN = getattr(sys, "frozen", False)
APP_HOME = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", APP_HOME))
ROOT = APP_HOME
STATE_DIR = APP_HOME / ".launcher"
LOG_DIR = APP_HOME / "logs"
OUTPUT_DIR = APP_HOME / "outputs"
STATIC_DIR = BUNDLE_ROOT / "static"
SCRIPTS_DIR = APP_HOME / "scripts"
CONFIG_PATH = STATE_DIR / "config.json"
STATE_PATH = STATE_DIR / "state.json"
MAX_HISTORY_ITEMS = 30

DEFAULT_CONFIG = {
    "repoPath": "hunyuan-upstream",
    "workspaceOutputDir": "outputs",
    "hunyuanHost": "127.0.0.1",
    "hunyuanPort": 8080,
    "launcherPort": 7861,
    "preferredProfile": "mini-turbo",
    "enableTexture": False,
    "faceCount": 40000,
    "steps": 5,
    "guidanceScale": 5.0,
    "octreeResolution": 128,
}

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
JOB_LOCK = threading.Lock()
JOB_STORE: dict[str, dict[str, Any]] = {}
JOB_QUEUE: list[str] = []
ACTIVE_JOB_ID: str | None = None


def ensure_dirs() -> None:
    for path in (STATE_DIR, LOG_DIR, OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_config() -> dict[str, Any]:
    config = load_json(CONFIG_PATH, DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    return merged


def load_state() -> dict[str, Any]:
    return load_json(STATE_PATH, {})


def save_state(state: dict[str, Any]) -> None:
    save_json(STATE_PATH, state)


def get_history() -> list[dict[str, Any]]:
    state = load_state()
    history = state.get("history", [])
    if not isinstance(history, list):
        return []
    return history


def save_history(history: list[dict[str, Any]]) -> None:
    state = load_state()
    state["history"] = history[:MAX_HISTORY_ITEMS]
    save_state(state)


def upsert_history_entry(entry: dict[str, Any]) -> dict[str, Any]:
    history = get_history()
    updated = False
    for index, existing in enumerate(history):
        if existing.get("jobId") == entry.get("jobId"):
            history[index] = {**existing, **entry}
            updated = True
            break
    if not updated:
        history.insert(0, entry)
    history.sort(key=lambda item: item.get("createdAt", 0), reverse=True)
    save_history(history)
    return entry


def get_history_entry(job_id: str) -> dict[str, Any] | None:
    for entry in get_history():
        if entry.get("jobId") == job_id:
            return entry
    return None


def resolve_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (APP_HOME / candidate).resolve()


def sanitize_extension_from_mime(mime_type: str | None) -> str:
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }
    return mapping.get((mime_type or "").lower(), ".png")


def get_job_workspace_dir(job_id: str) -> Path:
    return OUTPUT_DIR / job_id


def write_job_source_image(job_id: str, image_base64: str, mime_type: str | None) -> Path:
    workspace = get_job_workspace_dir(job_id)
    workspace.mkdir(parents=True, exist_ok=True)
    extension = sanitize_extension_from_mime(mime_type)
    path = workspace / f"source{extension}"
    path.write_bytes(base64.b64decode(image_base64))
    return path


def write_job_notes(job_id: str, notes: str) -> Path:
    workspace = get_job_workspace_dir(job_id)
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / "notes.txt"
    path.write_text(notes or "", encoding="utf-8")
    return path


def copy_model_into_workspace(job_id: str, source_model_path: Path) -> Path:
    workspace = get_job_workspace_dir(job_id)
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "model.glb"
    shutil.copy2(source_model_path, target)
    return target


def run_command(command: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 1, "", f"Command not found: {command[0]}"
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out"


def get_command_output(command: list[str]) -> str:
    _, stdout, stderr = run_command(command)
    return stdout or stderr


def get_python_candidates() -> list[dict[str, Any]]:
    commands = [
        ["py", "-3.11", "--version"],
        ["py", "-3.10", "--version"],
        ["py", "-3.12", "--version"],
        ["python", "--version"],
    ]
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for command in commands:
        code, stdout, stderr = run_command(command)
        if code != 0:
            continue
        label = " ".join(command[:-1]) if len(command) > 2 else command[0]
        if label in seen:
            continue
        seen.add(label)
        candidates.append(
            {
                "label": label,
                "version": stdout or stderr,
                "recommended": label in {"py -3.11", "py -3.10"},
            }
        )
    return candidates


def get_gpu_info() -> dict[str, Any]:
    query = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]
    code, stdout, stderr = run_command(query)
    if code != 0 or not stdout:
        return {"available": False, "error": stderr or "nvidia-smi not available"}
    first = stdout.splitlines()[0]
    name, memory_mb, driver = [part.strip() for part in first.split(",")]
    memory_mb_int = int(memory_mb)
    if memory_mb_int >= 16000:
        recommended_profile = "full-shape-and-texture"
    elif memory_mb_int >= 12000:
        recommended_profile = "full-shape"
    else:
        recommended_profile = "mini-turbo"
    return {
        "available": True,
        "name": name,
        "memoryMb": memory_mb_int,
        "driverVersion": driver,
        "recommendedProfile": recommended_profile,
    }


def get_resource_metrics() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=0.2)
    metrics: dict[str, Any] = {
        "cpuPercent": round(cpu_percent, 1),
        "memory": {
            "usedGb": round(memory.used / (1024 ** 3), 2),
            "totalGb": round(memory.total / (1024 ** 3), 2),
            "percent": round(memory.percent, 1),
        },
    }

    gpu_query = [
        "nvidia-smi",
        "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]
    code, stdout, stderr = run_command(gpu_query)
    if code == 0 and stdout:
        util, used_mb, total_mb, temp_c = [part.strip() for part in stdout.splitlines()[0].split(",")]
        metrics["gpu"] = {
            "available": True,
            "utilizationPercent": int(util),
            "memoryUsedGb": round(int(used_mb) / 1024, 2),
            "memoryTotalGb": round(int(total_mb) / 1024, 2),
            "temperatureC": int(temp_c),
        }
    else:
        metrics["gpu"] = {"available": False, "error": stderr or "nvidia-smi not available"}

    return metrics


def pid_exists(pid: int | None) -> bool:
    if not pid:
        return False
    code, stdout, _ = run_command(["tasklist", "/FI", f"PID eq {pid}"])
    return code == 0 and str(pid) in stdout


def kill_process_on_port(port: int) -> int | None:
    script = (
        f"$conn = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
        "Select-Object -First 1 -ExpandProperty OwningProcess; "
        'if ($conn) { Write-Output $conn }'
    )
    code, stdout, _ = run_command(["powershell", "-NoProfile", "-Command", script])
    if code != 0 or not stdout:
        return None
    pid = int(stdout.splitlines()[0].strip())
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True, text=True)
    return pid


def can_reach_upstream(host: str, port: int) -> bool:
    url = f"http://{host}:{port}/status/ping"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def build_upstream_command(config: dict[str, Any], repo_path: Path) -> list[str]:
    venv_python = repo_path / ".venv" / "Scripts" / "python.exe"
    python_cmd = str(venv_python if venv_python.exists() else Path(sys.executable))
    command = [
        python_cmd,
        "api_server.py",
        "--host",
        config["hunyuanHost"],
        "--port",
        str(config["hunyuanPort"]),
        "--model_path",
        "tencent/Hunyuan3D-2mini",
    ]
    if config.get("enableTexture"):
        command.extend(["--tex_model_path", "tencent/Hunyuan3D-2", "--enable_tex"])
    return command


def get_upstream_status() -> dict[str, Any]:
    config = load_config()
    state = load_state()
    repo_path = resolve_path(config["repoPath"])
    venv_python = repo_path / ".venv" / "Scripts" / "python.exe"
    status = {
        "repoPath": str(repo_path),
        "repoPresent": repo_path.exists(),
        "apiServerPresent": (repo_path / "api_server.py").exists(),
        "venvPresent": venv_python.exists(),
        "venvPython": str(venv_python),
        "pid": state.get("hunyuanPid"),
        "running": pid_exists(state.get("hunyuanPid")),
        "reachable": can_reach_upstream(config["hunyuanHost"], config["hunyuanPort"]),
        "logPath": str((LOG_DIR / "hunyuan.log").resolve()),
    }
    status["readyToStart"] = status["repoPresent"] and status["apiServerPresent"]
    return status


def launch_bootstrap_setup() -> dict[str, Any]:
    setup_script = SCRIPTS_DIR / "setup_hunyuan.ps1"
    if not setup_script.exists():
        raise HTTPException(status_code=404, detail="Setup script is missing from the packaged app.")

    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "Start-Process powershell "
            f"-WorkingDirectory '{APP_HOME}' "
            f"-ArgumentList '-NoExit','-ExecutionPolicy','Bypass','-File','{setup_script}'"
        ),
    ]
    subprocess.Popen(command, cwd=APP_HOME)
    return {
        "started": True,
        "scriptPath": str(setup_script),
        "message": "Opened first-time setup in a separate PowerShell window.",
    }


def start_upstream_process() -> dict[str, Any]:
    config = load_config()
    repo_path = resolve_path(config["repoPath"])
    if not (repo_path / "api_server.py").exists():
        raise HTTPException(status_code=400, detail="Hunyuan repo is missing api_server.py")

    status = get_upstream_status()
    if status["reachable"]:
        return {"started": False, "message": "Upstream API is already reachable.", "status": status}

    command = build_upstream_command(config, repo_path)
    log_path = LOG_DIR / "hunyuan.log"
    log_handle = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        command,
        cwd=repo_path,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    )
    state = load_state()
    state["hunyuanPid"] = proc.pid
    state["lastStartCommand"] = command
    state["lastStartedAt"] = int(time.time())
    save_state(state)

    for _ in range(15):
        if can_reach_upstream(config["hunyuanHost"], config["hunyuanPort"]):
            break
        time.sleep(1)

    return {
        "started": True,
        "pid": proc.pid,
        "status": get_upstream_status(),
        "command": command,
    }


def stop_upstream_process() -> dict[str, Any]:
    state = load_state()
    pid = state.get("hunyuanPid")
    if pid and pid_exists(pid):
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True, text=True)
        state.pop("hunyuanPid", None)
        save_state(state)
        return {"stopped": True, "pid": pid}

    port_pid = kill_process_on_port(load_config()["hunyuanPort"])
    state.pop("hunyuanPid", None)
    save_state(state)
    if port_pid:
        return {"stopped": True, "pid": port_pid}
    return {"stopped": False, "message": "No tracked Hunyuan process is running."}


def fetch_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw)


def start_generation_job(payload: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    url = f"http://{config['hunyuanHost']}:{config['hunyuanPort']}/send"
    try:
        result = fetch_json(url, method="POST", payload=payload)
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Hunyuan API: {exc}") from exc
    return result


def fetch_generation_job(upstream_job_id: str) -> dict[str, Any]:
    config = load_config()
    url = f"http://{config['hunyuanHost']}:{config['hunyuanPort']}/status/{urllib.parse.quote(upstream_job_id)}"
    try:
        return fetch_json(url)
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Hunyuan API: {exc}") from exc


def serialize_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "jobId": job["jobId"],
        "status": job["status"],
        "createdAt": job["createdAt"],
        "updatedAt": job["updatedAt"],
        "seed": job.get("seed"),
        "steps": job.get("steps"),
        "guidanceScale": job.get("guidanceScale"),
        "texture": job.get("texture"),
        "inputImageBase64": job.get("inputImageBase64"),
        "inputImageMimeType": job.get("inputImageMimeType"),
        "downloadPath": job.get("downloadPath"),
        "previewPath": job.get("previewPath"),
        "fileName": job.get("fileName"),
        "fileSizeBytes": job.get("fileSizeBytes"),
        "workspaceDir": job.get("workspaceDir"),
        "sourceImagePath": job.get("sourceImagePath"),
        "notes": job.get("notes", ""),
        "workspaceModelPath": job.get("workspaceModelPath"),
        "cancelRequested": job.get("cancelRequested", False),
        "error": job.get("error"),
        "rerunOf": job.get("rerunOf"),
    }


def set_job_state(job_id: str, **updates: Any) -> dict[str, Any] | None:
    with JOB_LOCK:
        job = JOB_STORE.get(job_id)
        if not job:
            return None
        job.update(updates)
        job["updatedAt"] = int(time.time())
        return dict(job)


def get_job(job_id: str) -> dict[str, Any] | None:
    with JOB_LOCK:
        job = JOB_STORE.get(job_id)
        return dict(job) if job else None


def list_jobs() -> dict[str, Any]:
    with JOB_LOCK:
        active = serialize_job(JOB_STORE[ACTIVE_JOB_ID]) if ACTIVE_JOB_ID and ACTIVE_JOB_ID in JOB_STORE else None
        pending = [serialize_job(JOB_STORE[job_id]) for job_id in JOB_QUEUE if job_id in JOB_STORE]
        recent = [
            serialize_job(job)
            for job in sorted(JOB_STORE.values(), key=lambda item: item.get("createdAt", 0), reverse=True)
            if job["jobId"] != ACTIVE_JOB_ID and job["jobId"] not in JOB_QUEUE
        ][:12]
    return {"active": active, "pending": pending, "recent": recent}


def queue_history_job(
    request_payload: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    timestamp = int(time.time())
    job_id = str(uuid.uuid4())
    source_path = write_job_source_image(job_id, metadata["inputImageBase64"], metadata.get("inputImageMimeType"))
    notes_path = write_job_notes(job_id, metadata.get("notes", ""))
    workspace_dir = get_job_workspace_dir(job_id)
    job = {
        "jobId": job_id,
        "status": "queued",
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "requestPayload": request_payload,
        "workspaceDir": str(workspace_dir),
        "sourceImagePath": f"/api/workspace/{job_id}/source",
        "sourceImageFile": str(source_path),
        "notesPath": f"/api/workspace/{job_id}/notes",
        "notesFile": str(notes_path),
        **metadata,
    }
    with JOB_LOCK:
        JOB_STORE[job_id] = job
        JOB_QUEUE.append(job_id)
    upsert_history_entry(serialize_job(job))
    return {"uid": job_id, "status": "queued"}


def poll_generation_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if job:
        return serialize_job(job)
    existing = get_history_entry(job_id)
    if existing:
        return existing
    raise HTTPException(status_code=404, detail="Job not found")


def queue_worker() -> None:
    global ACTIVE_JOB_ID
    while True:
        next_job: dict[str, Any] | None = None
        with JOB_LOCK:
            if ACTIVE_JOB_ID is None and JOB_QUEUE:
                next_id = JOB_QUEUE.pop(0)
                ACTIVE_JOB_ID = next_id
                JOB_STORE[next_id]["status"] = "starting"
                JOB_STORE[next_id]["updatedAt"] = int(time.time())
                next_job = dict(JOB_STORE[next_id])
        if not next_job:
            time.sleep(1)
            continue

        job_id = next_job["jobId"]
        try:
            upstream = start_generation_job(next_job["requestPayload"])
            set_job_state(job_id, status="processing", upstreamJobId=upstream["uid"])
            upsert_history_entry(serialize_job(get_job(job_id) or next_job))
            while True:
                current = get_job(job_id)
                if not current:
                    break
                if current.get("cancelRequested"):
                    stop_upstream_process()
                    set_job_state(job_id, status="cancelled", error="Cancelled by user")
                    upsert_history_entry(serialize_job(get_job(job_id) or current))
                    start_upstream_process()
                    break

                status = fetch_generation_job(current["upstreamJobId"])
                if status.get("status") == "completed":
                    output_path = OUTPUT_DIR / f"{job_id}.glb"
                    output_bytes = base64.b64decode(status["model_base64"])
                    output_path.write_bytes(output_bytes)
                    workspace_model_path = copy_model_into_workspace(job_id, output_path)
                    set_job_state(
                        job_id,
                        status="completed",
                        downloadPath=f"/api/download/{job_id}",
                        previewPath=f"/api/download/{job_id}",
                        fileName=output_path.name,
                        fileSizeBytes=output_path.stat().st_size,
                        workspaceModelPath=str(workspace_model_path),
                    )
                    upsert_history_entry(serialize_job(get_job(job_id) or current))
                    break

                set_job_state(job_id, status=status.get("status", "processing"))
                upsert_history_entry(serialize_job(get_job(job_id) or current))
                time.sleep(2)
        except Exception as exc:
            set_job_state(job_id, status="failed", error=str(exc))
            failed = get_job(job_id)
            if failed:
                upsert_history_entry(serialize_job(failed))
        finally:
            with JOB_LOCK:
                if ACTIVE_JOB_ID == job_id:
                    ACTIVE_JOB_ID = None


ensure_dirs()
threading.Thread(target=queue_worker, daemon=True).start()
app = FastAPI(title="Hunyuan Local Launcher")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/system")
def system_info() -> dict[str, Any]:
    config = load_config()
    return {
        "cwd": str(ROOT),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "pythonCandidates": get_python_candidates(),
        "node": get_command_output(["node", "--version"]),
        "git": get_command_output(["git", "--version"]),
        "gpu": get_gpu_info(),
        "config": config,
    }


@app.get("/api/resources")
def resources() -> dict[str, Any]:
    return get_resource_metrics()


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return load_config()


@app.post("/api/config")
def update_config(payload: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    for key in DEFAULT_CONFIG:
        if key in payload:
            config[key] = payload[key]
    save_json(CONFIG_PATH, config)
    return config


@app.get("/api/hunyuan/status")
def hunyuan_status() -> dict[str, Any]:
    return get_upstream_status()


@app.post("/api/hunyuan/start")
def hunyuan_start() -> dict[str, Any]:
    return start_upstream_process()


@app.post("/api/hunyuan/stop")
def hunyuan_stop() -> dict[str, Any]:
    return stop_upstream_process()


@app.post("/api/shutdown")
def shutdown_launcher() -> dict[str, Any]:
    stop_upstream_process()
    threading.Timer(1.0, lambda: os._exit(0)).start()
    return {"shuttingDown": True}


@app.get("/api/hunyuan/logs")
def hunyuan_logs() -> dict[str, Any]:
    log_path = LOG_DIR / "hunyuan.log"
    if not log_path.exists():
        return {"lines": []}
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return {"lines": lines[-80:]}


@app.get("/api/history")
def history() -> dict[str, Any]:
    return {"items": get_history()}


@app.get("/api/workspace/{job_id}/source")
def workspace_source(job_id: str) -> FileResponse:
    item = get_history_entry(job_id) or get_job(job_id)
    if not item or not item.get("sourceImageFile"):
        raise HTTPException(status_code=404, detail="Source image not found")
    path = Path(item["sourceImageFile"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Source image not found")
    media_type = item.get("inputImageMimeType", "image/png")
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.post("/api/history/{job_id}/notes")
def update_history_notes(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    notes = str(payload.get("notes", ""))
    path = write_job_notes(job_id, notes)
    job = set_job_state(job_id, notes=notes, notesFile=str(path))
    history_item = get_history_entry(job_id)
    if history_item:
        upsert_history_entry({"jobId": job_id, "notes": notes})
        return get_history_entry(job_id) or history_item
    if job:
        return serialize_job(job)
    raise HTTPException(status_code=404, detail="History item not found")


@app.get("/api/jobs")
def jobs() -> dict[str, Any]:
    return list_jobs()


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    with JOB_LOCK:
        job = JOB_STORE.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job["status"] in {"completed", "failed", "cancelled"}:
            return serialize_job(job)
        if job_id in JOB_QUEUE:
            JOB_QUEUE.remove(job_id)
            job["status"] = "cancelled"
            job["updatedAt"] = int(time.time())
            upsert_history_entry(serialize_job(job))
            return serialize_job(job)
        job["cancelRequested"] = True
        job["updatedAt"] = int(time.time())
        return serialize_job(job)


@app.get("/api/bootstrap")
def bootstrap_instructions() -> dict[str, Any]:
    status = get_upstream_status()
    repo_path = resolve_path(load_config()["repoPath"])
    script_path = SCRIPTS_DIR / "setup_hunyuan.ps1"
    first_run_path = APP_HOME / "setup_and_start_hunyuan.bat"
    if status["reachable"]:
        setup_state = "ready"
        setup_message = "Hunyuan API is reachable. You can generate now."
    elif status["repoPresent"] and status["venvPresent"]:
        setup_state = "start-required"
        setup_message = "Setup files are present. Start the Hunyuan API before generating."
    else:
        setup_state = "setup-required"
        setup_message = "This PC still needs first-time Hunyuan setup. The launcher alone is not enough."
    return {
        "repoPath": str(repo_path),
        "scriptPath": str(script_path),
        "firstRunPath": str(first_run_path),
        "scriptPresent": script_path.exists(),
        "firstRunPresent": first_run_path.exists(),
        "setupState": setup_state,
        "setupMessage": setup_message,
        "notes": [
            "Use Python 3.11 if available. Python 3.10 is also a safer choice than 3.12 for ML packages.",
            "Your 8 GB GPU is best matched with Hunyuan3D-2mini for shape generation.",
            "Texture generation is available but likely memory-constrained on an RTX 4060 8 GB.",
        ],
    }


@app.post("/api/bootstrap/run")
def run_bootstrap() -> dict[str, Any]:
    return launch_bootstrap_setup()


@app.post("/api/generate")
def generate(payload: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    request_payload = {
        "image": payload["image"],
        "seed": int(payload.get("seed", 1234)),
        "num_inference_steps": int(payload.get("steps", config["steps"])),
        "guidance_scale": float(payload.get("guidanceScale", config["guidanceScale"])),
        "octree_resolution": int(payload.get("octreeResolution", config["octreeResolution"])),
        "texture": bool(payload.get("texture", config["enableTexture"])),
        "face_count": int(payload.get("faceCount", config["faceCount"])),
        "type": "glb",
    }
    metadata = {
        "seed": request_payload["seed"],
        "steps": request_payload["num_inference_steps"],
        "guidanceScale": request_payload["guidance_scale"],
        "octreeResolution": request_payload["octree_resolution"],
        "texture": request_payload["texture"],
        "inputImageBase64": payload["image"],
        "inputImageMimeType": payload.get("imageMimeType", "image/png"),
        "notes": str(payload.get("notes", "")),
    }
    return queue_history_job(request_payload, metadata)


@app.get("/api/generate/{job_id}")
def generation_status(job_id: str) -> dict[str, Any]:
    return poll_generation_job(job_id)


@app.post("/api/history/rerun/{job_id}")
def rerun_history_item(job_id: str) -> dict[str, Any]:
    existing = get_history_entry(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="History item not found")
    if not existing.get("inputImageBase64"):
        raise HTTPException(status_code=400, detail="History item is missing its source image")

    request_payload = {
        "image": existing["inputImageBase64"],
        "seed": int(existing.get("seed", 1234)),
        "num_inference_steps": int(existing.get("steps", load_config()["steps"])),
        "guidance_scale": float(existing.get("guidanceScale", load_config()["guidanceScale"])),
        "octree_resolution": int(existing.get("octreeResolution", load_config()["octreeResolution"])),
        "texture": bool(existing.get("texture", False)),
        "face_count": int(load_config()["faceCount"]),
        "type": "glb",
    }
    metadata = {
        "seed": request_payload["seed"],
        "steps": request_payload["num_inference_steps"],
        "guidanceScale": request_payload["guidance_scale"],
        "octreeResolution": request_payload["octree_resolution"],
        "texture": request_payload["texture"],
        "inputImageBase64": existing["inputImageBase64"],
        "inputImageMimeType": existing.get("inputImageMimeType", "image/png"),
        "notes": existing.get("notes", ""),
        "rerunOf": job_id,
    }
    return queue_history_job(request_payload, metadata)


@app.get("/api/download/{job_id}")
def download_output(job_id: str) -> FileResponse:
    file_path = OUTPUT_DIR / f"{job_id}.glb"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Generated file not found")
    return FileResponse(file_path, filename=file_path.name, media_type="model/gltf-binary")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


def launch_browser() -> None:
    launcher_port = load_config()["launcherPort"]
    try:
        webbrowser.open(f"http://127.0.0.1:{launcher_port}")
    except Exception:
        pass


def main() -> None:
    ensure_dirs()
    config = load_config()
    threading.Timer(1.2, launch_browser).start()
    uvicorn.run(app, host="127.0.0.1", port=int(config["launcherPort"]), log_level="info")


if __name__ == "__main__":
    main()
