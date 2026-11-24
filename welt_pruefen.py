"""Prueft von Hand die weniger bekannten Auslandsaktien (2 bis 9 Wikipedia-Sprachen), bevor sie in die Werteliste kommen.

Warum: welt.py nimmt Firmen ab 10 Wikipedia-Sprachen ohne Einzelpruefung. Bei weniger bekannten Firmen sind die
Boersenkuerzel in Wikidata oefter falsch oder veraltet – unter einem falschen Kuerzel stuende im Tool eine fremde Firma.

Pruefung je Firma: Die Yahoo-Suche nach der ISIN muss genau unser Kuerzel (Heimatboerse) nennen. Nur dann kommt die
Zeile nach listen/welt_geprueft.csv (eingecheckt; welt.py liest sie bei jedem Lauf). Alles andere steht mit Grund in
listen/welt_abgelehnt.csv. Bewusst von Hand und nicht bei jedem Online-Lauf: Der Lauf soll nicht von der Yahoo-Suche
abhaengen, und es sollen keine Werte kommen und gehen.

Aufruf (etwa einmal im Quartal, dauert rund 10–15 Minuten):
    python welt.py            # Rohdaten von Wikidata (ab 2 Sprachen)
    python welt_pruefen.py    # schreibt listen/welt_geprueft.csv und listen/welt_abgelehnt.csv
    git diff --stat listen/   # ansehen, dann einchecken
Unterbrochene Laeufe machen weiter (Zwischenstand in daten/welt/pruefung.json).
"""
import json
import sys
import time
import datetime as dt
import pandas as pd
import yfinance as yf

import einstellungen as E
import welt

ZWISCHEN = welt.ORDNER / "pruefung.json"
ABGELEHNT = E.BASIS / "listen" / "welt_abgelehnt.csv"


def suche(isin: str):
    """Kuerzel und Namen, die Yahoo zur ISIN nennt. None = Suche fehlgeschlagen (spaeter noch einmal)."""
    for versuch in range(3):
        try:
            q = yf.Search(isin, max_results=12, news_count=0).quotes
            return [(x.get("symbol") or "", x.get("longname") or x.get("shortname") or "", x.get("quoteType") or "") for x in q]
        except Exception:
            time.sleep(4 * (versuch + 1))
    return None


def main():
    alle = welt.kandidaten_alle()
    if alle.empty:
        return 1
    kand = alle[(alle["links"] < welt.MIN_LINKS) & (alle["symbol"] != "")].drop_duplicates(["isin", "symbol"]).reset_index(drop=True)
    stand = json.loads(ZWISCHEN.read_text()) if ZWISCHEN.exists() else {}
    print(f"{len(kand)} Kandidaten (unter {welt.MIN_LINKS} Sprachen, mit Heimatkürzel); {len(stand)} schon geprüft", flush=True)
    for n, z in enumerate(kand.itertuples(index=False), 1):
        key = f"{z.isin}|{z.symbol}"
        if key in stand:
            continue
        q = suche(z.isin)
        if q is None:
            print(f"  Suche fehlgeschlagen: {key}", flush=True)
            continue
        stand[key] = q
        if n % 50 == 0:
            ZWISCHEN.write_text(json.dumps(stand, ensure_ascii=False))
            print(f"  {n}/{len(kand)}", flush=True)
        time.sleep(0.35)
    ZWISCHEN.write_text(json.dumps(stand, ensure_ascii=False))
    heute = dt.date.today().isoformat()
    gut, schlecht = [], []
    for z in kand.itertuples(index=False):
        q = stand.get(f"{z.isin}|{z.symbol}")
        basis = {"isin": z.isin, "symbol": z.symbol, "name": z.name, "land": z.land, "links": int(z.links)}
        if q is None:
            schlecht.append(basis | {"grund": "Yahoo-Suche fehlgeschlagen", "yahoo": ""})
            continue
        treffer = [x for x in q if x[0] == z.symbol and x[2] in ("EQUITY", "")]
        if treffer:
            gut.append(basis | {"yahoo_name": treffer[0][1], "geprueft": heute})
        else:
            schlecht.append(basis | {"grund": "Yahoo kennt die ISIN nicht" if not q else "Yahoo nennt zur ISIN ein anderes Kürzel",
                                     "yahoo": "; ".join(f"{x[0]} ({x[1]})" for x in q[:4])})
    (E.BASIS / "listen").mkdir(exist_ok=True)
    pd.DataFrame(gut).sort_values(["land", "symbol"]).to_csv(welt.GEPRUEFT, index=False)
    pd.DataFrame(schlecht).sort_values(["grund", "land", "symbol"]).to_csv(ABGELEHNT, index=False)
    print(f"geprüft und aufgenommen: {len(gut)} · abgelehnt: {len(schlecht)} -> {welt.GEPRUEFT.name}, {ABGELEHNT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
