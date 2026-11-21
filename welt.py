"""Wichtige Aktien ausserhalb der USA: ISIN, Heimatboerse und Yahoo-Kuerzel aus Wikidata (gemeinfrei, CC0).

Warum: Das Tool kannte nur US-Aktien. Depotauszuege enthalten aber auch BYD, Xiaomi, Nestle, Toyota & Co.
Wikidata fuehrt fuer bekannte Firmen die ISIN (P946) und die Boersennotierungen mit Kuerzel (P414 + P249).

Auswahl "wichtig": Firmen mit mindestens MIN_LINKS Wikipedia-Artikeln (Sprachen) – ein grobes, aber offenes Mass
fuer Bekanntheit. Delistete Firmen fallen spaeter von selbst heraus, weil Yahoo keine Kurse liefert.

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
MIN_LINKS = 10
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
US_BOERSEN = {"new york stock exchange", "nasdaq", "nyse american", "nyse arca", "nasdaq stock market"}   # genaue Namen (nicht „Nasdaq Copenhagen“)
# ISIN-Land -> bevorzugte Laender der Boerse (sonst gleiches Land)
BEVORZUGT = {"CN": ["HK", "CN"], "KY": ["HK", "CN", "TW"], "BM": ["HK", "GB"], "JE": ["GB"], "GG": ["GB"], "IM": ["GB"],
             "LU": ["NL", "FR", "DE", "BE"], "AN": ["NL"], "PA": ["GB"]}


def laden() -> bool:
    ORDNER.mkdir(parents=True, exist_ok=True)
    if ROH.exists() and (time.time() - ROH.stat().st_mtime) < 6.5 * 86400:
        return False
    try:
        r = requests.get("https://query.wikidata.org/sparql", params={"query": ABFRAGE % MIN_LINKS}, headers=UA, timeout=180)
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


def bauen() -> pd.DataFrame:
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
        kandidaten.sort(key=lambda k: reihenfolge.index(k[0]) if k[0] in reihenfolge else 99)
        name = str(g["itemLabel"].iloc[0])
        if re.fullmatch(r"Q\d+", name):
            name = kandidaten[0][1] if kandidaten else us
        zeilen.append({"symbol": kandidaten[0][1] if kandidaten else "", "name": name, "land": kandidaten[0][0] if kandidaten else land_isin,
                       "isin": isin, "us": us or "", "links": int(g["links"].max())})
    out = pd.DataFrame(zeilen)
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
