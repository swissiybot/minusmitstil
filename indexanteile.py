"""Grobe Indexgewichte der groessten Titel fuer das Klumpenrisiko in „Mein Depot“ (nur echte Quellen, nichts geschaetzt).

Quellen:
  - S&P 500: taegliche Bestandsliste des SPDR S&P 500 ETF Trust (SPY) von State Street (Excel, oeffentlich),
    die 100 groessten Titel mit Gewicht. Hoechstens einmal pro Tag neu geladen; bei Netzfehlern bleibt der letzte Stand.
  - MSCI World, MSCI ACWI, MSCI Emerging Markets: Top 10 aus den offiziellen MSCI-Factsheets (Stand siehe FACTSHEETS).
  - FTSE All-World: Top 10 aus dem offiziellen FTSE-Russell-Factsheet.
    Factsheet-Werte stehen fest im Code und muessen von Hand erneuert werden (Datum wird angezeigt).
  - Nasdaq-100: Mitgliederliste aus daten/nasdaq100.json (Wikipedia, nasdaq100.py) – ohne Gewichte, weil Nasdaq die
    Gewichte nur nach Anmeldung zeigt.
Ergebnis: web/daten/indexanteile.json  {indizes: {schluessel: {name, etfs, quelle, stand, titel:[{name, ids, gewicht}], nur_mitglieder}}}
Die ids sind moegliche Werte im Tool (US-Kuerzel, Heimatboerse); der Browser nimmt, was im Depot vorkommt.

Aufruf: python indexanteile.py
"""
import io
import json
import re
import sys
import time
import requests

import einstellungen as E

ZIEL = E.WEB_DATEN / "indexanteile.json"
SPY_URL = "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"
SPY_CACHE = E.DATEN / "indexanteile_spy.json"
KOPF = {"User-Agent": "Mozilla/5.0 (minusmitstil-dashboard, Hobbyprojekt)"}

# Top 10 aus den Factsheets – exakt wie gedruckt (Name, Gewicht in %), dazu die passenden Werte im Tool.
_MSCI = "MSCI-Factsheet"
FACTSHEETS = {
    "msci_world": {
        "name": "MSCI World", "etfs": ["URTH", "IWDA"], "stand": "2026-10-30", "bestand": 1248,
        "quelle": f"{_MSCI} „MSCI World Index (USD)“, Stand 30.10.2026 (msci.com)",
        "titel": [("Apple", ["AAPL"], 5.65), ("Nvidia", ["NVDA"], 5.25), ("Microsoft", ["MSFT"], 4.11),
                  ("Amazon", ["AMZN"], 2.60), ("Alphabet A", ["GOOGL"], 1.83), ("Broadcom", ["AVGO"], 1.64),
                  ("Meta Platforms", ["META"], 1.51), ("Alphabet C", ["GOOG"], 1.45), ("Tesla", ["TSLA"], 1.28),
                  ("Eli Lilly", ["LLY"], 1.27)],
    },
    "msci_acwi": {
        "name": "MSCI ACWI", "etfs": ["ACWI"], "stand": "2026-10-30", "bestand": 2413,
        "quelle": f"{_MSCI} „MSCI ACWI Index“, Stand 30.10.2026 (msci.com)",
        "titel": [("Apple", ["AAPL"], 5.02), ("Nvidia", ["NVDA"], 4.66), ("Microsoft", ["MSFT"], 3.65),
                  ("Amazon", ["AMZN"], 2.31), ("Taiwan Semiconductor (TSMC)", ["TSM", "2330.TW"], 1.78),
                  ("Alphabet A", ["GOOGL"], 1.63), ("Broadcom", ["AVGO"], 1.46), ("Meta Platforms", ["META"], 1.34),
                  ("Alphabet C", ["GOOG"], 1.29), ("Tesla", ["TSLA"], 1.13)],
    },
    "msci_em": {
        "name": "MSCI Emerging Markets", "etfs": ["EEM"], "stand": "2026-10-30", "bestand": None,
        "quelle": f"{_MSCI} „MSCI Emerging Markets Index“, Stand 30.10.2026 (msci.com)",
        "titel": [("Taiwan Semiconductor (TSMC)", ["TSM", "2330.TW"], 15.87), ("Samsung Electronics", ["005930.KS"], 6.99),
                  ("SK Hynix", ["000660.KS", "SKHY"], 5.20), ("Tencent", ["0700.HK"], 2.66), ("Alibaba", ["9988.HK", "BABA"], 1.84),
                  ("MediaTek", ["2454.TW"], 1.54), ("China Construction Bank", ["0939.HK"], 0.97),
                  ("Samsung Electronics (Vorzugsaktie)", ["005935.KS"], 0.93), ("Hon Hai Precision (Foxconn)", ["2317.TW"], 0.82),
                  ("HDFC Bank", ["HDB", "HDFCBANK.NS"], 0.74)],
    },
    "ftse_aw": {
        "name": "FTSE All-World", "etfs": ["VWRL"], "stand": "2026-10-30", "bestand": 4200,
        "quelle": "FTSE-Russell-Factsheet „FTSE All-World Index“, Stand 30.10.2026 (ftserussell.com)",
        "titel": [("Apple", ["AAPL"], 4.79), ("Nvidia", ["NVDA"], 4.59), ("Microsoft", ["MSFT"], 3.73),
                  ("Amazon", ["AMZN"], 2.24), ("Taiwan Semiconductor (TSMC)", ["TSM", "2330.TW"], 1.70),
                  ("Alphabet A", ["GOOGL"], 1.57), ("Broadcom", ["AVGO"], 1.46), ("Meta Platforms", ["META"], 1.30),
                  ("Alphabet C", ["GOOG"], 1.27), ("Tesla", ["TSLA"], 1.12)],
    },
}


