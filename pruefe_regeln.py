"""Automatische Pruefung der Rechenregeln (laeuft im Online-Lauf nach analyse.py und VOR dem Veroeffentlichen).

Scheitert eine Regel, bricht der Lauf ab: Die Seite bleibt auf dem letzten guten Stand und der Ausfall-Alarm meldet sich.
Geprueft wird mit echten Daten an einer festen Stichprobe (alle ETFs, Krypto, Rohstoffe und jede 25. Aktie):
  1. Ampel liegt zwischen 0 und 100; Stufe (zone) passt zur Ampel.
  2. Kurs ueber der Kaufzone „15“ (sehr teuer)   => Ampel <= 15.
     Kurs unter der Kaufzone „80“ (sehr guenstig) => Ampel >= 80.
  3. Kaufzonen geordnet: 80 <= 60 <= 40 <= 15 (Kurs).
  4. Unter der 200-Wochen-Linie gilt die Anker-Formel: Ampel = min(100, 70 + 2 x Abstand in %).
  5. Die letzte Woche der Kaufzonen im Chart = Kaufzonen in der Kopfzeile (info.kz) und in der Rangliste.
  6. Kauf- und Verkaufsqualitaet liegen zwischen 0 und 100.
  7. Die ausgegebene Ampel ist genau die der Formel (nachgerechnet mit anker_ampel).
Dazu Rechenproben mit kuenstlichen Kursreihen (konstanter Kurs = an der Linie = 70, steiler Absturz = 100).

Aufruf: python pruefe_regeln.py          (Ausgabe: Anzahl gepruefter Werte und Fehler; Rueckgabecode 1 bei Fehlern)
"""
import json
import math
import sys
import numpy as np

import einstellungen as E
import analyse as A

FEHLER: list[str] = []


def pruef(bed: bool, text: str):
    if not bed:
        FEHLER.append(text)


def kuenstlich():
    c = np.full(400, 100.0)
    s, kz, _ = A.anker_ampel(c, A.WARMUP)
    pruef(abs(s[-1] - A.ANKER) < 1e-9, f"Probe konstanter Kurs: Ampel {s[-1]} statt {A.ANKER}")
    c2 = np.concatenate([np.full(399, 100.0), [50.0]])
    s2, _, _ = A.anker_ampel(c2, A.WARMUP)
    pruef(s2[-1] == 100.0, f"Probe Absturz um 50 %: Ampel {s2[-1]} statt 100")
    # Kurs genau an der Kaufzone 80 -> Ampel 80
    p = kz[80][-1]
    c3 = np.concatenate([c[:-1], [p]])
    s3, _, _ = A.anker_ampel(c3, A.WARMUP)
    pruef(abs(s3[-1] - 80) < 1e-6, f"Probe Kurs = Kaufzone 80: Ampel {s3[-1]:.4f} statt 80")


