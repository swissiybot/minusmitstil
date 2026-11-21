"""Statischer Export fuer die Online-Seite (GitHub Pages). Laeuft NUR im GitHub-Lauf.

Ergebnis ist der Ordner site/ (index.html, lib/, daten/) – nur dieser wird veroeffentlicht;
web/daten bleibt unveraendert (lokale Fassung).

Schalter KURSE_OEFFENTLICH (unten):
  True  = Variante a (Entscheidung Marc, 21.11.2026 abends): die Online-Seite zeigt den eigenen Chart
          mit Kursen wie lokal (Pfeile, 200-Wochen-Linie, Pi Cycle, Prognose-Kegel). Kurse: Yahoo Finance.
  False = reduzierter Modus (Variante b), wie folgt beschrieben:

Reduzierter, oeffentlicher Modus (frueher Entscheidung Marc: Variante b): Die Online-Seite enthaelt KEINE
Kursreihen und keine Einzelkurse aus Yahoo, nur eigene Ergebnisse:
  - je Wert web/daten/werte/<id>.json: Kennzahlen (ohne Kurs), Ampel-Verlauf, Markierungen,
    Pi-Cycle-Zonen (nur Ja/Nein je Woche), Walk-forward-Pruefung, Strategie-Vergleich (Standardwerte),
    Monte-Carlo-Ergebnisse als Verhaeltnisse zum heutigen Kurs (Kegel und Verteilungen in Prozent)
  - rangliste.json und umfeld.json werden ueberschrieben: ohne Kurse, VIX nur als Stufe und Perzentil
  - statisch.json: Datenstand und Download-Ergebnis
Den Kurs-Chart zeigt online das TradingView-Widget (Kurse von TradingView, nicht von uns).
Am Ende prueft das Skript alle Dateien und bricht ab, falls doch Kursfelder enthalten sind.
Lokal nicht noetig (der lokale Server zeigt alles voll); die Dateien sind in .gitignore.
"""
import json
import re
import shutil
import sys
import time
import datetime as dt
import numpy as np
import pandas as pd

import einstellungen as E
import analyse
import montecarlo
import pruefung
import strategie
import umfeld
from kurse import alle_laden

# Felder, die Kurse oder Kursreihen enthalten und deshalb nie veroeffentlicht werden
KURSE_OEFFENTLICH = True
VERBOTEN = set() if KURSE_OEFFENTLICH else {"o", "h", "l", "c", "kurs", "sma200w", "trend", "trend_o", "trend_u", "pi_ema150", "pi_sma471",
            "preis", "pfad", "p0", "ende_median", "reihe_kurs"}
STUFEN = np.linspace(0, 100, 101)   # Perzentile fuer die Monte-Carlo-Verteilungen


