"""Bewertung des US-Gesamtmarkts (S&P 500) ueber das Shiller-CAPE – getrennt von der Kurs-Ampel.

Warum: Die Ampel schaut nur auf den Kurs. Ob die Gewinne mitgefallen sind, weiss sie nicht.
Das CAPE (Kurs / Durchschnittsgewinn der letzten 10 Jahre, inflationsbereinigt) misst dagegen,
wie viel man fuer die Gewinne bezahlt. Daten: Robert J. Shiller, monatlich ab 1871
(https://shillerdata.com/, Datei ie_data.xls). Nur fuer den S&P 500 gibt es eine so lange freie Reihe.

Grundsatz wie bei der Ampel: Die Bewertung zum Zeitpunkt t wird NUR mit der Geschichte bis t verglichen.
  Bewertung (0-100, hoch = historisch guenstig) = 100 - Perzentil des CAPE unter allen Monaten bis t.

Pruefung (ehrlich, ausserhalb der Lernzeit):
  - Walk-forward: Fuer jeden Monat t wird die Rendite der folgenden 10 Jahre (bzw. 1 Jahr) aus log(CAPE)
    vorhergesagt – mit einer Geraden, die NUR aus Monaten geschaetzt ist, deren Ergebnis bei t schon feststand.
    Verglichen mit der einfachen Vorhersage "Durchschnitt aller bisher bekannten Ergebnisse" (Basis).
    R2 ausserhalb der Lernzeit > 0 heisst: CAPE hat besser vorhergesagt als die Basis.
  - Sparplan gegen "nur kaufen, wenn die Bewertung guenstig ist, sonst Geld im Geldmarkt parken",
    in rollierenden 20-Jahres-Fenstern ab 1934 (Geldmarktzins FRED TB3MS), real, ohne Kosten und Steuern.

Aufruf:  python bewertung.py    laedt die Shiller-Datei (hoechstens alle 20 Stunden) und schreibt
                                web/daten/bewertung.json. Netzfehler stoppen den Tageslauf nicht.
"""
import json
import math
import re
import sys
import time
import datetime as dt
import numpy as np
import pandas as pd
import requests

import warnings
import einstellungen as E

warnings.filterwarnings("ignore", message=".*xlrd.*")

SEITE = "https://shillerdata.com/"
ORDNER = E.DATEN / "shiller"
DATEI = ORDNER / "ie_data.xls"
MIN_MONATE = 240            # mind. 20 Jahre CAPE-Geschichte, bevor eine Bewertung angezeigt wird
AEHNLICH = 0.10             # aehnliche Lage: CAPE hoechstens 10 % hoeher/niedriger als heute
LERN_MIN = 240              # Walk-forward: mind. 20 Jahre bekannte Ergebnisse zum Lernen
STUFEN = [(80, "historisch sehr günstig"), (60, "günstig"), (40, "neutral"), (15, "teuer"), (-1, "historisch sehr teuer")]
ZONEN = [("≥ 80", 80, 101), ("60–80", 60, 80), ("40–60", 40, 60), ("15–40", 15, 40), ("≤ 15", -1, 15)]


# ----------------------------------------------------------------- Laden
def laden() -> bool:
    ORDNER.mkdir(parents=True, exist_ok=True)
    if DATEI.exists() and time.time() - DATEI.stat().st_mtime < 20 * 3600:
        return True
    for versuch in range(3):
        try:
            seite = requests.get(SEITE, timeout=60).text
            m = re.search(r'href="([^"]*ie_data\.xls[^"]*)"', seite)
            if not m:
                raise ValueError("Download-Link ie_data.xls nicht gefunden")
            url = m.group(1).replace("&amp;", "&")
            url = "https:" + url if url.startswith("//") else url
            daten = requests.get(url, timeout=120).content
            tmp = DATEI.with_suffix(".tmp")
            tmp.write_bytes(daten)
            if len(_einlesen(tmp)) < 1500:
                raise ValueError("Datei unvollständig")
            tmp.replace(DATEI)
            return True
        except Exception as ex:
            print(f"  Shiller-Daten: {ex.__class__.__name__}: {ex} (Versuch {versuch + 1})")
            time.sleep(10 * (versuch + 1))
    return DATEI.exists()


