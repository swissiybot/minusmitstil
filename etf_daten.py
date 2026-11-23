"""ETF-Inhalt und Kosten fuer die Titelseite (Wunsch Marc 23.11.2026) – nur, was die Quelle wirklich liefert.

Quelle: Yahoo Finance ueber yfinance (Ticker.funds_data; Yahoo bezieht Fondsdaten von Morningstar):
  - laufende Kosten pro Jahr laut letztem Jahresbericht („Annual Report Expense Ratio“),
  - die 10 groessten Positionen mit Gewicht, Branchenanteile, Aktien-/Anleihen-/Bargeld-Anteil, Anbieter.
Laenderanteile liefert diese Quelle nicht – sie fehlen deshalb (nichts geschaetzt). Fehlt ein Teil (z. B. die Kosten
bei VWRL), fehlt nur dieser Teil; liefert Yahoo gar nichts, gibt es fuer den ETF kein Feld „etf“.
Yahoo nennt keinen Stichtag fuer die Positionen; „stand“ ist der Tag des Abrufs.

Aufruf: python etf_daten.py          jeden ETF hoechstens einmal pro Woche neu, je Lauf hoechstens ETF_MINUTEN (5) Minuten
        python etf_daten.py --neu    alle jetzt neu laden
Ergebnis: daten/etf_daten.json {symbol: {...}} (nicht im Repo); analyse.py haengt es als Feld „etf“ an die Kopfzeile.
"""
import datetime as dt
import json
import math
import os
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
    """Laedt die ETFs, deren Stand aelter als ALTER_TAGE ist (nie geladene zuerst), hoechstens ETF_MINUTEN (Standard 5) lang;
    der Rest folgt im naechsten Lauf. Nach jedem ETF wird gesichert."""
    t0 = time.time()
    minuten = float(os.environ.get("ETF_MINUTEN", "5"))
    alt = json.loads(DATEI.read_text()) if DATEI.exists() else {}
    heute = dt.date.today()
    alle = etf_symbole()
    faellig = [s for s in alle if "--neu" in argv or s not in alt
               or (heute - dt.date.fromisoformat(alt[s].get("abruf", alt[s].get("stand", "2000-01-01")))).days >= ALTER_TAGE]
    faellig.sort(key=lambda s: alt.get(s, {}).get("abruf", ""))
    if not faellig:
        print(f"ETF-Daten: alle {len(alle)} ETFs in den letzten {ALTER_TAGE} Tagen geladen – nichts zu tun")
        return
    ohne, zeit_um = [], False
    for s in faellig:
        if time.time() - t0 > minuten * 60:
            zeit_um = True
            break
        try:
            d = ein_etf(s)
        except Exception as ex:
            print(f"  ETF-Daten {s}: {ex.__class__.__name__}: {ex}", file=sys.stderr)
            d = None
        if d:
            alt[s] = d | {"abruf": heute.isoformat()}
        else:
            ohne.append(s)
            if s in alt:
                alt[s]["abruf"] = heute.isoformat()   # letzter guter Stand bleibt (mit seinem alten „stand“)
        tmp = DATEI.with_suffix(".tmp")
        tmp.write_text(json.dumps(alt, ensure_ascii=False, indent=0))
        tmp.replace(DATEI)
        time.sleep(1.0)
    ohne_ter = [s for s, d in alt.items() if "ter" not in d]
    offen = [s for s in alle if s not in alt or alt[s].get("abruf") != heute.isoformat()] if zeit_um else []
    print(f"ETF-Daten: {len(alt)} von {len(alle)} ETFs mit Daten; diesmal ohne Daten: {', '.join(ohne) or '–'}; "
          f"ohne Kosten: {', '.join(ohne_ter) or '–'}" + (f"; Zeitgrenze erreicht, {len(offen)} folgen im nächsten Lauf" if zeit_um else ""))


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
