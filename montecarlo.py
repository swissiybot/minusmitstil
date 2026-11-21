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


# Standard-Einstellungen: die Variante mit der besten Trefferquote aus kegelpruefung.py (daten/kegelpruefung.json).
# Ergebnis 21.11.2026: „Schwankung von heute, abklingend 13 Wochen“ (Abstand 3,2 statt 4,2 Punkte zu 90 %/50 %).
STANDARD = {"jahre": 20, "vol_tau": 13, "drift": 1.0}
try:
    import json as _json
    import einstellungen as _E
    _f = _E.DATEN / "kegelpruefung.json"
    if _f.exists():
        STANDARD.update(_json.loads(_f.read_text()).get("sieger_einst") or {})
except Exception:
    pass


def simulation(w: pd.DataFrame, wochen: int = 52, jahre: int | None = None, pfade: int = 10000, block: int = 13,
               seed_text: str = "", kegel_wochen: int | None = None, ab=None,
               vol_tau: float | None = "standard", drift: float | None = None) -> dict | None:
    """wochen: Zeitraum fuer Wahrscheinlichkeiten (Kauflimit, Verlust ...); kegel_wochen: so weit reicht der Kegel im Chart.
    ab: fruehester Tag der Historie (Bitcoin: erst ab Yahoo-Start).
    vol_tau: Schwankung von heute (EWMA) statt Durchschnitt, klingt mit dieser Zeitkonstante (Wochen) zum Mittel ab; None = aus.
    drift: Anteil der historischen Durchschnittsrendite, der in die Pfade geht (1 = wie gewesen, 0.5 = vorsichtiger)."""
    jahre = STANDARD["jahre"] if jahre is None else jahre
    vol_tau = STANDARD["vol_tau"] if vol_tau == "standard" else vol_tau
    drift = STANDARD["drift"] if drift is None else drift
    w = w[w.index >= w.index[-1] - pd.DateOffset(years=jahre)]
    if ab is not None:
        w = w[w.index >= ab]
    lang = max(wochen, kegel_wochen or wochen)
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
    n_bl = -(-lang // block)
    starts = rng.integers(0, m - block + 1, size=(pfade, n_bl))
    ind_lang = (starts[:, :, None] + np.arange(block)).reshape(pfade, -1)[:, :lang]
    mu = float(r_c.mean())
    if vol_tau or drift != 1.0:
        # Abweichung vom Mittel skalieren (aktuelle Schwankung, abklingend) und Grundrendite anpassen
        skala = np.ones(lang)
        if vol_tau:
            abw = r_c - mu
            ew = abw[0] ** 2
            for x in abw[1:]:
                ew = 0.94 * ew + 0.06 * x * x
            s_rel = float(np.clip(np.sqrt(ew) / abw.std(), 0.5, 3.0))
            skala = 1 + (s_rel - 1) * np.exp(-np.arange(lang) / vol_tau)
        rc_p = mu * drift + (r_c[ind_lang] - mu) * skala
        rl_p = rc_p + (r_l[ind_lang] - r_c[ind_lang]) * skala
        rh_p = rc_p + (r_h[ind_lang] - r_c[ind_lang]) * skala
    else:
        rc_p, rl_p, rh_p = r_c[ind_lang], r_l[ind_lang], r_h[ind_lang]
    kegel_log = np.cumsum(rc_p, axis=1)
    ind = ind_lang[:, :wochen]                                 # gleiche Pfade, nur die ersten Wochen
    log_pfad = kegel_log[:, :wochen]                           # Schluss relativ zu heute
    vorher = np.concatenate([np.zeros((pfade, 1)), log_pfad[:, :-1]], axis=1)
    tief = np.minimum.accumulate(vorher + rl_p[:, :wochen], axis=1)   # tiefster Stand bis Woche k
    hoch = np.maximum.accumulate(vorher + rh_p[:, :wochen], axis=1)
    p0 = float(c[-1])
    return {"p0": p0, "pfad": np.exp(log_pfad) * p0, "kegel_pfad": np.exp(kegel_log) * p0, "kegel_wochen": lang, "tief": np.exp(tief[:, -1]) * p0, "hoch": np.exp(hoch[:, -1]) * p0,
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
    q = np.percentile(sim["kegel_pfad"], QUANTILE, axis=0)
    t0 = sim["letzte"]
    t = [int(((t0 + pd.Timedelta(weeks=k + 1)) - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)) for k in range(sim["kegel_wochen"])]
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
