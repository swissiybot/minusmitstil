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
  8. Nachkauf je Titel: Art lohnt/zufall/egal/unklar/daten, nachgerechnet; „lohnt“ nur mit bestandener Zufallsprobe; Nachkauf-Preis = Kurs, bei dem die Ampel heute die Schwelle erreicht;
     „heute erfüllt“ passt zur Ampel; Kurse für Ampel 90 <= 80 <= 70; Kurs unter dem Kurs für Ampel 90 => Ampel >= 90.
  9. Dividenden: nicht negativ, Jahre lückenlos bis zum laufenden Jahr, Rendite 0–25 % = Summe 12 Monate / Kurs,
     Rangliste = Kopfzeile.  10. ETF-Inhalt: Kosten 0–5 %, Gewichte der Top-Positionen zusammen höchstens 100 %,
     Branchen zusammen etwa 100 %.
 11. Hebel-Produkte mit nachgebauter Vorgeschichte (hebel_nachbau.py): Nachbau nur bei den fest freigegebenen Produkten;
     nachbau_bis liegt vor dem ersten echten Kurs und steht gleich in Kopfzeile, Chart und Rangliste; Anschluss ohne Sprung
     (letzter nachgebauter Tag gegen ersten echten Kurs höchstens 25 %); nachgebaute Tage haben nur einen Schlusskurs (> 0);
     die frische Prüfung gegen echte Kurse liegt innerhalb der Alarmgrenzen. Vergleich mit dem Basiswert in sich stimmig
     (Endwert passt zur Jahresrendite, größter Verlust zwischen −100 und 0 %, Nachbau-Datum im Zeitraum).
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
    # Nachbau der Hebel-Produkte: Basiswert +1 % am Tag ohne Zins und Kosten -> +2 %; unveränderter Basiswert -> nur Zins und Kosten gehen ab
    import pandas as pd
    import hebel_nachbau as H
    tage = pd.date_range("2020-01-01", periods=4, freq="D")
    null = pd.Series(0.0, index=tage)
    f1 = H.faktoren(pd.Series([100, 101, 101, 99.99], index=tage), null, 0.0)
    pruef(np.allclose(f1.values, [1, 1.02, 1.02, 1.02 * 0.98]), f"Probe Nachbau 2-fach täglich: {f1.values}")
    f2 = H.faktoren(pd.Series(100.0, index=tage), pd.Series(3.6, index=tage), 0.73)
    pruef(np.allclose(f2.values, np.cumprod([1] + [1 - 0.036 / 360 - 0.0073 / 365] * 3)), f"Probe Nachbau Zins und Kosten: {f2.values}")


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
    pruef(isinstance(nk, dict) and nk.get("art") in ("lohnt", "zufall", "egal", "unklar", "daten"), f"{wid}: Nachkauf fehlt oder unbekannte Art ({nk})")
    if isinstance(nk, dict):   # nachgerechnet (Zufallsvergleich mit festem Startwert je Titel)
        nk2 = A.nachkauf(c, score, kz, zeile["kurs"], wid)
        pruef(nk2.get("art") == nk.get("art") and nk2.get("ab") == nk.get("ab"), f"{wid}: Nachkauf {nk.get('art')}/{nk.get('ab')} ≠ nachgerechnet {nk2.get('art')}/{nk2.get('ab')}")
        if nk.get("art") == "lohnt":
            pruef(nk.get("z_besser", 99) <= A.NK_SIM_MAX_BESSER, f"{wid}: „lohnt“ ohne bestandene Zufallsprobe ({nk.get('z_besser')})")
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
    zusatz_pruefen(wid, zeile, rl.get((wid, z["gruppe"])) or {})
    nachbau_pruefen(wid, z, zeile, chart, roh, rl.get((wid, z["gruppe"])) or {})
    return True


