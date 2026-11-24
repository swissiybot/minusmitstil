"""Wichtige Aktien ausserhalb der USA: ISIN, Heimatboerse und Yahoo-Kuerzel aus Wikidata (gemeinfrei, CC0).

Warum: Das Tool kannte nur US-Aktien. Depotauszuege enthalten aber auch BYD, Xiaomi, Nestle, Toyota & Co.
Wikidata fuehrt fuer bekannte Firmen die ISIN (P946) und die Boersennotierungen mit Kuerzel (P414 + P249).

Auswahl "wichtig": Firmen mit mindestens MIN_LINKS Wikipedia-Artikeln (Sprachen) – ein grobes, aber offenes Mass
fuer Bekanntheit. Delistete Firmen fallen spaeter von selbst heraus, weil Yahoo keine Kurse liefert.

Seit 24.11.2026 (Wunsch Marc: „noch mehr von den wichtigeren Aktien“) kommen Firmen mit MIN_LINKS_ROH bis MIN_LINKS-1
Sprachen dazu – aber nur, wenn ISIN und Kuerzel bei Yahoo nachweislich zusammengehoeren. Das prueft welt_pruefen.py von
Hand (Yahoo-Suche nach der ISIN muss genau unser Kuerzel nennen); das Ergebnis liegt eingecheckt in
listen/welt_geprueft.csv. Grund: Bei weniger bekannten Firmen sind die Kuerzel in Wikidata oefter falsch oder veraltet,
und unter einem falschen Kuerzel stuende eine fremde Firma. Die bisherigen Werte (ab MIN_LINKS Sprachen) bleiben unveraendert.

Je Firma eine Heimatboerse: bevorzugt die Boerse des ISIN-Landes (bei chinesischen H-Aktien Hongkong), sonst die
erste grosse Boerse ausserhalb der USA. Zusaetzlich wird ein US-Kuerzel (ADR, z. B. NVO fuer Novo Nordisk)
gemerkt, damit eine Heimat-ISIN auch auf das ADR im Tool passt.

Speicher: daten/welt/wikidata.csv (Rohdaten, wenige hundert KB, hoechstens einmal pro Woche neu)
Ergebnis: daten/welt.csv  (symbol, name, land, isin, us)  -> universum.py und isin.py

Aufruf:  python welt.py
"""
import io
import re
import time
import datetime as dt
import pandas as pd
import requests

import einstellungen as E

ORDNER = E.DATEN / "welt"
ROH = ORDNER / "wikidata.csv"
ZIEL = E.DATEN / "welt.csv"
MIN_LINKS = 10          # ab so vielen Sprachen wie bisher ohne Einzelpruefung
MIN_LINKS_ROH = 2       # Rohdaten ab 2 Sprachen; darunter-liegende (2 bis 9) nur mit Eintrag in GEPRUEFT
GEPRUEFT = E.BASIS / "listen" / "welt_geprueft.csv"
UA = {"User-Agent": "minusmitstil/1.0 (https://github.com/swissiybot/minusmitstil)", "Accept": "text/csv"}

ABFRAGE = """
SELECT ?item ?itemLabel ?isin ?exchLabel ?ticker ?links WHERE {
  ?item wdt:P946 ?isin ; wikibase:sitelinks ?links .
  FILTER(?links >= %d)
  FILTER(!STRSTARTS(?isin, "US"))
  ?item p:P414 ?st . ?st ps:P414 ?exch ; pq:P249 ?ticker .
  FILTER NOT EXISTS { ?st pq:P582 ?ende }
  ?exch rdfs:label ?exchLabel . FILTER(LANG(?exchLabel) = "en")
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,de". }
}
"""

