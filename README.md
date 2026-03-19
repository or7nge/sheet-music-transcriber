# Sheet Music Transcriber Studio

Single-app browser workflow for sheet music transcription.

Upload a JPG, PNG, or PDF and export:
- `Notes`
- `MIDI`
- `MusicXML`

## Current Architecture

- `server.py`: FastAPI server, job orchestration, static file serving
- `transcriber_core.py`: shared transcription pipeline
- `frontend/`: lightweight custom HTML/CSS/JS client

The old Gradio variants have been removed. There is now one supported app implementation.

## Prerequisites

- Python `3.10+`
- Poetry for your local `homr` install
- Poppler for PDF conversion
  - macOS: `brew install poppler`
  - Linux: `apt-get install poppler-utils`

## Setup

### 1. Install `homr`

```bash
git clone https://github.com/liebharc/homr.git
cd homr
poetry install --only main
poetry run homr --init
```

If `homr` is not at `/Users/andrew/Documents/git/homr`, set:

```bash
export HOMR_DIR="/path/to/homr"
```

### 2. Install app dependencies

```bash
pip install -r requirements.txt
```

## Start Options

- `./start.sh`: canonical launcher for the web app on `http://127.0.0.1:7860`
- `./start_minimal.sh`: compatibility alias; now just forwards to `./start.sh`
- `./start_premium.sh`: compatibility alias; now just forwards to `./start.sh`

Environment variables:
- `HOMR_DIR`: override the `homr` repo location
- `BROWSER_TARGET=chrome|safari|default`: choose browser auto-open target
- `AUTO_OPEN_BROWSER=0`: disable automatic browser launch
- `HOST` / `PORT`: override bind address and port

## API

- `GET /api/health`
- `POST /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/files/midi`
- `GET /api/jobs/{job_id}/files/musicxml`
- `GET /api/jobs/{job_id}/files/preview`

## Notes

- Recognition quality is best with high-resolution printed sheet music.
- PDFs currently rasterize and process only page 1 for speed.
- Job artifacts are stored temporarily under your system temp directory.
