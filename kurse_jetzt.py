"""Schlanker Kurs-Abruf zwischen den vollen Laeufen (Wunsch Marc 25.11.2026: „viel öfter Kurse, alle 15 oder 30 min“).

Holt fuer ALLE Werte der veroeffentlichten Rangliste den aktuellen Kurs von Yahoo – in wenigen Sammelabrufen
(je 250 Kuerzel eine Anfrage, rund 30 Anfragen fuer 7.000 Werte) statt Kursreihen je Wert. Dazu fuer eine Auswahl
(AUSWAHL_HEUTE) den feinen Verlauf der letzten Handelstage in 15-Minuten-Kerzen.

Arbeitet NUR auf einem fertigen Seiten-Ordner (site/ bzw. das heruntergeladene Paket), nicht auf dem Zwischenspeicher
des vollen Laufs:
  liest   <site>/daten/rangliste.json, statisch.json, werte/<id>.json
  schreibt <site>/daten/kurse_jetzt.json und <site>/daten/heute/<id>.json

Was die Datei je Wert enthaelt (Reihenfolge = FELDER): Kurs, Eroeffnung/Hoch/Tief des Tages, Schlusskurs des Vortags,
Zeitpunkt des Kurses, und – nur wenn sich der Kurs gegenueber der Auswertung geaendert hat – die Ampel, der Abstand zur
200-Wochen-Linie, die Raenge und der Abstand zum Allzeithoch, NEU GERECHNET MIT DERSELBEN FUNKTION wie im vollen Lauf
(analyse.ampel_rechnen) auf den Wochenschlusskursen der Seite, in denen die laufende Woche durch den frischen Kurs
ersetzt ist. Die Ampel-Logik wird hier nicht nachgebaut und nicht veraendert. Einzige Ungenauigkeit: Die Wochenkurse
der Seite sind auf 4 Stellen gerundet (gemessen an 5.610 Werten: im Mittel 0,03 Ampel-Punkte, 91 % exakt gleich).

Grundsaetze: nie Kurse erfinden. Liefert Yahoo fuer ein Kuerzel nichts, bleibt der Eintrag des vorigen Abrufs stehen
(mit seiner alten Uhrzeit) oder er fehlt. Kurse, die aelter sind als die Auswertung, und unplausible Spruenge
(Faktor > 4, meist andere Waehrungseinheit) werden weggelassen. Sperrt Yahoo, wird mit dem Erreichten weitergearbeitet;
kommt gar nichts, bleibt die vorhandene Datei unveraendert.

Aufruf:  python kurse_jetzt.py --site site            (alles)
         python kurse_jetzt.py --site site --ohne-heute
Rueckgabe: 0 = Datei geschrieben · 2 = kein einziger Kurs, keine Datei · 3 = nichts Neues, alte Datei bleibt
"""
import argparse
import datetime as dt
import json
import math
import re
import sys
import time
from pathlib import Path

import numpy as np

FELDER = ["k", "o", "h", "l", "v", "t", "off", "a", "z", "ru", "rn", "dd", "li"]
STAPEL = 250            # Kuerzel je Sammelabruf
PAUSE = 0.35            # Sekunden zwischen den Abrufen (Drosselung)
SPERRE_NACH = 2         # so viele gescheiterte Stapel in Folge = Yahoo sperrt, aufhoeren
SPRUNG = 4.0            # Kurs / Kurs der Auswertung ausserhalb 1/4 … 4: weglassen
HEUTE_TAGE = "5d"       # feiner Verlauf: so weit zurueck
HEUTE_SCHRITT = "15m"
HEUTE_STAPEL = 40
URL = "https://query1.finance.yahoo.com/v7/finance/quote"
YF_FELDER = "regularMarketPrice,regularMarketOpen,regularMarketDayHigh,regularMarketDayLow,regularMarketPreviousClose,regularMarketTime,gmtOffSetMilliseconds"


def auswahl_heute(w: dict) -> bool:
    """AUSWAHL fuer den feinen Tagesverlauf – nur hier aendern. Marcs gemerkte Werte kennt der Server nicht (sie liegen
    nur in seinem Browser); darum die Werte der Uebersicht: alle ETFs samt Hebel-Produkten, Rohstoffe, die fuenf Krypto-Kernwerte."""
    import einstellungen as E
    return w.get("gruppe") in ("ETF", "Rohstoffe") or w.get("id") in E.KRYPTO_KERN_IDS or bool(w.get("hebel"))


