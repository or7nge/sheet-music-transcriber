const state = {
  file: null,
  busy: false,
  jobId: null,
  pollTimer: null,
  cards: new Map(),
};

const elements = {
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("fileInput"),
  fileChip: document.getElementById("fileChip"),
  fileName: document.getElementById("fileName"),
  fileMeta: document.getElementById("fileMeta"),
  fileMetaHint: document.getElementById("fileMetaHint"),
  pasteImageButton: document.getElementById("pasteImageButton"),
  progressBar: document.getElementById("progressBar"),
  progressText: document.getElementById("progressText"),
  historyPanel: document.getElementById("historyPanel"),
  historyList: document.getElementById("historyList"),
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

function formatTime(timestamp = Date.now()) {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function showToast(message) {
  if (!message || !elements.toast) {
    return;
  }

  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    elements.toast.classList.remove("show");
  }, 2600);
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
  document.body.classList.toggle("is-busy", isBusy);
  elements.pasteImageButton.disabled = isBusy;
  elements.fileInput.disabled = isBusy;
  elements.dropzone.classList.toggle("is-disabled", isBusy);
  elements.fileMetaHint.textContent = isBusy
    ? "Transcription in progress"
    : state.file
      ? "Choose another score after the current job finishes"
      : "Choose one score to transcribe";
}

function setProgress(progress, message) {
  const safeProgress = Math.max(0, Math.min(1, Number(progress) || 0));
  elements.progressBar.style.width = `${(safeProgress * 100).toFixed(1)}%`;
  elements.progressText.textContent = message || "Waiting for a file.";
}

function setDownloadLink(anchor, href) {
  if (!href) {
    anchor.href = "#";
    anchor.classList.add("is-disabled");
    anchor.setAttribute("aria-disabled", "true");
    return;
  }

  anchor.href = href;
  anchor.classList.remove("is-disabled");
  anchor.removeAttribute("aria-disabled");
}

function ensureResultsVisible() {
  document.body.classList.add("has-results");
  if (elements.historyPanel) {
    elements.historyPanel.hidden = false;
  }
}

function resetProgress() {
  setProgress(0, "Waiting for processing to start.");
}

function createHistoryCard(jobId, filename) {
  const article = document.createElement("article");
  article.className = "history-card";
  article.dataset.jobId = jobId;
  article.innerHTML = `
    <div class="history-card-head">
      <div>
        <p class="history-title"></p>
        <p class="history-meta"></p>
      </div>
      <span class="history-status">Queued</span>
    </div>
    <div class="history-preview" hidden>
      <img alt="Transcribed score preview" loading="lazy" />
    </div>
    <div class="history-actions">
      <button class="secondary" type="button" data-copy="notes" disabled>Copy Notes</button>
      <a class="download-link is-disabled" data-link="midi" href="#" aria-disabled="true">MIDI</a>
      <a class="download-link is-disabled" data-link="musicxml" href="#" aria-disabled="true">MusicXML</a>
      <button class="secondary" type="button" data-toggle-log disabled>Show Log</button>
    </div>
    <section class="history-section">
      <h3>Notes</h3>
      <pre class="history-notes">Notes will appear here.</pre>
    </section>
    <section class="history-section" data-log-section hidden>
      <h3>Execution Log</h3>
      <pre class="history-log">Execution log will appear here.</pre>
    </section>
  `;

  const card = {
    root: article,
    title: article.querySelector(".history-title"),
    meta: article.querySelector(".history-meta"),
    status: article.querySelector(".history-status"),
    previewWrap: article.querySelector(".history-preview"),
    previewImage: article.querySelector(".history-preview img"),
    copyNotesButton: article.querySelector('[data-copy="notes"]'),
    midiLink: article.querySelector('[data-link="midi"]'),
    musicxmlLink: article.querySelector('[data-link="musicxml"]'),
    logToggleButton: article.querySelector("[data-toggle-log]"),
    logSection: article.querySelector("[data-log-section]"),
    notes: article.querySelector(".history-notes"),
    log: article.querySelector(".history-log"),
  };

  card.title.textContent = filename;
  card.meta.textContent = `Started ${formatTime()}`;

  card.copyNotesButton.addEventListener("click", async () => {
    const text = card.notes.textContent || "";
    if (!text || text === "Notes will appear here.") {
      showToast("No note output to copy yet.");
      return;
    }

    try {
      await navigator.clipboard.writeText(text);
      showToast("Notes copied.");
    } catch (_error) {
      showToast("Clipboard access failed.");
    }
  });

  card.logToggleButton.addEventListener("click", () => {
    const willShow = card.logSection.hidden;
    card.logSection.hidden = !willShow;
    card.logToggleButton.textContent = willShow ? "Hide Log" : "Show Log";
  });

  return card;
}

function renderJobIntoCard(card, job) {
  card.status.textContent = job.status === "complete" ? "Complete" : job.status === "error" ? "Error" : "Running";
  card.status.dataset.state = job.status;
  card.meta.textContent =
    job.status === "complete"
      ? `Finished ${formatTime(job.updated_at * 1000)}`
      : job.status === "error"
        ? `Failed ${formatTime(job.updated_at * 1000)}`
        : `${job.message || "Processing"} • ${formatTime(job.updated_at * 1000)}`;

  if (job.preview_url) {
    card.previewImage.src = `${job.preview_url}?v=${job.updated_at}`;
    card.previewWrap.hidden = false;
  }

  if (job.concise_notes_text && job.concise_notes_text.trim()) {
    card.notes.textContent = job.concise_notes_text;
    card.copyNotesButton.disabled = false;
  }

  const hasLog = Array.isArray(job.log) && job.log.length > 0;
  card.log.textContent = hasLog ? job.log.join("\n") : "Execution log will appear here.";
  card.logToggleButton.disabled = !hasLog;
  if (job.status === "error" && hasLog) {
    card.logSection.hidden = false;
    card.logToggleButton.textContent = "Hide Log";
  }

  setDownloadLink(card.midiLink, job.downloads?.midi || null);
  setDownloadLink(card.musicxmlLink, job.downloads?.musicxml || null);
}

