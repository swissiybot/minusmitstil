#!/bin/bash
# Taegliche Aktualisierung: Werteliste -> Kurse -> Auswertung. Protokoll in daten/aktualisierung.log
cd "$(dirname "$0")"
{
  echo "=== $(date '+%F %T') Start"
  # fundamente.py lädt nur mit SEC_KONTAKT (sonst nichts). umfeld.py (FRED-Zinsdaten) und bewertung.py (Shiller-CAPE) brechen bei Netzfehlern nicht ab, sondern nutzen die letzten Dateien
  .venv/bin/python btc_alt.py   # Bitcoin vor 2014 (einmalig, danach aus daten/btc_alt)
  .venv/bin/python mvrv.py      # Bitcoin MVRV-Z (Coin Metrics), höchstens alle 20 Stunden
  .venv/bin/python welt.py   # Auslandsaktien (Wikidata, höchstens wöchentlich)
  .venv/bin/python universum.py && .venv/bin/python kurse.py && .venv/bin/python umfeld.py \
    && .venv/bin/python bewertung.py && .venv/bin/python fundamente.py && { .venv/bin/python nasdaq100.py || true; } && .venv/bin/python isin.py && { .venv/bin/python beschreibung.py || true; } \
    && .venv/bin/python analyse.py && .venv/bin/python tagebuch_pruefung.py \
    && { .venv/bin/python trendstudie.py || echo "Trendstudie nicht gerechnet"; }
  rc=$?
  # Signal-Tagebuch lokal in Git festhalten (macht nachtraegliche Aenderungen sichtbar)
  if [ $rc -eq 0 ] && [ -n "$(git status --porcelain daten/tagebuch)" ]; then
    git add daten/tagebuch && git commit -q -m "Signal-Tagebuch $(date +%F)" -- daten/tagebuch && echo "Tagebuch in Git gesichert"
  fi
  echo "=== $(date '+%F %T') Ende (Code $rc)"
  exit $rc
} >> daten/aktualisierung.log 2>&1