def ein_wert(z: dict, rl: dict):
    erg = A.werte_eines(z)
    if erg is None or erg[0].get("jung") or erg[0].get("score") is None:
        return False
    zeile, chart, roh = erg
    wid = z["id"]
    c = roh["w"]["Close"].values.astype(float)
    score, kz, _ = A.anker_ampel(c, A.WARMUP)
    s_aus = np.asarray(roh["score"], dtype=float)
    gleich = np.isclose(score, s_aus, atol=1e-6) | (np.isnan(score) & np.isnan(s_aus))
    pruef(bool(gleich.all()), f"{wid}: ausgegebene Ampel weicht von der Formel ab ({int((~gleich).sum())} Wochen)")
    ok = ~np.isnan(score)
    pruef(bool(((score[ok] >= 0) & (score[ok] <= 100)).all()), f"{wid}: Ampel außerhalb 0–100")
    eps = 1e-9
    m15 = ok & ~np.isnan(kz[15]) & (c > kz[15] * (1 + eps))
    pruef(bool((score[m15] <= 15 + 1e-6).all()), f"{wid}: Kurs über Kaufzone 15, Ampel trotzdem über 15 ({int((score[m15] > 15 + 1e-6).sum())} Wochen)")
    m80 = ok & ~np.isnan(kz[80]) & (c < kz[80] * (1 - eps))
    pruef(bool((score[m80] >= 80 - 1e-6).all()), f"{wid}: Kurs unter Kaufzone 80, Ampel trotzdem unter 80 ({int((score[m80] < 80 - 1e-6).sum())} Wochen)")
    alle4 = ~np.isnan(kz[80]) & ~np.isnan(kz[60]) & ~np.isnan(kz[40]) & ~np.isnan(kz[15])
    geordnet = (kz[80] <= kz[60] * (1 + 1e-9)) & (kz[60] <= kz[40] * (1 + 1e-9)) & (kz[40] <= kz[15] * (1 + 1e-9))
    pruef(bool(geordnet[alle4].all()), f"{wid}: Kaufzonen nicht geordnet ({int((~geordnet[alle4]).sum())} Wochen)")
    linie = np.convolve(c, np.ones(200) / 200, "valid")
    lin = np.full(len(c), np.nan); lin[199:] = linie
    unter = ok & ~np.isnan(lin) & (c <= lin)
    soll = np.minimum(100, A.ANKER + A.ANKER_STEIL * (1 - c / lin) * 100)
    pruef(bool(np.allclose(score[unter], soll[unter], atol=1e-6)), f"{wid}: Anker-Formel unter der Linie verletzt")
    # Kopfzeile, Chart und Rangliste
    zk = zeile.get("kz") or {}
    for k in ("80", "60", "40", "15"):
        reihe = [x for x in chart.get(f"kz{k}", []) if x is not None]
        if zk.get(k) is None or not reihe:
            continue
        pruef(math.isclose(reihe[-1], zk[k], rel_tol=1e-3, abs_tol=0.011), f"{wid}: Kaufzone {k} im Chart ({reihe[-1]}) ≠ Kopfzeile ({zk[k]})")
        rz = (rl.get(wid) or {}).get("kz") or {}
        if rz.get(k) is not None:
            pruef(math.isclose(rz[k], zk[k], rel_tol=1e-3, abs_tol=0.011), f"{wid}: Kaufzone {k} in der Rangliste ({rz[k]}) ≠ Kopfzeile ({zk[k]})")
    pruef(zeile.get("zone") == A.zone(zeile["score"]), f"{wid}: Stufe {zeile.get('zone')} passt nicht zur Ampel {zeile['score']}")
    for k in ("kq", "vq"):
        v = [x for x in chart.get(k, []) if x is not None]
        pruef(all(0 <= x <= 100 for x in v), f"{wid}: {'Kauf' if k == 'kq' else 'Verkaufs'}qualität außerhalb 0–100")
    return True


def main():
    kuenstlich()
    rl_datei = E.WEB_DATEN / "rangliste.json"
    rl = {w["id"]: w for w in json.loads(rl_datei.read_text())["werte"]} if rl_datei.exists() else {}
    for w in rl.values():   # Rangliste: Ampel und Stufe
        if w.get("score") is not None:
            pruef(0 <= w["score"] <= 100, f"Rangliste {w['id']}: Ampel {w['score']} außerhalb 0–100")
            pruef(w.get("zone") == A.zone(w["score"]), f"Rangliste {w['id']}: Stufe {w.get('zone')} passt nicht zur Ampel {w['score']}")
    uni = A.universum()
    sonder = uni[uni["gruppe"].isin(["ETF", "Krypto", "Rohstoffe"])]
    aktien = uni[~uni["gruppe"].isin(["ETF", "Krypto", "Rohstoffe"])].iloc[::25]
    A.alle_laden()
    geprueft = 0
    for z in list(sonder.to_dict("records")) + list(aktien.to_dict("records")):
        try:
            geprueft += bool(ein_wert(z, rl))
        except Exception as ex:
            FEHLER.append(f"{z['id']}: Rechenfehler {ex.__class__.__name__}: {ex}")
    pruef(geprueft >= 20, f"zu wenige Werte geprüft ({geprueft})")
    print(f"Rechenregeln: {geprueft} Werte und {len(rl)} Ranglisten-Zeilen geprüft, {len(FEHLER)} Fehler")
    for f in FEHLER[:30]:
        print("  ✗ " + f)
    if FEHLER:
        sys.exit(1)


if __name__ == "__main__":
    main()
