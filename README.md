# Sheet Music Transcriber

A local web app that converts sheet music images into playable formats. Upload a photo or scan of sheet music and get back MIDI, MusicXML, and a plain text note list.

It runs entirely on your machine — no cloud, no accounts.

## Demo

Input image and detected structure:

<p float="left">
  <img src="docs/assets/sample.png" width="48%" />
  <img src="docs/assets/sample_teaser.png" width="48%" />
</p>

## How it works

The app uses [homr](https://github.com/liebharc/homr), an open-source optical music recognition model, to detect and transcribe notes from sheet music images. A FastAPI backend handles job processing and a lightweight browser frontend handles the UI.

Supported input formats: JPG, PNG, PDF (first page only).

## Setup

**1. Install homr**

```bash
git clone https://github.com/liebharc/homr.git
cd homr
poetry install --only main
poetry run homr --init
```

By default the app looks for a sibling `../homr` checkout. If yours lives elsewhere, set the path:

```bash
export HOMR_DIR="/path/to/homr"
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

You'll also need Poppler for PDF support:

```bash
# macOS
brew install poppler

# Linux
apt-get install poppler-utils
```

## Running

```bash
./start.sh
```

This starts the server and opens the app at `http://127.0.0.1:7860`.

## Testing

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

## Notes

Recognition works best on clean, high-resolution printed sheet music. Handwritten or low-quality scans may produce poor results.
