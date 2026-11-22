"""Berechnet fuer jeden Wert Ampel, Rendite, Wahrscheinlichkeiten und schreibt die Dashboard-Daten.

Grundsatz: Jede Kennzahl zum Zeitpunkt t wird NUR mit der Historie bis t verglichen
(kein Blick in die Zukunft). Nur so sind die Trefferquoten aus der Vergangenheit ehrlich.

Ampel (0-100, hoch = historisch guenstig), seit 22.11.2026 abends: je Gruppe 3-4 Bausteine aus der Ampel-Studie
(AMPEL_BAUSTEINE), jeder als Perzentil gegen alle frueheren Wochen desselben Werts; Ampel = 100 - Mittel der Perzentile.
(22.11. mittags: nur Kurs / 200-Wochen-Linie; bis 21.11.: Allzeithoch, 200-Wochen-Abstand, Langfristtrend, Wochen-RSI.)
Bitcoin: Pi Cycle Bottom/Top als Markierung.
Pi Cycle Bottom: faellt die 150-Tage-EMA UNTER die 471-Tage-SMA x 0,745, beginnt die
Bodenbildungszone; steigt sie wieder DARUEBER, ist das das Boden-Signal. Der Boden liegt laut Indikator
zwischen beiden Kreuzungen. EMA ueber der Linie = Aufwaertstrend bzw. Bodenbildung noch nicht begonnen.

Wahrscheinlichkeit: alle frueheren Wochen mit aehnlicher Ampel (+-7,5 Punkte) -> Anteil, bei dem der
Kurs 1/3/5 Jahre spaeter hoeher stand, Median-Rendite, Rueckschlagrisiko; Vergleich: alle Wochen.
"""
import bisect
import json
import math
import sys
import datetime as dt
import numpy as np
import pandas as pd

import warnings
import einstellungen as E
from kurse import lade_lokal, alle_laden

warnings.filterwarnings("ignore", category=RuntimeWarning)

H1, H3, H5 = 52, 156, 260          # Wochen
AEHNLICH = 7.5                       # Ampel-Spanne fuer "aehnliche Lage"
WARMUP = 260                         # Wochen Historie, bevor eine Ampel berechnet wird
VORL_WARMUP = 104                    # vorläufige Ampel (nur Anzeige im Chart) schon ab 2 Jahren Historie

QUELLEN_TEXT = {
    "index": ("Index ohne Dividenden", False),
    "index_tr": ("Index mit Dividenden", True),
    "vorlauf_etf": ("aehnlicher ETF als Vorlauf", True),
    "etf": ("ETF", True),
    "aktie": ("Aktie", True),
    "krypto": ("Krypto", False),
    "krypto_cm": ("Coin Metrics Community-Daten (nur Tagespreis, keine Kerzen)", False),
    "krypto_bs": ("Bitstamp (Börse, Tageskerzen)", False),
    "rohstoff": ("Endlos-Future (Spruenge beim Kontraktwechsel, ohne Rollkosten)", False),
}


# ----------------------------------------------------------------- Daten zusammensetzen
def verketten(etf: dict):
    """Index-Historie vor den ETF haengen (skaliert). Gibt Tagesdaten + Segmentliste zurueck."""
    kette = [(k, etf.get(k)) for k in ("index", "index_tr", "vorlauf_etf")] + [("etf", etf["etf"])]
    kette = [(k, s) for k, s in kette if s]
    akt, segmente = None, []
    for art, sym in reversed(kette):
        d = lade_lokal(sym)
        if d is None or d.empty:
            continue
        if akt is None:
            akt, segmente = d.copy(), [(d.index[0], art, sym)]
            continue
        start = akt.index[0]
        vor = d[d.index < start]
        if vor.empty:
            continue
        ref = d["Close"].asof(start)
        if not ref or math.isnan(ref):
            continue
        f = akt["Close"].iloc[0] / ref
        vor = vor.copy()
        for c in ("Open", "High", "Low", "Close"):
            vor[c] = vor[c] * f
        akt = pd.concat([vor, akt])
        segmente.insert(0, (vor.index[0], art, sym))
    return akt, segmente


def wochen(d: pd.DataFrame) -> pd.DataFrame:
    w = d.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    return w.dropna(subset=["Close"])


# ----------------------------------------------------------------- Kennzahlen
def expandierendes_perzentil(x: np.ndarray, start: int) -> np.ndarray:
    """Anteil der bisherigen Werte (bis einschl. t), die kleiner sind als x[t]. NaN vor 'start'."""
    out = np.full(len(x), np.nan)
    sortiert: list[float] = []
    for t, v in enumerate(x):
        if math.isnan(v):
            continue
        bisect.insort(sortiert, v)
        if t >= start and len(sortiert) > 50:
            out[t] = bisect.bisect_left(sortiert, v) / len(sortiert)
    return out


def trend_z(logp: np.ndarray) -> np.ndarray:
    """Abweichung vom expandierenden log-linearen Trend (nur Vergangenheit) in Standardabweichungen."""
    n = len(logp)
    t = np.arange(n, dtype=float)
    S1 = np.cumsum(np.ones(n)); St = np.cumsum(t); Sy = np.cumsum(logp)
    Stt = np.cumsum(t * t); Sty = np.cumsum(t * logp); Syy = np.cumsum(logp * logp)
    nenner = S1 * Stt - St * St
    with np.errstate(invalid="ignore", divide="ignore"):
        b = (S1 * Sty - St * Sy) / nenner
        a = (Sy - b * St) / S1
        ssr = np.maximum(Syy - a * Sy - b * Sty, 0)
        sd = np.sqrt(ssr / np.maximum(S1 - 2, 1))
        z = (logp - (a + b * t)) / sd
    z[:104] = np.nan
    return z


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    auf = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    ab = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + auf / ab)


def jahresrendite(tag: pd.Series, jahre: int):
    """Durchschnittliche Jahresrendite (CAGR) ueber 'jahre' oder ueber die verfuegbare Zeit."""
    ende = tag.index[-1]
    start_soll = ende - pd.DateOffset(years=jahre)
    if tag.index[0] <= start_soll + pd.Timedelta(days=10):
        s = tag[tag.index >= start_soll]
    else:
        s = tag
    j = (s.index[-1] - s.index[0]).days / 365.25
    if j < 1:
        return None, j, s.index[0]
    return (s.iloc[-1] / s.iloc[0]) ** (1 / j) - 1, j, s.index[0]


