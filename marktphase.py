"""Marktphase: steigt oder faellt der Markt gerade – und hilft das bei der Vorhersage?

Phase je Woche, nur mit dem Wissen dieser Woche berechnet:
  Aufwaertstrend (2): Kurs ueber der 200-Tage-Linie (40-Wochen-Durchschnitt) UND hoeher als vor 12 Monaten
  Abwaertstrend  (0): Kurs unter der 200-Tage-Linie UND tiefer als vor 12 Monaten
  Gemischt       (1): sonst (die beiden Zeichen widersprechen sich)
Warum 200 Tage und nicht 200 Wochen: Die 200-Wochen-Linie bewegt sich so langsam, dass sie fast nie
die Richtung wechselt (beim S&P 500 lag der Kurs seit 2012 fast immer darueber) – fuer eine Phase taugt sie nicht.

Zusaetzlich die klassische Lesart: ab 20 % unter dem bisherigen Hoch spricht man von Baerenmarkt.

Pruefung ohne Zukunftswissen (wie bei der Ampel): fuer jedes Pruefjahr Y werden die Quoten
"wie oft stand der Kurs nach h Wochen hoeher, je Phase" nur aus Wochen bestimmt, deren Ergebnis
Ende Y-1 schon feststand. Damit werden die Wochen des Jahres Y vorhergesagt und mit dem spaeter
eingetretenen Ergebnis verglichen. Vergleich: Grundquote = Anteil aller bisherigen Wochen mit hoeherem Kurs.
Skill > 0 heisst: die Phase hat besser vorhergesagt als die Grundquote.
"""
import math
import numpy as np
import pandas as pd

LINIE = 40          # Wochen, entspricht etwa der 200-Tage-Linie
MOMENTUM = 52       # Wochen (12 Monate)
HORIZONTE = {"3m": 13, "1": 52}
MIN_FAELLE = 26     # so viele Lernwochen je Phase, sonst wird die Grundquote genommen
NAMEN = {0: "Abwärtstrend", 1: "Gemischt", 2: "Aufwärtstrend"}
BAER = -0.20


def phasen(close: np.ndarray) -> np.ndarray:
    """Phase je Woche (0/1/2, NaN solange zu wenig Historie)."""
    s = pd.Series(close)
    linie = s.rolling(LINIE).mean().values
    vor = s.shift(MOMENTUM).values
    with np.errstate(invalid="ignore"):
        ueber, hoeher = close > linie, close > vor
        unter, tiefer = close < linie, close < vor
    p = np.where(ueber & hoeher, 2.0, np.where(unter & tiefer, 0.0, 1.0))
    p[np.isnan(linie) | np.isnan(vor)] = np.nan
    return p


def _vorwaerts(close: np.ndarray, h: int) -> np.ndarray:
    n = len(close)
    f = np.full(n, np.nan)
    if n > h:
        f[:n - h] = close[h:] / close[:n - h] - 1
    return f


def _absturz(close: np.ndarray, low: np.ndarray, h: int = 52) -> np.ndarray:
    """1, wenn der Kurs in den naechsten h Wochen irgendwann mindestens 20 % unter dem heutigen lag."""
    n = len(close)
    out = np.full(n, np.nan)
    if n <= h:
        return out
    tief = pd.Series(low[::-1]).rolling(h).min().values[::-1]   # Minimum von t..t+h-1
    tief = np.concatenate([tief[1:], [np.nan]])                  # Minimum von t+1..t+h
    ok = np.arange(n) < n - h
    out[ok] = (tief[ok] / close[ok] - 1 <= BAER).astype(float)
    return out


def walk_forward(close: np.ndarray, phase: np.ndarray, jahr: np.ndarray, h: int) -> dict | None:
    n = len(close)
    if n <= h + 60:
        return None
    fwd = _vorwaerts(close, h)
    gueltig = ~np.isnan(phase)
    idx_l, p_l, b_l = [], [], []
    for Y in np.unique(jahr):
        vor = np.flatnonzero(jahr < Y)
        if len(vor) == 0:
            continue
        grenze = vor[-1] - h + 1
        if grenze <= 0:
            continue
        train = np.flatnonzero(gueltig[:grenze])
        if len(train) < MIN_FAELLE:
            continue
        in_y = np.flatnonzero(jahr == Y)
        test = in_y[gueltig[in_y] & (in_y < n - h)]
        if len(test) == 0:
            continue
        hoch = fwd[train] > 0
        basis = hoch.mean()
        quote = {}
        for k in (0, 1, 2):
            m = phase[train] == k
            quote[k] = hoch[m].mean() if m.sum() >= MIN_FAELLE else basis
        idx_l.append(test)
        p_l.append(np.array([quote[int(k)] for k in phase[test]]))
        b_l.append(np.full(len(test), basis))
    if not idx_l:
        return None
    idx = np.concatenate(idx_l)
    return {"p": np.concatenate(p_l), "basis": np.concatenate(b_l), "treffer": (fwd[idx] > 0).astype(float),
            "fwd": fwd[idx], "phase": phase[idx], "jahr": jahr[idx]}