def _einlesen(pfad) -> pd.DataFrame:
    roh = pd.read_excel(pfad, sheet_name="Data", header=None, skiprows=8)
    datum = pd.to_numeric(roh[0], errors="coerce")
    roh = roh[datum.notna()].copy()
    datum = datum[datum.notna()]
    jahr = np.floor(datum).astype(int)
    monat = np.round((datum - jahr) * 100).astype(int)
    idx = pd.to_datetime({"year": jahr, "month": monat, "day": 1})
    zahl = lambda c: pd.to_numeric(roh[c], errors="coerce").values
    df = pd.DataFrame({"preis": zahl(1), "cpi": zahl(4), "gs10": zahl(6), "real_tr": zahl(9),
                       "cape": zahl(12), "ecy": zahl(16)}, index=pd.DatetimeIndex(idx.values))
    return df[~df.index.duplicated(keep="last")].sort_index()


def reihe() -> pd.DataFrame | None:
    return _einlesen(DATEI) if DATEI.exists() else None


# ----------------------------------------------------------------- Rechnen
def bewertungsscore(cape: np.ndarray) -> np.ndarray:
    """100 - Perzentil des CAPE unter allen bisherigen Monaten (ohne Blick in die Zukunft)."""
    out = np.full(len(cape), np.nan)
    bisher: list[float] = []
    import bisect
    for t, v in enumerate(cape):
        if math.isnan(v):
            continue
        bisect.insort(bisher, v)
        if len(bisher) >= MIN_MONATE:
            out[t] = 100 - bisect.bisect_left(bisher, v) / len(bisher) * 100
    return out


def stufe(s):
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return None
    return next(t for g, t in STUFEN if s >= g)


def rendite_vorwaerts(real_tr: np.ndarray, monate: int) -> np.ndarray:
    """Reale Rendite p.a. (mit Dividenden) in den folgenden 'monate' Monaten; NaN, wo noch unbekannt."""
    n = len(real_tr)
    out = np.full(n, np.nan)
    out[:n - monate] = (real_tr[monate:] / real_tr[:n - monate]) ** (12 / monate) - 1
    return out


def _phasen(idx: np.ndarray, luecke: int = 12) -> list[tuple[int, int]]:
    """Fasst Monate zu zusammenhaengenden Phasen zusammen (neue Phase nach mehr als 'luecke' Monaten Pause)."""
    if len(idx) == 0:
        return []
    out, start = [], idx[0]
    for a, b in zip(idx[:-1], idx[1:]):
        if b - a > luecke:
            out.append((start, a)); start = b
    out.append((start, idx[-1]))
    return out


def _spanne(x: np.ndarray) -> dict | None:
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return None
    r = lambda v: round(float(v) * 100, 1)
    return {"n": int(len(x)), "median": r(np.median(x)), "p10": r(np.percentile(x, 10)), "p90": r(np.percentile(x, 90)),
            "positiv": round(float((x > 0).mean()) * 100, 0)}


def walk_forward(log_cape: np.ndarray, fwd: np.ndarray, h: int, index: pd.DatetimeIndex) -> dict | None:
    """Vorhersage der Rendite der naechsten h Monate aus log(CAPE), nur mit damals bekanntem Wissen."""
    n = len(fwd)
    pm, pb, wahr, monat = [], [], [], []
    for t in range(n):
        if math.isnan(fwd[t]) or math.isnan(log_cape[t]):
            continue
        bekannt = t - h                    # Monate s mit s + h <= t: Ergebnis bei t schon bekannt
        if bekannt <= 0:
            continue
        x, y = log_cape[:bekannt + 1], fwd[:bekannt + 1]
        ok = ~np.isnan(x) & ~np.isnan(y)
        if ok.sum() < LERN_MIN:
            continue
        b, a = np.polyfit(x[ok], y[ok], 1)
        pm.append(a + b * log_cape[t]); pb.append(y[ok].mean()); wahr.append(fwd[t]); monat.append(t)
    if not pm:
        return None
    pm, pb, wahr, monat = map(np.asarray, (pm, pb, wahr, monat))

    def kennzahlen(m):
        if m.sum() < 24:
            return None
        se_m = ((wahr[m] - pm[m]) ** 2).sum(); se_b = ((wahr[m] - pb[m]) ** 2).sum()
        return {"r2": round((1 - se_m / se_b) * 100, 1),
                "fehler_modell": round(float(np.abs(wahr[m] - pm[m]).mean()) * 100, 1),
                "fehler_basis": round(float(np.abs(wahr[m] - pb[m]).mean()) * 100, 1),
                "n": int(m.sum()), "von": index[monat[m][0]].strftime("%Y-%m"), "bis": index[monat[m][-1]].strftime("%Y-%m")}
    jahre = index.year.values[monat]
    return {"alle": kennzahlen(np.ones(len(pm), bool)), "ab1990": kennzahlen(jahre >= 1990), "bis1989": kennzahlen(jahre < 1990),
            "_fehler": wahr - pm}