def kaufzonen_verlauf(c: np.ndarray, roh: dict, perz: dict, score: np.ndarray) -> dict:
    """Kaufzonen fuer jede Woche (wandern mit): Kurs, bei dem die Ampel in DIESER Woche 80 / 60 / 40 / 15 gezeigt haette.
    Gleiche Rechnung wie die Ampel: jeder Baustein wird fuer einen gedachten Schlusskurs p neu berechnet und mit allen
    frueheren Wochen verglichen (Perzentil = Anzahl frueherer Werte < Wert / (Anzahl + 1), genau wie
    expandierendes_perzentil). p wird per Halbierung gesucht, fuer alle Wochen gleichzeitig (numpy).
    Die letzte Woche ergibt die Kaufzonen von heute."""
    n = len(c)
    out = {z: np.full(n, np.nan) for z in (80, 60, 40, 15)}
    sel_alle = np.flatnonzero(~np.isnan(score))
    if len(sel_alle) == 0:
        return out
    logp = np.log(c)
    k_idx = np.arange(n, dtype=float)
    cum = lambda a: np.concatenate([[0.0], np.cumsum(a)])
    C, Clp, Ctlp, Clp2 = cum(c), cum(logp), cum(k_idx * logp), cum(logp * logp)
    ath_vor = np.concatenate([[np.nan], np.maximum.accumulate(c)[:-1]])

    def f(k, t, p):   # Baustein k in Woche t fuer gedachten Kurs p (Vektoren)
        if k == "dd":
            return p / np.maximum(ath_vor[t], p) - 1
        if k == "ratio":
            s199 = C[t] - C[t - 199]
            return p / ((s199 + p) / 200)
        if k == "r3j":
            return p / c[t - 156] - 1
        if k == "r5j":
            return p / c[t - 260] - 1
        if k == "mvrv":
            return roh["mvrv"][t] * p / c[t]
        if k == "trend":   # log-linearer Trend ueber Woche 0..t inklusive des gedachten Kurses
            lp = np.log(p); tf = t.astype(float); S1 = tf + 1
            St = tf * (tf + 1) / 2; Stt = tf * (tf + 1) * (2 * tf + 1) / 6
            Sy = Clp[t] + lp; Sty = Ctlp[t] + tf * lp; Syy = Clp2[t] + lp * lp
            nen = S1 * Stt - St * St
            b = (S1 * Sty - St * Sy) / nen; a = (Sy - b * St) / S1
            sd = np.sqrt(np.maximum(Syy - a * Sy - b * Sty, 0) / np.maximum(S1 - 2, 1))
            return np.where(sd > 0, (lp - (a + b * tf)) / np.where(sd > 0, sd, 1), 0.0)
        raise KeyError(k)

    teile = [k for k in roh if k in perz]
    for start in range(0, len(sel_alle), 400):   # in Stuecken, damit der Speicher klein bleibt
        T = sel_alle[start:start + 400]
        m = len(T)
        daten = {}
        for k in teile:
            x = roh[k]
            G = np.sort(x[~np.isnan(x)])
            if len(G) == 0:
                continue
            M = len(G) + 1
            rang = np.searchsorted(G, x, "left")
            pref = np.sort(rang[:T[0]][~np.isnan(x[:T[0]])])
            stuecke, offs, anz, zuletzt = [], np.zeros(m, dtype=np.int64), np.zeros(m), T[0]
            pos = 0
            for i, t in enumerate(T):
                if t > zuletzt:
                    neu = rang[zuletzt:t][~np.isnan(x[zuletzt:t])]
                    if len(neu):
                        pref = np.sort(np.concatenate([pref, neu]))
                    zuletzt = t
                stuecke.append(i * M + pref); offs[i] = pos; anz[i] = len(pref); pos += len(pref)
            flach = np.concatenate(stuecke) if stuecke else np.zeros(0, dtype=np.int64)
            aktiv = ~np.isnan(perz[k][T])
            daten[k] = (G, M, flach, offs, anz, aktiv)
        if not daten:
            continue
        ii = np.arange(m)

        def ampel(p):
            summe = np.zeros(m); zahl = np.zeros(m)
            for k, (G, M, flach, offs, anz, aktiv) in daten.items():
                with np.errstate(invalid="ignore", divide="ignore"):
                    v = f(k, T, p)
                ok = aktiv & ~np.isnan(v)
                rv = np.searchsorted(G, np.where(ok, v, 0.0), "left")
                cnt = np.searchsorted(flach, ii * M + rv, "left") - offs
                summe += np.where(ok, cnt / (anz + 1), 0.0); zahl += ok
            with np.errstate(invalid="ignore"):
                return np.where(zahl >= 2, (1 - summe / np.maximum(zahl, 1)) * 100, np.nan)

        ct = c[T]
        a_lo, a_hi = ampel(ct / 50), ampel(ct * 50)
        for ziel in out:
            gueltig = (a_lo >= ziel) & (a_hi <= ziel)
            lo, hi = ct / 50, ct * 50
            for _ in range(16):
                mid = np.sqrt(lo * hi)
                g = ampel(mid) >= ziel
                lo = np.where(g, mid, lo); hi = np.where(g, hi, mid)
            out[ziel][T] = np.where(gueltig, np.sqrt(lo * hi), np.nan)
    return out


def trendguete(w: pd.Series, jahre: int = 20) -> float:
    s = w[w.index >= w.index[-1] - pd.DateOffset(years=jahre)]
    if len(s) < 104:
        return float("nan")
    y = np.log(s.values); x = np.arange(len(y))
    r = np.corrcoef(x, y)[0, 1]
    return float(r * r) if r > 0 else 0.0


def episoden(maske: np.ndarray) -> int:
    idx = np.flatnonzero(maske)
    if len(idx) == 0:
        return 0
    return int(1 + np.sum(np.diff(idx) > 13))


