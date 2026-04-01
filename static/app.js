const systemSummary = document.getElementById("system-summary");
const hunyuanSummary = document.getElementById("hunyuan-summary");
const bootstrapCommand = document.getElementById("bootstrap-command");
const logsEl = document.getElementById("logs");
const jobStatus = document.getElementById("job-status");
const generateForm = document.getElementById("generate-form");
const notesInput = document.getElementById("notes-input");
const modelPreview = document.getElementById("model-preview");
const previewEmpty = document.getElementById("preview-empty");
const previewDownload = document.getElementById("preview-download");
const driveUpload = document.getElementById("drive-upload");
const resourceSummary = document.getElementById("resource-summary");
const previewPresets = Array.from(document.querySelectorAll(".preview-preset"));
const tintPicker = document.getElementById("tint-picker");
const tintSwatches = Array.from(document.querySelectorAll(".tint-swatch"));
const backendTextureToggle = document.getElementById("backend-texture-toggle");
const logsToggle = document.getElementById("logs-toggle");
const logsPanel = document.getElementById("logs-panel");
const bootstrapToggle = document.getElementById("bootstrap-toggle");
const bootstrapPanel = document.getElementById("bootstrap-panel");
const historyList = document.getElementById("history-list");
const compareLeftViewer = document.getElementById("compare-left-viewer");
const compareRightViewer = document.getElementById("compare-right-viewer");
const compareLeftMeta = document.getElementById("compare-left-meta");
const compareRightMeta = document.getElementById("compare-right-meta");
const queueBoard = document.getElementById("queue-board");
const themeOptions = Array.from(document.querySelectorAll(".theme-option"));

let currentJobId = null;
let pollHandle = null;
let currentPreviewPreset = "studio";
let currentTint = "#a8c5ff";
let currentConfig = null;
let historyEntries = [];
let compareSelection = { left: null, right: null };
let currentTheme = "green";

const previewPresetConfig = {
  studio: {
    backgroundClass: "preview-studio",
    exposure: "1.65",
    shadowIntensity: "0.55",
    cameraOrbit: "35deg 72deg auto",
  },
  twilight: {
    backgroundClass: "preview-twilight",
    exposure: "1.2",
    shadowIntensity: "0.85",
    cameraOrbit: "25deg 70deg auto",
  },
  light: {
    backgroundClass: "preview-light",
    exposure: "1.9",
    shadowIntensity: "0.35",
    cameraOrbit: "15deg 78deg auto",
  },
};

function applyTheme(themeName) {
  currentTheme = themeName;
  document.body.dataset.theme = themeName;
  themeOptions.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.theme === themeName);
  });
  try {
    window.localStorage.setItem("forge3d-theme", themeName);
  } catch (_error) {
  }
}

function applyPreviewPreset(name) {
  currentPreviewPreset = name;
  const preset = previewPresetConfig[name] || previewPresetConfig.studio;
  [modelPreview, compareLeftViewer, compareRightViewer].forEach((viewer) => {
    viewer.classList.remove("preview-studio", "preview-twilight", "preview-light");
    viewer.classList.add(preset.backgroundClass);
    viewer.setAttribute("exposure", preset.exposure);
    viewer.setAttribute("shadow-intensity", preset.shadowIntensity);
    viewer.setAttribute("camera-orbit", preset.cameraOrbit);
  });
  previewPresets.forEach((button) => {
    button.classList.toggle("is-active", button.id === `preset-${name}`);
  });
}

function hexToColorComponents(hex) {
  const normalized = hex.replace("#", "");
  const value = normalized.length === 3
    ? normalized.split("").map((part) => part + part).join("")
    : normalized;
  const intValue = parseInt(value, 16);
  return [
    ((intValue >> 16) & 255) / 255,
    ((intValue >> 8) & 255) / 255,
    (intValue & 255) / 255,
    1,
  ];
}

function applyModelTint(hex) {
  currentTint = hex;
  tintPicker.value = hex;
  tintSwatches.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.color.toLowerCase() === hex.toLowerCase());
  });

  const color = hexToColorComponents(hex);
  for (const viewer of [modelPreview, compareLeftViewer, compareRightViewer]) {
    if (!viewer.model || !viewer.model.materials) {
      continue;
    }
    for (const material of viewer.model.materials) {
      const pbr = material.pbrMetallicRoughness;
      if (!pbr) {
        continue;
      }
      pbr.setBaseColorFactor(color);
      pbr.setMetallicFactor(0.05);
      pbr.setRoughnessFactor(0.95);
    }
  }
}