class Sammler:
    """Summen ueber einen oder viele Werte (fuer die Gruppen-Pruefung in pruefung.json)."""

    def __init__(self):
        self.h = {k: {"bm": 0.0, "bb": 0.0, "n": 0.0, "ph_n": np.zeros(3), "ph_t": np.zeros(3), "ph_log": np.zeros(3),
                      "alle_t": 0.0, "alle_log": 0.0, "j0": 9999, "j1": 0, "werte": 0} for k in HORIZONTE}
        self.werte = 0

    def add(self, close, phase, jahr):
        beitrag = False
        for k, h in HORIZONTE.items():
            wf = walk_forward(close, phase, jahr, h)
            if wf is None:
                continue
            beitrag = True
            a = self.h[k]
            t = wf["treffer"]
            lg = np.log1p(wf["fwd"])
            a["bm"] += ((wf["p"] - t) ** 2).sum(); a["bb"] += ((wf["basis"] - t) ** 2).sum(); a["n"] += len(t)
            a["alle_t"] += t.sum(); a["alle_log"] += lg.sum()
            for ph in (0, 1, 2):
                m = wf["phase"] == ph
                a["ph_n"][ph] += m.sum(); a["ph_t"][ph] += t[m].sum(); a["ph_log"][ph] += lg[m].sum()
            a["j0"] = int(min(a["j0"], wf["jahr"].min())); a["j1"] = int(max(a["j1"], wf["jahr"].max())); a["werte"] += 1
        if beitrag:
            self.werte += 1

    def ergebnis(self) -> dict:
        out = {"werte": self.werte}
        for k, h in HORIZONTE.items():
            a = self.h[k]
            if not a["n"]:
                out[k] = None
                continue
            q = lambda t, n: None if not n else round(float(t / n) * 100, 1)
            rpa = lambda lg, n: None if not n else round((math.exp(lg / n * 52 / h) - 1) * 100, 1)
            out[k] = {
                "skill": round((1 - a["bm"] / a["bb"]) * 100, 1) if a["bb"] else None,
                "vorhersagen": int(a["n"]), "jahr_von": a["j0"], "jahr_bis": a["j1"], "werte": a["werte"],
                "alle": {"n": int(a["n"]), "quote": q(a["alle_t"], a["n"]), "rendite_pa": rpa(a["alle_log"], a["n"])},
                "phasen": [{"phase": ph, "name": NAMEN[ph], "n": int(a["ph_n"][ph]), "quote": q(a["ph_t"][ph], a["ph_n"][ph]),
                            "rendite_pa": rpa(a["ph_log"][ph], a["ph_n"][ph])} for ph in (2, 1, 0)],
            }
        return out


def fuer_wert(w: pd.DataFrame) -> dict | None:
    """Heutige Phase, Rueckblick je Phase (ganze Historie) und Pruefung ohne Zukunftswissen fuer einen Wert."""
    c = w["Close"].values.astype(float)
    low = w["Low"].values.astype(float) if "Low" in w else c
    ph = phasen(c)
    if np.isnan(ph[-1]):
        return None
    jahr = w.index.year.values
    t_unix = [int(x) for x in (w.index - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)]
    jetzt = int(ph[-1])
    i = len(ph) - 1
    while i > 0 and ph[i - 1] == jetzt:
        i -= 1
    linie = pd.Series(c).rolling(LINIE).mean().values
    hoch = np.maximum.accumulate(c)
    dd = c[-1] / hoch[-1] - 1
    # wie lange schon 20 % unter dem Hoch (klassischer Baerenmarkt)?
    baer_seit = None
    if dd <= BAER:
        j = len(c) - 1
        while j > 0 and c[j - 1] / hoch[j - 1] - 1 <= BAER:
            j -= 1
        baer_seit = w.index[j].strftime("%Y-%m-%d")
    rueck = {}
    absturz = _absturz(c, low)
    for k, h in HORIZONTE.items():
        f = _vorwaerts(c, h)
        zeilen = []
        for p_ in (2, 1, 0, None):
            m = (~np.isnan(f)) & (~np.isnan(ph)) & ((ph == p_) if p_ is not None else True)
            n = int(m.sum())
            z = {"phase": p_, "n": n,
                 "quote": round(float((f[m] > 0).mean()) * 100, 1) if n else None,
                 "median": round(float(np.median(f[m])) * 100, 1) if n else None}
            if h == 52:
                ma = m & ~np.isnan(absturz)
                z["absturz"] = round(float(absturz[ma].mean()) * 100, 1) if ma.sum() else None
            zeilen.append(z)
        rueck[k] = zeilen
    s = Sammler()
    s.add(c, ph, jahr)
    return {
        "phase": jetzt, "name": NAMEN[jetzt], "seit": w.index[i].strftime("%Y-%m-%d"),
        "zu_linie": round(float(c[-1] / linie[-1] - 1) * 100, 1),
        "mom12": round(float(c[-1] / c[-1 - MOMENTUM] - 1) * 100, 1),
        "dd": round(float(dd) * 100, 1), "baer_seit": baer_seit,
        "wochen": len(c) - int(np.isnan(ph).sum()), "ab": w.index[int(np.argmax(~np.isnan(ph)))].strftime("%Y-%m-%d"),
        "rueckblick": rueck,
        "pruefung": s.ergebnis(),
        "verlauf": "".join("-" if np.isnan(x) else str(int(x)) for x in ph),   # je Woche ein Zeichen (- = noch keine Phase)
        "_phase_arr": ph,
    }
