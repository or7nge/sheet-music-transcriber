#!/bin/bash
# Start the custom browser UI + API server

echo "Starting Sheet Music Transcriber Studio"
echo "http://127.0.0.1:7860"
echo ""
echo "Set HOMR_DIR if homr lives outside /Users/andrew/Documents/git/homr"
echo "Press Ctrl+C to stop the server"
echo ""

python3 server.py
