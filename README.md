# minus mit stil 📉✨

> Ein hochwissenschaftliches Werkzeug, das dir täglich sagt, was du vor drei Jahren hättest kaufen sollen.

**🌐 Live-Seite: https://swissiybot.github.io/minusmitstil/** – wird mehrmals täglich automatisch neu berechnet (werktags etwa alle 2 Stunden während der US-Börsenzeit, dazu jeden Morgen). Keine Echtzeitkurse.

**⚠️ Spaßprojekt. Historische Statistik, keine Anlageberatung.** Nichts hier ist eine Empfehlung, etwas zu kaufen oder zu verkaufen. Vergangene Kurse garantieren nichts. Wer nach diesem Tool handelt, tut das auf eigene Rechnung – und mit Stil.

## Was es macht
Ein lokales Dashboard im TradingView-Stil. Es zeigt täglich, welche Aktien (Nasdaq), Index-ETFs, Kryptowährungen (BTC, ETH, SOL, LINK, XLM) und Rohstoffe **im Vergleich zu ihrer eigenen Geschichte** günstig oder teuer stehen:

- **Ampel 0–100** aus Abstand zum Allzeithoch, 200-Wochen-Linie, Langfristtrend und Wochen-RSI – jeweils nur mit den Daten verglichen, die es zum jeweiligen Zeitpunkt schon gab (kein Blick in die Zukunft).
- **Ø Jahresrendite** über 20 Jahre (oder so viele, wie es Daten gibt), ETFs mit Index-Historie davor.
- **Trefferquote**: Wie oft stand der Kurs nach 1/3/5 Jahren höher, wenn die Lage früher ähnlich war – im Vergleich zu einem beliebigen Kauftag.
- **Bitcoin**: Pi Cycle Bottom (Bodenbildungszone und Boden-Signal), Pi Cycle Top, Mayer Multiple.
- **Prüfung**: Walk-forward-Test, Kalibrierung, Sparplan gegen „nur kaufen, wenn günstig“, Monte-Carlo-Kegel, Marktumfeld (Marktbreite, VIX, Zinskurve).
- **Signal-Tagebuch** (`daten/tagebuch/`): jeden Tag festgehalten und in Git gesichert, damit später niemand schummeln kann.

## Das ehrliche Ergebnis
Das Tool erkennt zuverlässig, wann etwas **historisch günstig** ist. Ob es sich **lohnt zu kaufen**, kann es nicht zuverlässig sagen: In der Prüfung brachte „nur bei günstiger Ampel kaufen, sonst warten“ bei S&P 500, Nasdaq-100, Gold und Bitcoin **weniger** als ein stumpfer monatlicher Sparplan. Märkte steigen meistens, und wer wartet, verpasst das. Die genauen, täglich neu berechneten Zahlen stehen im Dashboard unter „So liest du das Tool“.

Wissenschaftlich bewiesen: Ein Sparplan ist schlauer als du. Und als dieses Tool.

## Installieren (Linux / macOS)
Voraussetzung: Python 3.11 oder neuer.
```bash
git clone https://github.com/swissiybot/minusmitstil.git
cd minusmitstil
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./aktualisieren.sh    # lädt alle Kurse (beim ersten Mal ca. 10 Minuten)
./starten.sh          # öffnet das Dashboard auf http://localhost:8765
```
Windows: am einfachsten über WSL (Ubuntu) mit denselben Befehlen.

Täglich aktualisieren: `./aktualisieren.sh` von Hand oder per Cronjob / systemd-Timer, z. B. morgens um 07:00.

Optional FTSE All-World: Bestandsliste des Vanguard FTSE All-World ETF (Excel, „Download Fund Holdings Data“ auf der Vanguard-Seite) nach `daten/eingang/` legen.

