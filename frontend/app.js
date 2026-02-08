const stageOrder = [
  "queued",
  "validating",
  "preparing",
  "recognizing",
  "converting_abc",
  "converting_midi",
  "packaging",
  "complete",
];

const state = {
  file: null,
  busy: false,
  jobId: null,
  pollTimer: null,
  errorNotifiedForJob: null,
};

const elements = {
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("fileInput"),
  fileChip: document.getElementById("fileChip"),
  fileName: document.getElementById("fileName"),
  fileMeta: document.getElementById("fileMeta"),
  runButton: document.getElementById("runButton"),
  progressBar: document.getElementById("progressBar"),
  progressText: document.getElementById("progressText"),
  statusBadge: document.getElementById("statusBadge"),
  abcOutput: document.getElementById("abcOutput"),
  logOutput: document.getElementById("logOutput"),
  midiDownload: document.getElementById("midiDownload"),
  musicxmlDownload: document.getElementById("musicxmlDownload"),
  previewWrap: document.getElementById("previewWrap"),
  previewImage: document.getElementById("previewImage"),
  copyAbcButton: document.getElementById("copyAbcButton"),
  pipelineItems: Array.from(document.querySelectorAll("#pipeline li")),
  tabs: Array.from(document.querySelectorAll(".tab")),
  tabPanels: Array.from(document.querySelectorAll(".tab-panel")),
  toast: document.getElementById("toast"),
};

function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function showToast(message) {
  if (!message) {
    return;
  }

  elements.toast.textContent = message;
  elements.toast.classList.add("show");

  window.clearTimeout(showToast.hideTimer);
  showToast.hideTimer = window.setTimeout(() => {
    elements.toast.classList.remove("show");
  }, 2800);
}

function extractError(payload, fallback) {
  if (!payload) {
    return fallback;
  }
  if (typeof payload.error === "string") {
    return payload.error;
  }
  if (typeof payload.detail === "string") {
    return payload.detail;
  }
  if (payload.detail && typeof payload.detail.error === "string") {
    return payload.detail.error;
  }
  return fallback;
}

function setBusy(isBusy) {
  state.busy = isBusy;
  elements.runButton.disabled = isBusy || !state.file;
  elements.runButton.textContent = isBusy ? "Transcribing..." : "Transcribe Score";
}

function setStatusBadge(status) {
  elements.statusBadge.className = `status-badge ${status}`;
  elements.statusBadge.textContent = status;
}

function resetOutputs() {
  elements.abcOutput.textContent = "ABC output will appear here.";
  elements.logOutput.textContent = "Execution log will appear here.";
  elements.previewWrap.hidden = true;
  elements.previewImage.removeAttribute("src");
  setDownloadLink(elements.midiDownload, null);
  setDownloadLink(elements.musicxmlDownload, null);
  updatePipeline("queued", "queued");
  setProgress(0, "Waiting for processing to start.");
  setStatusBadge("idle");
}

function setDownloadLink(anchor, href) {
  if (!href) {
    anchor.href = "#";
    anchor.classList.add("disabled");
    anchor.setAttribute("aria-disabled", "true");
    return;
  }

  anchor.href = href;
  anchor.classList.remove("disabled");
  anchor.removeAttribute("aria-disabled");
}

function setProgress(progressValue, message) {
  const value = Math.max(0, Math.min(progressValue, 1));
  elements.progressBar.style.width = `${Math.round(value * 100)}%`;
  elements.progressText.textContent = message;
}

function updatePipeline(stage, status) {
  let stageIndex = stageOrder.indexOf(stage);
  if (stageIndex < 0) {
    stageIndex = 0;
  }

  elements.pipelineItems.forEach((item, index) => {
    item.classList.remove("is-active", "is-complete", "is-error");

    if (status === "complete") {
      item.classList.add("is-complete");
      return;
    }

    if (status === "error") {
      if (index < stageIndex) {
        item.classList.add("is-complete");
      } else if (index === stageIndex) {
        item.classList.add("is-error");
      }
      return;
    }

    if (index < stageIndex) {
      item.classList.add("is-complete");
    } else if (index === stageIndex) {
      item.classList.add("is-active");
    }
  });
}

function activateTab(tabName) {
  elements.tabs.forEach((tab) => {
    const active = tab.dataset.tab === tabName;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  });

  elements.tabPanels.forEach((panel) => {
    const active = panel.id === `tab-${tabName}`;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  });
}

function applySelectedFile(file) {
  state.file = file;
  if (!file) {
    elements.fileChip.hidden = true;
    elements.runButton.disabled = true;
    return;
  }

  elements.fileName.textContent = file.name;
  elements.fileMeta.textContent = `${formatBytes(file.size)} • ${file.type || "Unknown type"}`;
  elements.fileChip.hidden = false;
  elements.runButton.disabled = state.busy;
}