function resetPreview() {
  modelPreview.classList.add("hidden");
  modelPreview.removeAttribute("src");
  previewDownload.classList.add("hidden");
  previewDownload.removeAttribute("href");
  driveUpload.classList.add("hidden");
  previewEmpty.classList.remove("hidden");
}

function showPreview(result) {
  const previewUrl = `${result.previewPath}?v=${Date.now()}`;
  modelPreview.src = previewUrl;
  modelPreview.classList.remove("hidden");
  previewDownload.href = result.downloadPath;
  previewDownload.classList.remove("hidden");
  driveUpload.dataset.downloadPath = result.downloadPath;
  driveUpload.classList.remove("hidden");
  previewEmpty.classList.add("hidden");
  applyPreviewPreset(currentPreviewPreset);
}

function buildHistoryImage(item) {
  if (!item.inputImageBase64) {
    return "";
  }
  return `data:${item.inputImageMimeType || "image/png"};base64,${item.inputImageBase64}`;
}

function findHistoryItem(jobId) {
  return historyEntries.find((item) => item.jobId === jobId) || null;
}

function renderCompareSlot(side, item) {
  const viewer = side === "left" ? compareLeftViewer : compareRightViewer;
  const meta = side === "left" ? compareLeftMeta : compareRightMeta;
  if (!item || item.status !== "completed") {
    viewer.removeAttribute("src");
    meta.textContent = `Choose a run for the ${side} side.`;
    return;
  }

  viewer.src = `${item.previewPath}?compare=${Date.now()}`;
  meta.innerHTML = `
    <strong>${item.jobId.slice(0, 8)}</strong>
    <span class="muted">Seed ${item.seed} | Steps ${item.steps} | Guidance ${item.guidanceScale} | ${item.texture ? "Textured" : "Shape only"}</span>
  `;
}

function renderCompare() {
  renderCompareSlot("left", compareSelection.left ? findHistoryItem(compareSelection.left) : null);
  renderCompareSlot("right", compareSelection.right ? findHistoryItem(compareSelection.right) : null);
  applyPreviewPreset(currentPreviewPreset);
  applyModelTint(currentTint);
}

function renderHistory(entries) {
  if (!entries.length) {
    historyList.innerHTML = `<div class="muted">No generations yet.</div>`;
    return;
  }

  historyList.innerHTML = entries.map((item) => {
    const thumb = buildHistoryImage(item);
    const status = item.status || "unknown";
    const completed = status === "completed";
    return `
      <article class="history-card">
        ${thumb ? `<img class="history-thumb" src="${thumb}" alt="Reference image for ${item.jobId}" />` : `<div class="history-thumb history-thumb-empty">No image</div>`}
        <div class="history-body">
          <div class="history-title-row">
            <strong>${item.jobId.slice(0, 8)}</strong>
            <span class="history-status history-status-${status}">${status}</span>
          </div>
          <div class="history-meta">Seed ${item.seed} | Steps ${item.steps} | Guidance ${item.guidanceScale}</div>
          <div class="history-meta">${item.texture ? "Texture on" : "Shape only"}${item.rerunOf ? ` | Re-run of ${item.rerunOf.slice(0, 8)}` : ""}</div>
          <div class="history-meta">
            ${item.sourceImagePath ? `<a href="${item.sourceImagePath}" target="_blank" rel="noreferrer">Open source image</a>` : ""}
            ${item.workspaceDir ? `<span class="muted">${item.workspaceDir}</span>` : ""}
          </div>
          <label class="history-notes">
            <span class="muted">Notes</span>
            <textarea data-notes-input="${item.jobId}" rows="3" placeholder="Add notes for this run.">${item.notes || ""}</textarea>
          </label>
          <div class="history-actions">
            <button type="button" class="ghost" data-action="preview" data-job-id="${item.jobId}" ${completed ? "" : "disabled"}>Preview</button>
            <button type="button" class="ghost" data-action="left" data-job-id="${item.jobId}" ${completed ? "" : "disabled"}>Set Left</button>
            <button type="button" class="ghost" data-action="right" data-job-id="${item.jobId}" ${completed ? "" : "disabled"}>Set Right</button>
            <button type="button" class="ghost" data-action="save-notes" data-job-id="${item.jobId}">Save Notes</button>
            <button type="button" class="ghost" data-action="rerun" data-job-id="${item.jobId}">Re-run</button>
            <button type="button" class="ghost" data-action="download" data-job-id="${item.jobId}" ${completed ? "" : "disabled"}>Download</button>
          </div>
        </div>
      </article>
    `;
  }).join("");
}

