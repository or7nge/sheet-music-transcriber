# 🎹 Sheet Music Transcriber

Upload a photo or PDF of piano sheet music and get ABC notation, MIDI, and MusicXML output.

## Features

- 📸 **Upload** JPG, PNG, or PDF sheet music
- 🎼 **Get** ABC notation (text format)
- 🎵 **Download** MIDI files for playback
- 📄 **Export** MusicXML for professional notation software
- 🎨 **Clean UI** with dark theme support
- ⚡ **Fast processing** with homr OMR engine

## Architecture

- **OMR Engine**: [homr](https://github.com/liebharc/homr) - Neural network-based optical music recognition
- **Format Conversion**: [music21](https://web.mit.edu/music21/) - MusicXML → ABC and MIDI
- **Web Interface**: [Gradio](https://gradio.app/) - Simple, beautiful UI
- **PDF Support**: pdf2image for multi-page PDF processing

## Installation

### Prerequisites

- **Python**: 3.10, 3.11, or 3.12 (NOT 3.13)
- **Poetry**: >= 1.0.0 ([install instructions](https://python-poetry.org/docs/#installation))
- **Poppler** (for PDF support):
  - macOS: `brew install poppler`
  - Linux: `apt-get install poppler-utils`

### Setup

**Step 1**: Install homr (OMR engine)

```bash
# Clone homr repository
git clone https://github.com/liebharc/homr.git
cd homr

# Install dependencies (CPU-only for Apple Silicon)
poetry install --only main

# Download models (required on first run)
poetry run homr --init

# Go back to your working directory
cd ..
```

**Step 2**: Install this app

```bash
cd sheet-music-transcriber

# Install Python dependencies
pip install -r requirements.txt
```

**Step 3**: Run the app

```bash
python app.py
```

The app will open at `http://127.0.0.1:7860`

## Usage

1. **Upload** a sheet music image (JPG/PNG) or PDF
2. Click **"Transcribe"**
3. **Download** or copy your outputs:
   - **ABC tab**: Copy-paste text notation
   - **MIDI tab**: Download playable MIDI file
   - **MusicXML tab**: Download for MuseScore, Finale, etc.

## Supported Formats

### Input
- **Images**: JPG, PNG (recommended: high-res, well-lit)
- **PDFs**: Multi-page support (processes first page by default)

### Output
- **ABC Notation**: Text-based music notation (experimental)
- **MIDI**: Standard MIDI file (.mid)
- **MusicXML**: Industry-standard notation format (.musicxml)

## Apple Silicon (M-series) Notes

- ✅ **Supported**: Works on M1/M2/M3/M4 Macs
- ⚠️ **CPU-only**: No GPU acceleration available (only NVIDIA CUDA supported by homr)
- 🐌 **Performance**: Slower than GPU-accelerated systems (~30-60s per page)

Install homr with CPU-only mode:
```bash
poetry install --only main
```

## Limitations

### homr OMR Engine
- Only recognizes standard Western music notation
- Best with printed (not handwritten) sheet music
- No support for dynamics (pp, ff, etc.)
- Limited articulation support
- Single-page processing (for multi-page PDFs, only first page is processed)

### ABC Conversion
- Simplified ABC output (experimental)
- Complex rhythms may not convert perfectly
- **Recommendation**: Use MusicXML output for professional work

### Known Issues
- Processing timeout on very complex scores (>2 minutes)
- PDF conversion requires system dependencies (poppler)

## Troubleshooting

### "homr is not installed" error
Make sure you've installed homr via Poetry:
```bash
cd homr
poetry install --only main
poetry run homr --init
```

### PDF conversion fails
Install poppler:
```bash
# macOS
brew install poppler

# Linux
sudo apt-get install poppler-utils
```

### Slow processing on Apple Silicon
This is expected - homr only supports NVIDIA GPU acceleration. CPU processing takes 30-60 seconds per page.

### Bad transcription results
- Use high-resolution images (300 DPI recommended)
- Ensure good lighting and contrast
- Avoid handwritten music (printed only)
- Try cropping to a single staff or system

## Advanced Configuration

### Process specific page from PDF
Currently processes only the first page. To handle multiple pages, modify `process_sheet_music()` in `app.py`.

### GPU acceleration (NVIDIA only)
If you have an NVIDIA GPU with CUDA 12.1:
```bash
cd homr
poetry install --only main,gpu
```

Then run with GPU flag in `app.py`:
```python
# In process_with_homr(), add --gpu flag:
["poetry", "run", "homr", "--gpu", "force", image_path]
```

## Credits

- **OMR**: [homr](https://github.com/liebharc/homr) by liebharc
- **Music Library**: [music21](https://web.mit.edu/music21/) by MIT
- **UI Framework**: [Gradio](https://gradio.app/)

## License

MIT License - see individual dependencies for their licenses:
- homr: AGPL-3.0
- music21: BSD-3-Clause
- Gradio: Apache-2.0

## Disclaimer

⚠️ **Beta Software**: Results may contain errors, especially on complex or handwritten scores. Always verify transcriptions against the original sheet music.
