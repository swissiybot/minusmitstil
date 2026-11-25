"""Studie „Bewertung je Aktie“ (25.11.2026): Macht die Bewertung einer Aktie die drei Vorhersagen genauer?

Frage
  Sagt ein Modell, das zusätzlich die Bewertung der Aktie kennt (Gewinnrendite = Gewinn der letzten 12 Monate / Börsenwert,
  Kurs-Umsatz-Verhältnis; beides absolut und gemessen an der eigenen Geschichte der Aktie), „Kurs in 1 Jahr höher“ (a1),
  „Kurs in 3 Jahren höher“ (a3) und „Rückschlag von 20 % oder mehr in 12 Monaten“ (r1) genauer voraus als das heutige
  Modell aus vorhersage.py (Häufigkeit aus der eigenen Geschichte, gebündelt mit der Gruppe)?

Verfahren (dieselbe Messlatte wie vorhersage.py)
  * Geschäftszahlen aus daten/sec/fakten.parquet (US-Börsenaufsicht). Die Datei enthält kein Veröffentlichungsdatum; eine
    Zahl gilt deshalb erst 90 Tage nach dem Ende ihres Zeitraums als bekannt (fundamente.LAG_TAGE; Fristen der Aufsicht:
    Jahresbericht 60–90 Tage, Quartalsbericht 40–45 Tage) und höchstens 550 Tage lang. Kein Zukunftswissen.
  * Prüfung ohne Zukunftswissen je Kalenderjahr: gelernt wird nur aus Fällen, deren Ergebnis vor dem 1.1. feststand
    (logistische Regression auf die Bewertung, Ausgangswert = heutige Vorhersage), dann wird das Jahr vorhergesagt.
  * Maß: Brier-Wert. Verbesserung in % gegen das heutige Modell, Unsicherheit aus der Streichprobe über Blöcke von 3
    (a1, r1) bzw. 6 (a3) Kalenderjahren mit t-Verteilung (vorhersage.skill). „Belegt“ erst ab 95 % Sicherheit.
  * Gegenprobe mit vertauschten Bewertungen: Jede Aktie bekommt die Bewertungs-Geschichte einer zufällig gezogenen
    anderen Aktie (Kalenderwochen bleiben, der Zusammenhang Aktie ↔ Bewertung ist zerstört). Erreicht die Vertauschung
    die echte Verbesserung in mehr als 5 von 100 Fällen, ist sie ein Scheinerfolg. Verglichen wird je Durchgang die
    beste der drei Merkmal-Gruppen (sonst gewinnt, wer am meisten probiert) und nur der „Zusatz“: die Verbesserung
    über eine reine Verschiebung der Vorhersage hinaus (die Verschiebung lernt auch ein vertauschtes Merkmal mit; weil
    eine Bewertung nicht für alle Wochen vorliegt, wäre der Vergleich sonst schief).
  * Ergebnis „belegt genauer“ nur, wenn beides erfüllt ist. Sonst „nicht belegt“ – oder „nicht prüfbar“, wenn es
    weniger als 4 Prüfjahre gibt (dann nur eine Momentaufnahme, ausdrücklich ohne Beweiswert).

Grenzen
  * Nur heute gelistete Firmen (verschwundene fehlen); Bewertung nur für Firmen mit US-Bilanz in Dollar und Aktienzahl.
  * Die Aufsicht liefert je Zeitraum die zuletzt gemeldete Zahl (spätere Korrekturen eingeschlossen).
  * Kurse wie im Tool (um Aktiensplits bereinigt); Aktienzahl aus fundamente._aktien_bereinigt (rund 11 Jahre zurück).

Aufruf (im Hauptordner des Projekts, braucht daten/kurse.parquet, daten/universum.csv und daten/sec/fakten.parquet):
    .venv/bin/python studien/bewertung_je_aktie.py                 Studie, 200 Vertauschungen (Ergebnis nach studien/bewertung_je_aktie_ergebnis.json)
    .venv/bin/python studien/bewertung_je_aktie.py --vertausch 50  weniger Vertauschungen (schneller)
    .venv/bin/python studien/bewertung_je_aktie.py --selbsttest    prüft nur die RECHNUNG mit erfundenen Merkmalen (reines Rauschen
                                                                   darf nicht „belegt“ sein, ein eingebautes Signal muss gefunden werden) –
                                                                   keine Ergebnisse über Aktien, wird nicht gespeichert
Lädt nichts aus dem Netz und ändert keine Datei des Tools."""
import sys, os, json, math, time
from pathlib import Path
import multiprocessing as mp
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import vorhersage as VH
import analyse as A
import einstellungen as E
import fundamente as F
import kurse