def dateiname(wid: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", wid)   # im Dashboard gleich umgesetzt


def ohne_kurs(info: dict) -> dict:
    if KURSE_OEFFENTLICH:
        return info
    info = {k: v for k, v in info.items() if k != "kurs"}
    if info.get("pi_rueckblick"):
        info["pi_rueckblick"] = [{k: v for k, v in x.items() if k != "kurs"} for x in info["pi_rueckblick"]]
    return info


def mc_relativ(w, wid: str) -> dict:
    """Monte Carlo als Verhaeltnisse zum heutigen Kurs (1 = heute). Daraus rechnet die Seite
    Wahrscheinlichkeiten fuer beliebige Abstaende in Prozent, ohne einen Kurs zu kennen."""
    sim = montecarlo.simulation(w, seed_text=wid)
    if sim is None:
        return {"fehler": "zu wenig Kursdaten (mind. 2 Jahre)"}
    p0 = sim["p0"]
    q = np.percentile(sim["pfad"] / p0, montecarlo.QUANTILE, axis=0)
    rnd = lambda a: [round(float(x), 4) for x in a]
    t0 = sim["letzte"]
    return {
        "wochen": sim["wochen"], "pfade": sim["pfade"], "block": sim["block"],
        "hist_von": sim["von"].strftime("%Y-%m-%d"), "hist_jahre": sim["jahre_hist"],
        "t": [int((t0 + pd.Timedelta(weeks=k) - pd.Timestamp("1970-01-01")).total_seconds()) for k in range(sim["wochen"] + 1)],
        "kegel": {f"q{p}": [1.0] + rnd(q[i]) for i, p in enumerate(montecarlo.QUANTILE)},
        "tief": rnd(np.percentile(sim["tief"] / p0, STUFEN)),
        "hoch": rnd(np.percentile(sim["hoch"] / p0, STUFEN)),
        "ende": rnd(np.percentile(sim["pfad"][:, -1] / p0, STUFEN)),
    }


def pruefe(obj, pfad="") -> list[str]:
    """Findet verbotene Kursfelder in einer JSON-Struktur."""
    funde = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in VERBOTEN:
                funde.append(f"{pfad}.{k}")
            funde += pruefe(v, f"{pfad}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            funde += pruefe(v, f"{pfad}[{i}]")
    return funde


def schreiben(datei, obj):
    funde = pruefe(obj)
    if funde:
        raise RuntimeError(f"Kursfelder in {datei.name}: {funde[:5]}")
    text = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    datei.write_text(text)
    return len(text)


SITE = E.BASIS / "site"


def main():
    t0 = time.time()
    alle_laden()
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "daten").mkdir(parents=True)
    shutil.copy(E.WEB / "index.html", SITE / "index.html")
    shutil.copytree(E.WEB / "lib", SITE / "lib")
    for name in ("pruefung.json", "tagebuch_pruefung.json", "bewertung.json"):
        if (E.WEB_DATEN / name).exists():
            schreiben(SITE / "daten" / name, json.loads((E.WEB_DATEN / name).read_text()))
    rl = json.loads((E.WEB_DATEN / "rangliste.json").read_text())
    ids = {w["id"] for w in rl["werte"]}
    tmp = SITE / "daten" / "werte"
    tmp.mkdir()
    tage_ordner = SITE / "daten" / "tage"
    tage_ordner.mkdir()
    zins = umfeld.zins_monatlich()
    n = fehler = groesse = 0
    for z in analyse.universum().to_dict("records"):
        if z["id"] not in ids:
            continue
        try:
            erg = analyse.werte_eines(z)
            if erg is None:
                continue
            info, chart, roh = erg
            w, score = roh["w"], roh["score"]
            out = {
                "info": ohne_kurs(info) | {"tv": E.tv_symbol(z["id"], z["symbol"], z["gruppe"])},
                "chart": chart if KURSE_OEFFENTLICH else {"t": chart["t"], "score": chart["score"], "marken": chart["marken"],
                          **({"pi_zone": chart["pi_zone"]} if "pi_zone" in chart else {})},
                "mc": mc_relativ(w, z["id"]),
            }
            if info["score"] is not None:
                out["pruefung"] = pruefung.fuer_wert(w["Close"].values.astype(float), score, w.index.year.values)
                out["strategie"] = strategie.vergleich(w, score, zins) or {"fehler": "zu wenig Monate mit gültiger Ampel"}
            groesse += schreiben(tmp / f"{dateiname(z['id'])}.json", out)
            if KURSE_OEFFENTLICH and z["gruppe"] in ("ETF", "Krypto", "Rohstoffe"):
                tc = analyse.tageschart(info, chart, roh)
                if tc:
                    groesse += schreiben(tage_ordner / f"{dateiname(z['id'])}.json", tc)
            n += 1
        except Exception as ex:
            fehler += 1
            print(f"Export-Fehler bei {z['symbol']}: {ex.__class__.__name__}: {ex}", file=sys.stderr)
    ziel = tmp

    # Rangliste und Marktumfeld fuer die Online-Seite ohne Kurse ueberschreiben
    kurse_bis = max((w["datum"] for w in rl["werte"] if w.get("gruppe") != "Krypto"), default=None)
    rl["werte"] = [ohne_kurs(w) for w in rl["werte"]]
    schreiben(SITE / "daten" / "rangliste.json", rl)
    uf = E.WEB_DATEN / "umfeld.json"
    if uf.exists():
        u = json.loads(uf.read_text())
        if "vix" in u and not KURSE_OEFFENTLICH:
            v = u["vix"]
            stufe = "ruhig" if v["wert"] < 15 else "normal" if v["wert"] < 25 else "nervös" if v["wert"] < 35 else "Panik"
            u["vix"] = {"datum": v["datum"], "perzentil": v["perzentil"], "stufe": stufe,
                        "quelle": "Cboe VIX, online nur als Stufe und Perzentil"}
        schreiben(SITE / "daten" / "umfeld.json", u)

    lauf = {}
    f = E.DATEN / "kurse_lauf.json"
    if f.exists():
        lauf = json.loads(f.read_text())
    schreiben(SITE / "daten" / "statisch.json", {
        "erstellt": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "zeitzone": time.strftime("%Z"),
        "kurse_bis": kurse_bis, "werte": n, "export_fehler": fehler, "kurse_lauf": lauf,
    })

    # Schlusskontrolle: alle veroeffentlichten Dateien noch einmal komplett durchsuchen
    funde = []
    for d in [*(SITE / "daten").glob("*.json"), *ziel.glob("*.json")]:
        funde += [f"{d.name}{x}" for x in pruefe(json.loads(d.read_text()))]
    if funde:
        raise SystemExit(f"ABBRUCH: Kursfelder in den Online-Dateien gefunden: {funde[:10]}")
    print(f"Export: {n} Werte, {groesse / 1e6:.0f} MB, {fehler} Fehler, {time.time() - t0:.0f} s – " + ("mit Kursen (Variante a)" if KURSE_OEFFENTLICH else "geprüft: keine Kursfelder"))
    if lauf:
        print(f"Kursdownload: {lauf.get('geladen')} von {lauf.get('gesamt')} geladen, {lauf.get('ohne_daten')} ohne Daten"
              + (" – ABGEBROCHEN (alter Stand)" if lauf.get("abgebrochen") else ""))


if __name__ == "__main__":
    main()
