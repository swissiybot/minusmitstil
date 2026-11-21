"""Walk-forward-Pruefung und Kalibrierung der Ampel-Wahrscheinlichkeit.

Frage: Haette die angezeigte Wahrscheinlichkeit ("in X % der aehnlichen Lagen stand der Kurs
nach 1/3/5 Jahren hoeher") in der Vergangenheit gestimmt, wenn man sie damals nur mit dem
damaligen Wissen berechnet haette?

Vorgehen (Walk-forward mit jaehrlicher Neufestlegung):
  Fuer jedes Pruefjahr Y werden die Regeln (Zuordnung Ampel -> Wahrscheinlichkeit) NUR aus
  Wochen bestimmt, deren Ergebnis Ende des Jahres Y-1 schon feststand (Woche + Horizont <= Ende Y-1).
  Damit werden alle Wochen des Jahres Y vorhergesagt und mit dem spaeter tatsaechlich
  eingetretenen Ergebnis verglichen. Die Ampel selbst ist ohnehin ohne Zukunftswissen berechnet.

Kalibrierung: angezeigte Quote (in 10er-Schritten gruppiert) gegen eingetretene Quote.
Brier-Wert: mittlerer quadratischer Fehler der Vorhersage; verglichen mit der einfachen
Vorhersage "Anteil aller bisherigen Wochen mit hoeherem Kurs" (Basis). Skill > 0 heisst:
die Ampel hat ausserhalb der Lernzeit etwas besser vorhergesagt als die Basis.
"""
import math
import numpy as np

HORIZONTE = {"1": 52, "3": 156, "5": 260}   # Wochen
AEHNLICH = 7.5
MIN_FAELLE = 8
ZONEN = [  # (Name, Bedingung) – dieselben Stufen wie im Strategie-Vergleich
    ("≥ 90", lambda s: s >= 90),
    ("75–90", lambda s: (s >= 75) & (s < 90)),
    ("60–75", lambda s: (s >= 60) & (s < 75)),
    ("40–60", lambda s: (s > 40) & (s < 60)),
    ("15–40", lambda s: (s > 15) & (s <= 40)),
    ("≤ 15", lambda s: s <= 15),
]
N_BINS = 10
VIELE_FAELLE = 52   # zweite Kurve: nur Vorhersagen aus mindestens so vielen aehnlichen Wochen


def walk_forward(close: np.ndarray, score: np.ndarray, jahr: np.ndarray, h: int,
                 aehnlich: float = AEHNLICH, min_faelle: int = MIN_FAELLE) -> dict | None:
    """Vorhersagen ausserhalb der Lernzeit fuer einen Wert und einen Horizont h (Wochen)."""
    n = len(close)
    if n <= h + 60:
        return None
    fwd = np.full(n, np.nan)
    fwd[:n - h] = close[h:] / close[:n - h] - 1
    gueltig = ~np.isnan(score)
    idx_l, p_l, b_l, a_l = [], [], [], []
    for Y in np.unique(jahr):
        vor = np.flatnonzero(jahr < Y)
        if len(vor) == 0:
            continue
        grenze = vor[-1] - h + 1               # Wochen t < grenze: Ergebnis Ende Y-1 bekannt
        if grenze <= 0:
            continue
        train = np.flatnonzero(gueltig[:grenze])
        if len(train) < min_faelle:
            continue
        in_y = np.flatnonzero(jahr == Y)
        test = in_y[gueltig[in_y] & (in_y < n - h)]
        if len(test) == 0:
            continue
        ts = score[train]
        th = fwd[train] > 0
        o = np.argsort(ts)
        ts = ts[o]
        kum = np.concatenate([[0], np.cumsum(th[o])])
        lo = np.searchsorted(ts, score[test] - aehnlich, "left")
        hi = np.searchsorted(ts, score[test] + aehnlich, "right")
        anz = hi - lo
        p = np.where(anz >= min_faelle, (kum[hi] - kum[lo]) / np.maximum(anz, 1), np.nan)
        idx_l.append(test); p_l.append(p); b_l.append(np.full(len(test), th.mean())); a_l.append(anz)
    if not idx_l:
        return None
    idx = np.concatenate(idx_l)
    return {"idx": idx, "p": np.concatenate(p_l), "basis": np.concatenate(b_l), "anz": np.concatenate(a_l),
            "treffer": fwd[idx] > 0, "fwd": fwd[idx], "score": score[idx], "jahr": jahr[idx]}