def statistik(close: np.ndarray, low: np.ndarray, score: np.ndarray, s_jetzt: float):
    n = len(close)
    erg = {}
    gueltig = ~np.isnan(score)
    aehnlich = gueltig & (np.abs(score - s_jetzt) <= AEHNLICH)
    for name, h in (("1", H1), ("3", H3), ("5", H5)):
        m_a = aehnlich.copy(); m_a[n - h:] = False
        m_b = gueltig.copy(); m_b[n - h:] = False
        if m_a.sum() < 8:
            erg[name] = None
            continue
        fwd = np.full(n, np.nan); fwd[:n - h] = close[h:] / close[:n - h] - 1
        a, b = fwd[m_a], fwd[m_b]
        erg[name] = {
            "quote": round(float((a > 0).mean()) * 100, 1),
            "basis": round(float((b > 0).mean()) * 100, 1),
            "median": round(float(np.median(a)) * 100, 1),
            "median_pa": round(((1 + float(np.median(a))) ** (52 / h) - 1) * 100, 1),
            "basis_median_pa": round(((1 + float(np.median(b))) ** (52 / h) - 1) * 100, 1),
            "wochen": int(m_a.sum()),
            "episoden": episoden(m_a),
        }
    # Rueckschlagrisiko: faellt der Kurs innerhalb eines Jahres noch mind. 10 % unter den Kaufkurs?
    m = aehnlich.copy(); m[n - H1:] = False
    if m.sum() >= 8:
        tiefer = []
        for t in np.flatnonzero(m):
            mn = np.nanmin(low[t + 1:t + 1 + H1]) / close[t] - 1
            tiefer.append(mn)
        tiefer = np.array(tiefer)
        erg["rueckschlag10"] = round(float((tiefer <= -0.10).mean()) * 100, 1)
        erg["median_tiefer"] = round(float(np.median(tiefer)) * 100, 1)
    return erg


# ----------------------------------------------------------------- ein Wert
def zone(s):
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return "keine Daten"
    if s >= 80: return "historisch sehr guenstig"
    if s >= 60: return "guenstig"
    if s > 40: return "neutral"
    if s > 15: return "teuer"
    return "historisch sehr teuer"


def r(x, n=2):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), n)


AMPEL_BAUSTEINE = {   # Bausteine der Ampel je Gruppe (Ergebnis der Ampel-Studie vom 21.11.2026, siehe README); seit 22.11.2026 Hauptampel
    "aktien": ["dd", "r3j", "r5j"],                   # Abstand zum Allzeithoch, 3- und 5-Jahres-Rendite
    "index":  ["dd", "ratio", "trend", "r5j"],        # Abstand zum Hoch, 200-Wochen-Linie, Langfristtrend, 5-Jahres-Rendite
    "krypto": ["trend", "r3j", "mvrv"],               # Langfristtrend, 3-Jahres-Rendite, MVRV (nur Bitcoin)
}
BAUSTEIN_NAME = {"dd": "Abstand zum Allzeithoch", "ratio": "Abstand zur 200-Wochen-Linie", "trend": "Abstand zum Langfristtrend",
                 "r3j": "Rendite der letzten 3 Jahre", "r5j": "Rendite der letzten 5 Jahre", "mvrv": "MVRV (Bewertung auf der Blockchain)"}


def ampel_bausteine(zeile: dict, w: pd.DataFrame, c: np.ndarray, roh_alle: dict, krypto: bool, bitcoin: bool):
    """Rohwerte der Bausteine der Gruppe (je Woche). Rueckgabe: (art, {baustein: rohwerte})."""
    s = w["Close"]
    roh = {"dd": roh_alle["dd"], "ratio": roh_alle["ratio"], "trend": roh_alle["trend"],
           "r3j": c / s.shift(156).values - 1, "r5j": c / s.shift(260).values - 1}
    if bitcoin:
        try:
            import mvrv as _mv
            d = _mv.reihe()
            if d is not None and "mvrv" in d:
                roh["mvrv"] = d["mvrv"].resample("W-FRI").last().reindex(w.index, method="ffill").values.astype(float)
        except Exception:
            pass
    art = "krypto" if krypto else "index" if zeile["gruppe"] in ("ETF", "Rohstoffe") else "aktien"
    return art, {k: roh[k] for k in AMPEL_BAUSTEINE[art] if k in roh}


def ampel_aus(perz: dict, mindest: int) -> np.ndarray:
    m = np.vstack(list(perz.values()))
    with np.errstate(invalid="ignore"):
        anz = np.sum(~np.isnan(m), axis=0)
        return np.where(anz >= mindest, (1 - np.nanmean(m, axis=0)) * 100, np.nan)


