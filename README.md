# minus mit stil 📉✨

> Ein hochwissenschaftliches Werkzeug, das dir täglich sagt, was du vor drei Jahren hättest kaufen sollen.

**🌐 Live-Seite: https://swissiybot.github.io/minusmitstil/** – wird mehrmals täglich automatisch neu berechnet (werktags etwa alle 2 Stunden während der US-Börsenzeit, dazu jeden Morgen). Keine Echtzeitkurse.

**⚠️ Spaßprojekt. Historische Statistik, keine Anlageberatung.** Nichts hier ist eine Empfehlung, etwas zu kaufen oder zu verkaufen. Vergangene Kurse garantieren nichts. Wer nach diesem Tool handelt, tut das auf eigene Rechnung – und mit Stil.

## Was es macht
Ein lokales Dashboard im TradingView-Stil. Es zeigt täglich, welche Aktien (Nasdaq), Index-ETFs, Kryptowährungen (BTC, ETH, SOL, LINK, XLM) und Rohstoffe **im Vergleich zu ihrer eigenen Geschichte** günstig oder teuer stehen:

- **Ampel 0–100** (seit 22.11.2026 spätabends, Wunsch Marc): an der **200-Wochen-Linie verankert** (`anker_ampel` in `analyse.py`). An der Linie 70 (günstig), darunter +2 Punkte je % Abstand (5 % darunter = 80, ab 15 % = 100); darüber 70 × (1 − Rang), Rang = Anteil aller früheren Wochen über der Linie, in denen der Kurs näher an der Linie lag – nur mit den Daten bis zum jeweiligen Tag. 70 und 2 Punkte je % sind gesetzte Werte (unter der Linie gleiche Skala für alle Werte). Kaufzonen exakt aus derselben Formel, Woche für Woche mitwandernd (sehr günstig = 5 % unter der Linie). Frühere Ampeln: bis 21.11. Mischung (Allzeithoch, 200-Wochen-Linie, Trend, RSI); 22.11. tagsüber reines 200-Wochen-Perzentil, abends Studien-Ampel (`AMPEL_BAUSTEINE`, siehe unten). Das Signal-Tagebuch wertet nur Einträge der heutigen Ampel aus (`ampel: anker200`).
- **Ø Jahresrendite** über 20 Jahre (oder so viele, wie es Daten gibt), ETFs mit Index-Historie davor.
- **Marktphase** (steigt oder fällt es?): Aufwärtstrend = Kurs über der 200-Tage-Linie und höher als vor 12 Monaten, Abwärtstrend = beides umgekehrt, sonst gemischt; dazu klassisch „Bärenmarkt“ ab 20 % unter dem Hoch. Je Wert Rückblick (wie oft danach höher, Median, Absturzrisiko) und Prüfung ohne Zukunftswissen gegen die Grundquote; Ergebnis über alle Gruppen: Die Phase sagt die Richtung **nicht** besser voraus als die Grundquote, zeigt aber das höhere Absturzrisiko nach Abwärtstrends. Kachel in der Übersicht, Abschnitt 4 auf der Prüfungsseite.
- **Wann hat sich Kaufen gelohnt?** Je Wert alle günstigen Phasen (Ampel ab 60) mit dem Ergebnis eines Kaufs zu Phasenbeginn nach 1/3/5 Jahren, im Vergleich zu beliebigen Wochen; im Chart als Punkt mit dem 1-Jahres-Ergebnis, günstige Phasen hellgrün (ab 80 kräftiger).
- **Trefferquote**: Wie oft stand der Kurs nach 1/3/5 Jahren höher, wenn die Lage früher ähnlich war – im Vergleich zu einem beliebigen Kauftag.
- **Bitcoin**: Pi Cycle Bottom (Bodenbildungszone und Boden-Signal), Pi Cycle Top, Mayer Multiple.
- **Bewertung S&P 500 (Shiller-CAPE)**: wie teuer der US-Markt gemessen an seinen **Gewinnen** ist (die Ampel schaut nur auf den Kurs). Getrennt von der Ampel, mit eigener ehrlicher Prüfung: Auf teure Phasen folgten im Mittel schwächere 10 Jahre, als Echtzeit-Vorhersage war das CAPE aber kaum besser als der einfache Durchschnitt (seit 1990 schlechter), und Warten auf günstige Bewertung schlug den Sparplan meist nicht. Nur für den S&P 500 gibt es eine so lange freie Reihe.
- **Geschäftszahlen und Fallen-Warnung** (Nasdaq-Aktien, nur im Online-Lauf): Gewinn, Umsatz, KGV und KUV aus den Pflichtberichten an die US-Börsenaufsicht (SEC EDGAR, gemeinfrei). ⚠ Fallen-Warnung, wenn die Ampel günstig steht, die Firma aber Verlust macht oder Gewinn bzw. Umsatz deutlich sinken – mit eigener Prüfung ohne Zukunftswissen (Abschnitt 4 der Prüfseite). Ausländische Firmen (IFRS) haben keine Zahlen.
- **Prüfung**: Walk-forward-Test, Kalibrierung, Sparplan gegen „nur kaufen, wenn günstig“, Monte-Carlo-Kegel, Marktumfeld (Marktbreite, VIX, Zinskurve).
- **Signal-Tagebuch** (`daten/tagebuch/`): jeden Tag festgehalten und in Git gesichert, damit später niemand schummeln kann.

