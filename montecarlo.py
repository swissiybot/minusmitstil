"""Monte-Carlo-Rechner: Wahrscheinlichkeitskegel und "Wird Kurs X in 12 Monaten erreicht?".

Methode: Block-Bootstrap der echten Wochenrenditen (keine Normalverteilung). Aus der Historie
(Standard: letzte 20 Jahre) werden zufaellig zusammenhaengende Bloecke von 13 Wochen gezogen und
aneinandergehaengt. So bleiben ruhige und stuermische Phasen, Crashs und Erholungen so, wie sie
wirklich vorkamen. Je Woche werden Schluss, Wochentief und Wochenhoch gemeinsam gezogen; damit
zaehlt auch, wenn ein Kauflimit nur kurz innerhalb der Woche beruehrt wird.

Grenze: Die Zukunft muss der Vergangenheit nicht aehneln; die Durchschnittsrendite der gewaehlten
Jahre steckt in den Pfaden. Wird live im Server berechnet (Millisekunden), nichts wird gespeichert.
"""
import zlib
import numpy as np
import pandas as pd

QUANTILE = [5, 25, 50, 75, 95]


def simulation(w: pd.DataFrame, wochen: int = 52, jahre: int = 20, pfade: int = 10000, block: int = 13,
               seed_text: str = "") -> dict | None:
    w = w[w.index >= w.index[-1] - pd.DateOffset(years=jahre)]
    c = w["Close"].values.astype(float)
    if len(c) < 104:
        return None
    lo = w["Low"].values.astype(float)[1:]
    hi = w["High"].values.astype(float)[1:]
    vor = c[:-1]
    r_c = np.log(c[1:] / vor)
    r_l = np.where(np.isnan(lo) | (lo <= 0), np.minimum(r_c, 0), np.log(lo / vor))
    r_h = np.where(np.isnan(hi) | (hi <= 0), np.maximum(r_c, 0), np.log(hi / vor))
    r_l = np.minimum(r_l, np.minimum(r_c, 0))      # Tief nie ueber Schluss/Vorwoche
    r_h = np.maximum(r_h, np.maximum(r_c, 0))
    m = len(r_c)
    block = min(block, m // 4)
    rng = np.random.default_rng(zlib.crc32(f"{seed_text}|{len(c)}|{c[-1]:.6g}".encode()))
    n_bl = -(-wochen // block)
    starts = rng.integers(0, m - block + 1, size=(pfade, n_bl))
    ind = (starts[:, :, None] + np.arange(block)).reshape(pfade, -1)[:, :wochen]
    log_pfad = np.cumsum(r_c[ind], axis=1)                    # Schluss relativ zu heute
    vorher = np.concatenate([np.zeros((pfade, 1)), log_pfad[:, :-1]], axis=1)
    tief = np.minimum.accumulate(vorher + r_l[ind], axis=1)   # tiefster Stand bis Woche k
    hoch = np.maximum.accumulate(vorher + r_h[ind], axis=1)
    p0 = float(c[-1])
    return {"p0": p0, "pfad": np.exp(log_pfad) * p0, "tief": np.exp(tief[:, -1]) * p0, "hoch": np.exp(hoch[:, -1]) * p0,
            "letzte": w.index[-1], "von": w.index[0], "wochen": wochen, "pfade": pfade, "block": block,
            "jahre_hist": round((w.index[-1] - w.index[0]).days / 365.25, 1)}


def wahrscheinlichkeit(sim: dict, preis: float) -> dict:
    p0 = sim["p0"]
    if preis <= p0:
        beruehrt = float((sim["tief"] <= preis).mean())
        ende = float((sim["pfad"][:, -1] <= preis).mean())
        art = "Kauflimit"
    else:
        beruehrt = float((sim["hoch"] >= preis).mean())
        ende = float((sim["pfad"][:, -1] >= preis).mean())
        art = "Verkaufsziel"
    return {"preis": round(preis, 6), "abstand": round((preis / p0 - 1) * 100, 1), "art": art,
            "beruehrt": round(beruehrt * 100, 1), "ende": round(ende * 100, 1)}


def ergebnis(sim: dict, preise: list[float]) -> dict:
    q = np.percentile(sim["pfad"], QUANTILE, axis=0)
    t0 = sim["letzte"]
    t = [int(((t0 + pd.Timedelta(weeks=k + 1)) - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)) for k in range(sim["wochen"])]
    t_heute = int((t0 - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1))
    kegel = {f"q{p}": [round(sim["p0"], 6)] + [float(f"{v:.5g}") for v in q[i]] for i, p in enumerate(QUANTILE)}
    standard = [sim["p0"] * f for f in (0.7, 0.8, 0.9, 0.95, 1.05, 1.1, 1.2, 1.3)]
    return {
        "kurs": round(sim["p0"], 6), "wochen": sim["wochen"], "pfade": sim["pfade"], "block": sim["block"],
        "hist_von": sim["von"].strftime("%Y-%m-%d"), "hist_jahre": sim["jahre_hist"],
        "t": [t_heute] + t, "kegel": kegel,
        "ende_median": round(float(np.median(sim["pfad"][:, -1])), 6),
        "verlust_wahrsch": round(float((sim["pfad"][:, -1] < sim["p0"]).mean()) * 100, 1),
        "standard": [wahrscheinlichkeit(sim, p) for p in standard],
        "eigene": [wahrscheinlichkeit(sim, p) for p in preise if p > 0],
    }
