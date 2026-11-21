#!/bin/bash
# Taegliche Aktualisierung: Werteliste -> Kurse -> Auswertung. Protokoll in daten/aktualisierung.log
cd "$(dirname "$0")"
{
  echo "=== $(date '+%F %T') Start"
  .venv/bin/python universum.py && .venv/bin/python kurse.py && .venv/bin/python analyse.py
  rc=$?
  echo "=== $(date '+%F %T') Ende (Code $rc)"
  exit $rc
} >> daten/aktualisierung.log 2>&1
