"""Nachpruefung des Signal-Tagebuchs (daten/tagebuch/) nach 1, 3 und 5 Jahren.

Die Tagebuch-Dateien werden NUR GELESEN, nie geaendert.
Fuer jedes Signal, dessen Horizont abgelaufen ist, wird geprueft, ob der Kurs danach hoeher stand.
Gerechnet wird mit der heutigen bereinigten Kursreihe (Kurs am Faelligkeitstag / Kurs am Signaltag),
weil bereinigte Kurse sich bei spaeteren Dividenden und Splits rueckwirkend aendern; der im Tagebuch
notierte Kurs dient nur zur Kontrolle.
Ergebnis: web/daten/tagebuch_pruefung.json (Trefferquote je Ampel-Zone, Vergleich mit der damals
angezeigten Wahrscheinlichkeit). Laeuft taeglich mit; solange nichts faellig ist, zeigt es die Termine.
"""
import json
import datetime as dt
import numpy as np
import pandas as pd

import einstellungen as E

ORDNER = E.DATEN / "tagebuch"
JAHRE = (1, 3, 5)
ZONEN = ["historisch sehr guenstig", "guenstig", "neutral", "teuer", "historisch sehr teuer"]


def eintraege() -> list[dict]:
    zeilen = []
    for f in sorted(ORDNER.glob("*.json")):
        with open(f, "r", encoding="utf-8") as fh:       # nur lesen
            d = json.load(fh)
        for s in d.get("signale", []):
            if s.get("datum") and s.get("kurs") is not None:
                zeilen.append({**s, "datei": f.stem})
    return zeilen


def kursreihe(zid: str, symbol: str, gruppe: dict):
    import analyse
    if zid in gruppe:  # ETF mit Index-Vorlauf
        tag, _ = analyse.verketten(gruppe[zid])
    else:
        from kurse import lade_lokal
        tag = lade_lokal(symbol)
    return None if tag is None or tag.empty else tag["Close"]


def main():
    zeilen = eintraege()
    out = {"stand": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "tage": 0, "signale": len(zeilen)}
    if not zeilen:
        out["hinweis"] = "Noch keine Tagebuch-Eintraege."
    else:
        tage = sorted({z["datei"] for z in zeilen})
        erstes = pd.Timestamp(min(z["datum"] for z in zeilen))
        out.update(tage=len(tage), erster_tag=tage[0], letzter_tag=tage[-1],
                   werte=len({z["id"] for z in zeilen}),
                   faellig_ab={str(j): (erstes + pd.DateOffset(years=j)).strftime("%Y-%m-%d") for j in JAHRE})
        etfs = {e["id"]: e for e in E.ETFS}
        reihen: dict = {}
        heute = pd.Timestamp(dt.date.today())
        erg = {}
        for j in JAHRE:
            faellig = [z for z in zeilen if pd.Timestamp(z["datum"]) + pd.DateOffset(years=j) <= heute]
            res = []
            for z in faellig:
                if z["id"] not in reihen:
                    reihen[z["id"]] = kursreihe(z["id"], z["symbol"], etfs)
                s = reihen[z["id"]]
                if s is None:
                    continue
                t0 = pd.Timestamp(z["datum"]); t1 = t0 + pd.DateOffset(years=j)
                if s.index[-1] < t1 or s.index[0] > t0:
                    continue
                r = float(s.asof(t1) / s.asof(t0) - 1)
                p = z.get(f"p{j}")
                res.append({"zone": z.get("zone"), "r": r, "p": p, "id": z["id"]})
            if not res:
                erg[str(j)] = {"faellig": len(faellig), "geprueft": 0}
                continue
            df = pd.DataFrame(res)
            zonen = []
            for zn in ZONEN:
                t = df[df["zone"] == zn]
                if len(t):
                    zonen.append({"zone": zn, "signale": len(t), "werte": int(t["id"].nunique()),
                                  "quote": round(float((t["r"] > 0).mean()) * 100, 1),
                                  "median": round(float(t["r"].median()) * 100, 1)})
            kal = []
            mit_p = df.dropna(subset=["p"])
            if len(mit_p):
                b = np.minimum((mit_p["p"] // 10).astype(int), 9)
                for k, t in mit_p.groupby(b):
                    kal.append({"von": int(k) * 10, "bis": int(k) * 10 + 10, "n": len(t),
                                "angezeigt": round(float(t["p"].mean()), 1), "eingetreten": round(float((t["r"] > 0).mean()) * 100, 1)})
            erg[str(j)] = {"faellig": len(faellig), "geprueft": len(df), "werte": int(df["id"].nunique()),
                           "quote": round(float((df["r"] > 0).mean()) * 100, 1), "zonen": zonen, "kalibrierung": kal}
        out["ergebnisse"] = erg
    tmp = E.WEB_DATEN / "tagebuch_pruefung.tmp"
    tmp.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(E.WEB_DATEN / "tagebuch_pruefung.json")
    gepr = sum((v or {}).get("geprueft", 0) for v in out.get("ergebnisse", {}).values())
    print(f"Tagebuch: {out['tage']} Tage, {out['signale']} Signale, davon nachgeprueft: {gepr}")


if __name__ == "__main__":
    main()