async function pollJob() {
  if (!state.jobId) {
    return;
  }

  try {
    const response = await fetch(`/api/jobs/${state.jobId}`);
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(extractError(payload, "Failed to fetch job status"));
    }

    renderJob(payload.job);

    if (payload.job.status === "complete" || payload.job.status === "error") {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
      setBusy(false);

      if (payload.job.status === "complete") {
        showToast("Transcription complete.");
      }
      if (payload.job.status === "error" && state.errorNotifiedForJob !== payload.job.id) {
        state.errorNotifiedForJob = payload.job.id;
        showToast(payload.job.error || "Transcription failed.");
      }
    }
  } catch (error) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
    setBusy(false);
    setStatusBadge("error");
    showToast(error.message || "Polling failed");
  }
}

function renderJob(job) {
  const status =
    job.status === "processing" || job.status === "queued"
      ? "processing"
      : job.status;
  setStatusBadge(status);
  updatePipeline(job.stage, job.status);
  setProgress(job.progress || 0, job.error || job.message || "Processing");

  if (job.preview_url) {
    elements.previewImage.src = `${job.preview_url}?v=${job.updated_at}`;
    elements.previewWrap.hidden = false;
  }

  if (job.abc_text && job.abc_text.trim()) {
    elements.abcOutput.textContent = job.abc_text;
  }

  const logText = Array.isArray(job.log) && job.log.length > 0
    ? job.log.join("\n")
    : "Execution log will appear here.";
  elements.logOutput.textContent = logText;

  setDownloadLink(elements.midiDownload, job.downloads?.midi || null);
  setDownloadLink(elements.musicxmlDownload, job.downloads?.musicxml || null);
}

async function submitJob() {
  if (!state.file || state.busy) {
    return;
  }

  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }

  resetOutputs();
  setBusy(true);
  setStatusBadge("processing");
  setProgress(0.05, "Uploading file...");

  try {
    const formData = new FormData();
    formData.append("file", state.file);

    const response = await fetch("/api/jobs", {
      method: "POST",
      body: formData,
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(extractError(payload, "Failed to start transcription job"));
    }

    state.jobId = payload.job.id;
    state.errorNotifiedForJob = null;
    renderJob(payload.job);

    await pollJob();
    if (!state.pollTimer) {
      state.pollTimer = window.setInterval(pollJob, 1500);
    }
  } catch (error) {
    setBusy(false);
    setStatusBadge("error");
    setProgress(1, error.message || "Failed to start transcription.");
    showToast(error.message || "Upload failed");
  }
}

function installDropzone() {
  const dropzone = elements.dropzone;

  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("drag-over");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("drag-over");
  });

  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("drag-over");

    const file = event.dataTransfer?.files?.[0];
    if (!file) {
      return;
    }

    elements.fileInput.files = event.dataTransfer.files;
    applySelectedFile(file);
  });
}

function installTabs() {
  elements.tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      activateTab(tab.dataset.tab);
    });
  });
}

function installConstellation() {
  const canvas = document.getElementById("constellation");
  if (!canvas) {
    return;
  }

  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return;
  }

  const points = [];
  let width = 0;
  let height = 0;
  let dpr = 1;

  function resize() {
    dpr = window.devicePixelRatio || 1;
    width = window.innerWidth;
    height = window.innerHeight;

    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const count = Math.max(18, Math.floor((width * height) / 42000));
    points.length = 0;

    for (let index = 0; index < count; index += 1) {
      points.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.22,
        vy: (Math.random() - 0.5) * 0.22,
      });
    }
  }

  function tick() {
    ctx.clearRect(0, 0, width, height);

    for (let i = 0; i < points.length; i += 1) {
      const a = points[i];
      a.x += a.vx;
      a.y += a.vy;

      if (a.x < 0 || a.x > width) {
        a.vx *= -1;
      }
      if (a.y < 0 || a.y > height) {
        a.vy *= -1;
      }

      ctx.fillStyle = "rgba(31, 111, 235, 0.33)";
      ctx.beginPath();
      ctx.arc(a.x, a.y, 1.2, 0, Math.PI * 2);
      ctx.fill();

      for (let j = i + 1; j < points.length; j += 1) {
        const b = points[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const distance = Math.hypot(dx, dy);

        if (distance < 112) {
          const alpha = 1 - distance / 112;
          ctx.strokeStyle = `rgba(14, 165, 183, ${alpha * 0.23})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    window.requestAnimationFrame(tick);
  }

  resize();
  window.addEventListener("resize", resize);
  window.requestAnimationFrame(tick);
}

function installCopyButton() {
  elements.copyAbcButton.addEventListener("click", async () => {
    const text = elements.abcOutput.textContent || "";
    if (!text || text === "ABC output will appear here.") {
      showToast("No ABC output to copy yet.");
      return;
    }

    try {
      await navigator.clipboard.writeText(text);
      showToast("ABC copied to clipboard.");
    } catch (_error) {
      showToast("Clipboard access failed.");
    }
  });
}

function init() {
  resetOutputs();
  installDropzone();
  installTabs();
  installConstellation();
  installCopyButton();

  elements.fileInput.addEventListener("change", (event) => {
    const file = event.target.files?.[0] || null;
    applySelectedFile(file);
  });

  elements.runButton.addEventListener("click", submitJob);
}

init();