def buffett_monatlich(index: pd.DatetimeIndex) -> pd.Series | None:
    """Buffett-Indikator: Boersenwert der US-Unternehmen (FRED NCBEILQ027S, Mio. $) / BIP (FRED GDP, Mrd. $), in %.
    Quartalswerte erscheinen erst Monate spaeter: fuer die Pruefung gilt ein Quartal erst 3 Monate nach Quartalsende als bekannt."""
    import umfeld
    mw, bip = umfeld.fred_reihe("NCBEILQ027S"), umfeld.fred_reihe("GDP")
    if mw is None or bip is None or mw.empty or bip.empty:
        return None
    q = (mw / (bip * 1000) * 100).dropna()
    q.index = q.index + pd.DateOffset(months=6)   # Quartalsanfang + 3 Monate Quartal + 3 Monate Veroeffentlichung
    return q.reindex(q.index.union(index)).ffill().reindex(index)


def erwartung(name: str, x: np.ndarray, fwd10: np.ndarray, fwd1: np.ndarray, index: pd.DatetimeIndex, log: bool) -> dict | None:
    """Erwartete reale Rendite p.a. der naechsten 10 Jahre aus einer Bewertungskennzahl (Gerade ueber alle bekannten Jahre),
    Spanne aus den Fehlern der Pruefung ohne Zukunftswissen (10.–90. Perzentil), dazu deren R2."""
    xx = np.log(x) if log else x.copy()
    ok = ~np.isnan(xx) & ~np.isnan(fwd10)
    jetzt_i = np.flatnonzero(~np.isnan(xx))
    if ok.sum() < LERN_MIN or len(jetzt_i) == 0:
        return None
    b, a = np.polyfit(xx[ok], fwd10[ok], 1)
    i = int(jetzt_i[-1])
    pred = a + b * xx[i]
    wf10, wf1 = walk_forward(xx, fwd10, 120, index), walk_forward(xx, fwd1, 12, index)
    fe = wf10["_fehler"] if wf10 else np.array([])
    r = lambda v: round(float(v) * 100, 1)
    return {"name": name, "wert": round(float(x[i]), 3 if not log else 1), "datum": index[i].strftime("%Y-%m"),
            "perzentil": round(float((x[~np.isnan(x)] < x[i]).mean()) * 100, 0),
            "erwartet": r(pred), "von": r(pred + np.percentile(fe, 10)) if len(fe) else None, "bis": r(pred + np.percentile(fe, 90)) if len(fe) else None,
            "r2_10": (wf10 or {}).get("alle", {}).get("r2") if wf10 and wf10.get("alle") else None,
            "r2_10_ab1990": wf10["ab1990"]["r2"] if wf10 and wf10.get("ab1990") else None,
            "r2_1": wf1["alle"]["r2"] if wf1 and wf1.get("alle") else None,
            "ab": index[int(np.flatnonzero(ok)[0])].strftime("%Y")}


