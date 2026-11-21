"""Statischer Export fuer die Online-Seite (GitHub Pages). Laeuft NUR im GitHub-Lauf.

Schreibt je Wert web/daten/werte/<id>.json mit Kennzahlen, Chart, Walk-forward-Pruefung und
Strategie-Vergleich (Standardwerte: 500 je Monat, bis 20 Jahre, 1 je Order, echter Zins).
Den Monte-Carlo-Rechner rechnet die Online-Seite selbst im Browser aus den Wochenkerzen des Charts,
deshalb muss dafuer nichts gespeichert werden.
Dazu web/daten/statisch.json mit Datenstand und Download-Ergebnis (fuer die Anzeige oben).

Lokal nicht noetig (der lokale Server rechnet alles live); die Dateien sind in .gitignore.
"""
import json
import re
import shutil
import sys
import time
import datetime as dt

import einstellungen as E
import analyse
import pruefung
import strategie
import umfeld
from kurse import alle_laden


def dateiname(wid: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", wid)   # im Dashboard gleich umgesetzt


def main():
    t0 = time.time()
    alle_laden()
    rl = json.loads((E.WEB_DATEN / "rangliste.json").read_text())
    ids = {w["id"] for w in rl["werte"]}
    ziel = E.WEB_DATEN / "werte"
    tmp = E.WEB_DATEN / "werte.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()
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
            out = {"info": info, "chart": chart}
            if info["score"] is not None:
                w, score = roh["w"], roh["score"]
                out["pruefung"] = pruefung.fuer_wert(w["Close"].values.astype(float), score, w.index.year.values)
                out["strategie"] = strategie.vergleich(w, score, zins) or {"fehler": "zu wenig Monate mit gültiger Ampel"}
            text = json.dumps(out, separators=(",", ":"), ensure_ascii=False)
            (tmp / f"{dateiname(z['id'])}.json").write_text(text)
            n += 1
            groesse += len(text)
        except Exception as ex:
            fehler += 1
            print(f"Export-Fehler bei {z['symbol']}: {ex.__class__.__name__}: {ex}", file=sys.stderr)
    if ziel.exists():
        shutil.rmtree(ziel)
    tmp.replace(ziel)

    lauf = {}
    f = E.DATEN / "kurse_lauf.json"
    if f.exists():
        lauf = json.loads(f.read_text())
    kurse_bis = max((w["datum"] for w in rl["werte"] if w.get("gruppe") != "Krypto"), default=None)
    (E.WEB_DATEN / "statisch.json").write_text(json.dumps({
        "erstellt": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "zeitzone": time.strftime("%Z"),
        "kurse_bis": kurse_bis, "werte": n, "export_fehler": fehler, "kurse_lauf": lauf,
    }, ensure_ascii=False))
    print(f"Export: {n} Werte, {groesse / 1e6:.0f} MB, {fehler} Fehler, {time.time() - t0:.0f} s")
    if lauf:
        print(f"Kursdownload: {lauf.get('geladen')} von {lauf.get('gesamt')} geladen, {lauf.get('ohne_daten')} ohne Daten"
              + (" – ABGEBROCHEN (alter Stand)" if lauf.get("abgebrochen") else ""))


if __name__ == "__main__":
    main()
