# Aktien-Kaufplan

Lokales Dashboard im TradingView-Stil: zeigt täglich, welche Aktien, ETFs und Bitcoin **historisch gesehen** günstig oder teuer stehen – mit Chart, Begründung, Ø Jahresrendite und Trefferquote aus der Vergangenheit. Historische Statistik, keine Anlageberatung.

## Starten
```bash
./starten.sh          # Dashboard auf http://localhost:8765
./aktualisieren.sh    # Werteliste, Kurse und Auswertung neu (läuft täglich 07:00 per systemd-Timer)
```

## Neu einrichten (z. B. nach Klonen)
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./aktualisieren.sh    # lädt alle Kurse (erstes Mal ca. 10 Min.)
```

## Aufbau
| Datei | Aufgabe |
|---|---|
| `einstellungen.py` | Pfade, ETF-Liste mit Index-Vorlauf, Drosselung |
| `universum.py` | Werteliste: Nasdaq-Verzeichnis, Vanguard-Excel (FTSE All-World) aus `daten/eingang/`, ETFs, Bitcoin |
| `kurse.py` | Tageskurse von Yahoo (yfinance) → eine komprimierte Datei `daten/kurse.parquet` |
| `analyse.py` | Ampel 0–100, Ø Jahresrendite, Wahrscheinlichkeiten, Rangliste, Signal-Tagebuch |
| `server.py` | lokaler Server, berechnet Charts beim Anklicken live |
| `web/index.html` | Dashboard (TradingView Lightweight Charts, lokal in `web/lib/`) |
| `daten/tagebuch/` | tägliche Signale – nie ändern, Grundlage der späteren Erfolgsprüfung |

Notizen, Entscheidungen und Log: Obsidian-Vault `10 Projekte/Aktien-Kaufplan/`.
