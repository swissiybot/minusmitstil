#!/bin/bash
# Startet das Dashboard lokal und oeffnet es im Browser (beenden mit Strg+C).
cd "$(dirname "$0")"
( sleep 2; xdg-open http://localhost:8765 >/dev/null 2>&1 ) &
exec .venv/bin/python server.py 8765