AUS = Path(__file__).resolve().parent / "bewertung_je_aktie_ergebnis.json"
LAG = pd.Timedelta(days=F.LAG_TAGE).value                 # ab wann eine Zahl als bekannt gilt
ALT = pd.Timedelta(days=550).value                        # wie lange sie höchstens gilt
MIN_EIGEN = 104                                           # „gemessen an der eigenen Geschichte“: ab 2 Jahren mit Bewertung
MIN_LERN = 2000                                           # Lernfälle mit Bewertung je Prüfjahr (wie vorhersage.py)
SAETZE = {"absolut": ["gr", "kuv"], "eigene Geschichte": ["gr_e", "kuv_e"], "beides": ["gr", "kuv", "gr_e", "kuv_e"]}
NAMEN = {"a1": "Kurs in 1 Jahr höher", "a3": "Kurs in 3 Jahren höher", "r1": "Rückschlag ab 20 % in 12 Monaten"}


def bewertung_einer(z: dict, f: dict, n: int):
    """Je Woche Gewinnrendite und log. Kurs-Umsatz-Verhältnis einer Aktie – nur aus Zahlen, die damals als bekannt galten."""
    w, _ = VH.laden(z)
    if w is None or len(w) != n or not f or f.get("waehrung") or not f.get("aktien_reihe"):
        return None
    t = w.index.values.astype("datetime64[ns]").astype(np.int64); c = w["Close"].values.astype(float)

    def stand(reihe):
        reihe = sorted({e: (e, v) for e, v in reihe}.values())
        if not reihe:
            return np.full(n, np.nan)
        ende = np.array([e.value for e, _ in reihe], dtype=np.int64); wert = np.array([v for _, v in reihe], dtype=float)
        i = np.searchsorted(ende + LAG, t, "right") - 1
        return np.where((i >= 0) & (t - ende[np.clip(i, 0, None)] <= ALT), wert[np.clip(i, 0, None)], np.nan)

    wert = c * stand(f["aktien_reihe"])                               # Börsenwert
    gewinn, umsatz = stand(list(f["ni_jahr"]) + list(f["ni_ttm"])), stand(list(f["rv_jahr"]) + list(f["rv_ttm"]))
    with np.errstate(divide="ignore", invalid="ignore"):
        gr = np.clip(gewinn / wert, -0.5, 0.5)                        # Gewinnrendite (Kehrwert des KGV, auch bei Verlust rechenbar)
        kuv = np.where(umsatz > 0, np.log(wert / umsatz), np.nan)
    eigen = lambda x: ((pd.Series(x) - pd.Series(x).expanding(MIN_EIGEN).mean()) / pd.Series(x).expanding(MIN_EIGEN).std()).values
    return {"gr": gr, "kuv": np.clip(kuv, -5, 8), "gr_e": np.clip(eigen(gr), -5, 5), "kuv_e": np.clip(eigen(kuv), -5, 5)}


def bewertung_bauen(D: dict, zeilen: list[dict]) -> dict:
    K = F.kennzahlen(); von_id = {z["id"]: z for z in zeilen}
    M = {k: np.full(len(D["t"]), np.nan) for k in SAETZE["beides"]}
    start = np.r_[0, np.cumsum(D["n_je"])]; mit = 0
    for i, wid in enumerate(D["ids"]):
        z = von_id[wid]; e = bewertung_einer(z, K.get(z["symbol"]), int(D["n_je"][i]))
        if e is None:
            continue
        mit += 1
        for k in M:
            M[k][start[i]:start[i + 1]] = e[k]
    M["_firmen"] = mit
    return M