def analysiere(zeile: dict, tag: pd.DataFrame, segmente: list):
    w = wochen(tag)
    if len(w) < 156:
        return None
    c = w["Close"].values.astype(float)
    logp = np.log(c)
    sma200 = w["Close"].rolling(200).mean().values
    ath = np.maximum.accumulate(c)
    dd = c / ath - 1
    ratio = c / sma200
    tz = trend_z(logp)
    rs = rsi(w["Close"]).values
    komponenten = {
        "dd": expandierendes_perzentil(dd, WARMUP),
        "ratio": expandierendes_perzentil(ratio, WARMUP),
        "trend": expandierendes_perzentil(tz, WARMUP),
        "rsi": expandierendes_perzentil(rs, WARMUP),
    }
    krypto = zeile["gruppe"] == "Krypto"
    bitcoin = zeile["symbol"] == E.BITCOIN["symbol"]   # Pi Cycle ist nur fuer Bitcoin geeicht
    tag_c = tag["Close"]
    extra = {}
    if krypto:
        mayer_tag = tag_c / tag_c.rolling(200).mean()
        mayer_w = mayer_tag.resample("W-FRI").last().reindex(w.index).values
        extra = {"mayer": r(mayer_tag.iloc[-1]), "mayer_w": mayer_w}
    if bitcoin:
        ema150 = tag_c.ewm(span=150, adjust=False).mean()
        sma471 = tag_c.rolling(471).mean() * 0.745
        sma111 = tag_c.rolling(111).mean(); sma350x2 = tag_c.rolling(350).mean() * 2
        unten = (ema150 < sma471)
        oben = (sma111 > sma350x2)
        gueltig_pi = sma471.notna()
        pi_bottom = list(tag_c.index[(unten & ~unten.shift(1, fill_value=False))])             # Zonenbeginn
        pi_signal = list(tag_c.index[gueltig_pi & ~unten & unten.shift(1, fill_value=False)])   # Boden-Signal
        pi_top = list(tag_c.index[(oben & ~oben.shift(1, fill_value=False))])
        abstand = float(ema150.iloc[-1] / sma471.iloc[-1] - 1) * 100
        de = lambda d: d.strftime("%d.%m.%Y")
        if bool(unten.iloc[-1]):
            pi_status = f"Pi Cycle: Bodenbildungszone seit {de(pi_bottom[-1])} (EMA {abs(abstand):.1f} % unter der Linie)".replace(f"{abs(abstand):.1f}", f"{abs(abstand):.1f}".replace(".", ","))
        else:
            pi_status = (f"Pi Cycle: keine Zone, EMA {abstand:.1f} % ueber der Linie".replace(f"{abstand:.1f}", f"{abstand:.1f}".replace(".", ","))
                         + (f"; letztes Boden-Signal {de(pi_signal[-1])}" if pi_signal else ""))
        rueckblick = []
        for d in pi_signal:
            k0 = float(tag_c.asof(d))
            zeile_r = {"datum": d.strftime("%Y-%m-%d"), "kurs": r(k0, 2),
                       "zone_ab": next((b.strftime("%Y-%m-%d") for b in reversed(pi_bottom) if b < d), None)}
            for j in (1, 2, 3):
                dj = d + pd.DateOffset(years=j)
                zeile_r[f"r{j}"] = r((float(tag_c.asof(dj)) / k0 - 1) * 100, 0) if dj <= tag_c.index[-1] else None
            rueckblick.append(zeile_r)
        zone_w = unten.resample("W-FRI").max().reindex(w.index).fillna(False).values
        extra = {
            "mayer": r(mayer_tag.iloc[-1]),
            "pi": True,
            "pi_bottom_aktiv": bool(unten.iloc[-1]),
            "pi_top_aktiv": bool(oben.iloc[-1]),
            "pi_bottom_daten": [d.strftime("%Y-%m-%d") for d in pi_bottom],
            "pi_signal_daten": [d.strftime("%Y-%m-%d") for d in pi_signal],
            "pi_status": pi_status, "pi_abstand": r(abstand, 1), "pi_rueckblick": rueckblick,
            "pi_zone_w": zone_w,
            "pi_top_daten": [d.strftime("%Y-%m-%d") for d in pi_top],
            "pi_ema150": ema150.resample("W-FRI").last().reindex(w.index).values,
            "pi_sma471": sma471.resample("W-FRI").last().reindex(w.index).values,
            "pi_top111": sma111.resample("W-FRI").last().reindex(w.index).values,
            "pi_top350x2": sma350x2.resample("W-FRI").last().reindex(w.index).values,
            "mayer_w": mayer_w,
        }
    # AMPEL (seit 22.11.2026 abends, Wunsch Marc): die fruehere violette Ampel ist die Hauptampel. Je Gruppe 3–4 Bausteine
    # aus der Ampel-Studie, jeder als Perzentil gegen alle frueheren Wochen desselben Werts (nur Vergangenheit),
    # Ampel = 100 − Mittel der Perzentile (mindestens 2 Bausteine). Bis 22.11. mittags: nur 200-Wochen-Linie; bis 21.11.:
    # Mischung aus Allzeithoch, 200-Wochen-Linie, Trend und RSI.
    art, roh = ampel_bausteine(zeile, w, c, {"dd": dd, "ratio": ratio, "trend": tz}, krypto, bitcoin)
    start_von = lambda k: 104 if k == "mvrv" else WARMUP
    perz = {k: expandierendes_perzentil(x, start_von(k)) for k, x in roh.items()}
    score = ampel_aus(perz, 2)
    # Vorläufige Ampel für die Anfangsjahre (ab 2 Jahren, nur Anzeige im Chart, nur wo die echte fehlt): dieselben Bausteine,
    # aber schon ab 104 Wochen verglichen, die 200-Wochen-Linie als Durchschnitt aller bisherigen Wochen; ein Baustein reicht.
    linie_v = w["Close"].rolling(200, min_periods=VORL_WARMUP).mean().values
    roh_v = {k: (c / linie_v if k == "ratio" else x) for k, x in roh.items()}
    score_v = ampel_aus({k: expandierendes_perzentil(x, VORL_WARMUP) for k, x in roh_v.items()}, 1)
    score_v = np.where(np.isnan(score), score_v, np.nan)
    s_jetzt = score[-1]

    jahre_daten = (tag.index[-1] - tag.index[0]).days / 365.25
    cagr20, j20, start20 = jahresrendite(tag_c, 20)
    cagr10, _, _ = jahresrendite(tag_c, 10)
    cagr_max, jmax, _ = jahresrendite(tag_c, 200)
    # Dividenden enthalten? Haengt davon ab, aus welchem Segment der Startpunkt stammt.
    def mit_div(start):
        art = segmente[0][1]
        for s_start, s_art, _ in segmente:
            if s_start <= start:
                art = s_art
        return QUELLEN_TEXT.get(art, ("", True))[1]

    stat = statistik(c, w["Low"].values.astype(float), score, s_jetzt) if not math.isnan(s_jetzt) else {}
    # Kaufzonen je Woche (mitwandernd) und heute: Kurse, bei denen die Ampel 80 / 60 / 40 / 15 zeigen wuerde
    kz, kzv = None, None
    try:
        kzv = kaufzonen_verlauf(c, roh, perz, score)
        if not math.isnan(s_jetzt):
            kz = {"jetzt": r(s_jetzt, 1), **{str(z): (None if math.isnan(a[-1]) else float(f"{a[-1]:.4g}")) for z, a in kzv.items()}}
    except Exception as ex:
        print(f"Kaufzonen nicht berechenbar ({zeile['symbol']}): {ex.__class__.__name__}: {ex}", file=sys.stderr)
    r2 = trendguete(w["Close"])
    qualitaet = bool(cagr20 is not None and cagr20 > 0.03 and r2 >= 0.6 and jahre_daten >= E.MIN_JAHRE_RANGLISTE)
    umsatz = float((tag["Close"] * tag["Volume"]).tail(63).mean()) if "Volume" in tag else 0.0

    # Begruendung in Worten
    def perz_text(k):   # Seltenheit eines Bausteins (Perzentil gegen fruehere Wochen)
        p = perz[k][-1]
        return "" if math.isnan(p) else f" – so tief nur in {max(p * 100, 1):.0f} % der Wochen" if p < 0.5 else f" – höher als in {p * 100:.0f} % der Wochen"
    def wert_text(k):
        x = roh[k][-1]
        if math.isnan(x): return None
        if k == "dd": return f"{abs(x) * 100:.0f} % unter dem Allzeithoch"
        if k == "ratio": return f"{abs(x - 1) * 100:.0f} % {'über' if x >= 1 else 'unter'} der 200-Wochen-Linie"
        if k == "trend": return f"{abs(x):.1f} Standardabweichungen {'über' if x >= 0 else 'unter'} dem Langfristtrend".replace(".", ",")
        if k == "r3j": return f"in 3 Jahren {x * 100:+.0f} %"
        if k == "r5j": return f"in 5 Jahren {x * 100:+.0f} %"
        if k == "mvrv": return f"MVRV {x:.2f}".replace(".", ",")
    grund = [wert_text(k) + perz_text(k) for k in roh if wert_text(k) and not math.isnan(perz[k][-1])]
    if krypto:
        grund.append(f"Mayer Multiple {extra['mayer']}".replace(".", ","))
        if extra.get("pi_status"): grund.append(extra["pi_status"])
        if extra.get("pi_top_aktiv"): grund.append("Pi Cycle Top AKTIV")
    vor4 = score[-5] if len(score) > 5 else np.nan
    # Kursveraenderung fuer die Heatmap: letzter Handelstag, 1 Woche, 1 Monat, 1 Jahr (Schlusskurs gegen Schlusskurs davor)
    def perf_seit(versatz):
        t0 = tag_c.index[-1] - versatz
        if t0 < tag_c.index[0]:
            return None
        k0 = float(tag_c.asof(t0))
        return r((float(tag_c.iloc[-1]) / k0 - 1) * 100, 1) if k0 > 0 else None
    perf = [r((float(tag_c.iloc[-1]) / float(tag_c.iloc[-2]) - 1) * 100, 2) if len(tag_c) > 1 else None,
            perf_seit(pd.Timedelta(days=7)), perf_seit(pd.DateOffset(months=1)), perf_seit(pd.DateOffset(years=1))]
    import marktphase
    mp = marktphase.fuer_wert(w)
    mp_arr = mp.pop("_phase_arr") if mp else None

    zeile_out = {
        **{k: zeile[k] for k in ("id", "symbol", "name", "gruppe", "land", "branche")},
        "datum": tag.index[-1].strftime("%Y-%m-%d"),
        "kurs": r(tag_c.iloc[-1], 4),
        "score": r(s_jetzt, 1), "score_vor4w": r(vor4, 1), "zone": zone(s_jetzt),
        "ampel_art": art,                    # Bausteine der Ampel: aktien / index / krypto
        "bausteine": [{"k": k, "name": BAUSTEIN_NAME[k], "wert": r(roh[k][-1] * (1 if k in ("trend", "mvrv") else 100), 2 if k in ("trend", "mvrv") else 1),
                       "perz": r(perz[k][-1] * 100, 0)} for k in roh if not math.isnan(perz[k][-1])],
        "cagr20": r(cagr20 * 100 if cagr20 is not None else None, 1), "cagr_jahre": r(j20, 1),
        "cagr20_div": mit_div(start20), "cagr10": r(cagr10 * 100 if cagr10 is not None else None, 1),
        "cagr_max": r(cagr_max * 100 if cagr_max is not None else None, 1), "jahre_daten": r(jmax, 1),
        "trend_r2": r(r2), "qualitaet": qualitaet,
        "dd": r(dd[-1] * 100, 1), "zu200w": r((ratio[-1] - 1) * 100, 1), "trend_z": r(tz[-1]), "rsi": r(rs[-1], 0),
        "p": stat, "umsatz_usd": r(umsatz, 0),
        "grund": " · ".join(grund),
        "segmente": [{"ab": s.strftime("%Y-%m-%d"), "art": QUELLEN_TEXT.get(a, (a,))[0], "symbol": sym} for s, a, sym in segmente],
        **{k: v for k, v in extra.items() if k != "mayer_w" and (not k.startswith("pi_") or k.endswith("aktiv") or k.endswith("daten")
           or k in ("pi_status", "pi_abstand", "pi_rueckblick"))},
        # Ampel des letzten Jahres alle 4 Wochen (Sparkline in der Liste)
        "sv": [None if math.isnan(x) else int(round(x)) for x in score[-53::4]],
        "mp": mp["phase"] if mp else None,   # Marktphase heute: 2 aufwaerts, 1 gemischt, 0 abwaerts
        "perf": perf,                        # Kursveraenderung in %: [Tag, Woche, Monat, Jahr]
        "kz": kz,                            # Kaufzonen: Kurs, bei dem die Ampel heute 80/60/40/15 waere
        "linie200": r(sma200[-1], 4),        # 200-Wochen-Linie heute
        "ampel_wochen": int(np.sum(~np.isnan(score))),   # Wochen mit Ampel
        "ampel_seit": w.index[int(np.flatnonzero(~np.isnan(score))[0])].strftime("%Y") if np.any(~np.isnan(score)) else None,
    }

    # Chartdaten (kompakt als Spaltenlisten)
    t_unix = [int(x) for x in (w.index - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)]
    marken = []   # Pfeile günstig/teuer entfernt (Wunsch Marc 22.11.2026); nur noch Pi-Cycle-Marken bei Bitcoin
    rund = lambda a, n=4: [None if (x is None or (isinstance(x, float) and math.isnan(x))) else float(f"{x:.{n}g}") for x in a]
    chart = {
        "t": t_unix,
        "o": rund(w["Open"].values), "h": rund(w["High"].values), "l": rund(w["Low"].values), "c": rund(c),
        "sma200w": rund(sma200),
        "score": rund(score, 3),
        "marken": marken,
    }
    for z, arr in (kzv or {}).items():   # Kaufzonen je Woche (mitwandernde Linien im Chart)
        if not np.all(np.isnan(arr)):
            chart[f"kz{z}"] = rund(arr)
    if not np.all(np.isnan(score_v)):
        chart["score_v"] = rund(score_v, 3)   # vorläufige Ampel (Anfangsjahre)
    if mp:
        chart["mp"] = mp
    if krypto and "mayer_w" in extra:
        chart["mayer"] = rund(extra["mayer_w"], 3)
    if bitcoin:
        chart["pi_ema150"] = rund(extra["pi_ema150"]); chart["pi_sma471"] = rund(extra["pi_sma471"])
        chart["pi_top111"] = rund(extra["pi_top111"]); chart["pi_top350x2"] = rund(extra["pi_top350x2"])
        chart["pi_zone"] = [1 if z else None for z in extra["pi_zone_w"]]
        # MVRV-Z-Score (Bewertung auf der Blockchain, Coin Metrics) – nur Bitcoin
        try:
            import mvrv as _mv
            d_mv = _mv.reihe()
            if d_mv is not None and d_mv["z"].notna().any():
                chart["mvrv"] = rund(d_mv["z"].reindex(w.index, method="ffill").values, 3)
                mi = _mv.auswerten(d_mv, tag_c)
                mi["pruefung"] = _mv.pruefung(d_mv, tag_c)
                chart["mvrv_info"] = mi
                zeile_out["mvrv_z"] = mi["z"]
        except Exception as ex:
            print(f"MVRV nicht auswertbar: {ex.__class__.__name__}: {ex}", file=sys.stderr)
        # Kreuzungen als Markierung an der Wochenkerze, in der sie lagen
        def woche(d):
            i = min(int(w.index.searchsorted(pd.Timestamp(d))), len(t_unix) - 1)
            return t_unix[i]
        chart["marken"] = sorted(marken + [[woche(d), "pi_beginn", None] for d in extra["pi_bottom_daten"]]
                                 + [[woche(d), "pi_boden", None] for d in extra["pi_signal_daten"]]
                                 + [[woche(d), "pi_top", None] for d in extra["pi_top_daten"]], key=lambda m: m[0])
    return zeile_out, chart, {"w": w, "score": score, "tag": tag, "mp": mp_arr}