def dateiname(wid: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", wid)   # wie export.py


def rund(x, stellen=4):
    """Kurs runden wie die Rangliste (4 Nachkommastellen); sehr kleine Kurse behalten 6 gueltige Stellen."""
    if x is None or not isinstance(x, (int, float)) or math.isnan(x) or math.isinf(x):
        return None
    return round(float(x), stellen) if abs(x) >= 1 else float(f"{x:.6g}")


def hole_kurse(symbole: list[str]) -> tuple[dict, bool]:
    """Sammelabruf. Rueckgabe: {symbol: rohe Yahoo-Antwort}, gesperrt (True = vorzeitig aufgehoert)."""
    from yfinance.data import YfData
    yd = YfData()
    out, fehl_in_folge = {}, 0
    for i in range(0, len(symbole), STAPEL):
        stapel = symbole[i:i + STAPEL]
        ok = False
        for versuch, warte in enumerate((0, 4, 12)):
            if warte:
                time.sleep(warte)
            try:
                r = yd.get(URL, params={"symbols": ",".join(stapel), "fields": YF_FELDER}, timeout=20)
                if r.status_code == 200:
                    for q in r.json()["quoteResponse"]["result"]:
                        out[q["symbol"]] = q
                    ok = True
                    break
                print(f"  Stapel {i // STAPEL + 1}: Antwort {r.status_code} (Versuch {versuch + 1})", flush=True)
            except Exception as ex:   # Sperre, Netzfehler, unlesbare Antwort
                print(f"  Stapel {i // STAPEL + 1}: {ex.__class__.__name__}: {str(ex)[:120]} (Versuch {versuch + 1})", flush=True)
        fehl_in_folge = 0 if ok else fehl_in_folge + 1
        if fehl_in_folge >= SPERRE_NACH:
            print(f"ABBRUCH des Abrufs nach {i + len(stapel)} von {len(symbole)} Kuerzeln: Yahoo antwortet nicht (Sperre?). Weiter mit dem Erreichten.", flush=True)
            return out, True
        time.sleep(PAUSE)
    return out, False


def freitag(d: dt.date) -> dt.date:
    """Wochenkerzen heissen nach dem Freitag ihrer Woche (analyse.wochen: W-FRI)."""
    return d + dt.timedelta(days=(4 - d.weekday()) % 7)


def eintrag(w: dict, q: dict, jetzt: float) -> tuple[list | None, str]:
    """Aus einer Yahoo-Antwort ein Eintrag [k,o,h,l,v,t,off] – oder None mit Grund."""
    k, t = q.get("regularMarketPrice"), q.get("regularMarketTime")
    if not isinstance(k, (int, float)) or not isinstance(t, (int, float)) or not k > 0 or t > jetzt + 3600:
        return None, "ohne Kurs"
    off = int((q.get("gmtOffSetMilliseconds") or 0) / 1000)
    tag = dt.datetime.fromtimestamp(t + off, dt.timezone.utc).date().isoformat()
    if w.get("datum") and tag < w["datum"]:
        return None, "aelter als die Auswertung"
    alt = w.get("kurs")
    if alt and alt > 0 and not (1 / SPRUNG < k / alt < SPRUNG):
        return None, "unplausibler Sprung"
    o, h, l, v = (q.get(f) for f in ("regularMarketOpen", "regularMarketDayHigh", "regularMarketDayLow", "regularMarketPreviousClose"))
    ok = lambda x: x if isinstance(x, (int, float)) and x > 0 else None
    o, h, l, v = ok(o), ok(h), ok(l), ok(v)
    if h is not None and l is not None and not (l <= k <= h):   # Tageswerte passen nicht zum Kurs: lieber weglassen als raten
        o = h = l = None
    return [rund(k), rund(o), rund(h), rund(l), rund(v), int(t), off], ""


def lage_rechnen(site: Path, w: dict, e: list) -> list:
    """Ampel & Co. aus dem frischen Kurs – mit der Funktion des vollen Laufs. Rueckgabe [a, z, ru, rn, dd, li] (None = bleibt wie in der Auswertung)."""
    import analyse
    leer = [None] * 6
    k = e[0]
    if w.get("kurs") is not None and abs(k - w["kurs"]) <= 1e-9 * max(1.0, abs(k)):
        return leer   # Kurs unveraendert: die Werte der Auswertung gelten weiter
    try:
        ch = json.loads((site / "daten" / "werte" / f"{dateiname(w['id'])}.json").read_text())["chart"]
        c, t = np.array(ch["c"], dtype=float), ch["t"]
    except Exception:
        return leer
    if len(c) < 2 or np.isnan(c).any() or not w.get("kurs") or abs(c[-1] / w["kurs"] - 1) > 2e-3:
        return leer   # Wochenreihe passt nicht zum Kurs der Rangliste (gerundet auf 4 Stellen: bis 0,05 %)
    letzte = dt.datetime.fromtimestamp(t[-1], dt.timezone.utc).date()
    woche = freitag(dt.datetime.fromtimestamp(e[5] + e[6], dt.timezone.utc).date())
    if woche < letzte:
        return leer
    c2 = np.append(c, k) if woche > letzte else np.append(c[:-1], k)   # neue Woche begonnen: neue Kerze, sonst laufende Woche ersetzen
    _, score, _, ru, rn = analyse.ampel_rechnen(c2)
    r = analyse.r
    linie = float(np.mean(c2[-200:])) if len(c2) >= 200 else None
    a = r(score[-1], 1)
    if w.get("score") is not None and a is None:
        return leer
    return [a, r((k / linie - 1) * 100, 1) if linie else None, r(ru[-1] * 100, 0), r(rn[-1] * 100, 0),
            r((k / float(np.max(c2)) - 1) * 100, 1), r(linie, 4) if linie else None]


def heute_laden(site: Path, werte: list[dict], stand: str) -> tuple[int, int]:
    """15-Minuten-Kerzen der letzten Handelstage fuer die Auswahl. Schreibt nur, was Yahoo wirklich liefert."""
    import pandas as pd
    import yfinance as yf
    ordner = site / "daten" / "heute"
    ordner.mkdir(parents=True, exist_ok=True)
    geschrieben = 0
    sig = lambda a: [float(f"{x:.6g}") for x in a]
    for i in range(0, len(werte), HEUTE_STAPEL):
        teil = werte[i:i + HEUTE_STAPEL]
        try:
            df = yf.download([w["symbol"] for w in teil], period=HEUTE_TAGE, interval=HEUTE_SCHRITT, auto_adjust=False,
                             group_by="ticker", threads=True, progress=False)
        except Exception as ex:
            print(f"  Tagesverlauf Stapel {i // HEUTE_STAPEL + 1}: {ex.__class__.__name__}: {str(ex)[:120]}", flush=True)
            time.sleep(5)
            continue
        for w in teil:
            try:
                d = (df[w["symbol"]] if isinstance(df.columns, pd.MultiIndex) else df)[["Open", "High", "Low", "Close"]].dropna()
                d = d[(d > 0).all(axis=1)]
                if len(d) < 2:
                    continue
                idx = d.index
                off = int(idx[-1].utcoffset().total_seconds()) if idx.tz is not None else 0
                t = [int(x.timestamp()) for x in idx]
                out = {"stand": stand, "schritt_min": 15, "off": off, "t": t,
                       "o": sig(d["Open"].values), "h": sig(d["High"].values), "l": sig(d["Low"].values), "c": sig(d["Close"].values)}
                ziel = ordner / f"{dateiname(w['id'])}.json"
                tmp = ziel.with_suffix(".tmp")
                tmp.write_text(json.dumps(out, separators=(",", ":")))
                tmp.replace(ziel)
                geschrieben += 1
            except Exception:
                continue
        time.sleep(1.0)
    return geschrieben, len(werte)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="site", help="Seiten-Ordner mit daten/rangliste.json")
    ap.add_argument("--ohne-heute", action="store_true", help="feinen Tagesverlauf auslassen")
    ap.add_argument("--nur", type=int, default=0, help="nur die ersten N Werte (zum Probieren)")
    arg = ap.parse_args(argv)
    site = Path(arg.site)
    t0 = time.time()
    rl = json.loads((site / "daten" / "rangliste.json").read_text())["werte"]
    if arg.nur:
        rl = rl[:arg.nur]
    basis = json.loads((site / "daten" / "statisch.json").read_text()).get("erstellt")
    ziel = site / "daten" / "kurse_jetzt.json"
    alt = {}
    try:
        alt = json.loads(ziel.read_text())
    except Exception:
        pass
    alt_w = alt.get("w", {}) if alt.get("felder") == FELDER else {}

    symbole = list(dict.fromkeys(w["symbol"] for w in rl))
    roh, gesperrt = hole_kurse(symbole)
    t_abruf = time.time() - t0
    jetzt = time.time()
    neu, gruende, von_heute, uebernommen = {}, {}, 0, 0
    for w in rl:
        q = roh.get(w["symbol"])
        e, grund = eintrag(w, q, jetzt) if q else (None, "keine Antwort")
        if e is None:
            gruende[grund] = gruende.get(grund, 0) + 1
            a = alt_w.get(w["id"])   # Eintrag des vorigen Abrufs behalten, solange er nicht aelter ist als die Auswertung
            if a and len(a) >= 7 and (not w.get("datum") or dt.datetime.fromtimestamp(a[5] + a[6], dt.timezone.utc).date().isoformat() >= w["datum"]):
                neu[w["id"]] = a[:7]
                uebernommen += 1
            continue
        neu[w["id"]] = e
        if dt.datetime.fromtimestamp(e[5] + e[6], dt.timezone.utc).date() == dt.datetime.fromtimestamp(jetzt + e[6], dt.timezone.utc).date():
            von_heute += 1
    geliefert = len(neu) - uebernommen
    print(f"Kurse: {geliefert} von {len(rl)} geliefert ({von_heute} mit Kurs von heute), {uebernommen} vom vorigen Abruf behalten; "
          f"weggelassen: {gruende or 'nichts'}; Abruf {t_abruf:.0f} s" + (" – GESPERRT, unvollstaendig" if gesperrt else ""), flush=True)
    if not neu:
        print("Kein einziger Kurs – es wird keine Datei geschrieben, die Seite zeigt den Stand der Auswertung.")
        return 2
    if geliefert == 0 and alt.get("basis") == basis:
        print("Nichts Neues – die vorhandene Datei bleibt unveraendert.")
        return 3

    # Ampel, Abstand zur Linie, Raenge: nur wo sich der Kurs geaendert hat; gleiche Funktion wie im vollen Lauf
    t1 = time.time()
    nach_id = {w["id"]: w for w in rl}
    gerechnet = 0
    for wid, e in neu.items():
        lage = lage_rechnen(site, nach_id[wid], e)
        gerechnet += lage[0] is not None
        neu[wid] = e + lage
    t_lage = time.time() - t1

    lokal = dt.datetime.now()
    stand = lokal.strftime("%Y-%m-%d %H:%M") if geliefert else alt.get("stand")
    out = {
        "stand": stand, "zeitzone": time.strftime("%Z"), "stand_unix": int(jetzt) if geliefert else alt.get("stand_unix"),
        "basis": basis,   # Auswertung, zu der Ampel & Co. gerechnet sind (statisch.json: erstellt) – die Seite nutzt die Datei nur bei gleichem Stand
        "quelle": "Yahoo Finance (Kurse je nach Boerse bis 15 Minuten verzoegert)",
        "felder": FELDER,
        "zahl": {"gesamt": len(rl), "geliefert": geliefert, "von_heute": von_heute, "behalten": uebernommen, "ampel_neu": gerechnet,
                 "weggelassen": gruende, "gesperrt": gesperrt, "sekunden": round(time.time() - t0)},
        "w": neu,
    }
    tmp = ziel.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    tmp.replace(ziel)   # erst fertig schreiben, dann umbenennen: nie eine halbe Datei
    print(f"Ampel aus dem frischen Kurs: {gerechnet} Werte in {t_lage:.0f} s; Datei {ziel.stat().st_size / 1e6:.2f} MB", flush=True)

    if not arg.ohne_heute and not gesperrt:
        t2 = time.time()
        try:
            n, von = heute_laden(site, [w for w in rl if auswahl_heute(w)], stand)
            print(f"Feiner Tagesverlauf: {n} von {von} Werten in {time.time() - t2:.0f} s", flush=True)
        except Exception as ex:   # der Verlauf ist Zugabe: scheitert er, bleiben die Kurse trotzdem
            print(f"Feiner Tagesverlauf nicht geladen: {ex.__class__.__name__}: {ex}", flush=True)
    print(f"Fertig in {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
