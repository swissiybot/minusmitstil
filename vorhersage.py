"""Vorhersage je Wert mit dem genauesten geprüften Modell (Studie 23.11.2026, Wunsch Marc: „das Modell, das am
genauesten ist, egal wie – finde es heraus und wende es an“).

Geprüft wurden an über 300.000 echten Fällen ohne Zukunftswissen (je Kalenderjahr nur aus dem gelernt, was vorher
schon feststand): Grundquoten mit verschieden starker Bündelung, die Ampel, der Abstand zur 200-Wochen-Linie,
sechs Merkmale aus dem Kursverlauf (logistische Regression), der Zustand des Gesamtmarkts, ähnlichste frühere
Wochen je Titel und ein nichtlineares Modell (Gradient Boosting). Ergebnis:

  * „Steht der Kurs in 1 bzw. 3 Jahren höher?“ – am genauesten ist die Häufigkeit aus der eigenen Geschichte des
    Titels, GEBÜNDELT mit seiner Gruppe (je weniger eigene Geschichte, desto stärker zählt die Gruppe). Kein Modell
    mit Ampel, Abstand oder anderen Merkmalen war belegbar genauer; die Ampel machte die Vorhersage leicht ungenauer.
  * „Fällt der Kurs in den nächsten 12 Monaten irgendwann um 20 % oder mehr?“ – bei Aktien belegbar genauer mit
    Merkmalen (Schwankung, Trend, Rückgang vom Hoch, Momentum), sonst ebenfalls die gebündelte Häufigkeit.
  * Gegenprobe mit Zufallsverläufen (echte Wochenrenditen des Titels in neu gereihten 26-Wochen-Stücken): Der
    Zusammenhang „hohe Ampel → mehr Ertrag danach“ und der Vorteil von „Warten auf günstig“ entstehen bei Aktien
    genauso oft von selbst; über dem Zufall liegen nur breite Index-ETFs (schwach) und Rohstoffe.

Dieses Modul rechnet beides laufend neu: (1) die Prüfung (höchstens einmal pro Woche, sonst aus
daten/vorhersage_pruefung.json) und (2) die Vorhersage für heute je Wert. Welches Modell je Gruppe gilt, entscheidet
allein die Prüfung: ein aufwendigeres Modell wird nur angewendet, wenn es in mindestens 90 % der Bootstrap-Ziehungen
genauer war als die gebündelte Häufigkeit. Ausgabe: web/daten/vorhersage.json. Die Ampel-Formel bleibt unberührt.

Grenzen (stehen auch in der Anzeige): Grundlage sind HEUTE gelistete Werte – verschwundene Firmen fehlen, die
Häufigkeiten sind dadurch eher zu hoch. Kurse ohne Garantie, keine Anlageberatung.

Aufruf: python vorhersage.py          (Prüfung nur, wenn älter als 7 Tage)
        python vorhersage.py --neu    (Prüfung neu rechnen)"""
import sys, os, json, math, time, zlib
import multiprocessing as mp
import numpy as np
import pandas as pd
import analyse as A
import einstellungen as E
import kurse

MIN_WOCHEN = 520                 # Prüfung und Gruppen-Häufigkeit: nur Werte mit mindestens 10 Jahren Wochenkursen
GRUPPEN = ["Index-ETF", "ETF", "Rohstoff", "Krypto", "Aktie"]
PRIORS = [24.0, 100.0, 400.0, 1500.0, 1e9]      # Stärke der Bündelung in Monats-Fällen (1e9 = nur die Gruppe)
ZIELE = {"a1": (52, "auf"), "a3": (156, "auf"), "r1": (52, "risiko")}
MERKMALE = ["lz", "dd", "tr", "mom", "vol", "mom3"]
RISIKO_GRENZE = -0.20            # „Rückschlag“: tiefster Wochenschluss der nächsten 52 Wochen mindestens 20 % unter heute
SICHER = 90.0                    # Merkmale-Modell gilt nur, wenn es in so viel % der Bootstrap-Ziehungen genauer war
MIN_PRUEF = 500                  # Gruppe gilt als geprüft ab so vielen Vorhersagen …
MIN_TITEL = 5                    # … aus mindestens so vielen Werten
ALT_TAGE = 7
SIMS, SIMS_AKTIE, BLOCK, AKTIEN_SIM = 100, 30, 26, 150   # Gegenprobe: Zufallsverläufe je Wert (Aktien weniger, dafür viele Werte), Blocklänge in Wochen, Stichprobe Aktien
PRUEF_DATEI = E.DATEN / "vorhersage_pruefung.json"
AUS_DATEI = E.WEB_DATEN / "vorhersage.json"
ZINS = None

