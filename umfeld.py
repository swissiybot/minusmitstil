"""Marktumfeld: Marktbreite (eigene Daten), VIX (Kursdatei) und Zinskurve 10J-2J (FRED).

Aufruf:  python umfeld.py     laedt die FRED-Reihen neu (T10Y2Y = Zinskurve, TB3MS = 3-Monats-Zins
                               fuer wartendes Geld im Strategie-Vergleich). Ohne Schluessel, kleine CSV-Dateien.
Faellt das Netz aus, bleiben die alten Dateien stehen und der Tageslauf laeuft trotzdem weiter.
Die Marktbreite wird in analyse.py beim Durchlauf ueber alle Aktien gezaehlt (kein zweites Einlesen).
"""
import io
import sys
import time
import datetime as dt
import requests
import numpy as np
import pandas as pd

import einstellungen as E

FRED = E.DATEN / "fred"
FRED_REIHEN = {"T10Y2Y": "Zinskurve 10 Jahre minus 2 Jahre (US-Staatsanleihen)",
               "TB3MS": "US-Geldmarkt 3 Monate (Treasury Bill)",
               "NCBEILQ027S": "Börsenwert der US-Unternehmen (Fed Z.1, für den Buffett-Indikator)",
               "GDP": "US-Bruttoinlandsprodukt (nominal, für den Buffett-Indikator)"}
START_BREITE = pd.Timestamp("1985-01-04")   # Freitag


# ----------------------------------------------------------------- FRED
def fred_laden(reihe: str) -> bool:
    FRED.mkdir(parents=True, exist_ok=True)
    ziel = FRED / f"{reihe}.csv"
    if ziel.exists() and time.time() - ziel.stat().st_mtime < 20 * 3600:
        return True
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={reihe}"
    for versuch in range(3):
        try:
            antwort = requests.get(url, timeout=60)   # Standard-Kennung von requests (FRED sperrt unbekannte)
            antwort.raise_for_status()
            daten = antwort.content
            df = pd.read_csv(io.BytesIO(daten))
            if df.shape[1] != 2 or len(df) < 100:
                raise ValueError(f"unerwartetes Format ({df.shape})")
            tmp = ziel.with_suffix(".tmp")
            tmp.write_bytes(daten)
            tmp.replace(ziel)
            return True
        except Exception as ex:
            print(f"  FRED {reihe}: {ex.__class__.__name__}: {ex} (Versuch {versuch + 1})")
            time.sleep(10 * (versuch + 1))
    return ziel.exists()


def fred_reihe(reihe: str) -> pd.Series | None:
    f = FRED / f"{reihe}.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f)
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(df.iloc[:, 0])
    return s.dropna()


def zins_monatlich() -> pd.Series | None:
    """3-Monats-Zins in % p.a. je Monat (Monatsanfang), aus FRED TB3MS."""
    s = fred_reihe("TB3MS")
    if s is None or s.empty:
        return None
    return s.resample("MS").last().ffill()


# ----------------------------------------------------------------- Marktbreite
class Breite:
    """Zaehlt je Woche, wie viele Aktien ueber ihrer 40-Wochen-Linie schliessen."""

    def __init__(self):
        self.index = pd.date_range(START_BREITE, pd.Timestamp(dt.date.today()) + pd.Timedelta(days=7), freq="W-FRI")
        self.ueber = np.zeros(len(self.index))
        self.gesamt = np.zeros(len(self.index))

    def add(self, w_close: pd.Series):
        sma = w_close.rolling(40).mean()
        ok = sma.notna() & (w_close.index >= self.index[0])
        if not ok.any():
            return
        pos = self.index.get_indexer(w_close.index[ok])
        gut = pos >= 0
        pos = pos[gut]
        np.add.at(self.gesamt, pos, 1)
        np.add.at(self.ueber, pos, (w_close[ok].values > sma[ok].values)[gut].astype(float))

    def reihe(self, min_aktien: int = 200) -> pd.Series:
        s = pd.Series(np.where(self.gesamt >= min_aktien, self.ueber / np.maximum(self.gesamt, 1) * 100, np.nan), index=self.index)
        return s.dropna()


