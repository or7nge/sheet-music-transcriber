#!/usr/bin/env python3
"""Custom web server for the Sheet Music Transcriber."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from uuid import uuid4
import os
import platform
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
import uvicorn

from transcriber_core import check_homr_installation, process_sheet_music_file


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
JOBS_ROOT = Path(tempfile.gettempdir()) / "sheet_music_transcriber_jobs"
JOBS_ROOT.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = 40
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
JOB_TTL_HOURS = 12
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
STATIC_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

CHROME_RELOAD_SCRIPT = """
on run argv
    set targetBaseURL to item 1 of argv
    set reloadURL to item 2 of argv
    tell application "Google Chrome"
        activate
        if (count of windows) = 0 then
            make new window
        end if

        set matched to false
        repeat with w in windows
            repeat with t in tabs of w
                set tabURL to ""
                try
                    set tabURL to (URL of t) as text
                end try
                if tabURL starts with targetBaseURL then
                    set active tab index of w to (index of t)
                    set index of w to 1
                    set URL of active tab of w to reloadURL
                    set matched to true
                    exit repeat
                end if
            end repeat
            if matched then
                exit repeat
            end if
        end repeat

        if matched is false then
            tell window 1
                set newTab to (make new tab with properties {URL:reloadURL})
                set active tab index to (index of newTab)
            end tell
        end if
    end tell
end run
"""

SAFARI_RELOAD_SCRIPT = """
on run argv
    set targetBaseURL to item 1 of argv
    set reloadURL to item 2 of argv
    tell application "Safari"
        activate
        if (count of windows) = 0 then
            make new document with properties {URL:reloadURL}
            return
        end if

        set matched to false
        repeat with w in windows
            repeat with t in tabs of w
                set tabURL to ""
                try
                    set tabURL to (URL of t) as text
                end try
                if tabURL starts with targetBaseURL then
                    set current tab of w to t
                    set index of w to 1
                    set URL of current tab of w to reloadURL
                    set matched to true
                    exit repeat
                end if
            end repeat
            if matched then
                exit repeat
            end if
        end repeat

        if matched is false then
            tell window 1
                set current tab to (make new tab with properties {URL:reloadURL})
            end tell
        end if
    end tell