# Boerse (englischer Wikidata-Name, Teilstring) -> Yahoo-Endung, ISO-Land
BOERSEN = [
    ("Hong Kong", ".HK", "HK"), ("Tokyo", ".T", "JP"), ("Nagoya", ".T", "JP"), ("London Stock", ".L", "GB"),
    ("Frankfurt", ".DE", "DE"), ("Xetra", ".DE", "DE"), ("Euronext Paris", ".PA", "FR"), ("Amsterdam", ".AS", "NL"),
    ("Euronext Brussels", ".BR", "BE"), ("Euronext Lisbon", ".LS", "PT"), ("Euronext Dublin", ".IR", "IE"), ("Irish Stock", ".IR", "IE"),
    ("Euronext Athens", ".AT", "GR"), ("Athens", ".AT", "GR"), ("Swiss", ".SW", "CH"), ("SIX", ".SW", "CH"), ("Italian", ".MI", "IT"),
    ("Borsa Italiana", ".MI", "IT"), ("Madrid", ".MC", "ES"), ("Copenhagen", ".CO", "DK"), ("Stockholm", ".ST", "SE"),
    ("Helsinki", ".HE", "FI"), ("OMX", ".ST", "SE"), ("Oslo", ".OL", "NO"), ("Wiener", ".VI", "AT"), ("Vienna", ".VI", "AT"), ("Warsaw", ".WA", "PL"),
    ("Toronto", ".TO", "CA"), ("Australian", ".AX", "AU"), ("Shanghai", ".SS", "CN"), ("Shenzhen", ".SZ", "CN"),
    ("Korea", ".KS", "KR"), ("Korean", ".KS", "KR"), ("Taiwan", ".TW", "TW"), ("National Stock Exchange of India", ".NS", "IN"),
    ("Bombay", ".BO", "IN"), ("São Paulo", ".SA", "BR"), ("B3", ".SA", "BR"), ("Mexican", ".MX", "MX"), ("Johannesburg", ".JO", "ZA"),
    ("Singapore", ".SI", "SG"), ("Tel Aviv", ".TA", "IL"), ("Thailand", ".BK", "TH"), ("Malaysia", ".KL", "MY"),
    ("Indonesia", ".JK", "ID"), ("Istanbul", ".IS", "TR"), ("Saudi", ".SR", "SA"), ("New Zealand", ".NZ", "NZ"),
]
ENDUNG_NR = {}
for _nr, (_teil, _endung, _land) in enumerate(BOERSEN):
    ENDUNG_NR.setdefault(_endung, _nr)
US_BOERSEN = {"new york stock exchange", "nasdaq", "nyse american", "nyse arca", "nasdaq stock market"}   # genaue Namen (nicht „Nasdaq Copenhagen“)
# ISIN-Land -> bevorzugte Laender der Boerse (sonst gleiches Land)
BEVORZUGT = {"CN": ["HK", "CN"], "KY": ["HK", "CN", "TW"], "BM": ["HK", "GB"], "JE": ["GB"], "GG": ["GB"], "IM": ["GB"],
             "LU": ["NL", "FR", "DE", "BE"], "AN": ["NL"], "PA": ["GB"]}


def laden() -> bool:
    ORDNER.mkdir(parents=True, exist_ok=True)
    if ROH.exists() and (time.time() - ROH.stat().st_mtime) < 6.5 * 86400:
        try:   # eine frische Datei aus der Zeit vor dem 24.11.2026 enthaelt nur Firmen ab MIN_LINKS -> trotzdem neu laden
            if pd.to_numeric(pd.read_csv(ROH, usecols=["links"])["links"], errors="coerce").min() < MIN_LINKS:
                return False
        except Exception:
            pass
    try:
        r = requests.get("https://query.wikidata.org/sparql", params={"query": ABFRAGE % MIN_LINKS_ROH}, headers=UA, timeout=180)
        r.raise_for_status()
        d = pd.read_csv(io.StringIO(r.text), dtype=str)
        if len(d) < 500:
            raise ValueError(f"nur {len(d)} Zeilen")
    except Exception as ex:
        print(f"Wikidata nicht erreichbar ({ex.__class__.__name__}: {ex}) – nutze vorhandene Datei." if ROH.exists() else f"Wikidata nicht erreichbar ({ex}).")
        return False
    d.to_csv(ROH, index=False)
    return True


def _boerse(label: str):
    for teil, endung, land in BOERSEN:
        if teil.lower() in str(label).lower():
            return endung, land
    return None


def _yahoo(ticker: str, endung: str) -> str | None:
    t = str(ticker).strip()
    t = t.split(":")[-1].strip().upper()
    # Nordische Gattungen heissen bei Yahoo „NOVO-B.CO“, „VOLV-B.ST“ (bei Wikidata „NOVO B“)
    t = re.sub(r"\s+", "-" if endung in (".CO", ".ST", ".HE", ".OL") else "", t)
    if re.search(r"-(DKK|NOK|SEK|EUR|FI|DK|SE)$", t):   # Waehrungs-/Laenderzusatz, kein Yahoo-Kuerzel
        return None
    if not t or t == "NAN":
        return None
    if endung == ".HK":
        if not t.isdigit() or len(t) > 4:   # 5-stellige Zweitlinien (RMB-Handel) nicht
            return None
        t = t.zfill(4)
    if endung in (".T", ".SS", ".SZ", ".KS", ".TW") and not re.fullmatch(r"\d{4,6}", t):
        return None
    if endung == ".L":
        t = t.rstrip(".").replace(".", "-")
    t = t.replace("/", "-")
    return t + endung