function renderJob(job) {
  const card = state.cards.get(job.id);
  if (card) {
    renderJobIntoCard(card, job);
  }

  setProgress(
    job.status === "complete" ? 1 : job.progress || 0,
    job.error || job.message || "Processing",
  );
}

function stopPolling() {
  if (state.pollTimer) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

async function pollJob() {
  if (!state.jobId) {
    return;
  }

  try {
    const response = await fetch(`/api/jobs/${state.jobId}`);
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(extractError(payload, "Failed to fetch job status."));
    }

    const job = payload.job;
    renderJob(job);

    if (job.status === "complete" || job.status === "error") {
      stopPolling();
      setBusy(false);
      ensureResultsVisible();
      if (job.status === "error") {
        showToast(job.error || "Transcription failed.");
      }
      return;
    }

    state.pollTimer = window.setTimeout(pollJob, 1200);
  } catch (error) {
    stopPolling();
    setBusy(false);
    setProgress(1, error.message || "Polling failed.");
    showToast(error.message || "Polling failed.");
  }
}

async function submitJob() {
  if (!state.file || state.busy) {
    return;
  }

  stopPolling();
  resetProgress();
  setBusy(true);
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
      throw new Error(extractError(payload, "Failed to start transcription job."));
    }

    const { job } = payload;
    state.jobId = job.id;

    const card = createHistoryCard(job.id, job.filename || state.file.name || "Untitled score");
    elements.historyList.prepend(card.root);
    state.cards.set(job.id, card);

    ensureResultsVisible();
    renderJob(job);
    state.pollTimer = window.setTimeout(pollJob, 400);
  } catch (error) {
    setBusy(false);
    setProgress(1, error.message || "Upload failed.");
    showToast(error.message || "Upload failed.");
  }
}

function applySelectedFile(file) {
  if (!file) {
    return;
  }

  if (state.busy) {
    showToast("Wait for the current transcription to finish.");
    return;
  }

  state.file = file;
  elements.fileChip.hidden = false;
  elements.fileName.textContent = file.name;
  elements.fileMeta.textContent = `${formatBytes(file.size)} • ${file.type || "Unknown type"}`;
  elements.fileMetaHint.textContent = "File selected. Starting transcription.";
  submitJob();
}

function fileExtensionForImageType(type) {
  if (type === "image/jpeg") {
    return "jpg";
  }
  if (type && type.startsWith("image/")) {
    return type.slice(6);
  }
  return "png";
}

function buildClipboardImageFile(blob) {
  if (!blob || !blob.type || !blob.type.startsWith("image/")) {
    return null;
  }

  if (blob instanceof File && blob.name) {
    return blob;
  }

  const extension = fileExtensionForImageType(blob.type);
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  return new File([blob], `clipboard-image-${stamp}.${extension}`, {
    type: blob.type,
    lastModified: Date.now(),
  });
}

function extractImageFromClipboardData(items) {
  if (!items) {
    return null;
  }

  for (const item of Array.from(items)) {
    if (item.kind === "file" && item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) {
        return buildClipboardImageFile(file);
      }
    }
  }

  return null;
}

async function extractImageFromClipboardApi(items) {
  for (const item of items) {
    const imageType = (item.types || []).find((type) => type.startsWith("image/"));
    if (!imageType) {
      continue;
    }

    const blob = await item.getType(imageType);
    const file = buildClipboardImageFile(blob);
    if (file) {
      return file;
    }
  }

  return null;
}

function installClipboardPaste() {
  window.addEventListener("paste", (event) => {
    if (state.busy) {
      return;
    }

    const file = extractImageFromClipboardData(event.clipboardData?.items);
    if (!file) {
      return;
    }

    event.preventDefault();
    applySelectedFile(file);
  });

  elements.pasteImageButton.addEventListener("click", async () => {
    if (state.busy) {
      showToast("Wait for the current transcription to finish.");
      return;
    }

    if (!navigator.clipboard || typeof navigator.clipboard.read !== "function") {
      showToast("Paste with Cmd/Ctrl+V instead.");
      return;
    }

    try {
      const clipboardItems = await navigator.clipboard.read();
      const file = await extractImageFromClipboardApi(clipboardItems);
      if (!file) {
        showToast("No image found in clipboard.");
        return;
      }
      applySelectedFile(file);
    } catch (_error) {
      showToast("Clipboard access denied.");
    }
  });
}

function installDropzone() {
  const dropzone = elements.dropzone;

  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (!state.busy) {
      dropzone.classList.add("is-drag-over");
    }
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("is-drag-over");
  });

  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-drag-over");
    if (state.busy) {
      return;
    }

    const file = event.dataTransfer?.files?.[0];
    if (!file) {
      return;
    }

    elements.fileInput.files = event.dataTransfer.files;
    applySelectedFile(file);
  });

  elements.fileInput.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (file) {
      applySelectedFile(file);
    }
  });
}

function init() {
  resetProgress();
  if (elements.historyPanel) {
    elements.historyPanel.hidden = true;
  }
  installDropzone();
  installClipboardPaste();
}

window.addEventListener("DOMContentLoaded", init);