## Daten und Lizenzen
- Kurse: Yahoo Finance über [yfinance](https://github.com/ranaroussi/yfinance) – nur für den privaten Gebrauch, werden **nicht** mitgeliefert, sondern bei jedem selbst geladen.
- Nasdaq-Werteliste: nasdaqtrader.com · Zinsen: FRED (Federal Reserve Bank of St. Louis).
- Charts: [TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts) (Apache-2.0), liegt in `web/lib/`.
- Eigener Code: MIT-Lizenz, siehe `LICENSE`.

## Aufbau
| Datei | Aufgabe |
|---|---|
| `einstellungen.py` | Pfade, ETF-Liste mit Index-Vorlauf, Krypto- und Rohstoffliste, Drosselung |
| `universum.py` | Werteliste: Nasdaq-Verzeichnis, Vanguard-Excel (FTSE All-World) aus `daten/eingang/`, ETFs, Krypto, Rohstoffe |
| `kurse.py` | Tageskurse von Yahoo (yfinance) → eine komprimierte Datei `daten/kurse.parquet` |
| `analyse.py` | Ampel 0–100, Ø Jahresrendite, Wahrscheinlichkeiten, Rangliste, Signal-Tagebuch |
| `umfeld.py` | FRED-Reihen (Zinskurve T10Y2Y, 3-Monats-Zins TB3MS); Marktumfeld (Marktbreite, VIX, Zinskurve) |
| `pruefung.py` | Walk-forward-Prüfung und Kalibrierung der Ampel-Wahrscheinlichkeit |
| `strategie.py` | Sparplan gegen Staffelkäufe 60/75/90 (+ Teilverkauf ≤ 15), mit Kosten, Abgeltungssteuer, Zins |
| `montecarlo.py` | Block-Bootstrap echter Wochenrenditen: Kegel und „Wird Kurs X in 12 Monaten erreicht?“ |
| `tagebuch_pruefung.py` | Nachprüfung des Signal-Tagebuchs nach 1/3/5 Jahren (liest nur) |
| `server.py` | lokaler Server (nur 127.0.0.1), berechnet Charts, Prüfung, Strategie und Monte Carlo live |
| `web/index.html` | Dashboard |
| `daten/tagebuch/` | tägliche Signale – nie ändern |

Erzeugte Dateien (jederzeit neu erzeugbar, nicht im Repository): `daten/kurse.parquet`, `web/daten/*.json`, `daten/fred/*.csv`.

## Online-Fassung (GitHub Pages)
Der Workflow `.github/workflows/dashboard.yml` lädt die Kurse auf GitHub, rechnet alles neu und veröffentlicht mit `export.py` eine **reduzierte Fassung** (Ordner `site/`): Sie enthält **keine Kursreihen und keine Einzelkurse**, nur eigene Ergebnisse – Ampel und Ampel-Verlauf, Kennzahlen in Prozent, Wahrscheinlichkeiten, Prüfung, Lohnt-sich-Check, Strategie-Vergleich (Standardwerte) und Monte-Carlo-Ergebnisse als Prozentwerte. `export.py` prüft jede Datei und bricht ab, falls doch ein Kursfeld enthalten ist. Die Kursdatei bleibt zwischen den Läufen im GitHub-Cache, nie im Repository. Sperrt Yahoo, wird der letzte Stand veröffentlicht und oben auf der Seite als veraltet markiert. Die lokale Fassung bleibt voll (eigene Charts, freie Rechner).

### Datenquellen und Bedingungen
- **Kurs-Charts online: TradingView** über das kostenlose [Advanced Chart Widget](https://www.tradingview.com/widget-docs/widgets/charts/advanced-chart/). Laut TradingView sind Widgets mit dem Standard-Branding kostenlos; die Attribution („Chart von TradingView“, Logo) muss unverändert bleiben ([Nutzungsbedingungen, Abschnitt Attribution](https://www.tradingview.com/policies/)), und kommerzielle Nutzung ist ausgeschlossen. Dieses Projekt ist nicht kommerziell. Futures von CME/ICE und Werte der Londoner Börse sind im Gratis-Widget gesperrt; Rohstoffe erscheinen deshalb als TradingView-Referenzkurs (TVC) bzw. CFD-Kurs von Capital.com, VWRL und ISF ohne Chart.
- **Berechnungen: Yahoo Finance** (über yfinance) – nur intern, die Kurse selbst werden online nicht veröffentlicht.
- **Zinsen: FRED** (Federal Reserve Bank of St. Louis): T10Y2Y (Zinskurve), TB3MS (3-Monats-Zins).
- **Krypto:** Ein eigener Bitcoin-Chart mit Pi-Cycle-Linien ist online nicht möglich: Die Marktdaten-Bedingungen von Coinbase verbieten die Anzeige für Dritte, andere Quellen sind ungeprüft. Online zeigt TradingView den Kurs, die Pi-Cycle-Zonen erscheinen als Fläche im Ampel-Verlauf.