def tagebuch(zeilen):
    """Signal-Tagebuch: einmal je Tag festhalten, was das Tool angezeigt hat (wird nie ueberschrieben).
    Spaeter wird damit nachgeprueft, ob die Signale tatsaechlich gut waren."""
    ordner = E.DATEN / "tagebuch"; ordner.mkdir(exist_ok=True)
    datei = ordner / f"{dt.date.today().isoformat()}.json"
    if datei.exists():
        return
    eintraege = [
        {k: z.get(k) for k in ("id", "symbol", "datum", "kurs", "score", "zone", "qualitaet")}
        | ({"falle": z["f"]["falle"]} if z.get("f") else {})
        | {f"p{h}": (z["p"].get(h) or {}).get("quote") if z.get("p") else None for h in ("1", "3", "5")}
        for z in zeilen
        if z["gruppe"] in ("ETF", "Krypto", "Rohstoffe") or (z["score"] is not None and (z["score"] >= 80 or z["score"] <= 15))
    ]
    datei.write_text(json.dumps({"erstellt": dt.datetime.now().isoformat(timespec="seconds"), "ampel": "studie", "signale": eintraege}, ensure_ascii=False, indent=0))


def _etfs():
    return {e["id"]: e for e in E.ETFS}


def _rohstoff_art():
    return {r["id"]: r["art"] for r in E.ROHSTOFFE}


