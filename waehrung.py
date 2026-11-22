"""Wechselkurs Euro/US-Dollar fuer den Umschalter „$ / €“ im Chart (nur echte Kurse, nichts geschaetzt).

Quellen:
  - FRED DEXUSEU (US-Notenbank, H.10, Dollar je Euro, taeglich seit 04.01.1999) – amtlicher Hauptteil.
  - Yahoo EURUSD=X fuer die letzten Tage, die FRED noch nicht veroeffentlicht hat (FRED hinkt etwa eine Woche hinterher).
Vor 1999 gab es keinen Euro – dort wird nicht umgerechnet (der Chart zeigt in Euro erst ab 1999).
Ergebnis: web/daten/eurusd.json  {quelle, stand, tag0, d: [Tage seit tag0], k: [Dollar je Euro]}

Aufruf: python waehrung.py
"""
import datetime as dt
import json
import sys
import pandas as pd

import einstellungen as E
import umfeld

ZIEL = E.WEB_DATEN / "eurusd.json"


def yahoo(ab: pd.Timestamp) -> pd.Series | None:
    try:
        import yfinance as yf
        d = yf.download("EURUSD=X", start=(ab - pd.Timedelta(days=10)).strftime("%Y-%m-%d"), interval="1d",
                        auto_adjust=True, progress=False)
        if d is None or d.empty:
            return None
        s = d["Close"]
        s = s.iloc[:, 0] if isinstance(s, pd.DataFrame) else s
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        s = s.dropna()
        return s[(s > 0.5) & (s < 2.5)]   # offensichtliche Fehlwerte weg
    except Exception as ex:
        print(f"EUR/USD: Yahoo nicht ladbar ({ex.__class__.__name__}: {ex})", file=sys.stderr)
        return None


def main():
    umfeld.fred_laden("DEXUSEU")
    f = umfeld.fred_reihe("DEXUSEU")
    if f is None or len(f) < 1000:
        print("EUR/USD: keine FRED-Reihe – nichts geschrieben", file=sys.stderr)
        return
    f = f[(f > 0.5) & (f < 2.5)]
    y = yahoo(f.index[-1])
    teile = [f]
    if y is not None and len(y):
        teile.append(y[y.index > f.index[-1]])
    s = pd.concat(teile).sort_index()
    s = s[~s.index.duplicated(keep="first")]
    tag0 = s.index[0]
    out = {"quelle": "FRED DEXUSEU (US-Notenbank, Dollar je Euro)" + (", letzte Tage Yahoo EURUSD=X" if len(teile) > 1 and len(teile[1]) else ""),
           "stand": s.index[-1].strftime("%Y-%m-%d"), "tag0": tag0.strftime("%Y-%m-%d"),
           "d": [int((t - tag0).days) for t in s.index], "k": [round(float(v), 4) for v in s.values]}
    ZIEL.write_text(json.dumps(out, separators=(",", ":")))
    print(f"EUR/USD: {len(s)} Tage {tag0:%Y}–{s.index[-1]:%d.%m.%Y}, zuletzt {s.iloc[-1]:.4f} $ je €")


if __name__ == "__main__":
    main()
