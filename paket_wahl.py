"""Welches veroeffentlichte Paket ist „das letzte“? – gemeinsame Auswahl fuer den schlanken Kurs-Lauf und den Schnellweg.

Drei Ablaeufe veroeffentlichen die Seite: der volle Lauf (neue Auswertung), der schlanke Kurs-Lauf und der Schnellweg der
Seite (beide nehmen ein vorhandenes Paket und legen etwas hinein). „Das letzte“ Paket ist deshalb NICHT das juengst
hochgeladene, sondern das mit der NEUESTEN AUSWERTUNG – und unter mehreren mit derselben Auswertung das juengste
(es enthaelt die frischesten Kurse).

Damit das ohne Herunterladen entscheidbar ist, laedt jeder Ablauf neben dem Paket „github-pages“ ein winziges zweites
Artefakt hoch, dessen NAME den Stand der Auswertung traegt: stand-JJJJMMTT-HHMM (aus daten/statisch.json: erstellt).
Die Auswahl liest nur die Artefakt-Liste des Repos.

Laeufe ohne Marke (Pakete aus der Zeit vor dieser Regel, hoechstens einen Tag lang vorhanden): Gibt es noch kein Paket mit
Marke, gilt das juengste Paket. Ist ein Paket ohne Marke juenger als das beste mit Marke, gilt es (das kann nur ein voller
Lauf sein, der noch mit der alten Fassung gestartet wurde).

Aufruf (im GitHub-Lauf, braucht GH_TOKEN und GITHUB_REPOSITORY):
  python paket_wahl.py                       waehlt; schreibt lauf=, stand=, hochgeladen= nach $GITHUB_OUTPUT
  python paket_wahl.py --pruefe STAND ZEIT   vor dem Veroeffentlichen: Rueckgabe 10, wenn inzwischen ein Paket mit
                                             NEUERER Auswertung da ist (dann nicht veroeffentlichen), sonst 0
  python paket_wahl.py --marke site          gibt den Namen der Marke fuer diesen Seiten-Ordner aus
"""
import json
import os
import re
import subprocess
import sys

PAKET = "github-pages"
MARKE = re.compile(r"^stand-(\d{8}-\d{4})$")


def marke(site: str) -> str:
    erstellt = json.load(open(os.path.join(site, "daten", "statisch.json")))["erstellt"]   # "2026-11-25 09:24"
    name = "stand-" + erstellt.replace("-", "").replace(":", "").replace(" ", "-")
    if not MARKE.match(name):
        raise SystemExit(f"Unerwarteter Stand in statisch.json: {erstellt!r}")
    return name


def artefakte() -> list[dict]:
    repo = os.environ["GITHUB_REPOSITORY"]
    out = []
    for seite in (1, 2, 3):   # neueste zuerst; 300 reichen fuer mehr als einen Tag
        roh = subprocess.run(["gh", "api", f"repos/{repo}/actions/artifacts?per_page=100&page={seite}"],
                             check=True, capture_output=True, text=True).stdout
        teil = json.loads(roh).get("artifacts", [])
        out += teil
        if len(teil) < 100:
            break
    return [a for a in out if not a.get("expired")]


def waehle(liste: list[dict], ohne_lauf: str = "") -> dict | None:
    """Bestes Paket: {lauf, stand ('' = ohne Marke), hochgeladen}. Reine Funktion (pruefbar ohne GitHub)."""
    laeufe: dict[str, dict] = {}
    for a in liste:
        lauf = str((a.get("workflow_run") or {}).get("id") or "")
        if not lauf or lauf == str(ohne_lauf):
            continue
        e = laeufe.setdefault(lauf, {"lauf": lauf, "stand": "", "hochgeladen": ""})
        m = MARKE.match(a["name"])
        if m:
            e["stand"] = m.group(1)
        elif a["name"] == PAKET:
            e["hochgeladen"] = a["created_at"]   # ISO-Zeit in UTC: als Text vergleichbar
    kandidaten = [e for e in laeufe.values() if e["hochgeladen"]]
    if not kandidaten:
        return None
    mit = [e for e in kandidaten if e["stand"]]
    ohne = [e for e in kandidaten if not e["stand"]]
    beste_mit = max(mit, key=lambda e: (e["stand"], e["hochgeladen"])) if mit else None
    beste_ohne = max(ohne, key=lambda e: e["hochgeladen"]) if ohne else None
    if beste_mit and (not beste_ohne or beste_ohne["hochgeladen"] < beste_mit["hochgeladen"]):
        return beste_mit
    return beste_ohne


def ueberholt(beste: dict | None, stand: str, hochgeladen: str) -> bool:
    """Ist seit der Auswahl (stand, hochgeladen) ein Paket mit NEUERER Auswertung dazugekommen?"""
    if not beste:
        return False
    if stand and beste["stand"]:
        return beste["stand"] > stand            # gleiche Auswertung, nur juenger hochgeladen: kein Grund abzubrechen
    return beste["hochgeladen"] > hochgeladen     # ohne Marken (Uebergang): vorsichtshalber jedes juengere Paket


def main(argv: list[str]) -> int:
    if argv[:1] == ["--marke"]:
        print(marke(argv[1]))
        return 0
    selbst = os.environ.get("GITHUB_RUN_ID", "")
    beste = waehle(artefakte(), ohne_lauf=selbst)
    if argv[:1] == ["--pruefe"]:
        stand, hochgeladen = argv[1], argv[2]
        if ueberholt(beste, stand, hochgeladen):
            print(f"Inzwischen gibt es ein Paket mit neuerer Auswertung (Lauf {beste['lauf']}, Stand {beste['stand'] or 'ohne Marke'}) – dieser Lauf veröffentlicht nicht.")
            return 10
        print("Kein neueres Paket – weiter.")
        return 0
    if not beste:
        print("::error::Kein veröffentlichtes Paket mehr vorhanden – bitte den vollen Lauf „Dashboard aktualisieren“ starten")
        return 1
    print(f"Paket aus Lauf {beste['lauf']} (Auswertung {beste['stand'] or 'ohne Marke'}, hochgeladen {beste['hochgeladen']})")
    ziel = os.environ.get("GITHUB_OUTPUT")
    if ziel:
        with open(ziel, "a") as f:
            f.write(f"lauf={beste['lauf']}\nstand={beste['stand']}\nhochgeladen={beste['hochgeladen']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
