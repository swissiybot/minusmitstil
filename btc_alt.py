"""Bitcoin-Vorgeschichte vor Yahoo (Yahoo liefert BTC-USD erst ab 17.09.2014).

Quellen (Entscheidung Marc 21.11.2026: beide, lokal und online):
  - Coin Metrics Community-API: Tagespreis in USD ab 18.07.2010 (nur ein Preis je Tag, keine Kerzen).
    Genutzt bis zum ersten Bitstamp-Tag.
  - Bitstamp (Boerse), oeffentliche Schnittstelle: echte Tageskerzen ab Ende 2011.
    Genutzt bis zum ersten Yahoo-Tag.
Die Nutzungsbedingungen beider Quellen fuer eine oeffentliche Webseite sind nicht abschliessend geklaert
(Coin-Metrics-Lizenzseite nur mit Anmeldung lesbar, Bitstamp-Bedingungen leer); siehe Vault „Datenquellen“.

Die Vorgeschichte aendert sich nicht mehr; sie wird einmal geladen und in daten/btc_alt/ gespeichert
(nicht im Repo). Aufruf: python btc_alt.py [--neu]
"""
import sys
import time
import pandas as pd
import requests

import einstellungen as E

ORDNER = E.DATEN / "btc_alt"
CM_DATEI = ORDNER / "coinmetrics.csv"
BS_DATEI = ORDNER / "bitstamp.csv"
BIS = "2014-12-31"   # etwas ueber den Yahoo-Start hinaus, damit der Uebergang geprueft werden kann
KOPF = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}


def coinmetrics() -> pd.DataFrame:
    url = ("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=PriceUSD"
           f"&frequency=1d&start_time=2010-01-01&end_time={BIS}&page_size=10000&paging_from=start")
    zeilen = []
    while url:
        d = requests.get(url, headers=KOPF, timeout=60).json()
        zeilen += [(r["time"][:10], float(r["PriceUSD"])) for r in d.get("data", []) if r.get("PriceUSD")]
        url = d.get("next_page_url")
        time.sleep(1)
    df = pd.DataFrame(zeilen, columns=["datum", "Close"])
    df["datum"] = pd.to_datetime(df["datum"])
    return df.set_index("datum").sort_index()


def bitstamp() -> pd.DataFrame:
    start, ende = 1312000000, int(pd.Timestamp(BIS).timestamp())   # 30.07.2011 (Bitstamp startete im August 2011)
    zeilen = []
    while start < ende:
        d = requests.get("https://www.bitstamp.net/api/v2/ohlc/btcusd/", headers=KOPF, timeout=60,
                         params={"step": 86400, "limit": 1000, "start": start}).json()
        ohlc = d.get("data", {}).get("ohlc", [])
        if not ohlc:
            start += 1000 * 86400
            continue
        for r in ohlc:
            zeilen.append((int(r["timestamp"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"])))
        start = int(ohlc[-1]["timestamp"]) + 86400
        time.sleep(1)
    df = pd.DataFrame(zeilen, columns=["ts", "Open", "High", "Low", "Close", "Volume"]).drop_duplicates("ts")
    df["datum"] = pd.to_datetime(df["ts"], unit="s").dt.normalize()
    df = df.drop(columns="ts").set_index("datum").sort_index()
    return df[(df["Close"] > 0) & (df.index <= BIS)]


def laden(neu: bool = False):
    ORDNER.mkdir(parents=True, exist_ok=True)
    for datei, fn, name in ((CM_DATEI, coinmetrics, "Coin Metrics"), (BS_DATEI, bitstamp, "Bitstamp")):
        if datei.exists() and not neu:
            print(f"{name}: vorhanden ({datei.name})")
            continue
        try:
            df = fn()
            if len(df) < 300:
                raise RuntimeError(f"nur {len(df)} Tage")
            df.to_csv(datei)
            print(f"{name}: {len(df)} Tage, {df.index[0].date()} bis {df.index[-1].date()}")
        except Exception as ex:
            print(f"{name} nicht ladbar ({ex.__class__.__name__}: {ex}) – Bitcoin startet dann später", file=sys.stderr)


def verlaengern(tag: pd.DataFrame, segmente: list) -> tuple[pd.DataFrame, list]:
    """Haengt die Vorgeschichte vor die Yahoo-Tageskurse (ohne Skalierung, beides USD)."""
    if tag is None or tag.empty:
        return tag, segmente
    teile, seg = [], []
    erster = tag.index[0]
    if BS_DATEI.exists():
        bs = pd.read_csv(BS_DATEI, index_col=0, parse_dates=True)
        bs = bs[bs.index < erster]
        if not bs.empty:
            teile.append(bs)
            seg.append((bs.index[0], "krypto_bs", "Bitstamp BTC/USD"))
            erster = bs.index[0]
    if CM_DATEI.exists():
        cm = pd.read_csv(CM_DATEI, index_col=0, parse_dates=True)
        cm = cm[cm.index < erster]
        if not cm.empty:
            cm = cm.assign(Open=cm["Close"], High=cm["Close"], Low=cm["Close"], Volume=0.0)
            teile.insert(0, cm)
            seg.insert(0, (cm.index[0], "krypto_cm", "Coin Metrics PriceUSD"))
    if not teile:
        return tag, segmente
    spalten = ["Open", "High", "Low", "Close", "Volume"]
    voll = pd.concat([t[spalten].astype("float64") for t in teile] + [tag[spalten]])
    return voll, seg + segmente


if __name__ == "__main__":
    laden("--neu" in sys.argv)
