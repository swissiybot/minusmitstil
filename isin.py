"""ISIN-Liste fuer den Depot-Import: welche ISIN gehoert zu welchem Wert im Tool?

Warum: Depotauszuege (PDF/CSV) nennen Wertpapiere ueber die ISIN, das Tool kennt die Werte ueber ihr Kuerzel
(MSFT, NVDA ...). Ohne Zuordnung bleiben Einzelaktien beim Import "offen".

Quelle: SEC "Fails-to-Deliver"-Daten (gemeinfrei, zweimal im Monat, je Datei ca. 1 MB gepackt). Sie enthalten fuer
fast alle in den USA gehandelten Aktien und ETFs CUSIP und Kuerzel. Eine US-ISIN ist "US" + CUSIP + Pruefziffer,
die Pruefziffer wird berechnet. (Kanadische Firmen haben "CA" statt "US" – beide Varianten kommen in die Liste;
eine Variante, die es nicht gibt, schadet nicht, weil keine echte ISIN darauf passt.)
Auslaendische Heimat-ISINs (z. B. NL... fuer ASML in Amsterdam) lassen sich so nicht bilden; die bleiben offen.

Damit ein spaeter neu vergebenes Kuerzel keine falsche Firma bekommt: je Kuerzel zaehlen nur die CUSIPs aus der
neuesten Datei, in der es vorkommt, und aeltere nur, wenn die Firmenbezeichnung mit demselben Wort beginnt.

Die SEC verlangt eine Kontaktangabe im User-Agent (Umgebungsvariable SEC_KONTAKT, nie im Code).
Ohne SEC_KONTAKT wird nichts geladen; vorhandene Dateien werden trotzdem ausgewertet.

Speicher: daten/isin/ftd_JJJJMMa.csv (nur CUSIP, Kuerzel, Bezeichnung; wenige hundert KB je Datei).
Ergebnis: web/daten/isin.json  {ISIN: id im Tool}

Aufruf:  python isin.py
"""
import io
import json
import os
import time
import zipfile
import datetime as dt
import pandas as pd
import requests

import einstellungen as E

ORDNER = E.DATEN / "isin"
ZIEL = E.WEB_DATEN / "isin.json"
URL = "https://www.sec.gov/files/data/fails-deliver-data/cnsfails{}.zip"
MONATE = 13


def pruefziffer(rumpf: str) -> str:
    """ISIN-Pruefziffer (Buchstaben -> Zahlen A=10..Z=35, dann Luhn)."""
    ziffern = "".join(str(int(c, 36)) for c in rumpf)
    summe = 0
    for i, ch in enumerate(reversed(ziffern)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            d = d - 9 if d > 9 else d
        summe += d
    return str((10 - summe % 10) % 10)


def _perioden() -> list[str]:
    heute = dt.date.today()
    out = []
    for k in range(MONATE):
        j, m = heute.year, heute.month - k
        while m <= 0:
            j, m = j - 1, m + 12
        out += [f"{j}{m:02d}b", f"{j}{m:02d}a"]
    return out   # neueste zuerst


def laden() -> int:
    kontakt = os.environ.get("SEC_KONTAKT", "").strip()
    if not kontakt:
        print("ISIN: keine Kontaktangabe (SEC_KONTAKT) – nichts geladen, nutze vorhandene Dateien.")
        return 0
    ORDNER.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers.update({"User-Agent": kontakt})
    neu = 0
    for p in _perioden():
        datei = ORDNER / f"ftd_{p}.csv"
        if datei.exists():
            continue   # abgeschlossene Halbmonate aendern sich nicht
        try:
            r = s.get(URL.format(p), timeout=60)
        except requests.RequestException as ex:
            print(f"  {p}: Netzfehler {ex.__class__.__name__}")
            continue
        time.sleep(0.2)
        if r.status_code == 404:
            continue   # noch nicht veroeffentlicht
        if r.status_code != 200:
            print(f"  {p}: HTTP {r.status_code}")
            continue
        try:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            roh = z.read(z.namelist()[0]).decode("latin-1")
            df = pd.read_csv(io.StringIO(roh), sep="|", dtype=str, usecols=[1, 2, 4], on_bad_lines="skip")
        except Exception as ex:
            print(f"  {p}: nicht lesbar ({ex.__class__.__name__})")
            continue
        df.columns = ["cusip", "symbol", "name"]
        df = df.dropna(subset=["cusip", "symbol"])
        df = df[df["cusip"].str.fullmatch(r"[0-9A-Z]{9}")].drop_duplicates(["cusip", "symbol"])
        df.to_csv(datei, index=False)
        neu += 1
    # alte Dateien (aelter als der Zeitraum) loeschen, damit der Ordner klein bleibt
    gueltig = {f"ftd_{p}.csv" for p in _perioden()}
    for f in ORDNER.glob("ftd_*.csv"):
        if f.name not in gueltig:
            f.unlink()
    return neu


def bauen() -> dict:
    dateien = sorted(ORDNER.glob("ftd_*.csv"), reverse=True)   # neueste zuerst
    if not dateien:
        print("ISIN: keine SEC-Dateien vorhanden – keine ISIN-Liste.")
        return {}
    uni = pd.read_csv(E.DATEN / "universum.csv")
    sym_zu_id = {str(s).upper(): str(i) for s, i in zip(uni["symbol"], uni["id"]) if "." not in str(s) and "-" not in str(s) and "=" not in str(s)}
    erstes_wort = lambda t: (str(t).split() or [""])[0].upper()
    gefunden: dict[str, dict] = {}   # symbol -> {"wort": ..., "cusips": set}
    for f in dateien:
        df = pd.read_csv(f, dtype=str).dropna(subset=["cusip", "symbol"])
        for c, s, n in zip(df["cusip"], df["symbol"].str.upper(), df["name"].fillna("")):
            if s not in sym_zu_id:
                continue
            g = gefunden.get(s)
            if g is None:
                gefunden[s] = {"wort": erstes_wort(n), "datei": f.name, "cusips": {c}}
            elif g["datei"] == f.name or erstes_wort(n) == g["wort"]:
                g["cusips"].add(c)
    tabelle = {}
    for s, g in gefunden.items():
        for c in g["cusips"]:
            for land in ("US", "CA") if c[0].isdigit() else ("US",):
                rumpf = land + c
                tabelle[rumpf + pruefziffer(rumpf)] = sym_zu_id[s]
    E.WEB_DATEN.mkdir(parents=True, exist_ok=True)
    ZIEL.write_text(json.dumps(tabelle, separators=(",", ":"), sort_keys=True))
    print(f"ISIN: {len(gefunden)} von {len(sym_zu_id)} US-Werten im Tool mit ISIN ({len(dateien)} SEC-Dateien) -> {ZIEL.name}")
    return tabelle


def main():
    neu = laden()
    if neu:
        print(f"ISIN: {neu} neue SEC-Dateien geladen")
    bauen()


if __name__ == "__main__":
    main()