def vorbereiten(D: dict, ziel: str):
    """Heutiges Modell je Prüfjahr wie vorhersage.pruefe_ziel (Spalte „gewählt“): Lernzeilen, Prüfzeilen, Vorhersage je Wert."""
    h, y, kenn = VH.ziel_daten(D, ziel)
    nt = len(D["ids"]); tid, jahr = D["tid"], D["jahr"]
    basis = np.flatnonzero(kenn & D["lang"] & D["xok"] & np.isfinite(D["score"]))
    ende = (D["e3"] if h == 156 else D["e1"]).astype(np.int64)
    warte = int(math.ceil(h / 52)) + 1; fehler, aus = {}, []
    for J in range(1975, int(jahr[basis].max()) + 1):
        grenze = int(np.datetime64(f"{J}-01-01").astype("datetime64[D]").astype(int))
        L = basis[ende[basis] < grenze]; Z = basis[jahr[basis] == J]
        if len(L) < 2000 or not len(Z):
            continue
        pg = y[L].mean(); n_i = np.bincount(tid[L], minlength=nt); k_i = np.bincount(tid[L], weights=y[L], minlength=nt)
        P = np.stack([((k_i + pr * pg) / (n_i + pr))[tid[Z]] for pr in VH.PRIORS], axis=1)
        su = sum((v for jj, v in fehler.items() if jj + warte <= J), np.zeros(len(VH.PRIORS)))
        wahl = int(np.argmin(su)) if su.sum() > 0 else 2
        fehler[J] = ((P - y[Z][:, None]) ** 2).sum(0)
        aus.append((J, L, Z, (k_i + VH.PRIORS[wahl] * pg) / (n_i + VH.PRIORS[wahl])))
    return h, y, aus


def pruefen(D: dict, y, vorb: list, X: np.ndarray):
    """Prüfung ohne Zukunftswissen mit den Merkmalen X (Zeilen ohne Merkmal zählen nicht).
    Rückgabe: Zeilen, heutiges Modell, Modell mit Merkmalen, heutiges Modell nur verschoben (ohne Merkmal)."""
    tid = D["tid"]; ok = np.all(np.isfinite(X), axis=1); teile = []
    for J, L, Z, p0 in vorb:
        LF, ZF = L[ok[L]], Z[ok[Z]]
        if len(LF) < MIN_LERN or not len(ZF):
            continue
        mu, sd = X[LF].mean(0), X[LF].std(0) + 1e-9
        b = VH.logreg(np.clip((X[LF] - mu) / sd, -5, 5), y[LF], VH.logit(p0[tid[LF]]))
        p = VH.sig(VH.logit(p0[tid[ZF]]) + b[0] + np.clip((X[ZF] - mu) / sd, -5, 5) @ b[1:])
        c = VH.logreg(np.zeros((len(LF), 0)), y[LF], VH.logit(p0[tid[LF]]))        # nur Verschiebung, ohne Merkmal
        teile.append((ZF, np.clip(p0[tid[ZF]], .02, .98), np.clip(p, .02, .98), np.clip(VH.sig(VH.logit(p0[tid[ZF]]) + c[0]), .02, .98)))
    if not teile:
        return None
    return tuple(np.concatenate([x[i] for x in teile]) for i in range(4))


def verbesserung(D, y, erg, block):
    """skill: [Verbesserung in %, 5-%-Grenze, 95-%-Grenze, Sicherheit in %] gegen das heutige Modell; zusatz: Verbesserung in %
    gegen das nur verschobene heutige Modell (Anteil der Merkmale); dazu Fälle, Firmen, Jahre."""
    if erg is None:
        return None
    Z, p0, p, pc = erg; jahr = D["jahr"][Z]
    return {"skill": [None if v is None else float(v) for v in VH.skill((p - y[Z]) ** 2, (p0 - y[Z]) ** 2, jahr, block)],
            "zusatz": round(float(1 - ((p - y[Z]) ** 2).sum() / ((pc - y[Z]) ** 2).sum()) * 100, 2),      # über die reine Verschiebung hinaus
            "faelle": int(len(Z)), "firmen": int(len(np.unique(D["tid"][Z]))), "von": int(jahr.min()), "bis": int(jahr.max()),
            "jahre": int(len(np.unique(jahr))), "brier_heute": round(float(((p0 - y[Z]) ** 2).mean()), 4), "brier_neu": round(float(((p - y[Z]) ** 2).mean()), 4)}


