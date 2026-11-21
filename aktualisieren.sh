#!/bin/bash
# Taegliche Aktualisierung: Werteliste -> Kurse -> Auswertung. Protokoll in daten/aktualisierung.log
cd "$(dirname "$0")"
{
  echo "=== $(date '+%F %T') Start"
  .venv/bin/python universum.py && .venv/bin/python kurse.py && .venv/bin/python analyse.py
  rc=$?
  # Signal-Tagebuch lokal in Git festhalten (macht nachtraegliche Aenderungen sichtbar)
  if [ $rc -eq 0 ] && [ -n "$(git status --porcelain daten/tagebuch)" ]; then
    git add daten/tagebuch && git commit -q -m "Signal-Tagebuch $(date +%F)" -- daten/tagebuch && echo "Tagebuch in Git gesichert"
  fi
  echo "=== $(date '+%F %T') Ende (Code $rc)"
  exit $rc
} >> daten/aktualisierung.log 2>&1