end run
"""


@dataclass(slots=True)
class JobState:
    id: str
    filename: str
    status: str = "queued"
    stage: str = "queued"
    progress: float = 0.0
    message: str = "Waiting to start"
    error: Optional[str] = None
    abc_text: str = ""
    concise_notes_text: str = ""
    files: dict[str, str] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


jobs: dict[str, JobState] = {}
job_lock = threading.Lock()
app = FastAPI(title="Sheet Music Transcriber Studio")


def now_ts() -> float:
    return time.time()


def cleanup_old_jobs() -> None:
    cutoff = now_ts() - (JOB_TTL_HOURS * 3600)
    stale_ids: list[str] = []

    with job_lock:
        for job_id, job in list(jobs.items()):
            if job.updated_at < cutoff:
                stale_ids.append(job_id)
                del jobs[job_id]

    for job_id in stale_ids:
        shutil.rmtree(JOBS_ROOT / job_id, ignore_errors=True)


def auto_open_browser_enabled() -> bool:
    raw = os.environ.get("AUTO_OPEN_BROWSER", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def wait_for_server(url: str, timeout_seconds: float = 20.0) -> bool:
    deadline = now_ts() + timeout_seconds
    while now_ts() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5):
                return True
        except urllib.error.HTTPError:
            return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    return False


def run_applescript(script: str, target_base_url: str, reload_url: str) -> bool:
    try:
        result = subprocess.run(
            ["osascript", "-e", script, target_base_url, reload_url],
            capture_output=True,
            text=True,
            timeout=6,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def browser_target() -> str:
    value = os.environ.get("BROWSER_TARGET", "chrome").strip().lower()
    if value in {"chrome", "safari", "default"}:
        return value
    return "chrome"


def open_app_url(app_name: str, url: str) -> bool:
    try:
        result = subprocess.run(
            ["open", "-a", app_name, url],
            capture_output=True,
            text=True,
            timeout=8,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def with_cache_buster(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query["__v"] = [str(int(time.time() * 1000))]
    rebuilt_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, rebuilt_query, parsed.fragment))


def open_or_reload_browser(url: str) -> None:
    target = browser_target()
    reload_url = with_cache_buster(url)

    if platform.system() == "Darwin":
        if target == "chrome":
            if run_applescript(CHROME_RELOAD_SCRIPT, url, reload_url):
                return
            if open_app_url("Google Chrome", reload_url):
                return
            print("Could not auto-open Google Chrome. Open this URL manually:", url)
            return

        if target == "safari":
            if run_applescript(SAFARI_RELOAD_SCRIPT, url, reload_url):
                return
            if open_app_url("Safari", reload_url):
                return
            print("Could not auto-open Safari. Open this URL manually:", url)
            return

        # `default`: prefer smart Chrome/Safari reload, then OS default browser.
        if run_applescript(CHROME_RELOAD_SCRIPT, url, reload_url):
            return
        if run_applescript(SAFARI_RELOAD_SCRIPT, url, reload_url):
            return

    webbrowser.open(reload_url, new=0, autoraise=True)


def launch_browser_when_ready(host: str, port: int) -> None:
    if not auto_open_browser_enabled():
        return

    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{browser_host}:{port}"

    def worker() -> None:
        if wait_for_server(url):
            open_or_reload_browser(url)

    threading.Thread(target=worker, daemon=True).start()


def static_file_response(path: Path) -> FileResponse:
    """Return static file responses with no-cache headers for dev freshness."""
    return FileResponse(str(path), headers=STATIC_NO_CACHE_HEADERS)


def sanitize_filename(name: str) -> str:
    base = Path(name or "upload").name
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in base)
    return safe.strip("._") or "upload"


def job_to_dict(job: JobState) -> dict:
    downloads: dict[str, str] = {}
    if "midi" in job.files:
        downloads["midi"] = f"/api/jobs/{job.id}/files/midi"
    if "musicxml" in job.files:
        downloads["musicxml"] = f"/api/jobs/{job.id}/files/musicxml"

    preview_url = f"/api/jobs/{job.id}/files/preview" if "preview" in job.files else None

    return {
        "id": job.id,
        "filename": job.filename,
        "status": job.status,
        "stage": job.stage,
        "progress": round(job.progress, 4),
        "message": job.message,
        "error": job.error,
        "abc_text": job.abc_text,
        "concise_notes_text": job.concise_notes_text,
        "downloads": downloads,
        "preview_url": preview_url,
        "log": job.log,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def set_job(job_id: str, **updates) -> None:
    with job_lock:
        job = jobs.get(job_id)
        if not job:
            return

        for key, value in updates.items():
            setattr(job, key, value)
        job.updated_at = now_ts()


def append_log(job_id: str, message: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    with job_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job.log.append(f"[{timestamp}] {message}")
        job.updated_at = now_ts()


def run_job(job_id: str, input_path: Path, job_dir: Path) -> None:
    try:
        set_job(
            job_id,
            status="processing",
            stage="validating",
            progress=0.04,
            message="Validating runtime dependencies",
        )
        append_log(job_id, "Checking homr availability")

        if not check_homr_installation():
            raise RuntimeError(
                "homr is not installed or not accessible. Set HOMR_DIR to your homr folder "
                "or install homr with: poetry install --only main && poetry run homr --init"
            )

        set_job(
            job_id,
            stage="validating",
            progress=0.08,
            message="Runtime dependencies ready",
        )

        seen_progress_messages: set[str] = set()

        def on_progress(stage: str, progress: float, message: str) -> None:
            set_job(job_id, stage=stage, progress=progress, message=message)
            if message and message not in seen_progress_messages:
                seen_progress_messages.add(message)
                append_log(job_id, message)

        result = process_sheet_music_file(
            input_path=input_path,
            output_dir=job_dir,
            progress_callback=on_progress,
        )

        files: dict[str, str] = {}
        set_job(
            job_id,
            stage="packaging",
            progress=0.955,
            message="Packaging output files",
        )

        packaging_targets = 1
        if result.midi_path and result.midi_path.exists():
            packaging_targets += 1
        if result.preview_path and result.preview_path.exists():
            packaging_targets += 1
        packaging_step = 0.035 / max(packaging_targets, 1)
        packaging_progress = 0.955

        def advance_packaging_progress() -> None:
            nonlocal packaging_progress
            packaging_progress = min(0.99, packaging_progress + packaging_step)
            set_job(
                job_id,
                stage="packaging",
                progress=packaging_progress,
                message="Packaging output files",
            )

        musicxml_target = job_dir / "output.musicxml"
        if result.musicxml_path.resolve() != musicxml_target.resolve():
            shutil.copy2(result.musicxml_path, musicxml_target)
        else:
            musicxml_target = result.musicxml_path
        files["musicxml"] = musicxml_target.name
        advance_packaging_progress()

        if result.midi_path and result.midi_path.exists():
            midi_target = job_dir / "output.mid"
            if result.midi_path.resolve() != midi_target.resolve():
                shutil.copy2(result.midi_path, midi_target)
            else:
                midi_target = result.midi_path
            files["midi"] = midi_target.name
            advance_packaging_progress()

        if result.preview_path and result.preview_path.exists():
            preview_ext = result.preview_path.suffix.lower() or ".jpg"
            preview_target = job_dir / f"preview{preview_ext}"
            if result.preview_path.resolve() != preview_target.resolve():
                shutil.copy2(result.preview_path, preview_target)
            else:
                preview_target = result.preview_path
            files["preview"] = preview_target.name
            advance_packaging_progress()

        for line in result.log:
            if line in seen_progress_messages:
                continue
            append_log(job_id, line)

        set_job(
            job_id,
            status="complete",
            stage="complete",
            progress=1.0,
            message="Transcription complete",
            abc_text=result.abc_text,
            concise_notes_text=result.concise_notes_text,
            files=files,
        )
        append_log(job_id, "Outputs are ready for download")

    except Exception as exc:
        set_job(
            job_id,
            status="error",
            progress=1.0,
            message="Transcription failed",
            error=str(exc),
        )
        append_log(job_id, f"ERROR: {exc}")


async def save_upload(upload: UploadFile, destination: Path) -> None:
    written = 0
    with destination.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Max upload size is {MAX_UPLOAD_MB}MB.",
                )
            handle.write(chunk)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "homr_available": check_homr_installation(),
        "max_upload_mb": MAX_UPLOAD_MB,
        "active_jobs": len(jobs),
    }


@app.post("/api/jobs", status_code=202)
async def create_job(file: UploadFile = File(...)) -> dict:
    cleanup_old_jobs()

    original_name = sanitize_filename(file.filename or "upload")
    suffix = Path(original_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Unsupported file format. Upload JPG, PNG, or PDF.",
                "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
            },
        )

    job_id = uuid4().hex
    job_dir = JOBS_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = job_dir / f"input{suffix}"
    await save_upload(file, input_path)

    job = JobState(
        id=job_id,
        filename=original_name,
        message="Queued for processing",
    )

    with job_lock:
        jobs[job_id] = job

    worker = threading.Thread(
        target=run_job,
        args=(job_id, input_path, job_dir),
        daemon=True,
    )
    worker.start()

    return {"job": job_to_dict(job)}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with job_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"job": job_to_dict(job)}


@app.get("/api/jobs/{job_id}/files/{artifact}")
def get_file(job_id: str, artifact: str):
    with job_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        artifact_map = {
            "midi": "midi",
            "musicxml": "musicxml",
            "preview": "preview",
        }
        key = artifact_map.get(artifact)
        if not key or key not in job.files:
            raise HTTPException(status_code=404, detail="Artifact not available")

        relative_path = job.files[key]
        filename = job.filename

    file_path = JOBS_ROOT / job_id / relative_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Artifact file is missing")

    if key == "preview":
        return FileResponse(str(file_path))

    ext = ".mid" if key == "midi" else ".musicxml"
    safe_stem = Path(filename).stem or "transcription"
    download_name = f"{safe_stem}{ext}"

    return FileResponse(str(file_path), filename=download_name)


@app.get("/")
def index():
    return static_file_response(FRONTEND_DIR / "index.html")


@app.get("/{path:path}")
def static_files(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    candidate = (FRONTEND_DIR / path).resolve()
    if str(candidate).startswith(str(FRONTEND_DIR.resolve())) and candidate.is_file():
        return static_file_response(candidate)

    return static_file_response(FRONTEND_DIR / "index.html")


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "7860"))

    print("Starting Sheet Music Transcriber web server")
    print(f"Frontend: http://{host}:{port}")
    print(f"Jobs directory: {JOBS_ROOT}")

    launch_browser_when_ready(host=host, port=port)
    uvicorn.run("server:app", host=host, port=port, reload=False)
