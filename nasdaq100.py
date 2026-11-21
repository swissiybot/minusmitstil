"""Mitglieder des Nasdaq-100 mit Branche (ICB), fuer die Heatmap.

Quelle: Wikipedia „List of NASDAQ-100 companies“ (Tabelle id="constituents": Kuerzel, Firma, ISIN,
ICB-Branche, ICB-Untersektor; Inhalt unter CC BY-SA, Quelle wird im Dashboard genannt).
Gespeichert in daten/nasdaq100.json (nicht im Repo), hoechstens einmal pro Tag neu geladen;
bei Netzfehlern bleibt die letzte Datei.

Aufruf: python nasdaq100.py
"""
import json
import re
import sys
import time
import requests

import einstellungen as E

DATEI = E.DATEN / "nasdaq100.json"
URL = "https://en.wikipedia.org/w/api.php"
KOPF = {"User-Agent": "minusmitstil-dashboard/1.0 (Hobbyprojekt)"}
BRANCHE_DE = {
    "Technology": "Technologie", "Consumer Discretionary": "Zyklischer Konsum", "Consumer Staples": "Basiskonsum",
    "Health Care": "Gesundheit", "Industrials": "Industrie", "Telecommunications": "Telekommunikation",
    "Utilities": "Versorger", "Energy": "Energie", "Basic Materials": "Grundstoffe", "Financials": "Finanzen",
    "Real Estate": "Immobilien",
}


def _sauber(zelle: str) -> str:
    zelle = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", zelle)
    zelle = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", r"\1", zelle)
    zelle = re.sub(r"\{\{ISIN\|(?:[^|}]*\|)*([A-Z0-9]{12})\}\}", r"\1", zelle)
    return re.sub(r"\{\{[^}]*\}\}", "", zelle).strip()


def laden() -> list[dict]:
    p = {"action": "parse", "page": "List_of_NASDAQ-100_companies", "prop": "wikitext", "format": "json",
         "formatversion": "2", "redirects": "1"}
    t = requests.get(URL, params=p, headers=KOPF, timeout=60).json()["parse"]["wikitext"]
    k = t.find('id="constituents"')
    if k < 0:
        raise RuntimeError("Tabelle constituents nicht gefunden")
    tab = t[k:t.find("|}", k)]
    out = []
    for zeile in tab.split("\n|-")[1:]:
        zeile = zeile.strip()
        if not zeile.startswith("|") or zeile.startswith("|}"):
            continue
        z = [_sauber(x) for x in zeile.lstrip("|").split("||")]
        if len(z) < 4 or not re.fullmatch(r"[A-Z.\-]{1,6}", z[0]):
            continue
        out.append({"symbol": z[0].replace(".", "-"), "name": z[1], "isin": z[2] if len(z) > 2 else "",
                    "branche": BRANCHE_DE.get(z[3], z[3] or "Sonstige"), "untersektor": z[4] if len(z) > 4 else ""})
    if not 95 <= len(out) <= 110:
        raise RuntimeError(f"unplausibel viele Mitglieder: {len(out)}")
    return out


def main():
    if DATEI.exists() and time.time() - DATEI.stat().st_mtime < 20 * 3600:
        print(f"Nasdaq-100: Liste aktuell ({DATEI.name})")
        return
    try:
        liste = laden()
        DATEI.write_text(json.dumps({"stand": time.strftime("%Y-%m-%d"), "quelle": "Wikipedia: List of NASDAQ-100 companies",
                                     "mitglieder": liste}, ensure_ascii=False))
        print(f"Nasdaq-100: {len(liste)} Mitglieder gespeichert")
    except Exception as ex:
        print(f"Nasdaq-100 nicht ladbar ({ex.__class__.__name__}: {ex}) – nutze letzte Liste", file=sys.stderr)


def mitglieder() -> dict[str, dict]:
    """Symbol -> {branche, untersektor} (leer ohne Datei)."""
    if not DATEI.exists():
        return {}
    return {m["symbol"]: m for m in json.loads(DATEI.read_text())["mitglieder"]}


if __name__ == "__main__":
    main()
