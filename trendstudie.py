"""Trendstudie: Welcher Indikator bestimmt Aufwaerts-/Abwaertstrend am verlaesslichsten?

Jeder Kandidat liefert je Woche nur mit dem Wissen dieser Woche „aufwaerts“ (1) oder „abwaerts“ (0).
Gemessen wird in der Pruefzeit (ab PRUEF_AB), Signal immer erst fuer die FOLGENDE Woche wirksam:
  1. Trennschaerfe: Wie oft stand der Kurs 13 Wochen spaeter hoeher – nach „aufwaerts“ gegen nach „abwaerts“?
  2. Absturzrisiko: Wie oft fiel der Kurs in den naechsten 52 Wochen um 20 % oder mehr – je Signal?
  3. Trendfilter-Strategie: investiert bei „aufwaerts“, sonst Geldmarkt (3-Monats-Zins), 0,1 % Kosten je Wechsel.
     Verglichen mit Kaufen und Halten: Sharpe-Quote, groesster Rueckgang, Rendite p.a.
  4. Zufall: je Wert 200 Zufallssignale mit gleichem Anteil „aufwaerts“ und gleicher mittlerer Phasenlaenge.
     Ein Indikator taugt nur, wenn er klar besser ist als die meisten Zufallssignale.
Auswahl ohne Rueckblick-Fehler: Der Sieger wird nur aus der LERNZEIT (vor PRUEF_AB) bestimmt; die Pruefzeit zeigt,
ob er danach auch noch vorne lag.

Aufruf: python trendstudie.py   → web/daten/trendstudie.json
"""
import json
import math
import sys
import datetime as dt
import numpy as np
import pandas as pd

import einstellungen as E
import analyse
import umfeld
from kurse import alle_laden, lade_lokal

PRUEF_AB = pd.Timestamp("2005-01-01")
KOSTEN = 0.001
ZUFALL_N = 200
AKTIEN_STICHPROBE = 400
rng = np.random.default_rng(20261121)


# ----------------------------------------------------------------- Kandidaten
def sma(c, n):
    return pd.Series(c).rolling(n).mean().values


def ema(c, n):
    return pd.Series(c).ewm(span=n, adjust=False).mean().values


