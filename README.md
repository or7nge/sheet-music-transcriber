# Sheet Music Transcriber Studio

Browser-based sheet music transcription with a fully custom UI and a job-based API.

Upload a sheet image/PDF and export:
- `ABC` notation text
- `MIDI` file
- `MusicXML` file

## Stack

- `homr` for OMR recognition
- `music21` for MusicXML parsing/conversion
- `FastAPI` backend for job orchestration + downloads
- Custom `HTML/CSS/JS` frontend (no Gradio dependency for the primary UI)

## Prerequisites

- Python `3.10+`
- Poetry (for your local `homr` installation)
- Poppler (for PDF conversion)
  - macOS: `brew install poppler`
  - Linux: `apt-get install poppler-utils`

## Setup

### 1) Install homr

```bash
git clone https://github.com/liebharc/homr.git
cd homr
poetry install --only main
poetry run homr --init
```

If `homr` is not located at `/Users/andrew/Documents/git/homr`, set:

```bash
export HOMR_DIR="/path/to/homr"
```

### 2) Install app dependencies

```bash
cd sheet-music-transcriber
pip install -r requirements.txt
```

## Run

```bash
./start.sh
```

Open `http://127.0.0.1:7860`.

## UX Flow

1. Upload JPG/PNG/PDF
2. Start transcription
3. Track pipeline stages in real time
4. Copy ABC or download MIDI/MusicXML

## API Endpoints

- `GET /api/health`
- `POST /api/jobs` (multipart file field: `file`)
- `GET /api/jobs/<job_id>`
- `GET /api/jobs/<job_id>/files/midi`
- `GET /api/jobs/<job_id>/files/musicxml`
- `GET /api/jobs/<job_id>/files/preview`

## Notes

- Recognition quality is best with high-resolution printed sheet music.
- Multi-page PDFs are accepted; processing currently uses page 1.
- Jobs/artifacts are stored temporarily under your OS temp directory.
