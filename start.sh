#!/bin/bash
# Quick start script for Sheet Music Transcriber

echo "🎹 Starting Sheet Music Transcriber..."
echo ""
echo "Make sure you're in the sheet-music-transcriber directory!"
echo "Opening browser at http://127.0.0.1:7860"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Add homr to PATH for the subprocess calls
export PATH="/Users/andrew/Documents/git/homr:$PATH"

# Run the app
python3 app.py
