const state = {
  file: null,
  busy: false,
  busyEndingTimer: null,
  layoutShiftTimer: null,
  startupHintDismissed: false,
  jobId: null,
  pollTimer: null,
  errorNotifiedForJob: null,
  displayedProgress: 0,
  progressTarget: 0,
  progressLastFrame: 0,
  progressAnimation: null,
  cards: new Map(),
};

const elements = {
  historyPanel: document.getElementById("historyPanel"),
  historyList: document.getElementById("historyList"),
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("fileInput"),
  fileChip: document.getElementById("fileChip"),
  fileName: document.getElementById("fileName"),
  fileMeta: document.getElementById("fileMeta"),
  fileMetaHint: document.getElementById("fileMetaHint"),
  pasteImageButton: document.getElementById("pasteImageButton"),
  progressBar: document.getElementById("progressBar"),
  progressText: document.getElementById("progressText"),
  startupHintZone: document.getElementById("startupHintZone"),
  startupHint: document.getElementById("startupHint"),
  toast: document.getElementById("toast"),
  glassPanels: Array.from(document.querySelectorAll(".glass-reactive")),
};

const pointerFine = window.matchMedia("(pointer:fine)").matches;
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const hardwareThreads = navigator.hardwareConcurrency || 4;
const lowPowerDevice = hardwareThreads <= 4 || (!pointerFine && !reduceMotion);

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatTime() {
  return new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function installResizePerformanceGuard() {
  let resizeTimer = null;

  window.addEventListener(
    "resize",
    () => {
      document.body.classList.add("is-resizing");
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        document.body.classList.remove("is-resizing");
      }, 220);
    },
    { passive: true },
  );
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

function setCompletionLayout(hasCompletedResult) {
  const nextState = Boolean(hasCompletedResult);
  const prevState = document.body.classList.contains("has-results");

  if (prevState === nextState) {
    if (!nextState) {
      document.body.classList.remove("layout-shifting");
    }
    refreshStartupHint();
    return;
  }

  document.body.classList.toggle("has-results", nextState);

  if (!reduceMotion) {
    document.body.classList.add("layout-shifting");
    if (state.layoutShiftTimer) {
      window.clearTimeout(state.layoutShiftTimer);
    }
    state.layoutShiftTimer = window.setTimeout(() => {
      document.body.classList.remove("layout-shifting");
      state.layoutShiftTimer = null;
    }, 560);
  }

  refreshStartupHint();
}

function refreshStartupHint() {
  if (!elements.startupHint || !elements.startupHintZone) {
    return;
  }

  const shouldShow =
    !state.startupHintDismissed &&
    !state.busy &&
    !state.file &&
    !document.body.classList.contains("has-results");

  elements.startupHint.classList.toggle("is-hidden", !shouldShow);
  elements.startupHintZone.classList.toggle("is-hidden", !shouldShow);
}

function installStartupHint() {
  if (!elements.startupHint || !elements.startupHintZone) {
    return;
  }

  let lastWidth = window.innerWidth;
  let lastHeight = window.innerHeight;

  window.addEventListener("resize", () => {
    const nextWidth = window.innerWidth;
    const nextHeight = window.innerHeight;
    const widthChanged = Math.abs(nextWidth - lastWidth) > 1;
    const heightChanged = Math.abs(nextHeight - lastHeight) > 1;
    lastWidth = nextWidth;
    lastHeight = nextHeight;

    if (!widthChanged && !heightChanged) {
      return;
    }

    if (state.startupHintDismissed) {
      return;
    }

    state.startupHintDismissed = true;
    refreshStartupHint();
  });

  refreshStartupHint();
}