def kandidaten_alle() -> pd.DataFrame:
    """Alle Firmen der Rohdatei mit Heimatkuerzel, ungefiltert (Spalten wie welt.csv). Grundlage fuer bauen() und welt_pruefen.py."""
    if not ROH.exists():
        print("Welt: keine Wikidata-Datei – keine Auslandsaktien.")
        return pd.DataFrame()
    d = pd.read_csv(ROH, dtype=str).dropna(subset=["isin", "ticker", "exchLabel"])
    d["links"] = pd.to_numeric(d["links"], errors="coerce").fillna(0)
    zeilen = []
    for isin, g in d.groupby("isin"):
        if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", isin):
            continue
        land_isin = isin[:2]
        kandidaten, us = [], None
        for _, z in g.iterrows():
            if z["exchLabel"].strip().lower() in US_BOERSEN:
                tk = str(z["ticker"]).split(":")[-1].strip().upper().replace(".", "-")
                if re.fullmatch(r"[A-Z][A-Z0-9-]{0,6}", tk):
                    us = us or tk
                continue
            b = _boerse(z["exchLabel"])
            if not b:
                continue
            sym = _yahoo(z["ticker"], b[0])
            if sym:
                kandidaten.append((b[1], sym))
        if not kandidaten and not us:
            continue
        reihenfolge = BEVORZUGT.get(land_isin, [land_isin])
        # Fest geregelte Reihenfolge statt „wie Wikidata gerade liefert“ (24.11.2026): Sonst wechselte dieselbe Firma von Lauf zu
        # Lauf das Kuerzel (Reliance mal Bombay, mal NSE) – und damit ihre Kennung im Tool. Bei gleichem Rang entscheidet die
        # Reihenfolge der Boersen in BOERSEN (NSE vor Bombay, Paris vor Lissabon), danach das Alphabet.
        kandidaten = sorted(set(kandidaten), key=lambda k: (reihenfolge.index(k[0]) if k[0] in reihenfolge else 99,
                                                             ENDUNG_NR.get("." + k[1].rsplit(".", 1)[-1], 99), k[1]))
        name = str(g["itemLabel"].iloc[0])
        if re.fullmatch(r"Q\d+", name):
            name = kandidaten[0][1] if kandidaten else us
        zeilen.append({"symbol": kandidaten[0][1] if kandidaten else "", "name": name, "land": kandidaten[0][0] if kandidaten else land_isin,
                       "isin": isin, "us": us or "", "links": int(g["links"].max())})
    return pd.DataFrame(zeilen)


def bauen() -> pd.DataFrame:
    out = kandidaten_alle()
    if out.empty:
        return out
    gepr = set()
    if GEPRUEFT.exists():
        g = pd.read_csv(GEPRUEFT, dtype=str)
        gepr = set(zip(g["isin"], g["symbol"]))
    behalten = [l >= MIN_LINKS or (i, sy) in gepr for l, i, sy in zip(out["links"], out["isin"], out["symbol"])]
    neu = int(sum(b and l < MIN_LINKS for b, l in zip(behalten, out["links"])))
    out = out[behalten].reset_index(drop=True)
    print(f"Welt: {neu} zusätzliche, einzeln geprüfte Firmen (unter {MIN_LINKS} Wikipedia-Sprachen, {GEPRUEFT.name})")
    # Eine Firma kann mehrere ISINs haben (Aktiengattungen) – je Yahoo-Kuerzel eine Zeile fuer die Werteliste,
    # die ISIN-Zuordnung behaelt alle (isin.py liest welt.csv vollstaendig)
    out.to_csv(ZIEL, index=False)
    print(f"Welt: {out['symbol'].replace('', pd.NA).nunique()} Auslandsaktien an der Heimatbörse, {int((out['us'] != '').sum())} mit US-Kürzel (ADR), {len(out)} ISINs -> {ZIEL.name}")
    return out


def main():
    if laden():
        print("Welt: Wikidata neu geladen")
    bauen()


if __name__ == "__main__":
    main()