## Bedienung
- **Übersicht** mit Marktwetter (Marktbreite, VIX, Zinskurve, Prüfung der Ampel), Heatmap aller ETFs, Kryptowährungen und Rohstoffe nach Ampel und „Heute auffällig“.
- **Suche** oben (Taste `/` oder `Strg K`), verzeiht Tippfehler („bitcon“ findet Bitcoin).
- **Liste** links mit Reitern Übersicht · ETFs · Krypto · Rohstoffe · Aktien (Screener mit Filtern, flüssig bei 3.000 Zeilen) · Meine (Favoriten-Stern); je Zeile Ampel, Verlauf des letzten Jahres und Änderung in 4 Wochen. Breiter ziehen zeigt mehr Spalten.
- **Detail**: Ampel-Halbkreis mit Klartext-Satz, Chart mit Zeitraum-Knöpfen (1J/5J/10J/Alles), Log/Linear, Fadenkreuz mit Werten und ein-/ausschaltbaren Linien (200-Wochen-Linie, Trendkanal (lineare Regression über den sichtbaren Ausschnitt, ±2 Standardabw., passt sich Zoom, Zeitebene und Skala an), Prognose-Kegel, Günstig-/Teuer-Phasen, Kaufzonen, bei Bitcoin Pi Cycle Bottom/Top und Mayer); Golden Pocket (Fibonacci 0,382 / 0,5 / 0,618 und Zone 0,618–0,65 zwischen Hoch und Tief des sichtbaren Ausschnitts, Richtung automatisch); Umschalter auf den TradingView-Chart (Monat, 200-Wochen-Linie). Darunter Karten: Lohnt-sich-Check, Wahrscheinlichkeiten gegen „beliebiger Tag“, Prognose, Rückschlag, Ø Rendite, weitere Kennzahlen – und Reiter für Details, Kurs-Rechner, Prüfung und Strategie-Vergleich.
- **Zeitebenen**: Monat, Woche, Tag im eigenen Chart (Tag: letzte 15 Jahre; online für ETFs, Krypto und Rohstoffe), 1 Std., 30 und 15 Min. über das TradingView-Widget (eigene Intraday-Kurse gibt es nicht). Die Ampel wird immer aus Wochenkursen berechnet.
- **Werkzeuge**: Lineal (zwei Klicks: Prozent, Betrag, Dauer, Zahl der Kerzen), Bollinger-Bänder (20, 2), Fibonacci-Zonen des sichtbaren Ausschnitts und eine Fläche für die ganze Günstig-/Teuer-Phase (Ampel ≥ 80 bzw. ≤ 15) – alles ein- und ausschaltbar.
- **Bereiche verstellen**: Trennlinien zwischen Liste, Chart, Ampel-Leiste und Seitenleiste ziehen, Doppelklick setzt zurück (wird im Browser gemerkt). Hell/Dunkel oben rechts. Auf dem Handy eine Spalte mit unterer Reiterleiste.
- Bildschirmfotos: `web/screenshots/`.