def spy_laden() -> dict | None:
    """Top 100 des SPY (State Street), hoechstens einmal pro Tag neu; sonst letzter Stand."""
    if SPY_CACHE.exists() and time.time() - SPY_CACHE.stat().st_mtime < 20 * 3600:
        return json.loads(SPY_CACHE.read_text())
    try:
        import pandas as pd
        r = requests.get(SPY_URL, headers=KOPF, timeout=60)
        r.raise_for_status()
        roh = pd.read_excel(io.BytesIO(r.content), header=None)
        stand = ""
        for v in map(str, roh.iloc[:5, 1].tolist()):
            if v.startswith("As of"):
                stand = pd.to_datetime(v.replace("As of", "").strip(), format="%d-%b-%Y").strftime("%Y-%m-%d")
        k = [i for i, v in zip(roh.index, roh.iloc[:, 0].tolist()) if str(v).strip() == "Name"][0]
        df = roh.iloc[k + 1:].copy()
        df.columns = [str(c).strip() for c in roh.iloc[k]]
        df = df[pd.to_numeric(df["Weight"], errors="coerce").notna()]
        df["Weight"] = df["Weight"].astype(float)
        df = df[[bool(re.fullmatch(r"[A-Z.]{1,6}", str(t))) for t in df["Ticker"]]].sort_values("Weight", ascending=False)
        summe = float(df["Weight"].sum())
        if not 90 <= summe <= 101 or len(df) < 400:
            raise RuntimeError(f"unplausibel: {len(df)} Titel, Summe {summe:.1f} %")
        titel = [{"name": str(z["Name"]).title(), "ids": [str(z["Ticker"]).replace(".", "-")], "gewicht": round(float(z["Weight"]), 2)}
                 for _, z in df.head(100).iterrows()]
        out = {"stand": stand, "bestand": int(len(df)), "titel": titel}
        SPY_CACHE.write_text(json.dumps(out, ensure_ascii=False))
        return out
    except Exception as ex:
        print(f"Indexanteile: SPY-Bestand nicht ladbar ({ex.__class__.__name__}: {ex})", file=sys.stderr)
        return json.loads(SPY_CACHE.read_text()) if SPY_CACHE.exists() else None


def main():
    indizes = {}
    spy = spy_laden()
    if spy:
        indizes["sp500"] = {"name": "S&P 500", "etfs": ["SPY"], "stand": spy["stand"], "bestand": spy["bestand"],
                            "quelle": f"Bestandsliste des SPDR S&P 500 ETF (State Street, ssga.com), Stand {spy['stand']}",
                            "titel": spy["titel"]}
    for k, f in FACTSHEETS.items():
        indizes[k] = {**{x: f[x] for x in ("name", "etfs", "stand", "bestand", "quelle")},
                      "titel": [{"name": n, "ids": ids, "gewicht": g} for n, ids, g in f["titel"]]}
    nf = E.DATEN / "nasdaq100.json"
    if nf.exists():
        d = json.loads(nf.read_text())
        indizes["nasdaq100"] = {"name": "Nasdaq-100", "etfs": ["QQQ"], "stand": d.get("stand"), "bestand": len(d["mitglieder"]),
                                "quelle": "Mitgliederliste Wikipedia „List of NASDAQ-100 companies“ (ohne Gewichte – Nasdaq zeigt sie nur nach Anmeldung)",
                                "nur_mitglieder": True, "titel": [{"name": m["name"], "ids": [m["symbol"]], "gewicht": None} for m in d["mitglieder"]]}
    ZIEL.write_text(json.dumps({"stand": time.strftime("%Y-%m-%d"), "indizes": indizes}, ensure_ascii=False, separators=(",", ":")))
    print(f"Indexanteile: {', '.join(f'{v['name']} ({len(v['titel'])})' for v in indizes.values())}")


if __name__ == "__main__":
    main()