driveUpload.addEventListener("click", () => {
  const downloadPath = driveUpload.dataset.downloadPath;
  if (!downloadPath) {
    jobStatus.textContent = "Generate a model first.";
    return;
  }

  window.open("https://drive.google.com/drive/my-drive", "_blank", "noopener,noreferrer");
  window.open(downloadPath, "_blank", "noopener,noreferrer");
  jobStatus.textContent =
    "Opened Google Drive and the current GLB download. Google still requires manual upload unless we add OAuth credentials.";
});

previewPresets.forEach((button) => {
  button.addEventListener("click", () => {
    const presetName = button.id.replace("preset-", "");
    applyPreviewPreset(presetName);
  });
});

tintPicker.addEventListener("input", (event) => {
  applyModelTint(event.target.value);
});

tintSwatches.forEach((button) => {
  button.style.background = button.dataset.color;
  button.addEventListener("click", () => {
    applyModelTint(button.dataset.color);
  });
});

themeOptions.forEach((button) => {
  button.addEventListener("click", () => {
    applyTheme(button.dataset.theme);
  });
});

modelPreview.addEventListener("load", () => {
  applyModelTint(currentTint);
});
compareLeftViewer.addEventListener("load", () => applyModelTint(currentTint));
compareRightViewer.addEventListener("load", () => applyModelTint(currentTint));

logsToggle.addEventListener("click", () => {
  const isHidden = logsPanel.classList.toggle("hidden");
  logsToggle.setAttribute("aria-expanded", String(!isHidden));
  logsToggle.textContent = isHidden ? "Show Logs" : "Hide Logs";
});

bootstrapToggle.addEventListener("click", () => {
  const isHidden = bootstrapPanel.classList.toggle("hidden");
  bootstrapToggle.setAttribute("aria-expanded", String(!isHidden));
  bootstrapToggle.textContent = isHidden ? "Show Hunyuan Painter" : "Hide Hunyuan Painter";
});

