# Aktien-Kaufplan

Lokales Dashboard im TradingView-Stil: zeigt täglich, welche Aktien, ETFs, Kryptowährungen (BTC, ETH, SOL, LINK, XLM) und Rohstoffe **historisch gesehen** günstig oder teuer stehen – mit Chart, Begründung, Ø Jahresrendite und Trefferquote aus der Vergangenheit. Historische Statistik, keine Anlageberatung.

## Starten
```bash
./starten.sh          # Dashboard auf http://localhost:8765
./aktualisieren.sh    # Werteliste, Kurse, FRED, Auswertung, Tagebuch-Prüfung (täglich 07:00 per systemd-Timer)
```

## Neu einrichten (z. B. nach Klonen)
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./aktualisieren.sh    # lädt alle Kurse (erstes Mal ca. 10 Min.)
```

## Aufbau
| Datei | Aufgabe |
|---|---|
| `einstellungen.py` | Pfade, ETF-Liste mit Index-Vorlauf, Krypto- und Rohstoffliste, Drosselung |
| `universum.py` | Werteliste: Nasdaq-Verzeichnis, Vanguard-Excel (FTSE All-World) aus `daten/eingang/`, ETFs, Krypto, Rohstoffe |
| `kurse.py` | Tageskurse von Yahoo (yfinance) → eine komprimierte Datei `daten/kurse.parquet` |
| `analyse.py` | Ampel 0–100, Ø Jahresrendite, Wahrscheinlichkeiten, Rangliste, Signal-Tagebuch |
| `umfeld.py` | FRED-Reihen (Zinskurve T10Y2Y, 3-Monats-Zins TB3MS) laden; Marktumfeld-Kachel (Marktbreite, VIX, Zinskurve) |
| `pruefung.py` | Walk-forward-Prüfung und Kalibrierung der Ampel-Wahrscheinlichkeit |
| `strategie.py` | Sparplan gegen Staffelkäufe 60/75/90 (+ Teilverkauf ≤ 15), mit Kosten, Abgeltungssteuer, Zins |
| `montecarlo.py` | Block-Bootstrap echter Wochenrenditen: Kegel und „Wird Kurs X in 12 Monaten erreicht?“ |
| `tagebuch_pruefung.py` | Nachprüfung des Signal-Tagebuchs nach 1/3/5 Jahren (liest nur) |
| `server.py` | lokaler Server, berechnet Charts, Prüfung, Strategie und Monte Carlo beim Anklicken live |
| `web/index.html` | Dashboard (TradingView Lightweight Charts, lokal in `web/lib/`) |
| `daten/tagebuch/` | tägliche Signale – nie ändern, Grundlage der späteren Erfolgsprüfung |

Notizen, Entscheidungen und Log: Obsidian-Vault `10 Projekte/Aktien-Kaufplan/`.

## Erzeugte Dateien (klein, jederzeit neu erzeugbar)
`web/daten/rangliste.json` (Rangliste), `pruefung.json` (Walk-forward über alle Werte, Strategie-Übersicht),
`umfeld.json` (Marktumfeld), `tagebuch_pruefung.json` (Tagebuch-Nachprüfung), `daten/fred/*.csv` (FRED-Rohdaten).
Monte Carlo, Strategie und Prüfung je Wert rechnet der Server live (`/api/mc`, `/api/strategie`, `/api/pruefung`).
