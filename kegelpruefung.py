"""Pruefung des Prognose-Kegels: Trifft er so oft, wie er verspricht?

Fuer viele Werte und viele vergangene Stichtage (alle 13 Wochen) wird der Kegel nur mit den Kursen bis zum
Stichtag gerechnet. Dann wird nachgesehen, wo der Kurs 13 bzw. 52 Wochen spaeter tatsaechlich lag.
Ein guter Kegel trifft das 90-%-Band in etwa 90 % und das 50-%-Band in etwa 50 % der Faelle.
Weniger heisst: zu schmal (zu selbstsicher), mehr heisst: zu breit.

Verglichen werden Varianten von montecarlo.simulation (Historie, Schwankung von heute, vorsichtigere Grundrendite).
Gewinner = kleinster Abstand zu 90 % und 50 % (Mittel ueber die Gruppen); nur bei praktisch gleichem Abstand (< 0,25) das schmalere Band.

Aufruf: python kegelpruefung.py  -> daten/kegelpruefung.json und web/daten/kegelpruefung.json
"""
import json
import datetime as dt
import numpy as np
import pandas as pd

import einstellungen as E
import analyse
import montecarlo
from kurse import alle_laden
from trendstudie import wochen_von

VARIANTEN = {
    "heute (20 Jahre)": {"jahre": 20, "vol_tau": None, "drift": 1.0},
    "Schwankung von heute (abklingend 26 W.)": {"jahre": 20, "vol_tau": 26, "drift": 1.0},
    "Schwankung von heute (abklingend 13 W.)": {"jahre": 20, "vol_tau": 13, "drift": 1.0},
    "ganze Historie": {"jahre": 100, "vol_tau": None, "drift": 1.0},
    "ganze Historie + Schwankung von heute": {"jahre": 100, "vol_tau": 26, "drift": 1.0},
    "vorsichtigere Grundrendite (50 %)": {"jahre": 20, "vol_tau": None, "drift": 0.5},
    "Schwankung von heute + vorsichtigere Grundrendite": {"jahre": 20, "vol_tau": 26, "drift": 0.5},
}
HORIZONTE = (13, 52)
PFADE = 2000
SCHRITT = 13
AKTIEN_N = 40


def werte():
    uni = analyse.universum().to_dict("records")
    n100 = {}
    try:
        import nasdaq100
        n100 = nasdaq100.mitglieder()
    except Exception:
        pass
    gruppen = {"etf": [], "krypto": [], "rohstoffe": [], "aktien": []}
    for z in uni:
        if z["gruppe"] == "ETF" and z.get("branche", "Index") in ("Index", "", None):
            gruppen["etf"].append(z)
        elif z["gruppe"] == "Krypto":
            gruppen["krypto"].append(z)
        elif z["gruppe"] == "Rohstoffe":
            gruppen["rohstoffe"].append(z)
        elif z["symbol"] in n100:
            gruppen["aktien"].append(z)
    gruppen["aktien"] = sorted(gruppen["aktien"], key=lambda z: z["symbol"])[:AKTIEN_N * 2]
    return gruppen


def main():
    import sys, shutil, time
    alt = E.DATEN / "kegelpruefung.json"
    if "--wenn-alt" in sys.argv and alt.exists() and time.time() - alt.stat().st_mtime < 7 * 86400:
        E.WEB_DATEN.mkdir(parents=True, exist_ok=True)
        shutil.copy(alt, E.WEB_DATEN / "kegelpruefung.json")   # Ergebnis aendert sich langsam: hoechstens einmal pro Woche neu rechnen
        print("Kegel-Prüfung: Ergebnis jünger als 7 Tage, nicht neu gerechnet")
        return
    alle_laden()
    gruppen = werte()
    erg = {v: {g: {h: [] for h in HORIZONTE} for g in gruppen} for v in VARIANTEN}   # Liste (pit, breite90)
    anzahl = {g: 0 for g in gruppen}
    for g, liste in gruppen.items():
        for z in liste:
            if g == "aktien" and anzahl[g] >= AKTIEN_N:
                break
            w = wochen_von(z)
            if w is None or len(w) < 156 + 52 + SCHRITT:
                continue
            ab = None
            if z["id"] == E.BITCOIN["id"]:
                from kurse import lade_lokal
                y = lade_lokal(z["symbol"])
                ab = y.index[0] if y is not None and not y.empty else None
            c = w["Close"].values.astype(float)
            start = 156 if ab is None else max(156, int(w.index.searchsorted(ab)) + 104)
            for i in range(start, len(w) - 52, SCHRITT):
                teil = w.iloc[:i + 1]
                for v, kw in VARIANTEN.items():
                    sim = montecarlo.simulation(teil, wochen=52, pfade=PFADE, seed_text=f"{z['id']}|{i}", ab=ab, **kw)
                    if sim is None:
                        continue
                    p0 = sim["p0"]
                    for h in HORIZONTE:
                        ende = sim["pfad"][:, h - 1] / p0
                        wahr = c[i + h] / c[i]
                        pit = float((ende < wahr).mean())
                        q5, q95 = np.percentile(ende, [5, 95])
                        erg[v][g][h].append((pit, float(np.log(q95 / q5))))
            anzahl[g] += 1
            print(f"  {g}: {z['id']} fertig", flush=True)

    def kennz(liste):
        if not liste:
            return None
        a = np.array(liste)
        pit = a[:, 0]
        return {"n": int(len(a)), "in90": round(float(((pit >= 0.05) & (pit <= 0.95)).mean()) * 100, 1),
                "in50": round(float(((pit >= 0.25) & (pit <= 0.75)).mean()) * 100, 1),
                "unter": round(float((pit < 0.05).mean()) * 100, 1), "ueber": round(float((pit > 0.95).mean()) * 100, 1),
                "breite90": round(float(np.median(np.exp(a[:, 1]) - 1)) * 100, 0)}
    tabelle = []
    for v in VARIANTEN:
        zeile = {"name": v, "einst": VARIANTEN[v], "gruppen": {}}
        fehler = []
        for g in gruppen:
            zeile["gruppen"][g] = {str(h): kennz(erg[v][g][h]) for h in HORIZONTE}
            for h in HORIZONTE:
                k = zeile["gruppen"][g][str(h)]
                if k:
                    fehler.append(abs(k["in90"] - 90) + abs(k["in50"] - 50))
        zeile["abstand"] = round(float(np.mean(fehler)), 2) if fehler else None
        tabelle.append(zeile)
    gueltig = [t for t in tabelle if t["abstand"] is not None]
    bester = min(gueltig, key=lambda t: t["abstand"])
    # praktisch gleich gut (unter 0,25 Punkten Unterschied): das schmalere Band gewinnt
    nah = [t for t in gueltig if t["abstand"] - bester["abstand"] < 0.25]
    breite = lambda t: np.mean([t["gruppen"][g]["52"]["breite90"] for g in t["gruppen"] if t["gruppen"][g]["52"]])
    sieger = min(nah, key=breite)
    out = {"stand": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "werte": anzahl, "schritt_wochen": SCHRITT, "pfade": PFADE,
           "varianten": tabelle, "sieger": sieger["name"], "sieger_einst": sieger["einst"]}
    for ziel in (E.DATEN / "kegelpruefung.json", E.WEB_DATEN / "kegelpruefung.json"):
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("Sieger:", sieger["name"], sieger["abstand"])
    for t in tabelle:
        print(f"{t['abstand']:6} {t['name']}")


if __name__ == "__main__":
    main()