def vertauschen(D: dict, M: dict, rng) -> dict:
    """Jede Firma mit Bewertung bekommt die Bewertungs-Geschichte einer anderen (gleiche Kalenderwochen)."""
    start = np.r_[0, np.cumsum(D["n_je"])]
    hat = [i for i in range(len(D["ids"])) if np.isfinite(M["kuv"][start[i]:start[i + 1]]).any() or np.isfinite(M["gr"][start[i]:start[i + 1]]).any()]
    geber = rng.permutation(hat); N = {k: np.full(len(D["t"]), np.nan) for k in SAETZE["beides"]}
    for a, b in zip(hat, geber):
        ta, tb = D["t"][start[a]:start[a + 1]], D["t"][start[b]:start[b + 1]]
        j = np.searchsorted(tb, ta); j[j >= len(tb)] = len(tb) - 1
        gleich = tb[j] == ta
        for k in N:
            N[k][start[a]:start[a + 1]] = np.where(gleich, M[k][start[b]:start[b + 1]][j], np.nan)
    return N


def matrix(M: dict, namen: list) -> np.ndarray:
    return np.stack([M[k] for k in namen], axis=1)


def gegenprobe(D, y, vorb, M, saetze: list, block: int, echt: float, n: int, rng) -> dict:
    """Vertauschte Bewertungen: je Durchgang der beste Zusatz unter den Merkmal-Gruppen `saetze`, verglichen mit dem echten."""
    null = []
    for _ in range(n):
        N = vertauschen(D, M, rng)
        werte = [v["zusatz"] for v in (verbesserung(D, y, pruefen(D, y, vorb, matrix(N, SAETZE[name])), block) for name in saetze) if v]
        if werte:
            null.append(max(werte))
    null = np.array(null)
    return {"vertauscht_mittel": round(float(null.mean()), 2), "vertauscht_95": round(float(np.quantile(null, .95)), 2),
            "vertauscht_erreicht_das": f"{int((null >= echt).sum())} von {len(null)}", "p": round(float((1 + (null >= echt).sum()) / (1 + len(null))), 3)}


def momentaufnahme(D, y, vorb, M, rng, n_vertausch):
    """Nur wenn die Prüfung nicht möglich ist: im selben Zeitraum gelernt UND geprüft (zu günstig), ein einziger Zeitabschnitt – kein Beleg.
    Zusatz = Verbesserung der Merkmale „absolut“ in % über eine reine Verschiebung der heutigen Vorhersage hinaus."""
    tid = D["tid"]; X = matrix(M, SAETZE["absolut"]); ok = np.all(np.isfinite(X), axis=1)
    Z = np.concatenate([Zj[ok[Zj]] for _, _, Zj, _ in vorb]) if vorb else np.zeros(0, int)
    if len(Z) < 500:
        return None
    p0 = np.concatenate([np.clip(p[tid[Zj[ok[Zj]]]], .02, .98) for _, _, Zj, p in vorb])

    def gewinn(XX, zeilen, p0z):
        g = np.all(np.isfinite(XX[zeilen]), axis=1); zz, pz = zeilen[g], p0z[g]
        if len(zz) < 500:
            return np.nan
        x = np.clip((XX[zz] - XX[zz].mean(0)) / (XX[zz].std(0) + 1e-9), -5, 5)
        b = VH.logreg(x, y[zz], VH.logit(pz)); c = VH.logreg(np.zeros((len(zz), 0)), y[zz], VH.logit(pz))
        return float(1 - ((VH.sig(VH.logit(pz) + b[0] + x @ b[1:]) - y[zz]) ** 2).mean() / ((VH.sig(VH.logit(pz) + c[0]) - y[zz]) ** 2).mean()) * 100
    echt = gewinn(X, Z, p0)
    null = np.array([gewinn(matrix(vertauschen(D, M, rng), SAETZE["absolut"]), Z, p0) for _ in range(n_vertausch)])
    null = null[np.isfinite(null)]
    t = D["t"][Z].astype("int64").astype("datetime64[D]")
    return {"faelle": int(len(Z)), "firmen": int(len(np.unique(tid[Z]))), "von": str(t.min()), "bis": str(t.max()),
            "zusatz_im_selben_zeitraum": round(echt, 2), "vertauscht_mittel": round(float(null.mean()), 2) if len(null) else None,
            "vertauscht_erreicht_das": f"{int((null >= echt).sum())} von {len(null)}",
            "hinweis": "im selben Zeitraum gelernt und geprüft, ein einziger Zeitabschnitt (alle Aktien teilen dieselbe Börsenphase) – kein Beleg"}