historyList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }

  const action = button.dataset.action;
  const jobId = button.dataset.jobId;
  const item = findHistoryItem(jobId);
  if (!item) {
    jobStatus.textContent = "History item no longer exists.";
    return;
  }

  try {
    if (action === "preview" && item.status === "completed") {
      showPreview(item);
      return;
    }
    if (action === "left" && item.status === "completed") {
      compareSelection.left = jobId;
      renderCompare();
      return;
    }
    if (action === "right" && item.status === "completed") {
      compareSelection.right = jobId;
      renderCompare();
      return;
    }
    if (action === "download" && item.status === "completed") {
      window.open(item.downloadPath, "_blank", "noopener,noreferrer");
      return;
    }
    if (action === "save-notes") {
      const textarea = historyList.querySelector(`textarea[data-notes-input="${jobId}"]`);
      const notes = textarea ? textarea.value : "";
      await api(`/api/history/${jobId}/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes }),
      });
      jobStatus.textContent = `Saved notes for ${jobId.slice(0, 8)}.`;
      await refresh();
      return;
    }
    if (action === "rerun") {
      const result = await api(`/api/history/rerun/${jobId}`, { method: "POST" });
      currentJobId = result.uid;
      resetPreview();
      jobStatus.textContent = `Queued rerun ${currentJobId} from history item ${jobId.slice(0, 8)}.`;
      clearInterval(pollHandle);
      pollHandle = setInterval(() => pollJob(currentJobId), 3000);
      pollJob(currentJobId);
      await refresh();
    }
  } catch (error) {
    jobStatus.textContent = error.message;
  }
});

queueBoard.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-queue-action='cancel']");
  if (!button) {
    return;
  }
  try {
    const result = await api(`/api/jobs/${button.dataset.jobId}/cancel`, { method: "POST" });
    jobStatus.textContent = result.status === "cancelled"
      ? `Cancelled job ${button.dataset.jobId.slice(0, 8)}.`
      : `Cancellation requested for job ${button.dataset.jobId.slice(0, 8)}.`;
    await refresh();
  } catch (error) {
    jobStatus.textContent = error.message;
  }
});

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

function renderKeyValues(container, rows) {
  container.innerHTML = rows
    .map(([key, value]) => `<div><strong>${key}</strong>: ${value}</div>`)
    .join("");
}

function renderResourceCards(resources) {
  const gpu = resources.gpu.available
    ? `
      <div class="resource-card">
        <span class="resource-label">GPU</span>
        <strong>${resources.gpu.utilizationPercent}%</strong>
        <span class="muted">VRAM ${resources.gpu.memoryUsedGb} / ${resources.gpu.memoryTotalGb} GB</span>
        <span class="muted">${resources.gpu.temperatureC} C</span>
      </div>
    `
    : `
      <div class="resource-card">
        <span class="resource-label">GPU</span>
        <strong>Unavailable</strong>
        <span class="muted">${resources.gpu.error}</span>
      </div>
    `;

  resourceSummary.innerHTML = `
    <div class="resource-card">
      <span class="resource-label">CPU</span>
      <strong>${resources.cpuPercent}%</strong>
      <span class="muted">Live utilization</span>
    </div>
    <div class="resource-card">
      <span class="resource-label">Memory</span>
      <strong>${resources.memory.percent}%</strong>
      <span class="muted">${resources.memory.usedGb} / ${resources.memory.totalGb} GB</span>
    </div>
    ${gpu}
  `;
}

function renderQueueBoard(jobs) {
  const active = jobs.active;
  const pending = jobs.pending || [];
  const recent = jobs.recent || [];
  if (!active && !pending.length && !recent.length) {
    queueBoard.innerHTML = `<div class="muted">No queue activity yet.</div>`;
    return;
  }

  const renderJobRow = (job, activeRow = false) => `
    <div class="queue-job ${activeRow ? "queue-job-active" : ""}">
      <div class="queue-job-meta">
        <strong>${job.jobId.slice(0, 8)}</strong>
        <span class="history-status history-status-${job.status}">${job.status}</span>
        <span class="muted">Seed ${job.seed} | Steps ${job.steps} | Guidance ${job.guidanceScale}</span>
        ${job.cancelRequested ? `<span class="muted">Cancel requested</span>` : ""}
        ${job.error ? `<span class="muted">${job.error}</span>` : ""}
      </div>
      <div class="queue-job-actions">
        ${(job.status === "queued" || job.status === "starting" || job.status === "processing") ? `<button type="button" class="ghost" data-queue-action="cancel" data-job-id="${job.jobId}">Cancel</button>` : ""}
      </div>
    </div>
  `;

  queueBoard.innerHTML = `
    <div class="queue-section">
      <div class="queue-heading">Active</div>
      ${active ? renderJobRow(active, true) : `<div class="muted">No active job.</div>`}
    </div>
    <div class="queue-section">
      <div class="queue-heading">Pending</div>
      ${pending.length ? pending.map((job) => renderJobRow(job)).join("") : `<div class="muted">No pending jobs.</div>`}
    </div>
    <div class="queue-section">
      <div class="queue-heading">Recent</div>
      ${recent.length ? recent.slice(0, 6).map((job) => renderJobRow(job)).join("") : `<div class="muted">No recent jobs.</div>`}
    </div>
  `;
}

async function refresh() {
  const [system, hunyuan, bootstrap, logs, resources, history, jobs] = await Promise.all([
    api("/api/system"),
    api("/api/hunyuan/status"),
    api("/api/bootstrap"),
    api("/api/hunyuan/logs"),
    api("/api/resources"),
    api("/api/history"),
    api("/api/jobs"),
  ]);

  const gpu = system.gpu.available
    ? `${system.gpu.name} (${system.gpu.memoryMb} MB, recommended: ${system.gpu.recommendedProfile})`
    : system.gpu.error;

  renderKeyValues(systemSummary, [
    ["Platform", system.platform],
    ["Python", system.python],
    ["Node", system.node],
    ["Git", system.git],
    ["GPU", gpu],
    ["Python choices", system.pythonCandidates.map((item) => item.version).join(" | ") || "Not found"],
  ]);

  renderKeyValues(hunyuanSummary, [
    ["Repo", hunyuan.repoPresent ? "present" : "missing"],
    ["Virtual env", hunyuan.venvPresent ? "present" : "missing"],
    ["Tracked PID", hunyuan.pid || "none"],
    ["Reachable", hunyuan.reachable ? "yes" : "no"],
    ["Texture backend", system.config.enableTexture ? "enabled" : "disabled"],
    ["Log", hunyuan.logPath],
  ]);

  currentConfig = system.config;
  backendTextureToggle.checked = Boolean(system.config.enableTexture);

  bootstrapCommand.textContent =
    `powershell -ExecutionPolicy Bypass -File "${bootstrap.scriptPath}"\n` +
    `python -m uvicorn app:app --host 127.0.0.1 --port ${system.config.launcherPort}`;

  logsEl.textContent = logs.lines.join("\n");
  renderResourceCards(resources);
  historyEntries = history.items || [];
  renderHistory(historyEntries);
  renderCompare();
  renderQueueBoard(jobs);
}

document.getElementById("refresh-btn").addEventListener("click", refresh);

document.getElementById("start-btn").addEventListener("click", async () => {
  try {
    const result = await api("/api/hunyuan/start", { method: "POST" });
    jobStatus.textContent = result.started
      ? `Started Hunyuan API with PID ${result.pid}.${backendTextureToggle.checked ? " Texture backend enabled." : ""}`
      : result.message;
    await refresh();
  } catch (error) {
    jobStatus.textContent = error.message;
  }
});

document.getElementById("stop-btn").addEventListener("click", async () => {
  try {
    const result = await api("/api/hunyuan/stop", { method: "POST" });
    jobStatus.textContent = result.stopped
      ? `Stopped Hunyuan API PID ${result.pid}.`
      : result.message;
    await refresh();
  } catch (error) {
    jobStatus.textContent = error.message;
  }
});

document.getElementById("exit-btn").addEventListener("click", async () => {
  try {
    jobStatus.textContent = "Shutting down Forge.AI and the Hunyuan backend...";
    await api("/api/shutdown", { method: "POST" });
    setTimeout(() => {
      window.open("", "_self");
      window.close();
      jobStatus.textContent = "Launcher stopped. You can close this tab if it stays open.";
    }, 400);
  } catch (error) {
    jobStatus.textContent = error.message;
  }
});

backendTextureToggle.addEventListener("change", async (event) => {
  try {
    const enableTexture = event.target.checked;
    await api("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enableTexture }),
    });
    currentConfig = { ...(currentConfig || {}), enableTexture };
    jobStatus.textContent = enableTexture
      ? "Texture backend enabled in config. Restart the Hunyuan API to load Hunyuan Paint."
      : "Texture backend disabled in config. Restart the Hunyuan API to unload Hunyuan Paint.";
    await refresh();
  } catch (error) {
    backendTextureToggle.checked = !event.target.checked;
    jobStatus.textContent = error.message;
  }
});

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result);
      resolve(result.split(",")[1]);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function pollJob(jobId) {
  try {
    const result = await api(`/api/generate/${jobId}`);
    if (result.status === "completed") {
      clearInterval(pollHandle);
      pollHandle = null;
      jobStatus.innerHTML =
        `Completed. <a href="${result.downloadPath}" target="_blank" rel="noreferrer">Download ${result.fileName}</a>`;
      showPreview(result);
      await refresh();
      return;
    }
    if (result.status === "cancelled") {
      clearInterval(pollHandle);
      pollHandle = null;
      jobStatus.textContent = `Job ${jobId} was cancelled.`;
      await refresh();
      return;
    }
    if (result.status === "failed") {
      clearInterval(pollHandle);
      pollHandle = null;
      jobStatus.textContent = result.error || `Job ${jobId} failed.`;
      await refresh();
      return;
    }
    jobStatus.textContent = `Job ${jobId} is ${result.status || "processing"}...`;
  } catch (error) {
    clearInterval(pollHandle);
    pollHandle = null;
    jobStatus.textContent = error.message;
  }
}

generateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const file = document.getElementById("image-input").files[0];
    if (!file) {
      throw new Error("Choose an image first.");
    }

    const image = await fileToBase64(file);
    const payload = {
      image,
      imageMimeType: file.type || "image/png",
      notes: notesInput.value || "",
      seed: Number(document.getElementById("seed-input").value || 1234),
      steps: Number(document.getElementById("steps-input").value || 5),
      guidanceScale: Number(document.getElementById("guidance-input").value || 5),
      texture: document.getElementById("texture-input").checked,
    };

    if (payload.texture && !(currentConfig && currentConfig.enableTexture)) {
      throw new Error("Enable Hunyuan Paint texture backend in Bootstrap first, then restart the Hunyuan API.");
    }

    const result = await api("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    currentJobId = result.uid;
    resetPreview();
    jobStatus.textContent = `Queued job ${currentJobId}. Waiting for output...`;
    clearInterval(pollHandle);
    pollHandle = setInterval(() => pollJob(currentJobId), 3000);
    pollJob(currentJobId);
  } catch (error) {
    jobStatus.textContent = error.message;
  }
});

resetPreview();
applyTheme((() => {
  try {
    return window.localStorage.getItem("forge3d-theme") || "green";
  } catch (_error) {
    return "green";
  }
})());
applyPreviewPreset(currentPreviewPreset);
applyModelTint(currentTint);
refresh();
setInterval(refresh, 15000);