# ----------------------------------------------------------------- Ausgabe
def _perzentil(reihe: pd.Series, wert: float) -> float:
    return round(float((reihe < wert).mean()) * 100, 0)


def _kompakt(s: pd.Series, n: int = 3):
    t = [int(x) for x in (s.index - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)]
    return {"t": t, "v": [round(float(v), n) for v in s.values]}


def schreiben(breite: Breite | None, anzahl_aktien: int = 0):
    from kurse import lade_lokal
    import json
    out = {"stand": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}

    if breite is not None:
        b = breite.reihe()
        letzte = b[b.index <= pd.Timestamp(dt.date.today()) + pd.Timedelta(days=6)]
        if not letzte.empty:
            jetzt = float(letzte.iloc[-1])
            ab2000 = letzte[letzte.index >= "2000-01-01"]
            out["breite"] = {
                "wert": round(jetzt, 1), "datum": letzte.index[-1].strftime("%Y-%m-%d"),
                "perzentil": _perzentil(ab2000, jetzt), "vor4w": round(float(letzte.iloc[-5]), 1) if len(letzte) > 5 else None,
                "aktien": int(breite.gesamt[breite.index.get_loc(letzte.index[-1])]),
                "reihe": _kompakt(letzte, 1),
                "quelle": "eigene Kursdaten: Nasdaq-Aktien mit mind. 3 Jahren Historie",
            }

    vix = lade_lokal("^VIX")
    if vix is not None and not vix.empty:
        c = vix["Close"].dropna()
        w = c.resample("W-FRI").last().dropna()
        jetzt = float(c.iloc[-1])
        out["vix"] = {"wert": round(jetzt, 2), "datum": c.index[-1].strftime("%Y-%m-%d"),
                      "perzentil": _perzentil(c, jetzt), "median": round(float(c.median()), 1),
                      "vor4w": round(float(w.iloc[-5]), 2) if len(w) > 5 else None,
                      "reihe": _kompakt(w, 2), "quelle": "Yahoo ^VIX (Cboe), seit " + c.index[0].strftime("%Y")}

    zk = fred_reihe("T10Y2Y")
    if zk is not None and not zk.empty:
        w = zk.resample("W-FRI").last().dropna()
        jetzt = float(zk.iloc[-1])
        neg = zk < 0
        # laengste/juengste Inversion
        letzte_inv = zk.index[neg][-1].strftime("%Y-%m-%d") if neg.any() else None
        if neg.iloc[-1]:
            seit = zk.index[~neg][-1] if (~neg).any() else zk.index[0]
            inv_text = f"invertiert seit {(seit + pd.Timedelta(days=1)).strftime('%d.%m.%Y')}"
        else:
            inv_text = f"zuletzt invertiert bis {pd.Timestamp(letzte_inv).strftime('%d.%m.%Y')}" if letzte_inv else "nie invertiert"
        out["zinskurve"] = {"wert": round(jetzt, 2), "datum": zk.index[-1].strftime("%Y-%m-%d"),
                            "invertiert": bool(neg.iloc[-1]), "text": inv_text, "perzentil": _perzentil(zk, jetzt),
                            "vor4w": round(float(w.iloc[-5]), 2) if len(w) > 5 else None,
                            "reihe": _kompakt(w, 2), "quelle": "FRED T10Y2Y, seit " + zk.index[0].strftime("%Y")}

    zm = zins_monatlich()
    if zm is not None:
        out["zins3m"] = {"wert": round(float(zm.iloc[-1]), 2), "datum": zm.index[-1].strftime("%Y-%m"), "quelle": "FRED TB3MS"}

    tmp = E.WEB_DATEN / "umfeld.tmp"
    tmp.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    tmp.replace(E.WEB_DATEN / "umfeld.json")


if __name__ == "__main__":
    ok = [r for r in FRED_REIHEN if fred_laden(r)]
    fehlt = [r for r in FRED_REIHEN if r not in ok]
    print(f"FRED: {len(ok)} Reihen aktuell" + (f", fehlen: {', '.join(fehlt)}" if fehlt else ""))
    sys.exit(0)   # Netzfehler sollen den Tageslauf nicht stoppen