def selbsttest_merkmale(D: dict, art: str, rng) -> dict:
    """Erfundene Merkmale, nur um die Rechnung zu prüfen: träges Rauschen je Firma; bei „signal“ dazu ein Anteil des späteren 1-Jahres-Ertrags."""
    start = np.r_[0, np.cumsum(D["n_je"])]; M = {k: np.full(len(D["t"]), np.nan) for k in SAETZE["beides"]}
    for i in range(len(D["ids"])):
        if not D["lang_je"][i]:
            continue
        n = int(D["n_je"][i])
        for k in M:
            e = rng.normal(size=n); x = np.empty(n); x[0] = e[0]
            for j in range(1, n):
                x[j] = 0.98 * x[j - 1] + 0.2 * e[j]
            if art == "signal" and k == "gr":
                x = x + 1.0 * np.nan_to_num(D["f1"][start[i]:start[i + 1]].astype(float))
            M[k][start[i]:start[i + 1]] = x
    return M


def main():
    t0 = time.time(); selbst = "--selbsttest" in sys.argv
    n_vertausch = int(sys.argv[sys.argv.index("--vertausch") + 1]) if "--vertausch" in sys.argv else 200
    kurse.alle_laden()
    zeilen = [z for z in A.universum().to_dict("records") if VH.gruppe_nr(z) == 4 and z.get("branche") != E.HEBEL_BRANCHE]
    with mp.get_context("fork").Pool(min(os.cpu_count() or 2, 15)) as pool:
        D = VH.daten_bauen(zeilen, True, pool)
    rng = np.random.default_rng(2511)
    print(f"Aktien mit Kursen: {len(D['ids'])}, davon mit mindestens 10 Jahren und ohne Kurssprünge: {int(D['lang_je'].sum())}  ({time.time() - t0:.0f} s)", flush=True)
    if selbst:
        print("SELBSTTEST – erfundene Merkmale, prüft nur die Rechnung. KEINE Aussage über Aktien.")
        for art in ("rauschen", "signal"):
            M = selbsttest_merkmale(D, art, rng)
            for ziel in ("a1",):
                h, y, vorb = vorbereiten(D, ziel)
                v = verbesserung(D, y, pruefen(D, y, vorb, matrix(M, SAETZE["absolut"])), 3)
                s = v["skill"]; belegt = s[3] is not None and s[0] > 0 and s[3] >= VH.SICHER
                soll = art == "signal"
                print(f"  {art:8s} {ziel}: {s[0]:+.2f} % [{s[1]} … {s[2]}], Sicherheit {s[3]} %, {v['faelle']} Fälle {v['von']}–{v['bis']} → "
                      f"{'belegt' if belegt else 'nicht belegt'} ({'richtig' if belegt == soll else 'FALSCH – Rechnung prüfen'})", flush=True)
                gp = gegenprobe(D, y, vorb, M, ["absolut"], 3, v["zusatz"], 39, rng)
                print(f"           Zusatz der Merkmale {v['zusatz']:+.2f} %; vertauscht im Mittel {gp['vertauscht_mittel']:+.2f} %, erreicht den echten Wert in {gp['vertauscht_erreicht_das']} "
                      f"({'richtig' if (gp['p'] <= 0.05) == soll else 'FALSCH – Rechnung prüfen'})", flush=True)
        return
    M = bewertung_bauen(D, zeilen)
    hat = np.isfinite(M["gr"]) | np.isfinite(M["kuv"]); tage = D["t"][hat].astype("int64").astype("datetime64[D]")
    lang = D["lang"]
    abd = {"firmen_mit_bewertung": int(len(np.unique(D["tid"][hat]))), "firmen_mit_bewertung_lang": int(len(np.unique(D["tid"][hat & lang]))),
           "aktien_lang": int(D["lang_je"].sum()), "wochen_mit_bewertung": int(hat.sum()),
           "erste_woche": str(tage.min()) if hat.any() else None, "letzte_woche": str(tage.max()) if hat.any() else None,
           "wochen_je_kalenderjahr": {str(j): int(n) for j, n in zip(*np.unique(D["jahr"][hat & lang], return_counts=True))},
           "firmen_ab_2_jahren_bewertung": int(sum(np.isfinite(M["kuv_e"][D["tid"] == i]).any() for i in np.unique(D["tid"][hat])))}
    print("Abdeckung:", json.dumps(abd, ensure_ascii=False), flush=True)
    aus = {"stand": time.strftime("%Y-%m-%d"), "vertauschungen": n_vertausch, "abdeckung": abd, "ziele": {}}
    for ziel in VH.ZIELE:
        h, y, vorb = vorbereiten(D, ziel); block = 6 if h == 156 else 3
        alle = np.concatenate([Z for _, _, Z, _ in vorb]); p_alle = np.concatenate([np.clip(p[D["tid"][Z]], .02, .98) for _, _, Z, p in vorb])
        eintrag = {"name": NAMEN[ziel], "heutiges_modell": {"faelle": int(len(alle)), "brier": round(float(((p_alle - y[alle]) ** 2).mean()), 4),
                                                            "mit_bewertung": int(hat[alle].sum())}, "saetze": {}}
        echt = {}
        for name, merk in SAETZE.items():
            v = verbesserung(D, y, pruefen(D, y, vorb, matrix(M, merk)), block)
            eintrag["saetze"][name] = v; echt[name] = v["skill"][0] if v else None
        pruefbar = [n for n, v in eintrag["saetze"].items() if v and v["skill"][3] is not None]
        if pruefbar:
            bester = max(pruefbar, key=lambda n: echt[n])
            gp = gegenprobe(D, y, vorb, M, pruefbar, block, max(eintrag["saetze"][n]["zusatz"] for n in pruefbar), n_vertausch, rng)
            s = eintrag["saetze"][bester]["skill"]
            belegt = s[0] > 0 and s[3] >= VH.SICHER and gp["p"] <= 0.05
            eintrag.update({"bester_satz": bester, "gegenprobe": gp, "urteil": "belegt genauer" if belegt else "nicht belegt"})
        else:
            eintrag.update({"urteil": "nicht prüfbar", "grund": "zu wenige Jahre mit Geschäftszahlen: keine Prüfung ohne Zukunftswissen über mindestens 4 Kalenderjahre möglich",
                            "momentaufnahme": momentaufnahme(D, y, vorb, M, rng, min(n_vertausch, 100))})
        aus["ziele"][ziel] = eintrag
        print(f"{ziel} ({NAMEN[ziel]}): {eintrag['urteil']}", flush=True)
        for name, v in eintrag["saetze"].items():
            print(f"    {name:18s}: " + ("keine Prüfjahre mit genug Lernfällen" if not v else
                  f"{v['skill'][0]:+.2f} % [{v['skill'][1]} … {v['skill'][2]}], Sicherheit {v['skill'][3]} %, Zusatz der Merkmale {v['zusatz']:+.2f} %, {v['faelle']} Fälle, {v['firmen']} Firmen, {v['von']}–{v['bis']}"), flush=True)
        for k in ("gegenprobe", "momentaufnahme"):
            if eintrag.get(k):
                print(f"    {k}: {json.dumps(eintrag[k], ensure_ascii=False)}", flush=True)
    AUS.write_text(json.dumps(aus, ensure_ascii=False, indent=1))
    print(f"Ergebnis: {AUS}  ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