function setBusy(isBusy) {
  const wasBusy = state.busy;
  state.busy = isBusy;
  if (elements.pasteImageButton) {
    elements.pasteImageButton.disabled = isBusy;
  }

  if (state.busyEndingTimer) {
    window.clearTimeout(state.busyEndingTimer);
    state.busyEndingTimer = null;
  }

  if (isBusy) {
    document.body.classList.add("is-busy");
    document.body.classList.remove("is-busy-ending");
    elements.fileMetaHint.textContent = "Transcribing automatically...";
    refreshStartupHint();
    return;
  }

  document.body.classList.remove("is-busy");
  if (wasBusy) {
    document.body.classList.add("is-busy-ending");
    state.busyEndingTimer = window.setTimeout(() => {
      if (!state.busy) {
        document.body.classList.remove("is-busy-ending");
      }
      state.busyEndingTimer = null;
    }, reduceMotion ? 420 : 3600);
  } else {
    document.body.classList.remove("is-busy-ending");
  }

  if (state.file) {
    elements.fileMetaHint.textContent = "Upload another score to transcribe again";
  } else {
    elements.fileMetaHint.textContent = "Choose one score to transcribe";
  }

  refreshStartupHint();
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

function animateProgress(now) {
  if (!state.progressLastFrame) {
    state.progressLastFrame = now;
  }

  const deltaSeconds = clamp((now - state.progressLastFrame) / 1000, 1 / 120, 0.08);
  state.progressLastFrame = now;

  const diff = state.progressTarget - state.displayedProgress;
  const response = 3.4 + Math.abs(diff) * 7.6;
  const blend = 1 - Math.exp(-response * deltaSeconds);
  state.displayedProgress += diff * blend;

  if (Math.abs(diff) < 0.0008) {
    state.displayedProgress = state.progressTarget;
  }

  elements.progressBar.style.width = `${(state.displayedProgress * 100).toFixed(2)}%`;

  if (state.displayedProgress === state.progressTarget) {
    state.progressAnimation = null;
    state.progressLastFrame = 0;
    return;
  }

  state.progressAnimation = window.requestAnimationFrame(animateProgress);
}

function setProgress(progressValue, message) {
  const incoming = clamp(progressValue, 0, 1);
  state.progressTarget = state.busy ? Math.max(state.progressTarget, incoming) : incoming;

  if (!state.progressAnimation && state.displayedProgress !== state.progressTarget) {
    state.progressLastFrame = 0;
    state.progressAnimation = window.requestAnimationFrame(animateProgress);
  }

  const safeMessage = typeof message === "string" ? message : "";
  elements.progressText.textContent = safeMessage;
  elements.progressText.classList.toggle("is-empty", safeMessage.length === 0);
}

function updatePipeline(_stage, _status, _options = {}) {
  // Stage wheel removed by design.
}

function applyMagnetic(scope = document) {
  if (!pointerFine) {
    return;
  }

  scope.querySelectorAll(".magnetic").forEach((element) => {
    if (element.dataset.magneticBound === "true") {
      return;
    }
    element.dataset.magneticBound = "true";

    element.addEventListener("pointermove", (event) => {
      if (element.disabled) {
        return;
      }
      const rect = element.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;
      element.style.transform = `translate(${x * 6}px, ${y * 5}px)`;
    });

    element.addEventListener("pointerleave", () => {
      element.style.transform = "";
    });
  });
}

function ensureHistoryPanelVisible() {
  if (document.body.classList.contains("has-results")) {
    return;
  }
  setCompletionLayout(true);
}

function setCardExpanded(card, expanded) {
  card.expanded = Boolean(expanded);
  card.root.classList.toggle("is-expanded", card.expanded);
  if (card.summary) {
    card.summary.setAttribute("aria-expanded", String(card.expanded));
  }
  if (card.toggleButton) {
    card.toggleButton.title = card.expanded ? "Collapse transcription" : "Expand transcription";
    card.toggleButton.setAttribute("aria-label", card.toggleButton.title);
  }
}

function createHistoryCard(jobId, filename) {
  const card = document.createElement("article");
  card.className = "history-card is-entering is-expanded";
  card.dataset.jobId = jobId;

  card.innerHTML = `
    <div class="history-summary" aria-expanded="true">
      <div class="history-main">
        <p class="history-title"></p>
        <p class="history-meta"></p>
      </div>
    </div>
    <div class="history-body">
      <div class="history-body-inner">
        <div class="history-preview" hidden>
          <img alt="Transcribed score preview" />
        </div>
        <div class="history-actions">
          <button class="secondary tiny magnetic history-copy-notes" type="button" disabled>Copy Notes</button>
          <button class="secondary tiny magnetic history-copy" type="button" disabled>Copy ABC</button>
          <a class="download-link magnetic disabled history-midi" href="#" aria-disabled="true">MIDI</a>
          <a class="download-link magnetic disabled history-xml" href="#" aria-disabled="true">MusicXML</a>
          <button class="secondary ghost tiny magnetic history-log-toggle" type="button" disabled>Show Log</button>
        </div>
        <pre class="history-notes">Concise notes will appear here.</pre>
        <pre class="history-abc">ABC output will appear here.</pre>
        <pre class="history-log" hidden>Execution log will appear here.</pre>
      </div>
    </div>
  `;

  const refs = {
    jobId,
    root: card,
    summary: card.querySelector(".history-summary"),
    title: card.querySelector(".history-title"),
    meta: card.querySelector(".history-meta"),
    toggleButton: card.querySelector(".history-toggle"),
    previewWrap: card.querySelector(".history-preview"),
    previewImage: card.querySelector(".history-preview img"),
    copyNotesButton: card.querySelector(".history-copy-notes"),
    copyButton: card.querySelector(".history-copy"),
    midiLink: card.querySelector(".history-midi"),
    musicxmlLink: card.querySelector(".history-xml"),
    logToggle: card.querySelector(".history-log-toggle"),
    notes: card.querySelector(".history-notes"),
    abc: card.querySelector(".history-abc"),
    log: card.querySelector(".history-log"),
    logVisible: false,
    expanded: true,
    status: "processing",
  };

  refs.title.textContent = filename;
  refs.meta.textContent = `Started ${formatTime()}`;

  refs.copyNotesButton.addEventListener("click", async () => {
    const text = refs.notes.textContent || "";
    if (!text || text === "Concise notes will appear here.") {
      showToast("No concise note output to copy yet.");
      return;
    }

    try {
      await navigator.clipboard.writeText(text);
      showToast("Concise notes copied to clipboard.");
    } catch (_error) {
      showToast("Clipboard access failed.");
    }
  });

  refs.copyButton.addEventListener("click", async () => {
    const text = refs.abc.textContent || "";
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

  refs.logToggle.addEventListener("click", () => {
    refs.logVisible = !refs.logVisible;
    refs.log.hidden = !refs.logVisible;
    refs.logToggle.textContent = refs.logVisible ? "Hide Log" : "Show Log";
  });

  applyMagnetic(card);

  window.setTimeout(() => {
    card.classList.remove("is-entering");
  }, 500);

  setCardExpanded(refs, true);
  return refs;
}

function setCardStatus(card, status) {
  card.status = status;

  if (status === "complete") {
    card.meta.textContent = `Finished ${formatTime()}`;
  } else if (status === "error") {
    card.meta.textContent = `Failed ${formatTime()}`;
  }
}

function renderJobIntoCard(card, job) {
  const status =
    job.status === "processing" || job.status === "queued"
      ? "processing"
      : job.status;

  setCardStatus(card, status);

  if (job.preview_url) {
    card.previewImage.src = `${job.preview_url}?v=${job.updated_at}`;
    card.previewWrap.hidden = false;
  }

  if (job.abc_text && job.abc_text.trim()) {
    card.abc.textContent = job.abc_text;
    card.copyButton.disabled = false;
  }

  if (job.concise_notes_text && job.concise_notes_text.trim()) {
    card.notes.textContent = job.concise_notes_text;
    card.copyNotesButton.disabled = false;
  }

  const hasLog = Array.isArray(job.log) && job.log.length > 0;
  card.log.textContent = hasLog ? job.log.join("\n") : "Execution log will appear here.";
  card.logToggle.disabled = !hasLog;
  if (!hasLog) {
    card.logVisible = false;
    card.log.hidden = true;
    card.logToggle.textContent = "Show Log";
  }

  setDownloadLink(card.midiLink, job.downloads?.midi || null);
  setDownloadLink(card.musicxmlLink, job.downloads?.musicxml || null);

  if (status === "error" && hasLog && !card.logVisible) {
    card.logVisible = true;
    card.log.hidden = false;
    card.logToggle.textContent = "Hide Log";
  }
}

function resetCurrentProgress() {
  updatePipeline("queued", "queued", { animate: false });
  if (state.progressAnimation) {
    window.cancelAnimationFrame(state.progressAnimation);
    state.progressAnimation = null;
  }
  state.progressLastFrame = 0;
  state.progressTarget = 0;
  state.displayedProgress = 0;
  elements.progressBar.style.width = "0%";
  setProgress(0, "Waiting for processing to start.");
}

function renderJob(job) {
  updatePipeline(job.stage, job.status);
  if (job.status === "complete") {
    setProgress(1, job.message || "Transcription complete.");
  } else {
    setProgress(job.progress || 0, job.error || job.message || "Processing");
  }

  const card = state.cards.get(job.id);
  if (card) {
    renderJobIntoCard(card, job);
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
      throw new Error(extractError(payload, "Failed to fetch job status"));
    }

    renderJob(payload.job);

    if (payload.job.status === "complete" || payload.job.status === "error") {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
      ensureHistoryPanelVisible();
      setBusy(false);

      if (payload.job.status === "error" && state.errorNotifiedForJob !== payload.job.id) {
        state.errorNotifiedForJob = payload.job.id;
        showToast(payload.job.error || "Transcription failed.");
      }
    }
  } catch (error) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
    setBusy(false);
    setProgress(1, error.message || "Polling failed.");
    showToast(error.message || "Polling failed");
  }
}

async function submitJob() {
  if (!state.file || state.busy) {
    return;
  }

  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }

  resetCurrentProgress();
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
      throw new Error(extractError(payload, "Failed to start transcription job"));
    }

    const job = payload.job;
    state.jobId = job.id;
    state.errorNotifiedForJob = null;

    const card = createHistoryCard(job.id, job.filename || state.file.name || "Untitled score");
    elements.historyList.prepend(card.root);
    state.cards.set(job.id, card);

    renderJob(job);

    await pollJob();
    if (!state.pollTimer) {
      state.pollTimer = window.setInterval(pollJob, 900);
    }
  } catch (error) {
    setBusy(false);
    setProgress(1, error.message || "Failed to start transcription.");
    showToast(error.message || "Upload failed");
  }
}