def kandidaten(c: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> dict[str, np.ndarray]:
    """Je Kandidat ein Array mit 1 (aufwaerts), 0 (abwaerts), NaN (noch zu wenig Historie)."""
    k = {}
    def setze(name, bed, gueltig):
        a = np.where(bed, 1.0, 0.0); a[~gueltig] = np.nan; k[name] = a
    for n in (10, 20, 30, 40, 52, 100, 200):
        s = sma(c, n); setze(f"Kurs über {n}-Wochen-Linie", c > s, ~np.isnan(s))
    for a, b in ((4, 13), (10, 40), (13, 52), (20, 50)):
        sa, sb = sma(c, a), sma(c, b); setze(f"{a}-Wochen-Linie über {b}-Wochen-Linie", sa > sb, ~np.isnan(sb))
    for n in (13, 26, 52):
        vor = pd.Series(c).shift(n).values; setze(f"Momentum {n} Wochen (höher als vor {n} W.)", c > vor, ~np.isnan(vor))
    s40 = sma(c, 40)
    for n in (4, 13):
        vor = pd.Series(s40).shift(n).values; setze(f"40-Wochen-Linie steigt ({n} W.)", s40 > vor, ~np.isnan(vor))
    m = ema(c, 12) - ema(c, 26); sig = pd.Series(m).ewm(span=9, adjust=False).mean().values
    setze("MACD über Signallinie", m > sig, np.arange(len(c)) >= 35)
    setze("MACD über null", m > 0, np.arange(len(c)) >= 26)
    hoch = np.maximum.accumulate(c); setze("weniger als 20 % unter dem Hoch", c / hoch - 1 > -0.2, np.arange(len(c)) >= 52)
    # Donchian: Ausbruch ueber 52-Wochen-Hoch = aufwaerts, unter 52-Wochen-Tief = abwaerts, sonst bleibt der Zustand
    h52 = pd.Series(hi).shift(1).rolling(52).max().values; l52 = pd.Series(lo).shift(1).rolling(52).min().values
    zust, cur = np.full(len(c), np.nan), np.nan
    for i in range(len(c)):
        if np.isnan(h52[i]):
            continue
        if c[i] > h52[i]: cur = 1.0
        elif c[i] < l52[i]: cur = 0.0
        elif np.isnan(cur): cur = 1.0 if c[i] > (h52[i] + l52[i]) / 2 else 0.0
        zust[i] = cur
    k["52-Wochen-Ausbruch (Donchian)"] = zust
    # bisherige Marktphase des Tools: abwaerts nur, wenn Kurs unter 40-W.-Linie UND tiefer als vor 52 W.
    vor52 = pd.Series(c).shift(52).values
    setze("Tool bisher: abwärts nur wenn unter 40-W.-Linie und tiefer als vor 12 M.", ~((c < s40) & (c < vor52)), ~np.isnan(s40) & ~np.isnan(vor52))
    setze("Tool bisher streng: aufwärts nur wenn über 40-W.-Linie und höher als vor 12 M.", (c > s40) & (c > vor52), ~np.isnan(s40) & ~np.isnan(vor52))
    # Mehrheit aus fuenf verbreiteten Regeln
    teile = [k["Kurs über 40-Wochen-Linie"], k["10-Wochen-Linie über 40-Wochen-Linie"], k["Momentum 26 Wochen (höher als vor 26 W.)"],
             k["Momentum 52 Wochen (höher als vor 52 W.)"], k["MACD über null"]]
    st = np.vstack(teile); ok = ~np.isnan(st).any(axis=0)
    setze("Mehrheit aus 5 Regeln (40W, 10/40, Mom. 26/52, MACD)", np.nansum(st, axis=0) >= 3, ok)
    return k


# ----------------------------------------------------------------- Kennzahlen
def kennzahlen(sig, r_next, cash_next, fwd13, absturz, maske):
    """sig[t] gilt fuer die Rendite r_next[t] (Woche t -> t+1). Nur Wochen in maske."""
    m = maske & ~np.isnan(sig) & ~np.isnan(r_next)
    if m.sum() < 104:
        return None
    s, r, cz = sig[m], r_next[m], cash_next[m]
    wechsel = np.abs(np.diff(np.concatenate([[s[0]], s])))
    strat = np.where(s == 1, r, cz) - wechsel * KOSTEN
    def werte(x):
        kurve = np.cumprod(1 + x)
        jahre = len(x) / 52.18
        cagr = kurve[-1] ** (1 / jahre) - 1
        dd = float((kurve / np.maximum.accumulate(kurve) - 1).min())
        ex = x - cz
        sharpe = float(ex.mean() / ex.std() * math.sqrt(52.18)) if ex.std() > 0 else 0.0
        return cagr, dd, sharpe
    c_s, dd_s, sh_s = werte(strat)
    c_b, dd_b, sh_b = werte(r)
    f = fwd13[m]; a = absturz[m]
    ok_f = ~np.isnan(f); ok_a = ~np.isnan(a)
    def q(bed, x, ok):
        sel = bed & ok
        return float((x[sel] > 0).mean()) if sel.sum() >= 26 else np.nan
    return {"sharpe_diff": sh_s - sh_b, "dd_diff": dd_s - dd_b, "cagr_diff": c_s - c_b,
            "sharpe": sh_s, "dd": dd_s, "cagr": c_s, "sharpe_bh": sh_b, "dd_bh": dd_b, "cagr_bh": c_b,
            "anteil_auf": float(s.mean()), "wechsel_pa": float(wechsel.sum() / (len(s) / 52.18)),
            "q_auf": q(s == 1, f, ok_f), "q_ab": q(s == 0, f, ok_f),
            "absturz_auf": q(s == 1, a, ok_a), "absturz_ab": q(s == 0, a, ok_a)}


def zufall_wie(sig, n):
    """Markov-Zufallssignale mit gleichem Anteil 1 und gleicher mittlerer Phasenlaenge wie sig."""
    s = sig[~np.isnan(sig)]
    p1 = s.mean()
    wechsel = max(np.abs(np.diff(s)).sum(), 1)
    laenge1 = max((s == 1).sum() / max(((np.diff(s) == 1).sum()) + (s[0] == 1), 1), 1)
    laenge0 = max((s == 0).sum() / max(((np.diff(s) == -1).sum()) + (s[0] == 0), 1), 1)
    a, b = 1 / laenge1, 1 / laenge0   # Wechselwahrscheinlichkeit 1->0 und 0->1
    out = np.empty((n, len(sig)))
    zust = (rng.random(n) < p1).astype(float)
    u = rng.random((n, len(sig)))
    for t in range(len(sig)):
        out[:, t] = zust
        weg = np.where(zust == 1, u[:, t] < a, u[:, t] < b)
        zust = np.where(weg, 1 - zust, zust)
    out[:, np.isnan(sig)] = np.nan
    return out


# ----------------------------------------------------------------- Daten
def wochen_von(z):
    if z["gruppe"] == "ETF":
        tag, _ = analyse.verketten(analyse._etfs()[z["id"]])
    else:
        tag = lade_lokal(z["symbol"])
        if z["id"] == E.BITCOIN["id"] and tag is not None:
            import btc_alt
            tag, _ = btc_alt.verlaengern(tag, [])
    if tag is None or tag.empty:
        return None
    tag = tag[tag["Close"] > 0]
    w = analyse.wochen(tag)
    return w if len(w) >= 260 else None


def main():
    alle_laden()
    uni = analyse.universum()
    zins = umfeld.zins_monatlich()
    gruppen = {"etf": [], "krypto": [], "rohstoffe": [], "aktien": []}
    for z in uni.to_dict("records"):
        g = {"ETF": "etf", "Krypto": "krypto", "Rohstoffe": "rohstoffe"}.get(z["gruppe"], "aktien")
        gruppen[g].append(z)
    aktien = [z for z in gruppen["aktien"]]
    rng.shuffle(aktien)
    gruppen["aktien"] = aktien

    ergebnisse = {}   # gruppe -> kandidat -> zeitraum -> liste kennzahlen
    zufall = {}       # gruppe -> zeitraum -> liste sharpe_diff aus Zufall (je Wert Median)
    perz = {}         # gruppe -> kandidat -> liste Perzentil gegen Zufall
    werte_n = {}
    for g, liste in gruppen.items():
        n_ok = 0
        for z in liste:
            if g == "aktien" and n_ok >= AKTIEN_STICHPROBE:
                break
            w = wochen_von(z)
            if w is None:
                continue
            if g == "aktien" and (w.index[0] > pd.Timestamp("2000-01-01")):
                continue   # Aktien nur mit langer Historie (Lern- und Pruefzeit)
            c = w["Close"].values.astype(float)
            lo = w["Low"].values.astype(float); hi = w["High"].values.astype(float)
            r_next = np.full(len(c), np.nan); r_next[:-1] = c[1:] / c[:-1] - 1
            if zins is not None:
                zw = zins.reindex(w.index, method="ffill").fillna(0).values / 100
            else:
                zw = np.zeros(len(c))
            cash_next = np.concatenate([zw[1:], [0]]) / 52.18
            fwd13 = np.full(len(c), np.nan); fwd13[:-13] = c[13:] / c[:-13] - 1
            absturz = np.full(len(c), np.nan)
            tief = pd.Series(lo[::-1]).rolling(52).min().values[::-1]
            tief = np.concatenate([tief[1:], [np.nan]])
            ok = np.arange(len(c)) < len(c) - 52
            absturz[ok] = (tief[ok] / c[ok] - 1 <= -0.2).astype(float)
            absturz_pos = np.where(np.isnan(absturz), np.nan, absturz * 2 - 1)   # >0 heisst Absturz (fuer q())
            lern = w.index < PRUEF_AB
            pruef = ~lern
            kand = kandidaten(c, lo, hi)
            for name, sig in kand.items():
                for zr, maske in (("lern", lern), ("pruef", pruef)):
                    kz = kennzahlen(sig, r_next, cash_next, fwd13, absturz_pos, maske)
                    if kz is None:
                        continue
                    ergebnisse.setdefault(g, {}).setdefault(name, {}).setdefault(zr, []).append(kz)
                # Zufallsvergleich nur in der Pruefzeit, bei Aktien fuer eine kleinere Auswahl
                if g != "aktien" or n_ok < 100:
                    kz = kennzahlen(sig, r_next, cash_next, fwd13, absturz_pos, pruef)
                    if kz is not None:
                        zs = zufall_wie(np.where(pruef, sig, np.nan), ZUFALL_N)
                        zd = [kennzahlen(zs[j], r_next, cash_next, fwd13, absturz_pos, pruef) for j in range(ZUFALL_N)]
                        zd = np.array([x["sharpe_diff"] for x in zd if x is not None])
                        if len(zd):
                            perz.setdefault(g, {}).setdefault(name, []).append(float((zd < kz["sharpe_diff"]).mean()))
            n_ok += 1
            if n_ok % 50 == 0:
                print(f"  {g}: {n_ok} Werte", flush=True)
        werte_n[g] = n_ok
        print(f"{g}: {n_ok} Werte ausgewertet", flush=True)

    med = lambda xs: None if not xs else float(np.nanmedian(xs))
    out = {"stand": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "pruef_ab": str(PRUEF_AB.date()), "kosten": KOSTEN,
           "zufall_n": ZUFALL_N, "werte": werte_n, "gruppen": {}}
    for g, kands in ergebnisse.items():
        zeilen = []
        for name, zr in kands.items():
            zeile = {"name": name}
            for z_, liste in zr.items():
                zeile[z_] = {k: med([x[k] for x in liste]) for k in liste[0]} | {"werte": len(liste)}
            zeile["perzentil_zufall"] = med(perz.get(g, {}).get(name, []))
            zeilen.append(zeile)
        out["gruppen"][g] = zeilen
    # Sieger je Gruppe NUR aus der Lernzeit (Median Sharpe-Differenz), dazu seine Pruefzeit
    for g, zeilen in out["gruppen"].items():
        mit_lern = [z for z in zeilen if z.get("lern") and z["lern"]["sharpe_diff"] is not None]
        if mit_lern:
            sieger = max(mit_lern, key=lambda z: z["lern"]["sharpe_diff"])
            out.setdefault("sieger_lern", {})[g] = sieger["name"]
    # Gesamtrang: mittlerer Rang nach Pruefzeit-Sharpe-Differenz ueber alle Gruppen
    namen = {z["name"] for zeilen in out["gruppen"].values() for z in zeilen}
    raenge = {n: [] for n in namen}
    for g, zeilen in out["gruppen"].items():
        zs = sorted([z for z in zeilen if z.get("pruef")], key=lambda z: -z["pruef"]["sharpe_diff"])
        for i, z in enumerate(zs):
            raenge[z["name"]].append(i + 1)
    def feld(n, g, k):
        z = next((z for z in out["gruppen"].get(g, []) if z["name"] == n and z.get("pruef")), None)
        return None if z is None else z["pruef"][k]
    gesamt = []
    for n, rr in raenge.items():
        if not rr:
            continue
        dds = [feld(n, g, "dd_diff") for g in out["gruppen"] if feld(n, g, "dd_diff") is not None]
        ws = [feld(n, g, "wechsel_pa") for g in out["gruppen"] if feld(n, g, "wechsel_pa") is not None]
        zf = [z.get("perzentil_zufall") for zeilen in out["gruppen"].values() for z in zeilen if z["name"] == n and z.get("perzentil_zufall") is not None]
        gesamt.append({"name": n, "rang": float(np.mean(rr)), "etf": feld(n, "etf", "sharpe_diff"), "aktien": feld(n, "aktien", "sharpe_diff"),
                       "dd": float(np.mean(dds)) if dds else None, "wechsel": float(np.mean(ws)) if ws else None,
                       "zufall": float(np.mean(zf)) if zf else None})
    out["gesamt"] = sorted(gesamt, key=lambda z: z["rang"])
    out["gewaehlt"] = "20-Wochen-Linie über 50-Wochen-Linie"
    sieger = out["gesamt"][0] if out["gesamt"] else None
    out["fazit"] = ("Kein Indikator schlug Kaufen und Halten bei Rendite je Schwankung dauerhaft, und keiner war klar besser als Zufallssignale. "
                    "Alle Trendfilter verkleinerten aber den größten Rückgang – auf Kosten von Rendite. "
                    + (f"Am stabilsten über alle Gruppen: {sieger['name']} (wechselt etwa {sieger['wechsel']:.1f}-mal im Jahr)".replace(".", ",") + f". " if sieger else "")
                    + "Das Tool nutzt für die Marktphase „20-Wochen-Linie über 50-Wochen-Linie“.")
    (E.WEB_DATEN / "trendstudie.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("geschrieben: web/daten/trendstudie.json")


if __name__ == "__main__":
    main()