def strategie(df: pd.DataFrame, score: np.ndarray, zins: pd.Series | None, schwelle: float) -> dict | None:
    """Sparplan (jeden Monat 1 kaufen) gegen 'monatlich 1 sparen, nur bei Bewertung >= schwelle alles investieren'.
    Real (inflationsbereinigt), Geld wartet im Geldmarkt (TB3MS), ohne Kosten/Steuern. 20-Jahres-Fenster ab 1934."""
    if zins is None or zins.empty:
        return None
    tb = zins.reindex(df.index).values
    rtr = df["real_tr"].values
    cpi = df["cpi"].values
    n = len(df)
    r_aktie = np.full(n, np.nan); r_cash = np.full(n, np.nan)
    r_aktie[:-1] = rtr[1:] / rtr[:-1] - 1
    r_cash[:-1] = (1 + tb[:-1] / 1200) * cpi[:-1] / cpi[1:] - 1
    gueltig = ~np.isnan(r_aktie) & ~np.isnan(r_cash) & ~np.isnan(score)
    start = np.flatnonzero(gueltig)
    if len(start) == 0:
        return None
    L = 240
    ergebnisse = []
    for s in range(start[0], n - L):
        if df.index[s].month != 1 or not gueltig[s:s + L].all():
            continue
        spar = aktie = cash = 0.0
        for t in range(s, s + L):
            spar += 1
            cash += 1
            if score[t] >= schwelle:
                aktie += cash; cash = 0.0
            spar *= 1 + r_aktie[t]; aktie *= 1 + r_aktie[t]; cash *= 1 + r_cash[t]
        w = aktie + cash
        ergebnisse.append((df.index[s].year, spar, w))
    if not ergebnisse:
        return None
    jahre = np.array([e[0] for e in ergebnisse]); sp = np.array([e[1] for e in ergebnisse]); wa = np.array([e[2] for e in ergebnisse])
    diff = (wa / sp - 1) * 100
    return {"schwelle": schwelle, "fenster": int(len(jahre)), "von": int(jahre[0]), "bis": int(jahre[-1]) + 20,
            "warten_besser": round(float((wa > sp).mean()) * 100, 0), "median_diff": round(float(np.median(diff)), 1),
            "schlechtestes": round(float(diff.min()), 1), "bestes": round(float(diff.max()), 1),
            "ab1990_fenster": int((jahre >= 1990).sum()),
            "ab1990_warten_besser": round(float((wa[jahre >= 1990] > sp[jahre >= 1990]).mean()) * 100, 0) if (jahre >= 1990).any() else None}