class Sammler:
    """Zaehlt Ergebnisse (fuer einen Wert oder ueber viele Werte) – nur Summen, wenig Speicher."""

    def __init__(self):
        self.h = {k: self._leer() for k in HORIZONTE}
        self.werte = 0

    @staticmethod
    def _leer():
        return {"bin_n": np.zeros(N_BINS), "bin_p": np.zeros(N_BINS), "bin_t": np.zeros(N_BINS),
                "zone_n": np.zeros(len(ZONEN)), "zone_t": np.zeros(len(ZONEN)), "zone_log": np.zeros(len(ZONEN)),
                "alle_n": 0.0, "alle_t": 0.0, "alle_log": 0.0,
                "brier_m": 0.0, "brier_b": 0.0, "brier_n": 0.0,
                "v_bin_n": np.zeros(N_BINS), "v_bin_p": np.zeros(N_BINS), "v_bin_t": np.zeros(N_BINS),
                "v_brier_m": 0.0, "v_brier_b": 0.0, "v_brier_n": 0.0,
                "jahr_min": 9999, "jahr_max": 0, "werte": 0}

    def add(self, close, score, jahr):
        beitrag = False
        for k, h in HORIZONTE.items():
            wf = walk_forward(close, score, jahr, h)
            if wf is None:
                continue
            beitrag = True
            a = self.h[k]
            t = wf["treffer"].astype(float)
            lg = np.log1p(wf["fwd"])
            a["alle_n"] += len(t); a["alle_t"] += t.sum(); a["alle_log"] += lg.sum()
            for i, (_, bed) in enumerate(ZONEN):
                m = bed(wf["score"])
                a["zone_n"][i] += m.sum(); a["zone_t"][i] += t[m].sum(); a["zone_log"][i] += lg[m].sum()
            for vor, ok in (("", ~np.isnan(wf["p"])), ("v_", ~np.isnan(wf["p"]) & (wf["anz"] >= VIELE_FAELLE))):
                if not ok.any():
                    continue
                p = wf["p"][ok]; tt = t[ok]
                b = np.minimum((p * N_BINS).astype(int), N_BINS - 1)
                np.add.at(a[vor + "bin_n"], b, 1); np.add.at(a[vor + "bin_p"], b, p); np.add.at(a[vor + "bin_t"], b, tt)
                a[vor + "brier_m"] += ((p - tt) ** 2).sum(); a[vor + "brier_b"] += ((wf["basis"][ok] - tt) ** 2).sum()
                a[vor + "brier_n"] += ok.sum()
            a["jahr_min"] = int(min(a["jahr_min"], wf["jahr"].min())); a["jahr_max"] = int(max(a["jahr_max"], wf["jahr"].max()))
            a["werte"] += 1
        if beitrag:
            self.werte += 1

    def ergebnis(self) -> dict:
        def q(t, n):
            return None if n == 0 else round(float(t / n) * 100, 1)

        def rpa(lg, n, h):
            return None if n == 0 else round((math.exp(lg / n * 52 / h) - 1) * 100, 1)

        out = {"werte": self.werte}
        for k, h in HORIZONTE.items():
            a = self.h[k]
            if a["alle_n"] == 0:
                out[k] = None
                continue
            def bins_von(v):
                return [{"von": i * 10, "bis": i * 10 + 10, "n": int(a[v + "bin_n"][i]),
                         "angezeigt": q(a[v + "bin_p"][i], a[v + "bin_n"][i]), "eingetreten": q(a[v + "bin_t"][i], a[v + "bin_n"][i])}
                        for i in range(N_BINS) if a[v + "bin_n"][i] > 0]

            def skill(v):
                if not a[v + "brier_n"] or not a[v + "brier_b"]:
                    return None
                return round((1 - a[v + "brier_m"] / a[v + "brier_b"]) * 100, 1)
            bins = bins_von("")
            zonen = [{"zone": ZONEN[i][0], "n": int(a["zone_n"][i]), "quote": q(a["zone_t"][i], a["zone_n"][i]),
                      "rendite_pa": rpa(a["zone_log"][i], a["zone_n"][i], h)} for i in range(len(ZONEN))]
            bm = a["brier_m"] / a["brier_n"] if a["brier_n"] else None
            bb = a["brier_b"] / a["brier_n"] if a["brier_n"] else None
            out[k] = {
                "bins": bins, "zonen": zonen,
                "alle": {"n": int(a["alle_n"]), "quote": q(a["alle_t"], a["alle_n"]), "rendite_pa": rpa(a["alle_log"], a["alle_n"], h)},
                "brier_modell": None if bm is None else round(bm, 4), "brier_basis": None if bb is None else round(bb, 4),
                "skill": skill(""),
                "bins_viele": bins_von("v_"), "skill_viele": skill("v_"), "vorhersagen_viele": int(a["v_brier_n"]),
                "vorhersagen": int(a["brier_n"]), "jahr_von": a["jahr_min"], "jahr_bis": a["jahr_max"], "werte": a["werte"],
            }
        return out


def fuer_wert(close: np.ndarray, score: np.ndarray, jahr: np.ndarray) -> dict:
    s = Sammler()
    s.add(close, score, jahr)
    return s.ergebnis()