logit = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
sig = lambda x: 1 / (1 + np.exp(-np.clip(x, -30, 30)))


def gruppe_nr(z: dict) -> int:
    if z["gruppe"] == "ETF":
        return 0 if z.get("branche") == "Index" else 1
    return {"Rohstoffe": 2, "Krypto": 3}.get(z["gruppe"], 4)


def laden(z: dict):
    """Wochenkerzen eines Werts wie im Tool (ETF mit Index-Vorgeschichte, Bitcoin mit Vorgeschichte)."""
    etf = A._etfs().get(z["id"]) if z["gruppe"] == "ETF" else None
    tag = A.verketten(etf)[0] if etf else kurse.lade_lokal(z["symbol"])
    if tag is None or tag.empty:
        return None
    if z["id"] == E.BITCOIN["id"]:
        import btc_alt
        tag, _ = btc_alt.verlaengern(tag, [(tag.index[0], "krypto", z["symbol"])])
    return A.wochen(tag[tag["Close"] > 0])


def satz(arg):
    """Je Woche: Merkmale NUR aus Wissen bis zu dieser Woche, dazu was 1 und 3 Jahre später kam (für das Lernen)."""
    z, mit_ampel = arg
    try:
        w = laden(z)
        if w is None:
            return None
        c = w["Close"].values.astype(float); n = len(c)
        if n < 60 or not np.all(np.isfinite(c)) or c.min() <= 0:
            return None
        s = pd.Series(c); lc = np.log(s)
        lr = np.log(s / s.rolling(200).mean())                       # Abstand zur 200-Wochen-Linie
        m = {"lz": lr / lr.expanding(104).std(),                     # … gemessen in den bisher üblichen Abständen dieses Werts
             "dd": s / s.cummax() - 1,                               # Rückgang vom bisherigen Hoch
             "tr": s.rolling(20).mean() / s.rolling(50).mean() - 1,  # Trend 20 gegen 50 Wochen
             "mom": lc.shift(4) - lc.shift(52),                      # Momentum 12 Monate ohne den letzten
             "vol": lc.diff().rolling(52).std() * math.sqrt(52),     # Schwankung der letzten 52 Wochen
             "mom3": lc - lc.shift(156)}                             # Kursveränderung der letzten 3 Jahre
        f32 = lambda x: np.asarray(x, dtype=np.float32)
        aus = {"id": z["id"], "g": gruppe_nr(z), "n": n,
               "t": ((w.index - pd.Timestamp("1970-01-01")) // pd.Timedelta(days=1)).values.astype(np.int32),
               "f1": f32(lc.shift(-52) - lc), "f3": f32(lc.shift(-156) - lc),
               "ddf": f32(s[::-1].rolling(52, min_periods=52).min()[::-1].shift(-1) / s - 1)}
        for k in MERKMALE:
            aus[k] = f32(m[k])
        aus["score"] = f32(A.ampel_rechnen(c, z["gruppe"] == "Krypto")[1]) if mit_ampel and n >= MIN_WOCHEN else np.full(n, np.nan, np.float32)
        return aus
    except Exception as ex:          # ein kaputter Wert darf den Lauf nicht stoppen – wird gezählt und gemeldet
        return {"fehler": f"{z.get('id')}: {type(ex).__name__}: {ex}"}


def daten_bauen(zeilen: list[dict], mit_ampel: bool, pool) -> dict:
    erg = pool.map(satz, [(z, mit_ampel) for z in zeilen], chunksize=20)
    fehler = [e["fehler"] for e in erg if e and "fehler" in e]
    gut = [e for e in erg if e and "fehler" not in e]
    D = {"ids": [e["id"] for e in gut], "n_je": np.array([e["n"] for e in gut]), "g_je": np.array([e["g"] for e in gut]), "fehler": fehler,
         "tid": np.concatenate([np.full(e["n"], i, np.int32) for i, e in enumerate(gut)]),
         "wo": np.concatenate([np.arange(e["n"], dtype=np.int32) for e in gut])}
    for k in ["t", "f1", "f3", "ddf", "score"] + MERKMALE:
        D[k] = np.concatenate([e[k] for e in gut])
    D["grp"] = D["g_je"][D["tid"]]
    D["lang"] = (D["n_je"] >= MIN_WOCHEN)[D["tid"]]
    D["monat"] = (D["n_je"][D["tid"]] - 1 - D["wo"]) % 4 == 0        # jede 4. Woche, von der jüngsten Woche rückwärts
    D["X"] = np.stack([D[k].astype(np.float64) for k in MERKMALE], axis=1)
    D["xok"] = np.all(np.isfinite(D["X"]), axis=1)
    D["jahr"] = D["t"].astype("int64").astype("datetime64[D]").astype("datetime64[Y]").astype(int) + 1970
    return D


def ziel_daten(D: dict, ziel: str):
    h, art = ZIELE[ziel]
    f = (D["ddf"] if art == "risiko" else D["f3"] if h == 156 else D["f1"]).astype(np.float64)
    y = ((f <= RISIKO_GRENZE) if art == "risiko" else (f > 0)).astype(np.float64)
    return h, y, D["monat"] & np.isfinite(f)


def logreg(X, y, off, lam=1.0, it=30):
    """Logistische Regression mit festem Ausgangswert (Offset), Newton-Verfahren, leichte Dämpfung der Steigungen."""
    Xb = np.c_[np.ones(len(X)), X]; b = np.zeros(Xb.shape[1])
    R = lam * np.eye(Xb.shape[1]); R[0, 0] = 0
    for _ in range(it):
        p = sig(off + Xb @ b); w = p * (1 - p)
        d = np.linalg.solve((Xb * w[:, None]).T @ Xb + R, Xb.T @ (y - p) - R @ b)
        b += d
        if np.max(np.abs(d)) < 1e-7:
            break
    return b


def nachjustierung(p, y):
    """Zwei Zahlen (a, b) für p_neu = sig(a + b · logit(p)): gleicht aus, wenn Vorhersagen im Schnitt zu hoch oder zu weit gespreizt waren."""
    return logreg(logit(p)[:, None], y, np.zeros(len(p)), lam=1e-3)


def anpassen(D, y, L, Z, p0, cols=None, ampel=False):
    """Verschiebt die gebündelte Häufigkeit p0 (je Wert) mit Merkmalen: gelernt aus den Zeilen L, angewendet auf Z."""
    XA = D["score"].astype(np.float64)[:, None] / 100.0 if ampel else D["X"] if cols is None else D["X"][:, cols]
    mu, sd = XA[L].mean(0), XA[L].std(0) + 1e-9
    XL, XZ = np.clip((XA[L] - mu) / sd, -5, 5), np.clip((XA[Z] - mu) / sd, -5, 5)
    b = logreg(XL, y[L], logit(p0[D["tid"][L]]))
    return sig(logit(p0[D["tid"][Z]]) + b[0] + XZ @ b[1:])


SPALTEN = ["eigen24", "p100", "p400", "p1500", "gruppe", "gewaehlt", "merkmale", "ampel", "nachjustiert"]


def pruefe_ziel(D: dict, ziel: str) -> dict:
    """Walk-forward: je Kalenderjahr J lernen aus allem, dessen Ergebnis vor dem 1.1.J feststand, dann Jahr J vorhersagen."""
    h, y, kenn = ziel_daten(D, ziel)
    nt = len(D["ids"]); tid, grp, jahr = D["tid"], D["grp"], D["jahr"]
    basis = np.flatnonzero(kenn & D["lang"] & D["xok"] & np.isfinite(D["score"]))
    ende = D["t"].astype(np.int64) + 7 * h
    teile, fehler_je, alt = [], {}, {}; warte = int(math.ceil(h / 52)) + 1
    for J in range(1975, int(jahr[basis].max()) + 1):
        grenze = int(np.datetime64(f"{J}-01-01").astype("datetime64[D]").astype(int))
        lern = basis[ende[basis] < grenze]; zl = basis[jahr[basis] == J]
        if len(lern) < 2000 or not len(zl):
            continue
        P = np.full((len(zl), len(SPALTEN)), np.nan)
        for g in np.unique(grp[zl]):
            L = lern[grp[lern] == g]; zi = np.flatnonzero(grp[zl] == g); Z = zl[zi]
            if len(L) < 200:
                continue
            pg = y[L].mean(); n_i = np.bincount(tid[L], minlength=nt); k_i = np.bincount(tid[L], weights=y[L], minlength=nt)
            for a, pr in enumerate(PRIORS):
                P[zi, a] = ((k_i + pr * pg) / (n_i + pr))[tid[Z]]
            su = sum((v for (gg, jj), v in fehler_je.items() if gg == g and jj + warte <= J), np.zeros(len(PRIORS)))
            wahl = int(np.argmin(su)) if su.sum() > 0 else 2          # Bündelung nur aus Prüfjahren gewählt, deren Ergebnis schon feststand
            p0 = (k_i + PRIORS[wahl] * pg) / (n_i + PRIORS[wahl])
            P[zi, 5] = p0[tid[Z]]
            P[zi, 6] = anpassen(D, y, L, Z, p0)
            P[zi, 7] = anpassen(D, y, L, Z, p0, ampel=True)
            # Nachjustierung: aus früheren Prüfjahren mit bekanntem Ergebnis lernen, ob die Häufigkeit zu hoch oder zu niedrig lag
            paare = [v for (gg, jj), v in alt.items() if gg == g and jj + warte <= J]
            P[zi, 8] = P[zi, 5]
            if paare and sum(len(a) for a, _ in paare) >= 500:
                k = nachjustierung(np.concatenate([a for a, _ in paare]), np.concatenate([b for _, b in paare]))
                P[zi, 8] = sig(k[0] + k[1] * logit(P[zi, 5]))
            alt[(int(g), J)] = (P[zi, 5].copy(), y[Z].copy())
            fehler_je[(int(g), J)] = ((P[zi, :len(PRIORS)] - y[Z][:, None]) ** 2).sum(0)
        gut = np.all(np.isfinite(P), axis=1)
        teile.append((zl[gut], np.clip(P[gut], .02, .98)))
    zeilen = np.concatenate([x[0] for x in teile]); P = np.concatenate([x[1] for x in teile])
    koef = {}
    for g in {gg for gg, _ in alt}:                                   # für heute: Nachjustierung aus allen geprüften Jahren
        pa = np.concatenate([a for (gg, _), (a, _b) in alt.items() if gg == g]); ya = np.concatenate([b for (gg, _), (_a, b) in alt.items() if gg == g])
        koef[g] = [round(float(x), 4) for x in nachjustierung(pa, ya)] if len(pa) >= 500 else None
    return {"h": h, "P": P, "y": y[zeilen], "grp": grp[zeilen], "tid": tid[zeilen], "jahr": jahr[zeilen], "koef": koef}


def skill(se_m, se_ref, jahr, block, rng, B=500):
    """Brier-Skill (1 − Fehler Modell / Fehler Maßstab) mit 5-/95-%-Grenze: ganze Blöcke von Kalenderjahren neu gezogen."""
    jj = np.unique(jahr)
    je = np.array([[se_m[jahr == j].sum(), se_ref[jahr == j].sum()] for j in jj])
    punkt = 1 - je[:, 0].sum() / je[:, 1].sum()
    nb = max(1, int(math.ceil(len(jj) / block))); aus = np.empty(B)
    for b in range(B):
        st = rng.integers(0, max(1, len(jj) - block + 1), nb)
        s = je[(st[:, None] + np.arange(block)[None, :]).ravel() % len(jj)].sum(0)
        aus[b] = 1 - s[0] / s[1]
    return [round(punkt * 100, 2), round(float(np.quantile(aus, .05)) * 100, 2), round(float(np.quantile(aus, .95)) * 100, 2), round(float((aus > 0).mean()) * 100, 1)]


def auswerten(V: dict) -> dict:
    """Je Gruppe: gewählte Bündelung, Modell-Entscheidung, Skill-Zahlen und Kalibrierung."""
    rng = np.random.default_rng(20261123); block = 4 if V["h"] == 156 else 2
    P, y, grp, jahr = V["P"], V["y"], V["grp"], V["jahr"]
    SE = (P - y[:, None]) ** 2; aus = {}
    for g in range(len(GRUPPEN)):
        ma = grp == g
        if ma.sum() < MIN_PRUEF or len(np.unique(V["tid"][ma])) < MIN_TITEL:
            continue
        bs = SE[ma].mean(0); j = jahr[ma]
        prior = int(np.argmin(bs[:len(PRIORS)]))                      # für heute: die bisher genaueste Bündelung
        sk = lambda m, ref: skill(SE[ma, m], SE[ma, ref], j, block, rng)
        merk, amp, nach = sk(6, 5), sk(7, 5), sk(8, 5)
        modell = "merkmale" if merk[0] > 0 and merk[3] >= SICHER else "nachjustiert" if nach[0] > 0 and nach[3] >= SICHER and V["koef"].get(g) else "quote"
        sp = {"merkmale": 6, "nachjustiert": 8}.get(modell, 5)
        o = np.argsort(P[ma, sp], kind="stable"); kal = [[round(float(P[ma, sp][t].mean()) * 100), round(float(y[ma][t].mean()) * 100)] for t in np.array_split(o, 5)]
        aus[GRUPPEN[g]] = {"n": int(ma.sum()), "titel": int(len(np.unique(V["tid"][ma]))), "von": int(j.min()), "bis": int(j.max()),
                           "quote": round(float(y[ma].mean()) * 100, 1), "prior": prior, "modell": modell,
                           "brier": round(float(bs[sp]), 4), "merk": merk, "ampel": amp, "nach": nach, "koef": V["koef"].get(g) if modell == "nachjustiert" else None,
                           "eigen": sk(5, 0), "gruppe": sk(5, 4), "kal": kal}
    return aus


# ----------------------------------------------------------------- Gegenprobe mit Zufallsverläufen
def _rang(x):
    o = np.argsort(x, kind="stable"); r = np.empty(len(x)); r[o] = np.arange(len(x)); return r


def _kennzahlen(w: pd.DataFrame, c: np.ndarray, krypto: bool) -> list:
    """Rangkorrelation Ampel ↔ Ertrag der folgenden 1 bzw. 3 Jahre und Vorsprung von „Warten auf Ampel ≥ 60 / ≥ 80“ vor dem Sparplan."""
    import strategie
    score = np.asarray(A.ampel_rechnen(c, krypto)[1], dtype=float)
    lc = np.log(c); n = len(c); aus = []
    for h in (52, 156):
        f = np.full(n, np.nan); f[:n - h] = lc[h:] - lc[:n - h]
        ok = np.isfinite(score) & np.isfinite(f) & ((n - 1 - np.arange(n)) % 4 == 0)
        aus.append(float(np.corrcoef(_rang(score[ok]), _rang(f[ok]))[0, 1]) if ok.sum() >= 60 and np.std(score[ok]) > 0 else np.nan)
    st = strategie.vergleich(w, score, ZINS, jahre=100, reihe=False)
    e = st["ergebnis"] if st else None
    if e and all(e[k]["irr"] is not None for k in ("spar", "warten60", "warten80")):
        aus += [e["warten60"]["irr"] - e["spar"]["irr"], e["warten80"]["irr"] - e["spar"]["irr"]]
    else:
        aus += [np.nan, np.nan]
    return aus


def zufall_einer(z: dict):
    try:
        w = laden(z)
        c = w["Close"].values.astype(float)
        kr = z["gruppe"] == "Krypto"
        aus = {"g": gruppe_nr(z), "echt": _kennzahlen(w, c, kr), "null": []}
        if z["_sim"]:
            r = np.diff(np.log(c)); m = len(r)
            rng = np.random.default_rng(zlib.crc32(z["id"].encode()))
            for _ in range(SIMS_AKTIE if aus["g"] == 4 else SIMS):
                starts = rng.integers(0, m, size=m // BLOCK + 1)
                idx = ((starts[:, None] + np.arange(BLOCK)[None, :]) % m).ravel()[:m]      # kreisförmiger Block-Bootstrap
                cs = c[0] * np.exp(np.r_[0.0, np.cumsum(r[idx])])
                ws = pd.DataFrame({"Open": np.r_[cs[0], cs[:-1]], "Close": cs}, index=w.index)
                aus["null"].append(_kennzahlen(ws, cs, kr))
        return aus
    except Exception as ex:
        return {"fehler": f"{z.get('id')}: {type(ex).__name__}: {ex}"}


def gegenprobe(zeilen: list[dict], D: dict, pool) -> dict:
    lang = {D["ids"][i] for i in np.flatnonzero(D["n_je"] >= MIN_WOCHEN)}
    Z = [dict(z) for z in zeilen if z["id"] in lang]
    akt = [i for i, z in enumerate(Z) if gruppe_nr(z) == 4]
    wahl = set(np.random.default_rng(7).choice(akt, min(AKTIEN_SIM, len(akt)), replace=False).tolist()) if akt else set()
    for i, z in enumerate(Z):
        z["_sim"] = gruppe_nr(z) != 4 or i in wahl
    erg = [e for e in pool.map(zufall_einer, Z, chunksize=4) if e and "fehler" not in e]
    aus = {}
    med = lambda x: None if not np.isfinite(x).any() else round(float(np.nanmedian(x)), 2)
    for g, name in enumerate(GRUPPEN):
        T = [e for e in erg if e["g"] == g]; S = [e for e in T if e["null"]]
        if not T:
            continue
        E_ = np.array([e["echt"] for e in T], dtype=float)
        ES = np.array([e["echt"] for e in S], dtype=float).reshape(len(S), 4)
        N = [np.array(e["null"], dtype=float) for e in S]
        eintrag = {"titel": len(T), "sim_titel": len(S), "sims": SIMS_AKTIE if g == 4 else SIMS}
        for k, key in enumerate(("rk52", "rk156", "warten60", "warten80")):
            p = np.array([np.mean(nn[:, k][np.isfinite(nn[:, k])] >= es[k]) if np.isfinite(es[k]) and np.isfinite(nn[:, k]).any() else np.nan for nn, es in zip(N, ES)])
            alle_null = np.concatenate([nn[:, k] for nn in N]) if N else np.array([np.nan])
            d = {"echt": med(E_[:, k]), "echt_sim": med(ES[:, k]) if len(S) else None, "zufall": med(alle_null),
                 "sig": None if not np.isfinite(p).any() else round(float(np.nanmean(p < .05)) * 100)}
            if key.startswith("warten"):                              # Anteil der Werte bzw. Zufallsverläufe, in denen Warten mehr brachte als der Sparplan
                d["besser"] = None if not np.isfinite(E_[:, k]).any() else round(float(np.mean(E_[:, k][np.isfinite(E_[:, k])] > 0)) * 100)
                d["besser_zufall"] = None if not np.isfinite(alle_null).any() else round(float(np.mean(alle_null[np.isfinite(alle_null)] > 0)) * 100)
            eintrag[key] = d
        aus[name] = eintrag
    return aus


# ----------------------------------------------------------------- Vorhersage für heute
def heute(D: dict, pruefung: dict) -> dict:
    """Aus allem gelernt, was bis heute feststeht; je Wert die Vorhersage mit dem Modell, das die Prüfung für seine Gruppe gewählt hat."""
    nt = len(D["ids"]); tid, grp = D["tid"], D["grp"]
    letzte = D["wo"] == D["n_je"][tid] - 1
    werte = {i: {"g": GRUPPEN[D["g_je"][k]], "j": round(float(D["n_je"][k]) / 52, 1)} for k, i in enumerate(D["ids"])}
    gruppen_heute = {}
    for ziel in ZIELE:
        h, y, kenn = ziel_daten(D, ziel)
        for g, name in enumerate(GRUPPEN):
            alle = np.flatnonzero(kenn & (grp == g))
            if not len(alle):
                continue
            pool_ = alle[D["lang"][alle]]
            if len(pool_) < 60:                                       # keine lange Reihe in der Gruppe: alle Werte der Gruppe bilden die Gruppen-Häufigkeit
                pool_ = alle
            pg = float(y[pool_].mean())
            pr = pruefung.get(ziel, {}).get(name)
            prior = PRIORS[pr["prior"]] if pr else 400.0
            n_i = np.bincount(tid[alle], minlength=nt); k_i = np.bincount(tid[alle], weights=y[alle], minlength=nt)
            p0 = (k_i + prior * pg) / (n_i + prior)
            p = p0.copy(); mit = np.zeros(nt, bool)
            if pr and pr["modell"] == "nachjustiert" and pr.get("koef"):
                p = sig(pr["koef"][0] + pr["koef"][1] * logit(p0))
            if pr and pr["modell"] == "merkmale":
                L = pool_[D["xok"][pool_]]; Z = np.flatnonzero(letzte & (grp == g) & D["xok"])
                if len(L) >= 2000 and len(Z):
                    p[tid[Z]] = anpassen(D, y, L, Z, p0); mit[tid[Z]] = True
            gruppen_heute.setdefault(name, {"titel_lang": int(((D["g_je"] == g) & (D["n_je"] >= MIN_WOCHEN)).sum())})[ziel] = round(pg * 100, 1)
            for k in np.flatnonzero(D["g_je"] == g):
                e = werte[D["ids"][k]]
                e[ziel] = int(round(float(np.clip(p[k], .02, .98)) * 100))
                e["e" + ziel] = int(round(k_i[k] / n_i[k] * 100)) if n_i[k] >= 12 else None      # eigene Häufigkeit, ungebündelt (ab 12 Monats-Fällen)
                if ziel == "r1":
                    e["m"] = bool(mit[k])
    return {"werte": werte, "gruppen_heute": gruppen_heute}


def pruefung_holen(zeilen, pool, neu: bool):
    if not neu and PRUEF_DATEI.exists() and time.time() - PRUEF_DATEI.stat().st_mtime < ALT_TAGE * 86400:
        try:
            return json.loads(PRUEF_DATEI.read_text()), None
        except Exception:
            pass
    t0 = time.time()
    D = daten_bauen(zeilen, True, pool)
    pr = {"stand": time.strftime("%Y-%m-%d"), "titel": int((D["n_je"] >= MIN_WOCHEN).sum())}
    for ziel in ZIELE:
        pr[ziel] = auswerten(pruefe_ziel(D, ziel))
        print(f"  Prüfung {ziel}: " + ", ".join(f"{g} {v['modell']} (Bündelung {v['prior']}, Merkmale {v['merk'][0]:+.2f} %, Ampel {v['ampel'][0]:+.2f} %)" for g, v in pr[ziel].items()) + f"  ({time.time() - t0:.0f} s)", flush=True)
        print("     Nachjustierung: " + ", ".join(f"{g} {v['nach'][0]:+.2f} % ({v['nach'][3]:.0f} %)" for g, v in pr[ziel].items()), flush=True)
    pr["zufall"] = gegenprobe(zeilen, D, pool)
    print(f"  Gegenprobe mit Zufallsverläufen fertig ({time.time() - t0:.0f} s)", flush=True)
    PRUEF_DATEI.write_text(json.dumps(pr, ensure_ascii=False))
    return pr, D


def main():
    global ZINS
    t0 = time.time()
    kurse.alle_laden()
    try:
        import umfeld
        ZINS = umfeld.zins_monatlich()
    except Exception as ex:
        print(f"Zinsen nicht lesbar ({type(ex).__name__}) – Gegenprobe rechnet ohne Zins aufs Wartegeld", file=sys.stderr)
    zeilen = A.universum().to_dict("records")
    with mp.get_context("fork").Pool(min(os.cpu_count() or 2, 15)) as pool:      # fork: Kurse und Zinsen liegen schon im Arbeitsspeicher
        pr, D = pruefung_holen(zeilen, pool, "--neu" in sys.argv)
        if D is None:
            D = daten_bauen(zeilen, False, pool)
    h = heute(D, pr)
    aus = {"stand": time.strftime("%Y-%m-%d"), "pruefung_stand": pr.get("stand"), "titel_geprueft": pr.get("titel"),
           "ziele": {k: pr.get(k, {}) for k in ZIELE}, "zufall": pr.get("zufall", {}), "gruppen_heute": h["gruppen_heute"], "werte": h["werte"]}
    AUS_DATEI.write_text(json.dumps(aus, ensure_ascii=False, separators=(",", ":")))
    print(f"Vorhersage: {len(h['werte'])} Werte, {len(D['fehler'])} Fehler, Prüfung vom {pr.get('stand')} ({time.time() - t0:.0f} s)")
    for x in D["fehler"][:10]:
        print("  Fehler:", x, file=sys.stderr)


if __name__ == "__main__":
    main()
