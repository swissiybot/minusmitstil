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
               "TB3MS": "US-Geldmarkt 3 Monate (Treasury Bill)"}
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


# ----------------------------------------------------------------- EZB-Einlagenzins
# Ersatz-Zins fuers Cash im Depot (Seite „Mein Depot“), wenn weder im PDF ein Zins steht noch einer eingetragen ist.
# Offizielle, schluessellose Datenschnittstelle der EZB (https://data.ecb.europa.eu/help/api/data):
# Reihe FM.D.U2.EUR.4F.KR.DFR.LEV = Einlagefazilitaet (Deposit Facility Rate), Stand je Tag, in % p.a.
EZB_REIHE = "FM.D.U2.EUR.4F.KR.DFR.LEV"
EZB_DATEI = "EZB_DFR.csv"
EZB_URL = "https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV?format=csvdata&lastNObservations=10"


def ezb_einlage_laden() -> bool:
    """Laedt die letzten Tageswerte des EZB-Einlagenzinses als kleine CSV. Faellt das Netz aus, bleibt die alte Datei stehen."""
    FRED.mkdir(parents=True, exist_ok=True)   # liegt neben den FRED-Dateien (derselbe Ordner wird online zwischengespeichert)
    ziel = FRED / EZB_DATEI
    if ziel.exists() and time.time() - ziel.stat().st_mtime < 20 * 3600:
        return True
    for versuch in range(3):
        try:
            antwort = requests.get(EZB_URL, timeout=60, headers={"Accept": "text/csv"})
            antwort.raise_for_status()
            daten = antwort.content
            df = pd.read_csv(io.BytesIO(daten))
            if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns or df.empty:
                raise ValueError(f"unerwartetes Format ({df.shape})")
            tmp = ziel.with_suffix(".tmp")
            tmp.write_bytes(daten)
            tmp.replace(ziel)
            return True
        except Exception as ex:
            print(f"  EZB Einlagenzins: {ex.__class__.__name__}: {ex} (Versuch {versuch + 1})")
            time.sleep(10 * (versuch + 1))
    return ziel.exists()


def ezb_einlage() -> dict | None:
    """Letzter Stand des EZB-Einlagenzinses aus der geladenen CSV: {wert (% p.a.), datum, quelle}. Fehlt die Datei oder ist sie unlesbar: None."""
    f = FRED / EZB_DATEI
    if not f.exists():
        return None
    try:
        df = pd.read_csv(f)
        df = df[["TIME_PERIOD", "OBS_VALUE"]].copy()
        df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
        df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"], errors="coerce")
        df = df.dropna().sort_values("TIME_PERIOD")
        if df.empty:
            return None
        wert = float(df["OBS_VALUE"].iloc[-1])
        if not -2 <= wert <= 15:   # unplausibel: lieber kein Feld als eine falsche Zahl
            return None
        return {"wert": round(wert, 2), "datum": df["TIME_PERIOD"].iloc[-1].strftime("%Y-%m-%d"),
                "quelle": "EZB, Einlagefazilität (" + EZB_REIHE + ")"}
    except Exception as ex:
        print(f"  EZB Einlagenzins nicht lesbar: {ex.__class__.__name__}: {ex}")
        return None


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

    ez = ezb_einlage()   # Ersatz-Zins fuers Cash im Depot; fehlt die Datei, fehlt einfach das Feld
    if ez:
        out["ezb_einlage"] = ez

    tmp = E.WEB_DATEN / "umfeld.tmp"
    tmp.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    tmp.replace(E.WEB_DATEN / "umfeld.json")


if __name__ == "__main__":
    import hebel_nachbau   # Tagesgeldzinsen für die nachgebaute Vorgeschichte der Hebel-Produkte
    alle = {**FRED_REIHEN, **hebel_nachbau.FRED_REIHEN}
    ok = [r for r in alle if fred_laden(r)]
    fehlt = [r for r in alle if r not in ok]
    print(f"FRED: {len(ok)} Reihen aktuell" + (f", fehlen: {', '.join(fehlt)}" if fehlt else ""))
    try:
        print("EZB-Einlagenzins: " + ("aktuell" if ezb_einlage_laden() else "fehlt (Netzfehler)"))
    except Exception as ex:   # darf den Lauf nie stoppen
        print(f"EZB-Einlagenzins: {ex.__class__.__name__}: {ex}")
    sys.exit(0)   # Netzfehler sollen den Tageslauf nicht stoppen
