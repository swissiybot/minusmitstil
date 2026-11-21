"""Branchen der Nasdaq-Aktien aus den SEC-Stammdaten (SIC-Code), fuer die Gruppen der Heatmap.

Quelle: data.sec.gov/submissions/CIK##########.json (Feld "sic"), amtliche US-Daten.
Wie fundamente.py nur mit Kontaktangabe SEC_KONTAKT (GitHub-Secret); ohne sie wird nichts geladen und die
vorhandene Datei genutzt. Gespeichert in daten/sec/branchen.json (nicht im Repo). Erster Lauf etwa 2.400 Abrufe
(gedrosselt auf unter 10 pro Sekunde, wie von der SEC verlangt), danach nur neue Werte und hoechstens
MAX_AUFFRISCHEN alte je Lauf.

Aufruf: python branchen.py
"""
import json
import os
import time
import datetime as dt
import requests

import einstellungen as E
import fundamente

DATEI = fundamente.ORDNER / "branchen.json"
PAUSE = 0.13
ALT_NACH_TAGEN = 180
MAX_AUFFRISCHEN = 200

# SIC-Code -> Branche (angelehnt an die Gliederung grosser Heatmaps); Reihenfolge: speziell vor allgemein
def branche(sic: int | None) -> str:
    if not sic:
        return "Sonstige"
    s = int(sic)
    regeln = [
        (2830, 2836, "Pharma & Biotech"), (3841, 3851, "Medizintechnik"), (8000, 8099, "Gesundheitsdienste"),
        (8731, 8734, "Pharma & Biotech"),
        (3570, 3579, "Technologie: Hardware"), (3670, 3679, "Halbleiter & Elektronik"), (3660, 3669, "Technologie: Hardware"),
        (7370, 7379, "Software & IT-Dienste"), (3820, 3829, "Halbleiter & Elektronik"),
        (4800, 4899, "Kommunikation & Medien"), (2710, 2799, "Kommunikation & Medien"), (7810, 7849, "Kommunikation & Medien"),
        (4900, 4999, "Versorger"),
        (1300, 1399, "Energie"), (2900, 2999, "Energie"),
        (1000, 1499, "Rohstoffe & Bergbau"), (3300, 3399, "Rohstoffe & Bergbau"),
        (2800, 2899, "Chemie & Material"), (2600, 2699, "Chemie & Material"), (3000, 3299, "Chemie & Material"),
        (3710, 3716, "Fahrzeuge"), (3720, 3729, "Luftfahrt & Verteidigung"), (3760, 3769, "Luftfahrt & Verteidigung"),
        (4000, 4799, "Transport & Logistik"),
        (6770, 6770, "Mantelgesellschaften (SPAC)"), (6798, 6798, "Immobilien"), (6500, 6599, "Immobilien"),
        (6000, 6299, "Banken & Finanzdienste"), (6300, 6499, "Versicherungen"), (6700, 6799, "Banken & Finanzdienste"),
        (5200, 5999, "Einzelhandel"), (5000, 5199, "Großhandel"),
        (2000, 2199, "Nahrungsmittel & Getränke"),
        (1500, 1799, "Bau"),
        (3400, 3569, "Industrie & Maschinenbau"), (3580, 3659, "Industrie & Maschinenbau"), (3680, 3819, "Industrie & Maschinenbau"),
        (3830, 3840, "Industrie & Maschinenbau"), (3852, 3999, "Konsumgüter"), (2200, 2599, "Konsumgüter"),
        (7000, 8999, "Dienstleistungen"), (100, 999, "Landwirtschaft"),
    ]
    for von, bis, name in regeln:
        if von <= s <= bis:
            return name
    return "Sonstige"


def laden() -> int:
    vorhanden = json.loads(DATEI.read_text()) if DATEI.exists() else {}
    kontakt = os.environ.get("SEC_KONTAKT", "").strip()
    if not kontakt:
        print(f"Branchen: keine Kontaktangabe (SEC_KONTAKT) – nutze vorhandene Datei ({len(vorhanden)} Werte)")
        return len(vorhanden)
    tick = fundamente._ticker_zu_cik()
    if not tick:
        print("Branchen: keine Tickerliste der SEC (fundamente.py zuerst)")
        return len(vorhanden)
    import analyse
    uni = analyse.universum()
    symbole = [z["symbol"] for z in uni.to_dict("records") if "Nasdaq" in z["gruppe"]]
    heute = dt.date.today()
    alt = [t for t, v in vorhanden.items() if (heute - dt.date.fromisoformat(v.get("stand", "2000-01-01"))).days > ALT_NACH_TAGEN]
    offen = [t for t in symbole if t not in vorhanden and t.upper().replace(".", "-") in tick] + alt[:MAX_AUFFRISCHEN]
    s = requests.Session()
    s.headers.update({"User-Agent": kontakt, "Accept-Encoding": "gzip, deflate"})
    geholt = fehler = 0
    for i, t in enumerate(offen):
        cik = tick.get(t.upper().replace(".", "-"))
        try:
            a = s.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", timeout=30)
            if a.status_code == 429:
                time.sleep(10); fehler += 1; continue
            if a.ok:
                d = a.json()
                vorhanden[t] = {"sic": int(d.get("sic") or 0), "text": d.get("sicDescription") or "", "stand": heute.isoformat()}
                geholt += 1
            else:
                fehler += 1
        except Exception:
            fehler += 1
        time.sleep(PAUSE)
        if (i + 1) % 250 == 0:
            DATEI.write_text(json.dumps(vorhanden))
            print(f"  Branchen: {i + 1}/{len(offen)}", flush=True)
    DATEI.parent.mkdir(parents=True, exist_ok=True)
    DATEI.write_text(json.dumps(vorhanden))
    print(f"Branchen: {geholt} geholt, {fehler} gescheitert, {len(vorhanden)} Werte gespeichert")
    return len(vorhanden)


def zuordnung() -> dict[str, str]:
    """Symbol -> Branche (leer, wenn keine Datei)."""
    if not DATEI.exists():
        return {}
    return {t: branche(v.get("sic")) for t, v in json.loads(DATEI.read_text()).items()}


if __name__ == "__main__":
    laden()