TAGE_JAHRE = 15   # Tageskerzen: so viele Jahre zurück (ältere Zeit zeigt der Wochen- bzw. Monatschart)


def tageschart(info: dict, chart: dict, roh: dict) -> dict | None:
    """Tageskerzen der letzten TAGE_JAHRE Jahre mit 200-Wochen-Linie und Ampel (beide wöchentlich, je Tag fortgeschrieben),
    bei Krypto Mayer Multiple, bei Bitcoin die Pi-Cycle-Linien aus Tageskursen."""
    tag = roh.get("tag")
    if tag is None or tag.empty:
        return None
    tag = tag[tag["Close"] > 0]
    voll = tag["Close"].astype(float)
    ab = tag.index[-1] - pd.DateOffset(years=TAGE_JAHRE)
    t = tag[tag.index >= ab]
    wt = pd.to_datetime(chart["t"], unit="s")
    woche = lambda werte: pd.Series(werte, index=wt, dtype="float64").reindex(t.index, method="ffill").values
    rund = lambda a, n=4: [None if (x is None or (isinstance(x, float) and math.isnan(x))) else float(f"{x:.{n}g}") for x in a]
    out = {
        "t": [int(x) for x in (t.index - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)],
        "o": rund(t["Open"].values), "h": rund(t["High"].values), "l": rund(t["Low"].values), "c": rund(t["Close"].values),
        "sma200w": rund(woche(chart["sma200w"])), "score": rund(woche(chart["score"]), 3),
        **({"score_v": rund(woche(chart["score_v"]), 3)} if "score_v" in chart else {}),
        **{k: rund(woche(chart[k])) for k in ("kz80", "kz60", "kz40", "kz15") if k in chart},
    }
    if info.get("gruppe") == "Krypto":
        out["mayer"] = rund((voll / voll.rolling(200).mean()).reindex(t.index).values, 3)
    if info.get("pi"):
        out["pi_ema150"] = rund(voll.ewm(span=150, adjust=False).mean().reindex(t.index).values)
        out["pi_sma471"] = rund((voll.rolling(471).mean() * 0.745).reindex(t.index).values)
        out["pi_top111"] = rund(voll.rolling(111).mean().reindex(t.index).values)
        out["pi_top350x2"] = rund((voll.rolling(350).mean() * 2).reindex(t.index).values)
        if "pi_zone" in chart:
            out["pi_zone"] = [1 if z == 1 else None for z in woche([1 if z else 0 for z in chart["pi_zone"]])]
        if "mvrv" in chart:
            try:
                import mvrv as _mv
                out["mvrv"] = rund(_mv.reihe()["z"].reindex(t.index, method="ffill").values, 3)
            except Exception:
                pass
    return out


def werte_eines(z: dict):
    """Ampel, Kennzahlen und Chartdaten fuer einen Eintrag aus universum.csv (oder None)."""
    if z["gruppe"] == "ETF":
        tag, seg = verketten(_etfs()[z["id"]])
    else:
        tag = lade_lokal(z["symbol"])
        art = {"Krypto": "krypto", "Rohstoffe": _rohstoff_art().get(z["id"], "rohstoff")}.get(z["gruppe"], "aktie")
        seg = [(tag.index[0], art, z["symbol"])] if tag is not None and not tag.empty else []
    if tag is None or tag.empty:
        return None
    mc_ab = None
    if z["id"] == E.BITCOIN["id"]:   # Vorgeschichte vor Yahoo (ab 2010/2011)
        import btc_alt
        mc_ab = tag.index[0]           # Simulation nur mit Yahoo-Zeit: die Anfangsjahre (Kurse unter 1 $) wiederholen sich nicht
        tag, seg = btc_alt.verlaengern(tag, seg)
    tag = tag[tag["Close"] > 0]
    erg = analysiere(z, tag, seg)
    if erg is not None and mc_ab is not None:
        erg[2]["mc_ab"] = mc_ab
    return erg


