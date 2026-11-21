"""Kleiner lokaler Server fuer das Dashboard.

- Liefert die Seite aus web/ aus.
- /api/wert?id=SPY berechnet Chart und Kennzahlen eines Werts live aus daten/kurse.parquet
  (ca. 0,1 s). So muessen keine Tausende Chartdateien gespeichert werden.
- /api/pruefung?id=SPY      Walk-forward-Pruefung und Kalibrierung dieses Werts
- /api/strategie?id=SPY&betrag=500&jahre=20&kfix=1&kproz=0&zins=echt|2.5   Sparplan gegen Staffelkauf
- /api/mc?id=SPY&wochen=52&jahre=20&preise=500,800   Monte-Carlo-Kegel und Wahrscheinlichkeiten
Nur auf diesem Rechner erreichbar (127.0.0.1).
"""
import gzip
import json
import sys
import threading
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import einstellungen as E
import analyse
import montecarlo
import pruefung
import strategie
import umfeld

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
_sperre = threading.Lock()
_zwischen: dict = {"stand": None, "werte": {}, "roh": {}, "uni": None, "zins": None}


def _aktuell():
    """Zwischenspeicher leeren, sobald die taegliche Auswertung eine neue Rangliste geschrieben hat."""
    rl = E.WEB_DATEN / "rangliste.json"
    stand = rl.stat().st_mtime if rl.exists() else None
    if stand != _zwischen["stand"]:
        _zwischen.update(stand=stand, werte={}, roh={}, uni={z["id"]: z for z in analyse.universum().to_dict("records")},
                         zins=umfeld.zins_monatlich())


def _berechnen(wid: str):
    """Ampel-Ergebnis eines Werts (mit Zwischenspeicher). Aufruf nur unter _sperre."""
    _aktuell()
    if wid in _zwischen["roh"]:
        return _zwischen["roh"][wid]
    z = _zwischen["uni"].get(wid)
    erg = analyse.werte_eines(z) if z is not None else None
    if len(_zwischen["roh"]) > 60:
        _zwischen["roh"].clear()
    _zwischen["roh"][wid] = erg
    return erg


def _gz(obj) -> bytes:
    return gzip.compress(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode())


def wert_json(wid: str) -> bytes | None:
    with _sperre:
        _aktuell()
        if wid in _zwischen["werte"]:
            return _zwischen["werte"][wid]
        erg = _berechnen(wid)
        if erg is None:
            return None
        info = erg[0] | {"tv": E.tv_symbol(erg[0]["id"], erg[0]["symbol"], erg[0]["gruppe"])}   # TradingView-Umschalter
        daten = _gz({"info": info, "chart": erg[1]})
        if len(_zwischen["werte"]) > 200:
            _zwischen["werte"].clear()
        _zwischen["werte"][wid] = daten
        return daten


def _zahl(q, name, standard, lo, hi):
    try:
        x = float(q.get(name, [standard])[0])
    except ValueError:
        x = standard
    return min(max(x, lo), hi)


def pruefung_json(wid: str, q) -> bytes | None:
    with _sperre:
        erg = _berechnen(wid)
        if erg is None or erg[0]["score"] is None:
            return None
        w, score = erg[2]["w"], erg[2]["score"]
        return _gz(pruefung.fuer_wert(w["Close"].values.astype(float), score, w.index.year.values))


def strategie_json(wid: str, q) -> bytes | None:
    with _sperre:
        erg = _berechnen(wid)
        if erg is None or erg[0]["score"] is None:
            return None
        z = q.get("zins", ["echt"])[0]
        fest = None if z == "echt" else _zahl(q, "zins", 0, -2, 20)
        st = strategie.vergleich(erg[2]["w"], erg[2]["score"], _zwischen["zins"],
                                 betrag=_zahl(q, "betrag", 500, 10, 1e6), jahre=int(_zahl(q, "jahre", 20, 3, 60)),
                                 kfix=_zahl(q, "kfix", 1, 0, 100), kproz=_zahl(q, "kproz", 0, 0, 5) / 100, fester_zins=fest)
        return _gz(st or {"fehler": "zu wenig Monate mit gültiger Ampel"})


def mc_json(wid: str, q) -> bytes | None:
    with _sperre:
        erg = _berechnen(wid)
        if erg is None:
            return None
        w = erg[2]["w"]
    preise = []
    for s in q.get("preise", [""])[0].split(","):
        try:
            preise.append(float(s.replace(" ", "")))
        except ValueError:
            pass
    sim = montecarlo.simulation(w, wochen=int(_zahl(q, "wochen", 52, 4, 260)), jahre=int(_zahl(q, "jahre", 20, 3, 100)),
                                seed_text=wid)
    if sim is None:
        return _gz({"fehler": "zu wenig Kursdaten (mind. 2 Jahre)"})
    return _gz(montecarlo.ergebnis(sim, preise[:10]))


API = {"/api/ping": lambda wid, q: _gz({"server": True}),   # zeigt dem Dashboard: lokaler Server laeuft
       "/api/wert": lambda wid, q: wert_json(wid), "/api/pruefung": pruefung_json,
       "/api/strategie": strategie_json, "/api/mc": mc_json}


class Anfrage(SimpleHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path in API:
            q = urllib.parse.parse_qs(url.query)
            wid = q.get("id", [""])[0]
            try:
                daten = API[url.path](wid, q)
            except Exception as ex:  # Fehler sichtbar machen statt still zu schlucken
                self.send_error(500, f"{ex.__class__.__name__}: {ex}")
                return
            if daten is None:
                self.send_error(404, "Keine Daten fuer " + wid)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(daten)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(daten)
            return
        super().do_GET()

    def end_headers(self):
        # Seite und Skripte immer frisch pruefen lassen (sonst zeigt der Browser nach Aenderungen alte Fassungen)
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args):  # ruhig bleiben
        pass


if __name__ == "__main__":
    print(f"Dashboard: http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), partial(Anfrage, directory=str(E.WEB))).serve_forever()
