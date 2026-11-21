"""MVRV-Z-Score fuer Bitcoin (Bewertung auf der Blockchain).

MVRV = Marktwert / „Realized Value“ (jeder Coin zu dem Preis bewertet, zu dem er zuletzt bewegt wurde,
also grob der Durchschnittseinstand aller Besitzer). Z-Score = (Marktwert - Realized Value) / Standardabweichung
des Marktwerts – hier nur mit der Geschichte bis zum jeweiligen Tag (ohne Blick in die Zukunft).
Faustregel aus der Krypto-Analyse: Z unter 0 = Kurs unter dem Durchschnittseinstand (historisch Boeden),
Z ueber 7 = ueberhitzt (historisch Hochs). Ob das ausserhalb der Rueckschau traegt, prueft auswerten().

Quelle: Coin Metrics Community-API (CapMVRVCur, CapMrktCurUSD), taeglich ab 18.07.2010.
Lizenz fuer oeffentliche Anzeige nicht abschliessend geklaert (wie bei btc_alt.py, Entscheidung Marc: anzeigen).
Gespeichert in daten/btc_alt/mvrv.csv (nicht im Repo), hoechstens alle 20 Stunden neu geladen.

Aufruf: python mvrv.py
"""
import sys
import time
import numpy as np
import pandas as pd
import requests

import einstellungen as E

DATEI = E.DATEN / "btc_alt" / "mvrv.csv"
KOPF = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
GUENSTIG, TEUER = 0.0, 7.0


def laden() -> bool:
    if DATEI.exists() and time.time() - DATEI.stat().st_mtime < 20 * 3600:
        return True
    url = ("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=CapMVRVCur,CapMrktCurUSD"
           "&frequency=1d&start_time=2010-07-01&page_size=10000&paging_from=start")
    zeilen = []
    try:
        while url:
            d = requests.get(url, headers=KOPF, timeout=60).json()
            for r in d.get("data", []):
                if r.get("CapMVRVCur") and r.get("CapMrktCurUSD"):
                    zeilen.append((r["time"][:10], float(r["CapMVRVCur"]), float(r["CapMrktCurUSD"])))
            url = d.get("next_page_url")
            time.sleep(1)
        if len(zeilen) < 3000:
            raise RuntimeError(f"nur {len(zeilen)} Tage")
        DATEI.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(zeilen, columns=["datum", "mvrv", "marktwert"]).to_csv(DATEI, index=False)
        print(f"MVRV: {len(zeilen)} Tage, bis {zeilen[-1][0]}")
        return True
    except Exception as ex:
        print(f"MVRV nicht ladbar ({ex.__class__.__name__}: {ex}) – nutze letzte Datei", file=sys.stderr)
        return DATEI.exists()


def reihe() -> pd.DataFrame | None:
    """Tageswerte: mvrv, marktwert, realisiert, z (Z-Score nur mit Vergangenheit)."""
    if not DATEI.exists():
        return None
    d = pd.read_csv(DATEI, parse_dates=["datum"]).set_index("datum").sort_index()
    d["realisiert"] = d["marktwert"] / d["mvrv"]
    sd = d["marktwert"].expanding(min_periods=365).std()
    d["z"] = (d["marktwert"] - d["realisiert"]) / sd
    return d