def auswerten(df: pd.DataFrame, zins: pd.Series | None) -> dict:
    df = df[df["cape"].notna() | df["real_tr"].notna()]
    cape = df["cape"].values.astype(float)
    score = bewertungsscore(cape)
    rtr = df["real_tr"].values.astype(float)
    f10, f1 = rendite_vorwaerts(rtr, 120), rendite_vorwaerts(rtr, 12)
    i = int(np.flatnonzero(~np.isnan(cape))[-1])
    jetzt, s_jetzt = float(cape[i]), float(score[i])
    ok = ~np.isnan(cape)
    seit1990 = ok & (df.index.year >= 1990)

    # Aehnliche Lagen: CAPE innerhalb +-10 % von heute, Ergebnis nach 10 Jahren bekannt
    aehnlich = np.flatnonzero(ok & (np.abs(cape / jetzt - 1) <= AEHNLICH) & ~np.isnan(f10))
    phasen = [{"von": df.index[a].strftime("%Y-%m"), "bis": df.index[b].strftime("%Y-%m")} for a, b in _phasen(aehnlich)]
    hoeher = np.flatnonzero(ok & (cape >= jetzt) & ~np.isnan(f10))

    zonen = []
    for name, lo, hi in ZONEN:
        m = (score >= lo) & (score < hi) & ~np.isnan(f10)
        zonen.append({"zone": name, "n": int(m.sum()), **({"r10": _spanne(f10[m])} if m.any() else {}),
                      **({"r1": _spanne(f1[m & ~np.isnan(f1)])} if m.any() else {})})

    logc = np.log(cape)
    wf = {"10": walk_forward(logc, f10, 120, df.index), "1": walk_forward(logc, f1, 12, df.index)}
    for v in wf.values():
        if v:
            v.pop("_fehler", None)
    # Erwartete Rendite der naechsten 10 Jahre aus drei Bewertungskennzahlen (jede ehrlich geprueft)
    bu = buffett_monatlich(df.index)
    modelle = [erwartung("Shiller-CAPE", cape, f10, f1, df.index, log=True),
               erwartung("Excess CAPE Yield", df["ecy"].values.astype(float) * 100, f10, f1, df.index, log=False)]
    if bu is not None:
        modelle.append(erwartung("Buffett-Indikator", bu.values.astype(float), f10, f1, df.index, log=True))
    gueltig_s = ~np.isnan(score)
    t = [int(x) for x in (df.index[ok] - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)]
    ecy = df["ecy"].values.astype(float)
    return {
        "stand": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "quelle": "Robert J. Shiller, shillerdata.com (ie_data.xls), S&P 500 monatlich ab 1871",
        "datum": df.index[i].strftime("%Y-%m"),
        "cape": round(jetzt, 1), "score": round(s_jetzt, 0), "stufe": stufe(s_jetzt),
        "median": round(float(np.median(cape[ok])), 1), "median_ab1990": round(float(np.median(cape[seit1990])), 1),
        "perzentil": round(float((cape[ok] < jetzt).mean()) * 100, 0),
        "perzentil_ab1990": round(float((cape[seit1990] < jetzt).mean()) * 100, 0),
        "hoechst": {"wert": round(float(np.nanmax(cape)), 1), "datum": df.index[int(np.nanargmax(cape))].strftime("%Y-%m")},
        "ecy": None if math.isnan(ecy[i]) else round(float(ecy[i]) * 100, 2),
        "max_score_ab1990": None if not (gueltig_s & (df.index.year >= 1990)).any() else round(float(np.nanmax(score[df.index.year >= 1990])), 0),
        "score_vor12m": None if i < 12 or math.isnan(score[i - 12]) else round(float(score[i - 12]), 0),
        "aehnlich": {"spanne": AEHNLICH * 100, "r10": _spanne(f10[aehnlich]), "phasen": phasen,
                     "letzte_bekannt": df.index[int(np.flatnonzero(~np.isnan(f10))[-1])].strftime("%Y-%m")},
        "hoeher": {"r10": _spanne(f10[hoeher]), "phasen": [{"von": df.index[a].strftime("%Y-%m"), "bis": df.index[b].strftime("%Y-%m")} for a, b in _phasen(hoeher)]},
        "basis": {"r10": _spanne(f10[~np.isnan(f10) & ok]), "r1": _spanne(f1[~np.isnan(f1) & ok])},
        "zonen": zonen,
        "walk_forward": wf,
        "erwartung": [m for m in modelle if m],
        "strategie": [x for x in (strategie(df, score, zins, s) for s in (60, 80)) if x],
        "reihe": {"t": t, "cape": [round(float(v), 2) for v in cape[ok]],
                  "score": [None if math.isnan(v) else round(float(v), 1) for v in score[ok]]},
        "score_ab": df.index[int(np.flatnonzero(gueltig_s)[0])].strftime("%Y-%m"),
    }


def schreiben(daten: dict):
    E.WEB_DATEN.mkdir(parents=True, exist_ok=True)
    tmp = E.WEB_DATEN / "bewertung.tmp"
    tmp.write_text(json.dumps(daten, separators=(",", ":"), ensure_ascii=False))
    tmp.replace(E.WEB_DATEN / "bewertung.json")


def main():
    if not laden():
        print("Shiller-Daten nicht verfügbar – Bewertung übersprungen.")
        return 0
    import umfeld
    d = auswerten(reihe(), umfeld.zins_monatlich())
    schreiben(d)
    w10 = (d["walk_forward"]["10"] or {}).get("alle") or {}
    print(f"Bewertung: CAPE {d['cape']} ({d['datum']}), Bewertung {d['score']:.0f} = {d['stufe']}; "
          f"Walk-forward 10 J.: R² {w10.get('r2')} %")
    return 0


if __name__ == "__main__":
    sys.exit(main())   # Netzfehler sollen den Tageslauf nicht stoppen
