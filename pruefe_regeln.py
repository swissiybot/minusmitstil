"""Automatische Pruefung der Rechenregeln (laeuft im Online-Lauf nach analyse.py und VOR dem Veroeffentlichen).

Scheitert eine Regel, bricht der Lauf ab: Die Seite bleibt auf dem letzten guten Stand und der Ausfall-Alarm meldet sich.
Geprueft wird mit echten Daten an einer festen Stichprobe (alle ETFs, Krypto, Rohstoffe und jede 25. Aktie):
  1. Ampel liegt zwischen 0 und 100; Stufe (zone) passt zur Ampel.
  2. Kurs ueber der Kaufzone „15“ (sehr teuer)   => Ampel <= 15.
     Kurs unter der Kaufzone „80“ (sehr guenstig) => Ampel >= 80.
  3. Kaufzonen geordnet: 80 <= 60 <= 40 <= 15 (Kurs).
  4. Anker-Ampel: an oder unter der 200-Wochen-Linie liegt die Ampel zwischen 70 und 100,
     darueber unter 70; unter der Linie gilt die Seltenheits-Formel (bzw. 70 + 2 x Abstand, solange es zu wenige fruehere
     Wochen unter der Linie gibt).
  5. Die letzte Woche der Kaufzonen im Chart = Kaufzonen in der Kopfzeile (info.kz) und in der Rangliste.
  6. Kauf- und Verkaufsqualitaet liegen zwischen 0 und 100.
  7. Die ausgegebene Ampel ist genau die der Formel (nachgerechnet mit ampel_rechnen).
  8. Nachkauf je Titel: Art lohnt/egal/unklar; Nachkauf-Preis = Kurs, bei dem die Ampel heute die Schwelle erreicht;
     „heute erfüllt“ passt zur Ampel; Kurse für Ampel 90 <= 80 <= 70; Kurs unter dem Kurs für Ampel 90 => Ampel >= 90.
Dazu Rechenproben mit kuenstlichen Kursreihen (konstanter Kurs = an der Linie = 70, Absturz tiefer als je zuvor = 100,
Kurs knapp unter/ueber der Kaufzone 80).

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
    s = A.anker_ampel(c, A.WARMUP)[0]
    pruef(abs(s[-1] - A.ANKER) < 1e-9, f"Probe konstanter Kurs: Ampel {s[-1]} statt {A.ANKER}")
    c2 = np.concatenate([np.full(399, 100.0), [50.0]])
    s2 = A.anker_ampel(c2, A.WARMUP)[0]
    pruef(s2[-1] == 100.0, f"Probe Absturz um 50 %: Ampel {s2[-1]} statt 100")
    # schwankender Kurs: knapp unter der Kaufzone 80 -> Ampel >= 80, knapp darüber -> unter 80; Absturz unter alle Tiefs -> 100
    rng = np.random.default_rng(7)
    c4 = 100 * np.exp(np.cumsum(rng.normal(0.002, 0.04, 700)))
    s4, kz4 = A.anker_ampel(c4, A.WARMUP)[:2]
    p = kz4[80][-1]
    for faktor, soll in ((1 - 1e-6, True), (1 + 1e-3, False)):
        s5 = A.anker_ampel(np.concatenate([c4[:-1], [p * faktor]]), A.WARMUP)[0]
        pruef((s5[-1] >= 80 - 1e-9) == soll, f"Probe Kurs {'unter' if soll else 'über'} Kaufzone 80: Ampel {s5[-1]:.3f}")
    s6 = A.anker_ampel(np.concatenate([c4[:-1], [c4.min() * 0.3]]), A.WARMUP)[0]
    pruef(s6[-1] == 100.0, f"Probe Rekordtiefe unter der Linie: Ampel {s6[-1]} statt 100")
    # tieferer Kurs -> nie niedrigere Ampel
    kurz = c4[:-1]
    werte = [A.anker_ampel(np.concatenate([kurz, [kurz[-1] * f]]), A.WARMUP)[0][-1] for f in (0.5, 0.8, 1.0, 1.2, 1.6)]
    pruef(all(werte[i] >= werte[i + 1] - 1e-9 for i in range(len(werte) - 1)), f"Probe: Ampel steigt mit dem Kurs ({werte})")


def stufe_passt(zone, score) -> bool:
    """Stufe passt zur Ampel; die Ampel ist auf 1 Nachkommastelle gerundet (79,96 → 80,0 bleibt „günstig“)."""
    return zone in {A.zone(score - 0.05), A.zone(score), A.zone(score + 0.05)}


def ein_wert(z: dict, rl: dict):
    erg = A.werte_eines(z)
    if erg is None or erg[0].get("jung") or erg[0].get("score") is None:
        return False
    zeile, chart, roh = erg
    wid = z["id"]
    c = roh["w"]["Close"].values.astype(float)
    art, score, kz, _, _ = A.ampel_rechnen(c)
    pruef(zeile.get("ampel_art") == art, f"{wid}: Modell {zeile.get('ampel_art')} statt {art}")
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
    ueber = ok & ~np.isnan(lin) & (c > lin)
    pruef(bool(((score[unter] >= A.ANKER - 1e-6) & (score[unter] <= 100 + 1e-6)).all()), f"{wid}: unter der Linie Ampel außerhalb 70–100")
    pruef(bool((score[ueber] <= A.ANKER + 1e-6).all()), f"{wid}: über der Linie Ampel über 70")
    # Kopfzeile, Chart und Rangliste
    zk = zeile.get("kz") or {}
    for k in ("80", "60", "40", "15"):
        reihe = [x for x in chart.get(f"kz{k}", []) if x is not None]
        if zk.get(k) is None or not reihe:
            continue
        pruef(math.isclose(reihe[-1], zk[k], rel_tol=1e-3, abs_tol=0.011), f"{wid}: Kaufzone {k} im Chart ({reihe[-1]}) ≠ Kopfzeile ({zk[k]})")
        rz = (rl.get((wid, z["gruppe"])) or {}).get("kz") or {}   # nach Kennung UND Gruppe (z. B. GOLD = Rohstoff Gold und Aktie Barrick)
        if rz.get(k) is not None:
            pruef(math.isclose(rz[k], zk[k], rel_tol=1e-3, abs_tol=0.011), f"{wid}: Kaufzone {k} in der Rangliste ({rz[k]}) ≠ Kopfzeile ({zk[k]})")
    pruef(stufe_passt(zeile.get("zone"), zeile["score"]), f"{wid}: Stufe {zeile.get('zone')} passt nicht zur Ampel {zeile['score']}")
    # Nachkauf: Art bekannt; Nachkauf-Preis = Kurs, bei dem die Ampel heute die Schwelle erreicht; „heute erfüllt“ passt zur Ampel
    nk = zeile.get("nk")
    pruef(isinstance(nk, dict) and nk.get("art") in ("lohnt", "egal", "unklar"), f"{wid}: Nachkauf fehlt oder unbekannte Art ({nk})")
    if isinstance(nk, dict) and nk.get("ab") is not None:
        g = nk["ab"]
        soll = kz[g][-1]
        if nk.get("preis") is not None and not math.isnan(soll):
            pruef(math.isclose(nk["preis"], soll, rel_tol=1e-3, abs_tol=0.011), f"{wid}: Nachkauf-Preis {nk['preis']} ≠ Kurs für Ampel {g} ({soll:.4g})")
        pruef(nk.get("jetzt") == bool(score[-1] >= g), f"{wid}: Nachkauf „heute erfüllt“ = {nk.get('jetzt')}, Ampel {score[-1]:.1f}, Schwelle {g}")
    alle_hoch = ~np.isnan(kz[70]) & ~np.isnan(kz[80]) & ~np.isnan(kz[90])
    hoch_geordnet = (kz[90] <= kz[80] * (1 + 1e-9)) & (kz[80] <= kz[70] * (1 + 1e-9))
    pruef(bool(hoch_geordnet[alle_hoch].all()), f"{wid}: Kurse für Ampel 90/80/70 nicht geordnet ({int((~hoch_geordnet[alle_hoch]).sum())} Wochen)")
    m90 = ok & ~np.isnan(kz[90]) & (c < kz[90] * (1 - eps))
    pruef(bool((score[m90] >= 90 - 1e-6).all()), f"{wid}: Kurs unter dem Kurs für Ampel 90, Ampel trotzdem unter 90 ({int((score[m90] < 90 - 1e-6).sum())} Wochen)")
    for k in ("kq", "vq"):
        v = [x for x in chart.get(k, []) if x is not None]
        pruef(all(0 <= x <= 100 for x in v), f"{wid}: {'Kauf' if k == 'kq' else 'Verkaufs'}qualität außerhalb 0–100")
    return True


def main():
    kuenstlich()
    rl_datei = E.WEB_DATEN / "rangliste.json"
    rl = {(w["id"], w.get("gruppe")): w for w in json.loads(rl_datei.read_text())["werte"]} if rl_datei.exists() else {}
    for w in rl.values():   # Rangliste: Ampel und Stufe
        if w.get("score") is not None:
            pruef(0 <= w["score"] <= 100, f"Rangliste {w['id']}: Ampel {w['score']} außerhalb 0–100")
            pruef(stufe_passt(w.get("zone"), w["score"]), f"Rangliste {w['id']}: Stufe {w.get('zone')} passt nicht zur Ampel {w['score']}")
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