function applySelectedFile(file) {
  if (!file) {
    state.file = null;
    elements.fileChip.hidden = true;
    elements.fileMetaHint.textContent = "Choose one score to transcribe";
    refreshStartupHint();
    return;
  }

  if (state.busy) {
    showToast("Wait for the current transcription to finish before uploading another score.");
    return;
  }

  if (!document.body.classList.contains("has-results")) {
    setCompletionLayout(true);
  }

  state.file = file;
  elements.fileName.textContent = file.name;
  elements.fileMeta.textContent = `${formatBytes(file.size)} • ${file.type || "Unknown type"}`;
  elements.fileChip.hidden = false;
  refreshStartupHint();

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

function extractImageFileFromDataItems(items) {
  if (!items) {
    return null;
  }

  for (const item of Array.from(items)) {
    if (item.kind !== "file" || !item.type || !item.type.startsWith("image/")) {
      continue;
    }
    const file = item.getAsFile();
    if (file) {
      return buildClipboardImageFile(file);
    }
  }

  return null;
}

async function extractImageFileFromClipboardApi(clipboardItems) {
  for (const clipboardItem of clipboardItems) {
    let imageType = null;
    for (const type of clipboardItem.types || []) {
      if (type.startsWith("image/")) {
        imageType = type;
        break;
      }
    }
    if (!imageType) {
      continue;
    }

    const blob = await clipboardItem.getType(imageType);
    const file = buildClipboardImageFile(blob);
    if (file) {
      return file;
    }
  }

  return null;
}

function installClipboardImagePaste() {
  window.addEventListener("paste", (event) => {
    if (state.busy) {
      return;
    }

    const file = extractImageFileFromDataItems(event.clipboardData?.items);
    if (!file) {
      return;
    }

    event.preventDefault();
    applySelectedFile(file);
  });

  if (!elements.pasteImageButton) {
    return;
  }

  elements.pasteImageButton.addEventListener("click", async () => {
    if (state.busy) {
      showToast("Wait for the current transcription to finish before uploading another score.");
      return;
    }

    if (!navigator.clipboard || typeof navigator.clipboard.read !== "function") {
      showToast("Use Cmd/Ctrl+V to paste an image here.");
      return;
    }

    try {
      const clipboardItems = await navigator.clipboard.read();
      const file = await extractImageFileFromClipboardApi(clipboardItems);
      if (!file) {
        showToast("No image found in clipboard.");
        return;
      }
      applySelectedFile(file);
    } catch (_error) {
      showToast("Clipboard access denied. Use Cmd/Ctrl+V to paste.");
    }
  });
}

function installDropzone() {
  const dropzone = elements.dropzone;
  if (!dropzone) {
    return;
  }

  const edgeFollowX = 0.2;
  const edgeFollowY = 0.24;

  const setBlobPosition = (xPercent, yPercent) => {
    dropzone.style.setProperty("--ab-x", `${xPercent}%`);
    dropzone.style.setProperty("--ab-y", `${yPercent}%`);
  };

  const resetDropzoneMotion = () => {
    dropzone.style.setProperty("--dz-mx", "50%");
    dropzone.style.setProperty("--dz-my", "42%");
    dropzone.style.setProperty("--dz-rx", "0deg");
    dropzone.style.setProperty("--dz-ry", "0deg");
    dropzone.style.setProperty("--dz-ix", "0px");
    dropzone.style.setProperty("--dz-iy", "0px");
    dropzone.style.setProperty("--dz-ir", "0deg");
    dropzone.style.setProperty("--dz-nx", "0px");
    dropzone.style.setProperty("--dz-ny", "0px");
    dropzone.style.setProperty("--dz-nr", "0deg");
  };

  const setAmbientMode = () => {
    if (dropzone.classList.contains("drag-over")) {
      return;
    }

    dropzone.classList.add("is-ambient");
    dropzone.classList.remove("is-near");
    setBlobPosition(50, 42);
    resetDropzoneMotion();
  };

  const setNearMode = (ratioX, ratioY) => {
    dropzone.classList.add("is-near");
    dropzone.classList.remove("is-ambient");
    setBlobPosition(ratioX * 100, ratioY * 100);
  };

  const updateDropzoneMotion = (event, allowOutOfBounds = false) => {
    if (!Number.isFinite(event.clientX) || !Number.isFinite(event.clientY)) {
      return null;
    }

    const rect = dropzone.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return null;
    }

    const rawX = (event.clientX - rect.left) / rect.width;
    const rawY = (event.clientY - rect.top) / rect.height;
    const inBoundsX = clamp(rawX, 0, 1);
    const inBoundsY = clamp(rawY, 0, 1);
    const ratioX = clamp(rawX, allowOutOfBounds ? -edgeFollowX : 0, allowOutOfBounds ? 1 + edgeFollowX : 1);
    const ratioY = clamp(rawY, allowOutOfBounds ? -edgeFollowY : 0, allowOutOfBounds ? 1 + edgeFollowY : 1);
    const centeredX = clamp(ratioX * 2 - 1, -1.26, 1.26);
    const centeredY = clamp(ratioY * 2 - 1, -1.26, 1.26);

    dropzone.style.setProperty("--dz-mx", `${(ratioX * 100).toFixed(1)}%`);
    dropzone.style.setProperty("--dz-my", `${(ratioY * 100).toFixed(1)}%`);
    dropzone.style.setProperty("--dz-rx", `${(-centeredY * 5.8).toFixed(2)}deg`);
    dropzone.style.setProperty("--dz-ry", `${(centeredX * 7.2).toFixed(2)}deg`);
    dropzone.style.setProperty("--dz-ix", `${(centeredX * 4.4).toFixed(2)}px`);
    dropzone.style.setProperty("--dz-iy", `${(centeredY * 2.8).toFixed(2)}px`);
    dropzone.style.setProperty("--dz-ir", `${(centeredX * 8.5).toFixed(2)}deg`);
    dropzone.style.setProperty("--dz-nx", `${(centeredX * 1.9).toFixed(2)}px`);
    dropzone.style.setProperty("--dz-ny", `${(centeredY * 1.25).toFixed(2)}px`);
    dropzone.style.setProperty("--dz-nr", `${(centeredX * 10).toFixed(2)}deg`);
    return { inBoundsX, inBoundsY, ratioX, ratioY };
  };

  resetDropzoneMotion();
  setBlobPosition(50, 42);

  const isNearDropzone = (clientX, clientY) => {
    const rect = dropzone.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return false;
    }

    const padX = Math.max(84, rect.width * 0.22);
    const padY = Math.max(70, rect.height * 0.44);
    return (
      clientX >= rect.left - padX &&
      clientX <= rect.right + padX &&
      clientY >= rect.top - padY &&
      clientY <= rect.bottom + padY
    );
  };

  const syncNearBlob = (event, allowOutOfBounds = false) => {
    const motion = updateDropzoneMotion(event, allowOutOfBounds);
    if (!motion) {
      return;
    }
    setNearMode(motion.ratioX, motion.ratioY);
  };

  if (pointerFine) {
    dropzone.addEventListener("pointerenter", (event) => {
      dropzone.classList.add("is-hovering");
      syncNearBlob(event, true);
    });

    dropzone.addEventListener("pointermove", (event) => {
      dropzone.classList.add("is-hovering");
      syncNearBlob(event, true);
    });

    dropzone.addEventListener("pointerleave", (event) => {
      dropzone.classList.remove("is-hovering");
      dropzone.classList.remove("is-pressing");

      if (!Number.isFinite(event.clientX) || !Number.isFinite(event.clientY)) {
        setAmbientMode();
        return;
      }

      if (isNearDropzone(event.clientX, event.clientY)) {
        syncNearBlob(event, true);
      } else {
        setAmbientMode();
      }
    });

    window.addEventListener("pointermove", (event) => {
      if (!Number.isFinite(event.clientX) || !Number.isFinite(event.clientY)) {
        return;
      }

      if (isNearDropzone(event.clientX, event.clientY)) {
        syncNearBlob(event, true);
        return;
      }

      if (!dropzone.matches(":hover") && !dropzone.classList.contains("drag-over")) {
        setAmbientMode();
      }
    });
  }

  dropzone.addEventListener("pointerdown", (event) => {
    dropzone.classList.add("is-pressing");
    if (pointerFine) {
      syncNearBlob(event, true);
    }
  });

  const releasePress = () => {
    dropzone.classList.remove("is-pressing");
  };

  dropzone.addEventListener("pointerup", releasePress);
  dropzone.addEventListener("pointercancel", releasePress);

  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("drag-over");
    dropzone.classList.add("is-hovering");
    syncNearBlob(event, true);
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("drag-over");
    if (!dropzone.matches(":hover")) {
      dropzone.classList.remove("is-hovering");
      setAmbientMode();
    }
  });

  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("drag-over");
    dropzone.classList.remove("is-pressing");
    if (!dropzone.matches(":hover")) {
      dropzone.classList.remove("is-hovering");
      setAmbientMode();
    }

    const file = event.dataTransfer?.files?.[0];
    if (!file) {
      return;
    }

    elements.fileInput.files = event.dataTransfer.files;
    applySelectedFile(file);
  });

  setAmbientMode();
}

