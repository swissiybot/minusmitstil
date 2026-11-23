"""Verbraucherpreise fuer die „Rendite nach Inflation“ auf der Titelseite (nur amtliche Reihen, nichts geschaetzt).

Quellen (ueber FRED, ohne Schluessel):
  - Deutschland: Harmonisierter Verbraucherpreisindex (HVPI), Eurostat, Reihe CP0000DEM086NEST (monatlich, seit 1996).
  - USA: Consumer Price Index for All Urban Consumers (CPI-U), BLS, Reihe CPIAUCSL (monatlich, saisonbereinigt, seit 1947).
Ergebnis: web/daten/inflation.json
  {"stand": "JJJJ-MM-TT", "reihen": {"de": {name, quelle, reihe, basis, stand, m: [["JJJJ-MM", Index], ...]}, "us": {...}}}
Der Browser rechnet daraus selbst die Rendite nach Inflation (Kursrendite geteilt durch Preisanstieg im selben Zeitraum).

Aufruf: python inflation.py
"""
import datetime as dt
import json
import sys

import einstellungen as E
import umfeld

ZIEL = E.WEB_DATEN / "inflation.json"
REIHEN = {
    "de": ("CP0000DEM086NEST", "Deutschland, Harmonisierter Verbraucherpreisindex (HVPI)",
           "Eurostat über FRED (Reihe CP0000DEM086NEST)", "2025 = 100"),
    "us": ("CPIAUCSL", "USA, Verbraucherpreisindex (CPI-U, saisonbereinigt)",
           "U.S. Bureau of Labor Statistics über FRED (Reihe CPIAUCSL)", "1982–1984 = 100"),
}


def main():
    out = {}
    for k, (reihe, name, quelle, basis) in REIHEN.items():
        umfeld.fred_laden(reihe)
        s = umfeld.fred_reihe(reihe)
        if s is None or len(s) < 120:
            print(f"Inflation {k}: Reihe {reihe} nicht ladbar – ausgelassen", file=sys.stderr)
            continue
        s = s[s > 0]
        out[k] = {"name": name, "quelle": quelle, "reihe": reihe, "basis": basis, "stand": s.index[-1].strftime("%Y-%m"),
                  "m": [[t.strftime("%Y-%m"), round(float(v), 3)] for t, v in s.items()]}
        print(f"Inflation {k}: {len(s)} Monate {s.index[0]:%Y-%m}–{s.index[-1]:%Y-%m}, "
              f"letzte 12 Monate {(s.iloc[-1] / s.iloc[-13] - 1) * 100:+.1f} %")
    if not out:
        print("Inflation: keine Reihe – nichts geschrieben", file=sys.stderr)
        return
    ZIEL.write_text(json.dumps({"stand": dt.date.today().isoformat(), "reihen": out}, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
