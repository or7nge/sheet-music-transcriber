#!/bin/bash
# Start the custom browser UI + API server

echo "Starting Sheet Music Transcriber Studio"
echo "http://127.0.0.1:7860"
echo ""
echo "Set HOMR_DIR if homr lives outside /Users/andrew/Documents/git/homr"
echo "Set BROWSER_TARGET=chrome|safari|default (default: chrome)"
echo "Press Ctrl+C to stop the server"
echo ""

if command -v lsof >/dev/null 2>&1; then
  EXISTING_PIDS="$(lsof -ti tcp:7860 2>/dev/null || true)"
  if [ -n "$EXISTING_PIDS" ]; then
    echo "Stopping existing process on port 7860: $EXISTING_PIDS"
    kill $EXISTING_PIDS 2>/dev/null || true
    sleep 0.4
  fi
fi

export BROWSER_TARGET="${BROWSER_TARGET:-chrome}"
python3 server.py