def nachbau_pruefen(wid: str, z: dict, zeile: dict, chart: dict, roh: dict, rz: dict):
    """11. Nachgebaute Vorgeschichte der Hebel-Produkte und Vergleich mit dem Basiswert."""
    import pandas as pd
    import hebel_nachbau as H
    etf = A._etfs().get(wid) if z["gruppe"] == "ETF" else None
    rezept = (etf or {}).get("nachbau")
    seg = zeile.get("segmente") or []
    hat = bool(seg) and seg[0]["art"] == A.QUELLEN_TEXT["nachbau"][0]
    pruef(not any(s["art"] == A.QUELLEN_TEXT["nachbau"][0] for s in seg[1:]), f"{wid}: Nachbau-Abschnitt nicht am Anfang der Reihe")
    if not hat:
        pruef("nachbau_bis" not in zeile and "nachbau_bis" not in chart, f"{wid}: nachbau_bis ohne nachgebauten Abschnitt")
    else:
        pruef(bool(rezept and rezept.get("aktiv")), f"{wid}: nachgebaute Vorgeschichte ohne Freigabe in einstellungen.NACHBAU")
        nb = zeile.get("nachbau_bis")
        pruef(bool(nb) and chart.get("nachbau_bis") == nb, f"{wid}: nachbau_bis fehlt oder Kopfzeile ≠ Chart ({nb} / {chart.get('nachbau_bis')})")
        if rz:
            pruef(rz.get("nachbau_bis") == nb, f"{wid}: nachbau_bis in der Rangliste ({rz.get('nachbau_bis')}) ≠ Kopfzeile ({nb})")
        if nb and len(seg) > 1:
            pruef(nb < seg[1]["ab"], f"{wid}: nachbau_bis {nb} liegt nicht vor dem ersten echten Kurs {seg[1]['ab']}")
            tag = roh["tag"]
            vor, echt = tag[tag.index <= pd.Timestamp(nb)], tag[tag.index >= pd.Timestamp(seg[1]["ab"])]
            pruef(len(vor) > 0 and len(echt) > 0 and vor.index[-1] == pd.Timestamp(nb) and echt.index[0] == pd.Timestamp(seg[1]["ab"]),
                  f"{wid}: Nachbau und echte Kurse überlappen oder haben eine Lücke im Datum")
            if len(vor) and len(echt):
                sprung = float(echt["Close"].iloc[0]) / float(vor["Close"].iloc[-1]) - 1
                pruef(abs(sprung) <= 0.25, f"{wid}: Sprung am Anschluss Nachbau → echte Kurse ({sprung * 100:.1f} %)")
                pruef(bool((vor["Close"] > 0).all()) and bool((vor[["Open", "High", "Low"]].values == vor[["Close"]].values).all()),
                      f"{wid}: nachgebaute Tage mit Kurs ≤ 0 oder mit Tagesspanne")
        p = (H.INFO.get(wid) or {}).get("pruefung") or {}
        pruef(p.get("abw_pa") is not None and abs(p["abw_pa"]) <= H.ALARM["abw_pa"] and (p.get("korr_w") or 0) >= H.ALARM["korr_w"],
              f"{wid}: Nachbau trotz frischer Prüfung außerhalb der Alarmgrenzen ({p})")
        pruef(zeile.get("nachbau_abw_pa") == p.get("abw_pa"), f"{wid}: nachbau_abw_pa ≠ frische Prüfung")
    v = zeile.get("hebel_vgl")
    if v:
        pruef(bool(rezept and rezept.get("vgl")), f"{wid}: Vergleich mit dem Basiswert ohne Freigabe")
        pruef(v["jahre"] > 0 and v["von"] < v["bis"], f"{wid}: Vergleich mit dem Basiswert: Zeitraum unplausibel")
        for seite in ("hebel", "basis"):
            pruef(-100 <= v[f"{seite}_tief"] <= 0, f"{wid}: Vergleich: größter Verlust ({seite}) {v[f'{seite}_tief']} % außerhalb −100 bis 0")
            soll = 10000 * (1 + v[f"{seite}_pa"] / 100) ** v["jahre"]
            pruef(v["jahre"] < 1.5 or math.isclose(v[f"{seite}_end"], soll, rel_tol=0.05 + 0.006 * v["jahre"]), f"{wid}: Vergleich: Endwert ({seite}) {v[f'{seite}_end']} passt nicht zu {v[f'{seite}_pa']} % pro Jahr über {v['jahre']} Jahre")
        pruef(v.get("nachbau_bis") is None or (v["von"] <= v["nachbau_bis"] < v["bis"] and v["nachbau_bis"] == zeile.get("nachbau_bis")), f"{wid}: Vergleich: nachbau_bis passt nicht")
        pruef((v.get("nachbau_bis") is None) == (v.get("nachbau_abw_pa") is None), f"{wid}: Vergleich: nachbau_abw_pa ohne nachbau_bis (oder umgekehrt)")


def zusatz_pruefen(wid: str, zeile: dict, rz: dict):
    """9. Dividenden, 10. ETF-Inhalt: nur ausgewiesen, in sich stimmig, Rangliste = Kopfzeile."""
    d = zeile.get("div")
    if d:
        pruef(d["summe12"] >= 0 and all(v >= 0 for _, v in d["jahre"]), f"{wid}: negative Ausschüttung")
        jahre = [j for j, _ in d["jahre"]]
        pruef(jahre == list(range(jahre[0], jahre[-1] + 1)) and jahre[-1] == d["laufend"], f"{wid}: Dividenden-Jahre nicht lückenlos bis zum laufenden Jahr")
        if d.get("rendite") is not None and zeile.get("kurs"):
            pruef(0 <= d["rendite"] <= 25, f"{wid}: Dividendenrendite {d['rendite']} % außerhalb 0–25")
            pruef(math.isclose(d["rendite"], d["summe12"] / zeile["kurs"] * 100, abs_tol=0.011), f"{wid}: Dividendenrendite ≠ Summe 12 Monate / Kurs")
        if rz:
            pruef((rz.get("div") or {}).get("rendite") == d.get("rendite"), f"{wid}: Dividendenrendite in Rangliste ≠ Kopfzeile")
    e = zeile.get("etf")
    if e:
        if e.get("ter") is not None:
            pruef(0 < e["ter"] < 5, f"{wid}: laufende Kosten {e['ter']} % unplausibel")
        top = e.get("top") or []
        pruef(all(0 < g <= 100 for _, g in top) and sum(g for _, g in top) <= 100.5, f"{wid}: Gewichte der größten Positionen unplausibel")
        if e.get("branchen"):
            pruef(90 <= sum(g for _, g in e["branchen"]) <= 110, f"{wid}: Branchenanteile ergeben nicht etwa 100 %")


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