function installGlassReactivity() {
  if (!pointerFine) {
    return;
  }

  elements.glassPanels.forEach((panel) => {
    panel.addEventListener("pointermove", (event) => {
      const rect = panel.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width) * 100;
      const y = ((event.clientY - rect.top) / rect.height) * 100;
      panel.style.setProperty("--mx", `${x}%`);
      panel.style.setProperty("--my", `${y}%`);
    });

    panel.addEventListener("pointerleave", () => {
      panel.style.setProperty("--mx", "56%");
      panel.style.setProperty("--my", "16%");
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
  const streaks = [];
  const rings = [];
  const notes = [];
  const pointer = { x: 0, y: 0, active: false };
  const noteKinds = ["quarter", "eighth", "double_eighth", "half", "whole"];
  const maxNotes = reduceMotion ? 12 : pointerFine ? 72 : 44;
  const maxBusyNotes = reduceMotion ? maxNotes : Math.round(maxNotes * (pointerFine ? 1.75 : 1.6));
  const dprCap = reduceMotion ? 1 : lowPowerDevice ? 1.25 : 1.5;
  const pointDivisor = lowPowerDevice ? 62000 : pointerFine ? 50000 : 56000;
  const streakDivisor = lowPowerDevice ? 34 : 28;
  const minPointCount = reduceMotion ? 12 : 16;
  const linkDistance = lowPowerDevice ? 92 : 104;
  const linkDistanceSquared = linkDistance * linkDistance;
  const pointerInfluenceRadius = lowPowerDevice ? 145 : 170;
  const pointerInfluenceRadiusSquared = pointerInfluenceRadius * pointerInfluenceRadius;
  const idleFrameInterval = 1000 / (reduceMotion ? 24 : lowPowerDevice ? 34 : 46);
  const busyFrameInterval = 1000 / (reduceMotion ? 26 : lowPowerDevice ? 38 : 52);
  let width = 0;
  let height = 0;
  let dpr = 1;
  let frameCount = 0;
  let wasBusy = false;
  let busyBlend = 0;
  let lastFrameTime = 0;
  let resizeFrame = null;

  function resetStreak(streak, spawnInView = false) {
    streak.x = width * 0.5 + (Math.random() - 0.5) * width * 0.74;
    streak.y = spawnInView ? Math.random() * height : height + Math.random() * height * 0.36;
    streak.vx = (Math.random() - 0.5) * 0.9;
    streak.speed = 2.6 + Math.random() * 5.8;
    streak.length = 70 + Math.random() * 170;
    streak.width = 0.8 + Math.random() * 1.7;
    streak.alpha = 0.1 + Math.random() * 0.24;
    streak.wave = Math.random() * Math.PI * 2;
  }

  function spawnRing(intensity) {
    rings.push({
      radius: 14 + Math.random() * 24,
      speed: 2.4 + Math.random() * 2.6 + intensity * 1.2,
      alpha: 0.12 + Math.random() * 0.16 + intensity * 0.1,
      width: 1 + Math.random() * 1.4,
    });
  }

  function spawnNote(intensity) {
    const size = 0.38 + Math.random() * 0.46;
    notes.push({
      x: Math.random() * width,
      y: -70 - Math.random() * (height * 0.35),
      vx: (Math.random() - 0.5) * (0.55 + intensity * 0.68),
      vy: 1.05 + Math.random() * 1.35 + intensity * 0.78,
      tilt: -0.24 + Math.random() * 0.14,
      spin: (Math.random() - 0.5) * 0.008,
      size,
      baseAlpha: 0.62 + Math.random() * 0.28,
      phase: Math.random() * Math.PI * 2,
      waveAmp: 10 + Math.random() * (16 + intensity * 8),
      waveSpeed: 0.014 + Math.random() * 0.02,
      life: 0,
      maxLife: 130 + Math.random() * 90,
      kind: noteKinds[Math.floor(Math.random() * noteKinds.length)],
      stemUp: Math.random() > 0.38,
    });
  }

  function drawNote(note, intensityScale) {
    const fadeIn = clamp(note.life / 12, 0, 1);
    const lifeT = note.life / note.maxLife;
    const fadeOut = Math.pow(clamp((1 - lifeT) / 0.16, 0, 1), 1.55);
    const alpha = note.baseAlpha * fadeIn * fadeOut * intensityScale;
    if (alpha <= 0.002) {
      return;
    }

    const scale = note.size * (0.62 + intensityScale * 0.16);
    ctx.save();
    ctx.translate(note.x, note.y);
    ctx.rotate(note.tilt + Math.sin(note.phase * 0.6) * 0.055);
    ctx.scale(scale, scale);
    ctx.globalAlpha = alpha;
    ctx.lineWidth = 1.35;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "rgba(19, 35, 62, 0.98)";
    ctx.fillStyle = "rgba(19, 35, 62, 0.98)";
    ctx.shadowColor = `rgba(86, 194, 255, ${Math.min(alpha * 0.82, 0.42)})`;
    ctx.shadowBlur = 6;

    ctx.save();
    ctx.rotate(-0.42);
    if (note.kind === "whole") {
      ctx.beginPath();
      ctx.ellipse(0, 0, 11.6, 7.2, 0, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(19, 35, 62, 0.98)";
      ctx.fill();
      ctx.strokeStyle = "rgba(19, 35, 62, 0.98)";
      ctx.stroke();
      ctx.restore();
      ctx.restore();
      return;
    }

    if (note.kind === "half") {
      ctx.beginPath();
      ctx.ellipse(0, 0, 10.2, 6.4, 0, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(19, 35, 62, 0.98)";
      ctx.fill();
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.ellipse(0, 0, 10.1, 6.5, 0, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(19, 35, 62, 0.98)";
      ctx.fill();
    }
    ctx.restore();

    const stemX = note.stemUp ? 8.4 : -8.4;
    const stemStartY = note.stemUp ? -1.2 : 1.2;
    const stemEndY = note.stemUp ? -36 : 36;
    ctx.beginPath();
    ctx.moveTo(stemX, stemStartY);
    ctx.lineTo(stemX, stemEndY);
    ctx.stroke();

    if (note.kind === "eighth" || note.kind === "double_eighth") {
      const direction = note.stemUp ? 1 : -1;
      const flagStartY = stemEndY + (note.stemUp ? 0 : -0.8);
      const flagTargetY = stemEndY + direction * 15;
      const flagCtrlX = stemX + direction * 12;
      const flagTipX = stemX + direction * 4.6;
      ctx.beginPath();
      ctx.moveTo(stemX, flagStartY);
      ctx.quadraticCurveTo(flagCtrlX, stemEndY + direction * 4.5, flagTipX, flagTargetY);
      ctx.quadraticCurveTo(stemX + direction * 2.2, stemEndY + direction * 9.8, stemX, stemEndY + direction * 11.6);
      ctx.stroke();
    }

    if (note.kind === "double_eighth") {
      const direction = note.stemUp ? 1 : -1;
      const y2 = stemEndY + direction * 9.6;
      ctx.beginPath();
      ctx.moveTo(stemX, y2);
      ctx.quadraticCurveTo(stemX + direction * 10.6, y2 + direction * 3.8, stemX + direction * 4.3, y2 + direction * 13.2);
      ctx.quadraticCurveTo(stemX + direction * 1.9, y2 + direction * 8.3, stemX, y2 + direction * 10.3);
      ctx.stroke();
    }

    ctx.restore();
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, dprCap);
    width = window.innerWidth;
    height = window.innerHeight;

    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const count = Math.max(minPointCount, Math.floor((width * height) / pointDivisor));
    points.length = 0;

    for (let index = 0; index < count; index += 1) {
      points.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.2,
        vy: (Math.random() - 0.5) * 0.2,
      });
    }

    const streakCount = Math.max(12, Math.floor(width / streakDivisor));
    streaks.length = 0;
    for (let index = 0; index < streakCount; index += 1) {
      const streak = {};
      resetStreak(streak, true);
      streaks.push(streak);
    }

    rings.length = 0;
    notes.length = 0;
    frameCount = 0;
  }

  function requestResize() {
    if (resizeFrame !== null) {
      return;
    }
    resizeFrame = window.requestAnimationFrame(() => {
      resizeFrame = null;
      resize();
    });
  }

  function drawBusyOverlay() {
    const isBusy = document.body.classList.contains("is-busy");
    const isBusyEnding = document.body.classList.contains("is-busy-ending");
    const targetBusy = isBusy ? 1 : isBusyEnding ? 0.18 : 0;
    const activeBusy = isBusy && targetBusy > 0.2;
    const noteLimit = activeBusy ? maxBusyNotes : maxNotes;
    const blendLerp = reduceMotion ? 0.12 : targetBusy > busyBlend ? 0.082 : 0.012;
    busyBlend = clamp(busyBlend + (targetBusy - busyBlend) * blendLerp, 0, 1);

    if (busyBlend < 0.004 && targetBusy === 0) {
      if (wasBusy) {
        rings.length = 0;
        notes.length = 0;
      }
      wasBusy = false;
      return;
    }

    const progressIntensity = clamp(0.36 + state.displayedProgress * 0.92, 0.36, 1.28);
    const launchIntensity = progressIntensity * (0.42 + busyBlend * 0.76);
    const originX = width * 0.5;
    const originY = height * 0.92;

    if (!wasBusy && targetBusy > 0 && !reduceMotion) {
      frameCount = 0;
      rings.length = 0;
      notes.length = 0;
      streaks.forEach((streak) => {
        resetStreak(streak, true);
      });
      for (let index = 0; index < Math.min(activeBusy ? 30 : 20, noteLimit); index += 1) {
        spawnNote(launchIntensity);
        notes[notes.length - 1].y = Math.random() * height * 0.75;
      }
    }
    wasBusy = targetBusy > 0 || busyBlend > 0.01;
    frameCount += 1;

    ctx.save();
    ctx.globalCompositeOperation = "screen";

    const ambient = ctx.createRadialGradient(
      originX,
      originY,
      16,
      originX,
      originY,
      Math.max(width, height) * 0.92,
    );
    ambient.addColorStop(0, `rgba(176, 228, 255, ${0.16 * busyBlend})`);
    ambient.addColorStop(0.34, `rgba(89, 170, 246, ${0.14 * busyBlend})`);
    ambient.addColorStop(1, "rgba(36, 93, 180, 0)");
    ctx.fillStyle = ambient;
    ctx.fillRect(0, 0, width, height);

    const wave = frameCount * 0.018;
    for (let layer = 0; layer < 4; layer += 1) {
      const drift =
        Math.sin(wave + layer * 1.53) * width * (0.034 + layer * 0.012) * (0.4 + busyBlend * 0.9);
      const topY = height * (0.26 - layer * 0.028);
      const plume = ctx.createRadialGradient(
        originX + drift * 0.22,
        originY,
        width * (0.016 + layer * 0.004),
        originX + drift,
        topY,
        width * (0.18 + layer * 0.08),
      );
      plume.addColorStop(0, `rgba(176, 232, 255, ${(0.13 + layer * 0.03) * busyBlend})`);
      plume.addColorStop(0.36, `rgba(71, 177, 255, ${(0.1 + layer * 0.02) * busyBlend})`);
      plume.addColorStop(1, "rgba(35, 111, 214, 0)");
      ctx.fillStyle = plume;
      ctx.beginPath();
      ctx.ellipse(
        originX + drift,
        height * (0.58 - layer * 0.02),
        width * (0.2 + layer * 0.07),
        height * (0.64 - layer * 0.08),
        0,
        0,
        Math.PI * 2,
      );
      ctx.fill();
    }

    for (let band = 0; band < 5; band += 1) {
      const bandPhase = frameCount * 0.032 + band * 1.2;
      const helixGradient = ctx.createLinearGradient(originX, originY, originX, 0);
      helixGradient.addColorStop(0, `rgba(196, 241, 255, ${(0.09 + band * 0.012) * busyBlend})`);
      helixGradient.addColorStop(0.5, `rgba(108, 198, 255, ${(0.08 + band * 0.01) * busyBlend})`);
      helixGradient.addColorStop(1, "rgba(108, 198, 255, 0)");
      ctx.strokeStyle = helixGradient;
      ctx.lineWidth = 1 + band * 0.35;
      ctx.beginPath();
      const steps = 30;
      for (let step = 0; step <= steps; step += 1) {
        const t = step / steps;
        const y = originY - t * height * 0.9;
        const radius = (22 + t * 56 + band * 10) * (0.6 + busyBlend * 0.9);
        const x = originX + Math.sin(t * 8 + bandPhase) * radius;
        if (step === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
    }

    const coreGlow = ctx.createRadialGradient(
      originX,
      originY,
      0,
      originX,
      originY,
      54 + launchIntensity * 68,
    );
    coreGlow.addColorStop(0, `rgba(214, 246, 255, ${0.24 * busyBlend})`);
    coreGlow.addColorStop(0.5, `rgba(92, 196, 255, ${0.18 * busyBlend})`);
    coreGlow.addColorStop(1, "rgba(92, 196, 255, 0)");
    ctx.fillStyle = coreGlow;
    ctx.beginPath();
    ctx.arc(originX, originY, 54 + launchIntensity * 68, 0, Math.PI * 2);
    ctx.fill();

    if (reduceMotion) {
      ctx.restore();
      return;
    }

    const ringEvery = Math.max(6, Math.round(14 - launchIntensity * 4));
    if (targetBusy > 0 && frameCount % ringEvery === 0 && rings.length < 18) {
      spawnRing(launchIntensity * (0.75 + busyBlend * 0.35));
    }

    const noteEvery = Math.max(
      1,
      Math.round((activeBusy ? 5.2 : 7) - launchIntensity * (activeBusy ? 3.4 : 2.4)),
    );
    if (targetBusy > 0 && frameCount % noteEvery === 0 && notes.length < noteLimit) {
      const lowWatermark = noteLimit * (activeBusy ? 0.55 : 0.35);
      const burstCount = activeBusy ? 3 : 2;
      const sustainCount = activeBusy ? 2 : 1;
      const spawnCount = notes.length < lowWatermark ? burstCount : sustainCount;
      for (let count = 0; count < spawnCount && notes.length < noteLimit; count += 1) {
        spawnNote(launchIntensity);
      }
    }

    for (let i = 0; i < streaks.length; i += 1) {
      const streak = streaks[i];
      streak.wave += 0.035 + streak.speed * 0.0015;
      const driftX = Math.sin(streak.wave + frameCount * 0.012) * (0.3 + busyBlend * 0.95);
      streak.y -= streak.speed * (0.56 + launchIntensity * 0.98) * (0.34 + busyBlend * 0.98);
      streak.x += streak.vx * (0.54 + launchIntensity * 0.74) + driftX;

      if (streak.y + streak.length < -20 || streak.x < -120 || streak.x > width + 120) {
        resetStreak(streak, false);
      }

      const endX = streak.x + streak.vx * 28 + Math.sin(streak.wave) * 8;
      const endY = streak.y + streak.length;
      const gradient = ctx.createLinearGradient(streak.x, streak.y, endX, endY);
      gradient.addColorStop(0, "rgba(230, 246, 255, 0)");
      gradient.addColorStop(0.35, `rgba(165, 221, 255, ${streak.alpha * 0.32 * busyBlend})`);
      gradient.addColorStop(
        1,
        `rgba(26, 111, 235, ${streak.alpha * (0.66 + launchIntensity * 0.34) * busyBlend})`,
      );
      ctx.strokeStyle = gradient;
      ctx.lineWidth = streak.width * (0.72 + busyBlend * 0.48);
      ctx.beginPath();
      ctx.moveTo(streak.x, streak.y);
      ctx.lineTo(endX, endY);
      ctx.stroke();
    }

    for (let index = rings.length - 1; index >= 0; index -= 1) {
      const ring = rings[index];
      ring.radius += ring.speed * (0.45 + busyBlend * 0.95);
      ring.alpha *= targetBusy > 0 ? 0.97 : 0.94;

      ctx.strokeStyle = `rgba(146, 216, 255, ${ring.alpha * (0.22 + busyBlend * 0.78)})`;
      ctx.lineWidth = ring.width;
      ctx.beginPath();
      ctx.arc(originX, originY, ring.radius, 0, Math.PI * 2);
      ctx.stroke();

      if (ring.alpha < 0.012 || ring.radius > Math.max(width, height) * 1.1) {
        rings.splice(index, 1);
      }
    }

    for (let index = notes.length - 1; index >= 0; index -= 1) {
      const note = notes[index];
      note.life += 1;
      note.phase += note.waveSpeed;
      note.tilt += note.spin * (0.44 + busyBlend * 0.86);
      note.x += note.vx * (0.42 + busyBlend * 0.82) + Math.sin(note.phase) * note.waveAmp * 0.05;
      note.y += note.vy * (0.36 + busyBlend * 0.9);
      drawNote(note, 0.42 + busyBlend * 0.86);

      const offscreen =
        note.y > height + 120 || note.x < -120 || note.x > width + 120 || note.life > note.maxLife;
      if (offscreen) {
        notes.splice(index, 1);
      }
    }

    ctx.restore();
  }

  function tick(now) {
    if (document.hidden) {
      lastFrameTime = now;
      window.requestAnimationFrame(tick);
      return;
    }

    const frameInterval = state.busy ? busyFrameInterval : idleFrameInterval;
    if (lastFrameTime && now - lastFrameTime < frameInterval) {
      window.requestAnimationFrame(tick);
      return;
    }

    const dtScale = clamp((now - lastFrameTime || frameInterval) / frameInterval, 0.7, 2.2);
    lastFrameTime = now;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "rgba(26, 111, 235, 0.28)";

    for (let i = 0; i < points.length; i += 1) {
      const a = points[i];

      if (pointer.active) {
        const dxp = pointer.x - a.x;
        const dyp = pointer.y - a.y;
        const dpSquared = dxp * dxp + dyp * dyp;
        if (dpSquared < pointerInfluenceRadiusSquared) {
          const invDp = 1 / Math.sqrt(dpSquared || 1);
          a.vx += dxp * invDp * 0.0035;
          a.vy += dyp * invDp * 0.0035;
        }
      }

      a.vx *= 0.98;
      a.vy *= 0.98;
      a.x += a.vx * dtScale;
      a.y += a.vy * dtScale;

      if (a.x < 0 || a.x > width) {
        a.vx *= -1;
      }
      if (a.y < 0 || a.y > height) {
        a.vy *= -1;
      }

      ctx.beginPath();
      ctx.arc(a.x, a.y, 1.1, 0, Math.PI * 2);
      ctx.fill();

      for (let j = i + 1; j < points.length; j += 1) {
        const b = points[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const distanceSquared = dx * dx + dy * dy;

        if (distanceSquared < linkDistanceSquared) {
          const alpha = 1 - Math.sqrt(distanceSquared) / linkDistance;
          ctx.strokeStyle = `rgba(23, 174, 189, ${alpha * 0.24})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    drawBusyOverlay();
    window.requestAnimationFrame(tick);
  }

  window.addEventListener("pointermove", (event) => {
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    pointer.active = true;
  });

  window.addEventListener("pointerleave", () => {
    pointer.active = false;
  });

  resize();
  window.addEventListener("resize", requestResize, { passive: true });
  window.requestAnimationFrame(tick);
}

function init() {
  setCompletionLayout(false);
  installResizePerformanceGuard();
  installStartupHint();
  resetCurrentProgress();
  applyMagnetic(document);
  installDropzone();
  installClipboardImagePaste();
  installGlassReactivity();
  installConstellation();

  elements.fileInput.addEventListener("change", (event) => {
    const file = event.target.files?.[0] || null;
    applySelectedFile(file);
    elements.fileInput.value = "";
  });
}

init();