def heatmap_zeile(z: dict, tag: pd.DataFrame, n100: dict, f: dict | None) -> dict | None:
    """Minimalzeile fuer die Heatmap (Nasdaq-100-Mitglieder mit weniger als 3 Jahren Kursen, z. B. junge Boersengaenge):
    nur Kurs, Kursveraenderung, Branche und Boersenwert – keine Ampel, keine Detailseite."""
    if tag is None or tag.empty:
        return None
    c = tag["Close"][tag["Close"] > 0]
    if len(c) < 2:
        return None
    def seit(versatz):
        t0 = c.index[-1] - versatz
        return None if t0 < c.index[0] else r((float(c.iloc[-1]) / float(c.asof(t0)) - 1) * 100, 1)
    zeile = {k: z[k] for k in ("id", "symbol", "name", "gruppe")}
    zeile.update({"datum": c.index[-1].strftime("%Y-%m-%d"), "kurs": r(c.iloc[-1], 4), "score": None, "kurz": True,
                  "seit": c.index[0].strftime("%Y-%m-%d"), "n100": True, "branche": n100.get("branche"), "untersektor": n100.get("untersektor", ""),
                  "perf": [r((float(c.iloc[-1]) / float(c.iloc[-2]) - 1) * 100, 2), seit(pd.Timedelta(days=7)),
                           seit(pd.DateOffset(months=1)), seit(pd.DateOffset(years=1))],
                  "umsatz_usd": r(float((tag["Close"] * tag["Volume"]).tail(63).mean()), 0) if "Volume" in tag else 0.0})
    if f is not None:
        try:
            import fundamente
            zeile["f"] = fundamente.fuer_zeile(f, zeile["kurs"], None) or None
        except Exception:
            pass
    return zeile


def jung_zeile(z: dict, tag: pd.DataFrame | None) -> dict | None:
    """Junge Aktien (unter 3 Jahren Kurse, mindestens 13 Wochen, aktuell gehandelt, z. B. SpaceX seit 06/2026):
    keine Ampel, aber Wochenkurse fuer die Depot-Prognose (eigene Schwankung statt Ersatz)."""
    if tag is None or tag.empty or z["gruppe"] in ("Krypto", "Rohstoffe"):
        return None
    c = tag["Close"][tag["Close"] > 0]
    w = c.resample("W-FRI").last().dropna()
    if len(w) < 13 or (pd.Timestamp(dt.date.today()) - c.index[-1]).days > 14:
        return None
    t = [int((d - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)) for d in w.index]
    return {"id": z["id"], "symbol": z["symbol"], "name": z["name"], "gruppe": z["gruppe"], "datum": c.index[-1].strftime("%Y-%m-%d"),
            "kurs": r(c.iloc[-1], 4), "seit": c.index[0].strftime("%Y-%m-%d"), "wochen": len(w),
            "t": t, "c": [float(f"{x:.6g}") for x in w.values]}


def universum() -> pd.DataFrame:
    return pd.read_csv(E.DATEN / "universum.csv").fillna("")


PRUEF_GRUPPEN = {"etf": "ETFs / Indizes", "krypto": "Krypto", "rohstoffe": "Rohstoffe", "aktien": "Aktien (alle)",
                 "aktien_stabil": "Aktien mit stabilem Aufwärtstrend (Auswahl mit Rückblick!)"}


class Stufe2:
    """Sammelt beim Durchlauf ueber alle Werte: Walk-forward-Pruefung, Strategie-Vergleich, Marktbreite."""

    def __init__(self):
        import pruefung, umfeld, fundamente
        import marktphase
        self.sammler = {k: pruefung.Sammler() for k in PRUEF_GRUPPEN}
        self.mp_sammler = {k: marktphase.Sammler() for k in PRUEF_GRUPPEN}
        self.fallen = fundamente.Pruefung()
        self.breite = umfeld.Breite()
        self.zins = umfeld.zins_monatlich()
        self.strat_einzeln, self.strat_aktien = [], []

    def add(self, z: dict, zeile: dict, roh: dict):
        import strategie
        w, score = roh["w"], roh["score"]
        c = w["Close"].values.astype(float)
        aktie = z["gruppe"] not in ("ETF", "Krypto", "Rohstoffe")
        if aktie:
            self.breite.add(w["Close"])
        gruppen = ["etf"] if z["gruppe"] == "ETF" else ["krypto"] if z["gruppe"] == "Krypto" else ["rohstoffe"] if z["gruppe"] == "Rohstoffe" else \
            ["aktien"] + (["aktien_stabil"] if zeile.get("qualitaet") else [])
        if roh.get("mp") is not None:
            for g in gruppen:
                self.mp_sammler[g].add(c, roh["mp"], w.index.year.values)
        if zeile["score"] is None:
            return
        for g in gruppen:
            self.sammler[g].add(c, score, w.index.year.values)
        st = strategie.vergleich(w, score, self.zins, reihe=False)
        if st is None:
            return
        e = st["ergebnis"]
        kurz = {"id": z["id"], "name": z["name"], "gruppe": z["gruppe"], "von": st["von"], "jahre": st["jahre"],
                "eingezahlt": st["eingezahlt"], "qualitaet": bool(zeile.get("qualitaet")),
                **{f"{k}_{f}": e[k][f] for k in e for f in ("netto", "irr", "max_verlust")}}
        (self.strat_aktien if aktie else self.strat_einzeln).append(kurz)

    def schreiben(self):
        import umfeld
        def zus(rows):
            rows = [r for r in rows if r["spar_irr"] is not None and r["staffel_irr"] is not None and r["staffel_vk_irr"] is not None]
            if not rows:
                return None
            d1 = np.array([r["staffel_irr"] - r["spar_irr"] for r in rows])
            d2 = np.array([r["staffel_vk_irr"] - r["spar_irr"] for r in rows])
            return {"werte": len(rows),
                    "staffel_besser": round(float((d1 > 0).mean()) * 100, 1), "staffel_vk_besser": round(float((d2 > 0).mean()) * 100, 1),
                    "median_diff_staffel": round(float(np.median(d1)), 2), "median_diff_staffel_vk": round(float(np.median(d2)), 2),
                    "median_irr_spar": round(float(np.median([r["spar_irr"] for r in rows])), 2)}
        out = {
            "stand": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "kalibrierung": {k: {"name": PRUEF_GRUPPEN[k], **s.ergebnis()} for k, s in self.sammler.items()},
            "marktphase": {k: {"name": PRUEF_GRUPPEN[k], **s.ergebnis()} for k, s in self.mp_sammler.items()},
            "fallen": self.fallen.ergebnis() if self.fallen.aktien["alle"] else None,
            "strategie": {
                "annahmen": "500 je Monat, bis 20 Jahre (ab erster gültiger Ampel), 1 je Order, Abgeltungssteuer 26,375 %, Zins US-Geldmarkt 3 Monate",
                "einzeln": self.strat_einzeln,
                "zusammen": {"etf": zus([r for r in self.strat_einzeln if r["gruppe"] == "ETF"]),
                             "rohstoffe": zus([r for r in self.strat_einzeln if r["gruppe"] == "Rohstoffe"]),
                             "aktien": zus(self.strat_aktien), "aktien_stabil": zus([r for r in self.strat_aktien if r["qualitaet"]]),
                             "aktien_20j": zus([r for r in self.strat_aktien if r["jahre"] >= 19.5])},
            },
        }
        tmp = E.WEB_DATEN / "pruefung.tmp"
        tmp.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
        tmp.replace(E.WEB_DATEN / "pruefung.json")
        umfeld.schreiben(self.breite)


