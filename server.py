"""Kleiner lokaler Server fuer das Dashboard.

- Liefert die Seite aus web/ aus.
- /api/wert?id=SPY berechnet Chart und Kennzahlen eines Werts live aus daten/kurse.parquet
  (ca. 0,1 s). So muessen keine Tausende Chartdateien gespeichert werden.
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

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
_sperre = threading.Lock()
_zwischen: dict = {"stand": None, "werte": {}, "uni": None}


def _aktuell():
    """Zwischenspeicher leeren, sobald die taegliche Auswertung eine neue Rangliste geschrieben hat."""
    rl = E.WEB_DATEN / "rangliste.json"
    stand = rl.stat().st_mtime if rl.exists() else None
    if stand != _zwischen["stand"]:
        _zwischen.update(stand=stand, werte={}, uni={z["id"]: z for z in analyse.universum().to_dict("records")})


def wert_json(wid: str) -> bytes | None:
    with _sperre:
        _aktuell()
        if wid in _zwischen["werte"]:
            return _zwischen["werte"][wid]
        z = _zwischen["uni"].get(wid)
        if z is None:
            return None
        erg = analyse.werte_eines(z)
        if erg is None:
            return None
        daten = gzip.compress(json.dumps({"info": erg[0], "chart": erg[1]}, separators=(",", ":")).encode())
        if len(_zwischen["werte"]) > 200:
            _zwischen["werte"].clear()
        _zwischen["werte"][wid] = daten
        return daten


class Anfrage(SimpleHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/api/wert":
            wid = urllib.parse.parse_qs(url.query).get("id", [""])[0]
            try:
                daten = wert_json(wid)
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

    def log_message(self, *args):  # ruhig bleiben
        pass


if __name__ == "__main__":
    print(f"Dashboard: http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), partial(Anfrage, directory=str(E.WEB))).serve_forever()