def auswerten(d: pd.DataFrame, kurs: pd.Series) -> dict:
    """Rueckblick je Zone (Ergebnis 1 Jahr spaeter) und Phasen unter 0 bzw. ueber 7, mit Kurs aus der Bitcoin-Reihe."""
    z = d["z"].dropna()
    k = kurs.reindex(z.index, method="ffill")
    vor1 = (k.shift(-365) / k - 1) * 100   # Kalendertage: Bitcoin handelt taeglich
    def phasen(maske):
        out, start, vorher = [], None, None
        for t, m in maske.items():
            if m and start is None:
                start = t
            if not m and start is not None:
                out.append((start, vorher)); start = None
            vorher = t
        if start is not None:
            out.append((start, vorher))
        # Phasen mit weniger als 30 Tagen Abstand zusammenfassen
        zus = []
        for a, b in out:
            if zus and (a - zus[-1][1]).days <= 30:
                zus[-1] = (zus[-1][0], b)
            else:
                zus.append((a, b))
        return zus
    def zeilen(maske):
        res = []
        for a, b in phasen(maske):
            r1 = vor1.get(a)
            res.append({"von": a.strftime("%Y-%m-%d"), "bis": b.strftime("%Y-%m-%d"), "z_extrem": round(float(z[a:b].min() if maske is unter else z[a:b].max()), 2),
                        "kurs": round(float(k[a]), 2), "r1": None if r1 is None or np.isnan(r1) else round(float(r1), 0)})
        return res
    unter = z < GUENSTIG
    ueber = z > TEUER
    def quote(m):
        x = vor1[m].dropna()
        return {"tage": int(len(x)), "hoeher": round(float((x > 0).mean()) * 100, 0) if len(x) else None,
                "median": round(float(x.median()), 0) if len(x) else None}
    jetzt = float(z.iloc[-1])
    return {"datum": z.index[-1].strftime("%Y-%m-%d"), "z": round(jetzt, 2), "mvrv": round(float(d["mvrv"].iloc[-1]), 2),
            "realisiert_kurs": round(float(d["realisiert"].iloc[-1] / (d["marktwert"].iloc[-1] / k.iloc[-1])), 0),
            "zone": "unter dem Durchschnittseinstand (historisch günstig)" if jetzt < GUENSTIG else "überhitzt (historisch teuer)" if jetzt > TEUER else
                    "dazwischen" ,
            "unter_null": zeilen(unter), "ueber_sieben": zeilen(ueber),
            "quote": {"unter_null": quote(unter), "ueber_sieben": quote(ueber), "alle": quote(z.notna())},
            "ab": z.index[0].strftime("%Y-%m-%d")}


if __name__ == "__main__":
    laden()


def pruefung(d: pd.DataFrame, kurs: pd.Series) -> dict | None:
    """Pruefung ohne Zukunftswissen: Fuer jedes Jahr Y wird die Quote „1 Jahr spaeter hoeher“ je Zone (unter 0 /
    0 bis 7 / ueber 7) nur aus Tagen gelernt, deren Ergebnis Ende Y-1 feststand, und auf die Tage von Y angewandt.
    Vergleich mit der Grundquote (alle bisherigen Tage). Skill > 0: die Zone hat besser vorhergesagt."""
    z = d["z"].dropna()
    k = kurs.reindex(z.index, method="ffill")
    f = k.shift(-365) / k - 1
    zone = pd.Series(np.where(z < GUENSTIG, 0, np.where(z > TEUER, 2, 1)), index=z.index)
    df = pd.DataFrame({"zone": zone, "f": f})
    bm = bb = 0.0
    n = 0
    zaehl = {0: [0, 0], 1: [0, 0], 2: [0, 0]}
    jahre = []
    for Y in range(z.index[0].year + 2, z.index[-1].year + 1):
        bek = df[df.index <= pd.Timestamp(f"{Y - 1}-12-31") - pd.Timedelta(days=365)].dropna()
        test = df[df.index.year == Y].dropna()
        if len(bek) < 365 or test.empty:
            continue
        basis = float((bek.f > 0).mean())
        q = {g: (float((bek[bek.zone == g].f > 0).mean()) if (bek.zone == g).sum() >= 30 else basis) for g in (0, 1, 2)}
        p = test.zone.map(q).values
        t = (test.f > 0).values.astype(float)
        bm += float(((p - t) ** 2).sum()); bb += float(((basis - t) ** 2).sum()); n += len(t)
        for g in (0, 1, 2):
            m = test.zone == g
            zaehl[g][0] += int(m.sum()); zaehl[g][1] += int((test.f[m] > 0).sum())
        jahre.append(Y)
    if not n or not bb:
        return None
    q = lambda g: {"tage": zaehl[g][0], "hoeher": round(zaehl[g][1] / zaehl[g][0] * 100, 0) if zaehl[g][0] else None}
    return {"skill": round((1 - bm / bb) * 100, 1), "tage": n, "von": jahre[0], "bis": jahre[-1],
            "unter_null": q(0), "dazwischen": q(1), "ueber_sieben": q(2)}
