"""ETF-Inhalt und Kosten fuer die Titelseite (Wunsch Marc 23.11.2026) – nur, was die Quelle wirklich liefert.

Quelle: Yahoo Finance ueber yfinance (Ticker.funds_data; Yahoo bezieht Fondsdaten von Morningstar):
  - laufende Kosten pro Jahr laut letztem Jahresbericht („Annual Report Expense Ratio“),
  - die 10 groessten Positionen mit Gewicht, Branchenanteile, Aktien-/Anleihen-/Bargeld-Anteil, Anbieter.
Laenderanteile liefert diese Quelle nicht – sie fehlen deshalb (nichts geschaetzt). Fehlt ein Teil (z. B. die Kosten
bei VWRL), fehlt nur dieser Teil; liefert Yahoo gar nichts, gibt es fuer den ETF kein Feld „etf“.
Yahoo nennt keinen Stichtag fuer die Positionen; „stand“ ist der Tag des Abrufs.

Aufruf: python etf_daten.py          hoechstens einmal pro Woche neu
        python etf_daten.py --neu    jetzt neu laden
Ergebnis: daten/etf_daten.json {symbol: {...}} (nicht im Repo); analyse.py haengt es als Feld „etf“ an die Kopfzeile.
"""
import datetime as dt
import json
import math
import sys
import time

import einstellungen as E

DATEI = E.DATEN / "etf_daten.json"
ALTER_TAGE = 6
QUELLE = "Yahoo Finance (Fondsdaten von Morningstar)"
BRANCHEN = {"technology": "Technologie", "financial_services": "Finanzen", "healthcare": "Gesundheit",
            "consumer_cyclical": "Zyklischer Konsum", "communication_services": "Kommunikation", "industrials": "Industrie",
            "consumer_defensive": "Basiskonsum", "energy": "Energie", "basic_materials": "Grundstoffe",
            "realestate": "Immobilien", "utilities": "Versorger"}
_CACHE: dict | None = None


def etf_symbole() -> list[str]:
    alle = list(E.ETFS) + list(getattr(E, "THEMEN_ETFS", []))
    return list(dict.fromkeys(e["etf"] for e in alle if e.get("etf")))


def _zahl(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def ein_etf(symbol: str) -> dict | None:
    import yfinance as yf
    fd = yf.Ticker(symbol).funds_data
    out = {}
    try:
        ops = fd.fund_operations
        ter = _zahl(ops.loc["Annual Report Expense Ratio"].iloc[0]) if ops is not None and "Annual Report Expense Ratio" in ops.index else None
        if ter is not None and 0 < ter < 0.05:   # als Anteil (0,0945 % = 0.000945); mehr als 5 % p. a. wäre unplausibel
            out["ter"] = round(ter * 100, 3)
            out["ter_quelle"] = "laufende Kosten laut letztem Jahresbericht"
    except Exception:
        pass
    try:
        th = fd.top_holdings
        if th is not None and len(th):
            top = [[str(r["Name"]), round(_zahl(r["Holding Percent"]) * 100, 2)] for _, r in th.iterrows()
                   if _zahl(r.get("Holding Percent")) is not None and _zahl(r["Holding Percent"]) > 0]
            if top:
                out["top"] = top
                out["top_summe"] = round(sum(x[1] for x in top), 1)
    except Exception:
        pass
    try:
        sw = fd.sector_weightings or {}
        br = sorted(([BRANCHEN.get(k, k), round(_zahl(v) * 100, 1)] for k, v in sw.items() if _zahl(v)), key=lambda x: -x[1])
        if br and 90 <= sum(x[1] for x in br) <= 110:
            out["branchen"] = [x for x in br if x[1] > 0]
    except Exception:
        pass
    try:
        ac = fd.asset_classes or {}
        anteile = {"aktien": ac.get("stockPosition"), "anleihen": ac.get("bondPosition"), "bargeld": ac.get("cashPosition")}
        anteile = {k: round(_zahl(v) * 100, 1) for k, v in anteile.items() if _zahl(v) is not None}
        if anteile:
            out["anteile"] = anteile
    except Exception:
        pass
    try:
        ov = fd.fund_overview or {}
        if ov.get("family"):
            out["anbieter"] = str(ov["family"])
    except Exception:
        pass
    if not out:
        return None
    out.update({"stand": dt.date.today().isoformat(), "quelle": QUELLE})
    return out


def main(argv):
    if "--neu" not in argv and DATEI.exists() and time.time() - DATEI.stat().st_mtime < ALTER_TAGE * 86400:
        print(f"ETF-Daten: Stand vom {dt.date.fromtimestamp(DATEI.stat().st_mtime):%d.%m.%Y} gilt noch (wöchentlich neu)")
        return
    alt = json.loads(DATEI.read_text()) if DATEI.exists() else {}
    neu, ohne = {}, []
    for s in etf_symbole():
        try:
            d = ein_etf(s)
        except Exception as ex:
            print(f"  ETF-Daten {s}: {ex.__class__.__name__}: {ex}", file=sys.stderr)
            d = None
        if d:
            neu[s] = d
        else:
            ohne.append(s)
            if s in alt:
                neu[s] = alt[s]   # letzter guter Stand bleibt (mit seinem alten Datum)
        time.sleep(1.0)
    if neu:
        DATEI.write_text(json.dumps(neu, ensure_ascii=False, indent=0))
    ohne_ter = [s for s, d in neu.items() if "ter" not in d]
    print(f"ETF-Daten: {len(neu)} von {len(etf_symbole())} ETFs mit Daten; ohne Daten: {', '.join(ohne) or '–'}; "
          f"ohne Kosten: {', '.join(ohne_ter) or '–'}")


def fuer_wert(symbol: str) -> dict | None:
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(DATEI.read_text()) if DATEI.exists() else {}
        except Exception:
            _CACHE = {}
    return _CACHE.get(symbol)


if __name__ == "__main__":
    main(sys.argv[1:])