## Mein Depot
Vermögensübersicht laden (von Hand, CSV-Datei, **PDF-Depotauszug** oder kopierte Tabelle mit Spalten-Zuordnung) und eine Prognose fürs ganze Depot rechnen – **nur im Browser**: die Datei wird nie hochgeladen, es gibt keine Broker-Logins, gespeichert wird nur auf Wunsch („In diesem Browser merken“), „Depot vergessen“ löscht alles.
- **PDF-Import:** erkennt Positionen über die ISIN (mit Prüfziffer), dazu Name, Stückzahl und Kurswert (geprüft über Stück × Kurs) und gleicht mit der Summe der PDF ab; Vorschau zum Korrigieren. Gelesen wird mit [pdf.js](https://github.com/mozilla/pdf.js) (Apache-2.0, liegt in `web/lib/pdfjs/`) nur im Browser. Gescannte PDFs (nur Bild) gehen nicht.
- **Mehrere Depots:** mehrere CSV-Dateien auf einmal wählen; jede Datei wird ein eigenes Depot mit Namen (umbenennen, entfernen, mit neuer Datei gleichen Namens ersetzen). Die Spaltenzuordnung wird für Dateien mit gleichem Aufbau gemerkt (nur Spaltenköpfe, im Browser). Prognose für alle Depots zusammen oder für eines; derselbe Wert in mehreren Depots wird dafür zu einer Position zusammengefasst, damit er gemeinsam schwankt.
- Zuordnung automatisch über: ISINs großer Index-ETFs/ETCs (gleicher Index), die **ISIN jeder US-Aktie und jedes US-ETFs im Tool** (Liste `isin.json` aus den gemeinfreien SEC-Fails-to-Deliver-Daten: US-ISIN = „US“ + CUSIP + Prüfziffer, gebaut von `isin.py`), exakte Kürzel, breite Indizes im Fondsnamen („MSCI World“, „Nasdaq 100“ … ohne Small Cap, Equal Weight, Hebel) und eindeutige Firmennamen (die letzten beiden mit „bitte prüfen“). Junge Werte (13 bis 155 Wochen Kurse, z. B. SpaceX seit 06/2026) haben keine Ampel, aber seit 22.11.2026 eine eigene Seite mit Wochen- und Tageschart und der Karte „Seit dem Börsengang“ (erster Kurs, Hoch, Tief, Durchschnitt; `jung_wert` in `analyse.py`); im Depot werden sie mit ihren eigenen Wochenkursen gerechnet (`daten/jung.json`; Beta vorsichtig Richtung 1 gezogen, keine eigene Überrendite). **Werteliste weltweit:** Nasdaq- und NYSE-Aktien (Nasdaq-Trader-Verzeichnis), rund 1.100 bekannte Auslandsaktien an ihrer Heimatbörse mit ISIN (`welt.py`, Wikidata, CC0; Auswahl: mindestens 10 Wikipedia-Sprachartikel, Heimat-ISIN passt auch auf das US-ADR) und 65 Themen-, Branchen-, Faktor-, Länder- und Anleihen-ETFs (US-gelistet; europäische Fonds werden am Namen dem passenden Thema zugeordnet, z. B. Uran → URA). Was trotzdem nicht im Tool ist, bekommt einen markierten **automatischen Ersatz** nach ISIN-Ländercode bzw. Fondsart (z. B. China → MSCI EM, USA → S&P 500, Fonds ohne passenden Index → MSCI ACWI); die eigene Wahl geht vor und bleibt beim nächsten Import erhalten. PDF-Depotauszüge: Kopfzeile (Stück, Name, Kurs, Wert) wird genau einer ISIN zugeordnet, Kopf-/Fußzeilen der Bank werden übergangen; Summenabgleich mit der passenden Summe der PDF (z. B. Wertpapiere ohne Cash). Der Anteil ohne Zuordnung wird angezeigt.
- Sparplan individuell: Betrag (0 = keiner), Verteilung, jährliche Erhöhung, Laufzeit, Einmalbeträge/Entnahmen, Kosten je Kauf, laufende Kosten, Abgeltungssteuer mit Sparerpauschbetrag und Teilfreistellung, Inflation, Zielbetrag.
- Monte Carlo: Marktwochen (S&P 500, Blöcke à 13 Wochen, letzte 20 Jahre) mal Beta je Position plus eigene, zufällig gezogene Einzelschwankung; Fächer 5–95 %, Verlust- und Ziel-Wahrscheinlichkeit, größter Rückgang. Standard „vorsichtig“: kein Wert wird besser als der Markt angenommen.
- Ehrlich: Simulation aus der Vergangenheit, keine Vorhersage und keine Beratung; Renditen in Währung der Werte ohne Wechselkurs; kurze Historien und überlebende Aktien lassen die Vergangenheit zu gut aussehen. Feste Vorlagen für einzelne Banken gibt es noch nicht.
- Bildschirmfotos mit „TESTDATEN“ im Namen zeigen ein ausgedachtes Testdepot.

### Nachprüfung der Ampel-Varianten (22.11.2026)
Gleicher Test ohne Zukunftswissen für alte Mischung / 200-Wochen-Perzentil / Studien-Ampel / Anker-Ampel (14 ETFs, 15 Rohstoffe, 5 Krypto, rund 2.200 Aktien, Prüfzeit ab 2005). Rangkorrelation Ampel ↔ 3-Jahres-Rendite: ETFs 0,46 / 0,49 / 0,47 / **0,50**; Aktien 0,24 / 0,22 / **0,27** / 0,25; Rohstoffe 0,13 / 0,09 / 0,12 / **0,22**; Krypto **0,66** / 0,61 / 0,41 / 0,40. Die Quoten „ähnliche Lage“ sind bei allen Varianten schlechter als die Grundquote. Schwäche der Anker-Ampel: Bei Krypto folgten auf „sehr teuer“ oft noch Anstiege, bei Einzelaktien liefen „sehr günstige“ Kurse im Schnitt weiter schlecht (fallende Firmen bleiben unter der Linie).

### Herkunft der früheren Studien-Ampel (Studie 21.11.2026)
Die Bausteine wurden in einer Studie mit bis zu 1.585 Varianten ermittelt (expandierende Perzentile, Auswahl nur in der Lernzeit, Stabilitätsmaß und Jahres-Bootstrap). Bis 22.11.2026 lief diese Ampel violett zusätzlich neben der Hauptampel; seitdem ist sie die einzige. Nachrechnung 22.11.2026 (Rangkorrelation mit der 3-Jahres-Rendite ab 2005, gegen die reine 200-Wochen-Ampel): ETFs 0,57 gegen 0,53, Aktien 0,23 gegen 0,18, Rohstoffe 0,23 gegen 0,13, Bitcoin 0,51 gegen 0,25 – zum Teil auf denselben Daten ausgewählt, also eher zu optimistisch. Schwäche: Bei Bitcoin wurde „sehr teuer“ (≤ 15) nur 2017 eine Woche erreicht, das Hoch 2021 nicht.

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
- Geschäftszahlen: SEC EDGAR (US-Börsenaufsicht, gemeinfrei). Die SEC verlangt bei automatischen Abrufen eine Kontaktangabe im User-Agent; sie kommt aus der Umgebungsvariable `SEC_KONTAKT` (auf GitHub als geheime Einstellung) und steht nicht im Code. Ohne sie wird nichts geladen.
- CAPE: Robert J. Shiller, [shillerdata.com](https://shillerdata.com/) (`ie_data.xls`, frei zum Herunterladen; Datei wird nicht mitgeliefert, sondern bei jedem Lauf selbst geladen).
- Charts: [TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts) (Apache-2.0), liegt in `web/lib/`. PDF-Leser: [pdf.js](https://github.com/mozilla/pdf.js) 3.11.174 (Apache-2.0, Mozilla), liegt in `web/lib/pdfjs/`.
- Eigener Code: MIT-Lizenz, siehe `LICENSE`.

## Aufbau
| Datei | Aufgabe |
|---|---|
| `einstellungen.py` | Pfade, ETF-Liste mit Index-Vorlauf, Krypto- und Rohstoffliste, Drosselung |
| `universum.py` | Werteliste: Nasdaq-Verzeichnis, Vanguard-Excel (FTSE All-World) aus `daten/eingang/`, ETFs, Krypto, Rohstoffe |
| `kurse.py` | Tageskurse von Yahoo (yfinance) → eine komprimierte Datei `daten/kurse.parquet` |
| `analyse.py` | Ampel 0–100, Ø Jahresrendite, Wahrscheinlichkeiten, Rangliste, Signal-Tagebuch |
| `bewertung.py` | Shiller-CAPE des S&P 500: Bewertung 0–100 ohne Blick in die Zukunft, Renditen danach, Walk-forward-Prüfung, Sparplan gegen Warten |
| `fundamente.py` | Geschäftszahlen aus SEC EDGAR (frames-Schnittstelle): KGV, KUV, Gewinn-/Umsatztrend, Fallen-Warnung und deren Prüfung; lädt nur mit `SEC_KONTAKT` |
| `isin.py` | ISIN-Liste für den Depot-Import aus den SEC-Fails-to-Deliver-Daten (13 Monate, je Halbmonat ca. 1 MB); lädt nur mit `SEC_KONTAKT`, schreibt `web/daten/isin.json` |
| `welt.py` | Wichtige Auslandsaktien aus Wikidata (ISIN, Heimatbörse → Yahoo-Kürzel, US-ADR), höchstens wöchentlich neu; schreibt `daten/welt.csv` für `universum.py` und `isin.py` |
| `umfeld.py` | FRED-Reihen (Zinskurve T10Y2Y, 3-Monats-Zins TB3MS); Marktumfeld (Marktbreite, VIX, Zinskurve) |
| `pruefung.py` | Walk-forward-Prüfung und Kalibrierung der Ampel-Wahrscheinlichkeit |
| `strategie.py` | Sparplan gegen Staffelkäufe 60/75/90 (+ Teilverkauf ≤ 15), mit Kosten, Abgeltungssteuer, Zins |
| `montecarlo.py` | Block-Bootstrap echter Wochenrenditen: Kegel und „Wird Kurs X in 12 Monaten erreicht?“ |
| `tagebuch_pruefung.py` | Nachprüfung des Signal-Tagebuchs nach 1/3/5 Jahren (liest nur) |
| `server.py` | lokaler Server (nur 127.0.0.1), berechnet Charts, Prüfung, Strategie und Monte Carlo live |
| `web/index.html` | Dashboard |
| `daten/tagebuch/` | tägliche Signale – nie ändern |

Erzeugte Dateien (jederzeit neu erzeugbar, nicht im Repository): `daten/kurse.parquet`, `web/daten/*.json`, `daten/fred/*.csv`, `daten/shiller/ie_data.xls`, `daten/sec/`.

## Online-Fassung (GitHub Pages)
Der Workflow `.github/workflows/dashboard.yml` lädt die Kurse auf GitHub, rechnet alles neu und veröffentlicht mit `export.py` den Ordner `site/`. Die Online-Seite zeigt den **eigenen Chart wie lokal** (Wochenkerzen, 200-Wochen-Linie, Langfristtrend, Kauf-/Teuer-Pfeile, Pi Cycle bei Bitcoin, Prognose-Kegel); per Knopf lässt sich auf den TradingView-Chart umschalten (Monatsansicht, 200-Wochen-Linie). Die Kursdatei bleibt zwischen den Läufen im GitHub-Cache, nie im Repository. Sperrt Yahoo, wird der letzte Stand veröffentlicht und oben auf der Seite als veraltet markiert. Online sind der Strategie-Vergleich (Standardwerte) und der Monte-Carlo-Rechner (12 Monate, 20 Jahre) vorab gerechnet; frei einstellbar in der lokalen Fassung. (In `export.py` lässt sich mit `KURSE_OEFFENTLICH = False` eine Fassung ganz ohne Kurse erzeugen.)

### Datenquellen und Bedingungen
- **Kurse: Yahoo Finance** (über yfinance). Hinweis: Yahoo erlaubt die Daten laut Nutzungsbedingungen nur für den persönlichen Gebrauch; die Veröffentlichung hier ist eine bewusste Entscheidung des Projekts für ein nicht-kommerzielles Hobby-Dashboard.
- **TradingView-Chart (Umschalter):** kostenloses [Advanced Chart Widget](https://www.tradingview.com/widget-docs/widgets/charts/advanced-chart/), Attribution („Chart von TradingView“, Logo) bleibt unverändert ([Nutzungsbedingungen, Abschnitt Attribution](https://www.tradingview.com/policies/)); keine kommerzielle Nutzung. Futures von CME/ICE und Werte der Londoner Börse sind im Gratis-Widget gesperrt; Rohstoffe erscheinen dort als TradingView-Referenzkurs (TVC) bzw. CFD-Kurs von Capital.com, VWRL und ISF ohne TradingView-Chart.
- **Zinsen: FRED** (Federal Reserve Bank of St. Louis): T10Y2Y, TB3MS. **CAPE:** Robert J. Shiller (shillerdata.com); online nur CAPE und eigene Auswertung, keine Kurse daraus. **VIX:** Cboe über Yahoo.
