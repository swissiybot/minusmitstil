#!/bin/bash
# Oeffnet das Dashboard per Doppelklick: startet den Server im Hintergrund (falls er noch nicht laeuft)
# und oeffnet http://localhost:8765 im Browser. Server beenden: pkill -f "aktien-kaufplan/server.py"
cd "$(dirname "$0")"
URL=http://localhost:8765
if ! curl -s -o /dev/null --max-time 1 "$URL"; then
  nohup .venv/bin/python "$PWD/server.py" 8765 > daten/server.log 2>&1 &
  for i in $(seq 1 30); do curl -s -o /dev/null --max-time 1 "$URL" && break; sleep 0.3; done
fi
xdg-open "$URL" >/dev/null 2>&1 &