def main(argv):
    uni = universum()
    if argv:
        uni = uni[uni["id"].isin(argv) | uni["symbol"].isin(argv)]
    else:
        alle_laden()   # einmal alles in den Arbeitsspeicher, dann geht es schnell
    zeilen, fehler, heatmap_extra, jung = [], 0, [], []
    s2 = None if argv else Stufe2()
    try:
        import fundamente
        fund = fundamente.kennzahlen()   # Geschaeftszahlen (SEC), leer, wenn nicht geladen
    except Exception as ex:
        print(f"Geschäftszahlen nicht lesbar: {ex.__class__.__name__}: {ex}", file=sys.stderr)
        fund = {}
    try:
        import nasdaq100
        n100 = nasdaq100.mitglieder()   # Symbol -> {branche, untersektor} laut Wikipedia-Liste (leer ohne Datei)
    except Exception as ex:
        print(f"Nasdaq-100-Liste nicht lesbar: {ex.__class__.__name__}: {ex}", file=sys.stderr)
        n100 = {}
    for i, z in enumerate(uni.to_dict("records")):
        try:
            erg = werte_eines(z)
            if erg is None and z["gruppe"] not in ("ETF", "Krypto", "Rohstoffe"):
                jz = jung_zeile(z, lade_lokal(z["symbol"]))
                if jz:
                    jung.append(jz)
            if erg is None and "Nasdaq" in z["gruppe"] and z["symbol"] in n100:
                hz = heatmap_zeile(z, lade_lokal(z["symbol"]), n100[z["symbol"]], fund.get(z["symbol"]))
                if hz:
                    heatmap_extra.append(hz)
            if erg is not None and "Nasdaq" in z["gruppe"] and z["symbol"] in n100:
                m = n100[z["symbol"]]
                erg[0]["n100"] = True
                erg[0]["branche"] = erg[0].get("branche") or m["branche"]
                erg[0]["untersektor"] = m.get("untersektor", "")
            if erg is not None:
                f = fund.get(z["symbol"]) if ("Nasdaq" in z["gruppe"] or "NYSE" in z["gruppe"]) else None   # SEC-Zahlen für US-Firmen beider Börsen
                if f is not None:
                    try:
                        erg[0]["f"] = fundamente.fuer_zeile(f, erg[0].get("kurs"), erg[0].get("score")) or None
                        if s2 is not None:
                            s2.fallen.add(z["symbol"], f, erg[2]["w"], erg[2]["score"])
                    except Exception as ex:
                        print(f"Geschäftszahlen-Fehler bei {z['symbol']}: {ex.__class__.__name__}: {ex}", file=sys.stderr)
                zeilen.append(erg[0])
                if s2 is not None:
                    try:
                        s2.add(z, erg[0], erg[2])
                    except Exception as ex:
                        print(f"Stufe-2-Fehler bei {z['symbol']}: {ex.__class__.__name__}: {ex}", file=sys.stderr)
        except Exception as ex:
            fehler += 1
            print(f"Fehler bei {z['symbol']}: {ex.__class__.__name__}: {ex}", file=sys.stderr)
        if (i + 1) % 250 == 0:
            print(f"  {i + 1}/{len(uni)} ausgewertet", flush=True)
    if not argv:
        out = {"stand": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "werte": zeilen,
               "heatmap_extra": heatmap_extra}   # Nasdaq-100-Mitglieder mit zu kurzer Historie (nur Heatmap)
        tmp = E.WEB_DATEN / "rangliste.tmp"
        tmp.write_text(json.dumps(out, separators=(",", ":")))
        tmp.replace(E.WEB_DATEN / "rangliste.json")
        # junge Aktien (ohne Ampel) mit Wochenkursen fuer die Depot-Prognose
        (E.WEB_DATEN / "jung.json").write_text(json.dumps({"stand": out["stand"], "werte": jung}, separators=(",", ":")))
        print(f"Junge Aktien (unter 3 Jahren Kurse, für die Depot-Prognose): {len(jung)}")
        tagebuch(zeilen)
        s2.schreiben()
    print(f"Fertig: {len(zeilen)} Werte ausgewertet, {fehler} Fehler" + (f", Geschäftszahlen für {sum(1 for z in zeilen if z.get('f'))}" if fund else ""))
    return zeilen


if __name__ == "__main__":
    erg = main(sys.argv[1:])
    if sys.argv[1:]:
        for z in erg:
            print(json.dumps({k: z[k] for k in ("name", "score", "zone", "cagr20", "cagr_jahre", "cagr20_div", "grund", "p", "segmente")}, ensure_ascii=False, indent=1))
