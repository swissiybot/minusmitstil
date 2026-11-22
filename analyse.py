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
    "etc": ("ETC (Wertpapier auf Rohstoff-Futures, Rollkosten enthalten)", False),
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


ANKER = 70.0        # Ampel genau an der 200-Wochen-Linie (gesetzter Wert, Wunsch Marc 22.11.2026: an der Linie = günstig)
ANKER_STEIL = 2.0   # Ersatz unter der Linie, solange es zu wenige frühere Wochen unter der Linie gibt: +2 Punkte je % Abstand
ANKER_MIN_UEBER = 52   # Mindestzahl früherer Wochen über der Linie, bevor „über der Linie“ bewertet wird
ANKER_MIN_UNTER = 26   # Mindestzahl früherer Wochen unter der Linie, bevor „unter der Linie“ nach Seltenheit bewertet wird


def anker_ampel(c: np.ndarray, start: int, min_ueber: int = ANKER_MIN_UEBER, min_linie: int = 200,
                min_unter: int = ANKER_MIN_UNTER):
    """Ampel an der 200-Wochen-Linie verankert, ohne Blick in die Zukunft (Modell für alle Gruppen).
    r = Kurs / 200-Wochen-Linie.
      r <= 1 (an oder unter der Linie), seit 22.11.2026 spät (Wunsch Marc, „das beste Modell“): nach Seltenheit der Tiefe.
        Ampel = 70 + 30 x Anteil aller FRÜHEREN Wochen unter der Linie, die weniger tief lagen (r größer).
        An der Linie 70; so tief wie nie zuvor = 100; so tief wie meistens unter der Linie = etwa 85.
        Gibt es weniger als min_unter frühere Wochen unter der Linie: Ersatzformel min(100, 70 + 2 x Abstand in %).
      r > 1 (über der Linie): Ampel = 70 x (1 - Rang), Rang = Anteil aller FRÜHEREN Wochen über der Linie mit kleinerem r.
        So weit über der Linie wie meistens -> etwa 35 (teuer); weiter darüber als fast immer -> nahe 0.
    Kaufzonen je Woche exakt aus derselben Formel: Ampel A bei Kurs p, wobei die Linie p selbst enthält
    (Linie = (Summe der 199 Vorwochen + p) / 200, also p = r * S199 / (200 - r)).
    min_linie: Wochen, aus denen die Linie mindestens besteht (200; für die vorläufige Ampel weniger).
    Rückgabe: score, {80,60,40,15: Kurs}, rang_ueber (über der Linie, sonst NaN), rang_unter (unter der Linie: Anteil
    früherer Wochen unter der Linie, die tiefer lagen; sonst NaN)."""
    n = len(c)
    score = np.full(n, np.nan); rang_ueber = np.full(n, np.nan); rang_unter = np.full(n, np.nan)
    kz = {z: np.full(n, np.nan) for z in (80, 60, 40, 15, 70, 90)}   # 70 und 90 nur für den Nachkauf-Preis
    C = np.concatenate([[0.0], np.cumsum(c)])
    ueber: list[float] = []
    unter: list[float] = []
    for t in range(n):
        m = min(t + 1, 200)
        if m < min_linie:
            continue
        linie = (C[t + 1] - C[t + 1 - m]) / m
        r = c[t] / linie
        if t >= start:
            s_vor = C[t] - C[t + 1 - m]          # Summe der Vorwochen innerhalb der Linie (ohne Woche t)
            p_zu = lambda rr: rr * s_vor / (m - rr)  # Kurs p, bei dem Kurs/Linie = rr wäre
            L = len(unter)
            if r <= 1:
                if L >= min_unter:
                    br = bisect.bisect_right(unter, r)          # frühere Wochen, die mindestens so tief lagen
                    score[t] = ANKER + (100 - ANKER) * (L - br) / L
                    rang_unter[t] = bisect.bisect_left(unter, r) / L
                else:
                    score[t] = min(100.0, ANKER + ANKER_STEIL * (1 - r) * 100)
            elif len(ueber) >= min_ueber:
                rg = bisect.bisect_left(ueber, r) / len(ueber)
                score[t] = ANKER * (1 - rg); rang_ueber[t] = rg
            kz[70][t] = p_zu(1.0)                          # an der Linie
            for z in (80, 90):
                if L >= min_unter:
                    # Ampel >= z  <=>  (L - br)/L >= (z-70)/30  <=>  br <= k  <=>  r < unter[k]
                    k = math.floor(L * (1 - (z - ANKER) / (100 - ANKER)) + 1e-9)
                    kz[z][t] = p_zu(min(1.0, unter[k]))
                else:
                    kz[z][t] = p_zu(1 - (z - ANKER) / (ANKER_STEIL * 100))
            if len(ueber) >= min_ueber:
                for z in (60, 40, 15):
                    k = math.ceil((1 - z / ANKER) * len(ueber) - 1e-9)
                    kz[z][t] = p_zu(1.0 if k <= 0 else ueber[k - 1])
        if r > 1:
            bisect.insort(ueber, r)
        else:
            bisect.insort(unter, r)
    return score, kz, rang_ueber, rang_unter


def ampel_rechnen(c: np.ndarray, krypto: bool = False, start: int = None):
    """Die Ampel des Werts (seit 22.11.2026 spät für alle Gruppen dasselbe Modell: Anker-Ampel mit Seltenheit).
    Geprüft ohne Zukunftswissen gegen eine Kurve je Wert (isotone Regression „Abstand zur Linie → Rang der
    3-Jahres-Rendite“): bei ETFs gleich, bei Aktien und Rohstoffen schlechter; bei Bitcoin nur wegen der frühen,
    extrem schwankenden Jahre besser – ab 2018 gemessen 0,79 gegen 0,80, ab 2020 0,84 gegen 0,88 (Anker besser).
    Rückgabe: art, score, kz, rang_ueber, rang_unter."""
    start = WARMUP if start is None else start
    score, kz, ru, rn = anker_ampel(c, start)
    return "anker200s", score, kz, ru, rn


KZ_STUFEN = (80, 60, 40, 15)   # Kaufzonen in Kopfzeile, Rangliste und Chart

NK_STUFEN = (60, 70, 80, 90)   # Nachkauf: geprüfte Ampel-Schwellen
NK_LUECKE = 13                 # Wochen Abstand, ab dem zwei Kaufzeiträume als getrennte Phasen zählen
NK_MIN_PHASEN, NK_MIN_WOCHEN = 3, 8
NK_TOL_QUOTE = 5               # Prozentpunkte: so viel seltener im Plus darf eine Schwelle sein und trotzdem zählen


def _phasen(maske: np.ndarray, luecke: int = NK_LUECKE) -> int:
    i = np.flatnonzero(maske)
    return 0 if not len(i) else 1 + int(np.sum(np.diff(i) > luecke))


def nachkauf(c: np.ndarray, score: np.ndarray, kzv: dict, kurs: float) -> dict | None:
    """Wunsch Marc 22.11.2026: „pro Titel wissen, wann es sich lohnt nachzukaufen“.
    Rückblick über die Geschichte DIESES Titels: Für jede Schwelle (Ampel ≥ 60/70/80/90) die Jahresrendite der folgenden
    3 Jahre (zu wenig Geschichte: 1 Jahr) nach allen Wochen mit dieser Ampel, verglichen mit Käufen in beliebigen Wochen.
    Eine Schwelle zählt, wenn sie mindestens NK_MIN_PHASEN getrennte Phasen hat, im Median mehr brachte und nicht deutlich
    seltener im Plus endete (höchstens NK_TOL_QUOTE Punkte). Unter den zählenden gilt die mit dem höchsten Median.
    Nachkauf-Preis = Kurs, bei dem die Ampel heute diese Schwelle erreicht (gleiche Formel wie die Kaufzonen).
    art: "lohnt" (Schwelle gefunden), "egal" (Warten brachte früher nichts), "unklar" (zu wenig Geschichte; Ersatz Ampel 80)."""
    n = len(c); ok = ~np.isnan(score)
    def heute(g):
        a = kzv.get(g)
        return None if a is None or math.isnan(a[-1]) else float(a[-1])
    erg = None
    for H in (156, 52):
        if n <= H:
            continue
        f = np.full(n, np.nan)
        f[:n - H] = ((c[H:] / c[:n - H]) ** (52 / H) - 1) * 100
        basis = ok & ~np.isnan(f)
        if basis.sum() < 52:
            continue
        stufen = []
        for g in NK_STUFEN:
            m = basis & (score >= g)
            ph = _phasen(m)
            if m.sum() >= NK_MIN_WOCHEN and ph >= NK_MIN_PHASEN:
                stufen.append([g, float(np.median(f[m])), float(np.mean(f[m] > 0) * 100), ph, int(m.sum())])
        if stufen or H == 52:
            erg = (H, float(np.median(f[basis])), float(np.mean(f[basis] > 0) * 100), int(basis.sum()), stufen)
            break
    if erg is None:
        p = heute(80)
        return {"art": "unklar", "ab": 80, "preis": r(p, 4), "abstand": r((p / kurs - 1) * 100, 1) if p else None,
                "jetzt": bool(ok[-1] and score[-1] >= 80)}
    H, b_med, b_q, b_n, stufen = erg
    gut = [s_ for s_ in stufen if s_[1] > b_med and s_[2] >= b_q - NK_TOL_QUOTE]
    aus = {"h": H // 52, "b_med": r(b_med, 1), "b_q": r(b_q, 0), "b_wo": b_n,
           "stufen": [[g, r(m, 1), r(q, 0), ph, wo] for g, m, q, ph, wo in stufen]}
    if not stufen:
        p = heute(80)
        return {"art": "unklar", "ab": 80, "preis": r(p, 4), "abstand": r((p / kurs - 1) * 100, 1) if p else None,
                "jetzt": bool(ok[-1] and score[-1] >= 80), **aus}
    if not gut:
        return {"art": "egal", "ab": None, "preis": None, **aus}
    g, m, q, ph, wo = max(gut, key=lambda s_: s_[1])
    p = heute(g)
    return {"art": "lohnt", "ab": g, "preis": r(p, 4), "abstand": r((p / kurs - 1) * 100, 1) if p else None,
            "jetzt": bool(ok[-1] and score[-1] >= g), "med": r(m, 1), "q": r(q, 0), "ph": ph, "wo": wo, **aus}


KQ_H, VQ_H = 156, 52   # Kaufqualität: Rendite der folgenden 3 Jahre; Verkaufsqualität: Kurs 1 Jahr später


def kauf_verkauf_qualitaet(idx: pd.DatetimeIndex, c: np.ndarray, ratio: np.ndarray):
    """Wunsch Marc 22.11.2026: Je Titel (1) im RÜCKBLICK für jede Woche, wie gut ein Kauf bzw. Verkauf war, und (2) wie es
    früher in ähnlicher Lage wie heute ausging.
    (1) Kaufqualität kq[t] = Rang (0–100) der Jahresrendite der folgenden 3 Jahre unter allen Wochen dieses Titels mit bekanntem
        Ergebnis (100 = bester Kaufzeitpunkt). Verkaufsqualität vq[t] = 100 − Rang der Kursveränderung im folgenden Jahr
        (100 = danach am stärksten gefallen, Verkauf war am besten). Kennt man erst hinterher; die letzten 3 bzw. 1 Jahr fehlen.
    (2) Vergleich: die 10 % der früheren Wochen (mindestens 26), deren Abstand zur 200-Wochen-Linie dem heutigen am nächsten
        lag, und wie es danach ausging – gegen alle Wochen. Dazu eine Probe ohne Zukunftswissen (alle 13 Wochen nur mit den
        damals bekannten Ergebnissen vorhergesagt): Wie oft lag die Methode bei diesem Titel richtig (über/unter dem
        damals bekannten Durchschnitt)? 50 % wäre Zufall."""
    n = len(c)
    f3 = np.full(n, np.nan); f1 = np.full(n, np.nan)
    if n > KQ_H:
        f3[:n - KQ_H] = (c[KQ_H:] / c[:n - KQ_H]) ** (52 / KQ_H) - 1
    if n > VQ_H:
        f1[:n - VQ_H] = c[VQ_H:] / c[:n - VQ_H] - 1
    kq = (pd.Series(f3).rank(pct=True).values * 100)
    vq = 100 - (pd.Series(f1).rank(pct=True).values * 100)
    info = {}
    lr = np.log(ratio)
    jetzt = lr[-1] if n and not np.isnan(lr[-1]) else np.nan
    def aehnlich(f):
        ok = ~np.isnan(lr) & ~np.isnan(f)
        if math.isnan(jetzt) or ok.sum() < 52:
            return None, ok
        d = np.where(ok, np.abs(lr - jetzt), np.inf)
        k = max(26, int(ok.sum() * 0.10))
        return np.argsort(d)[:k], ok
    sel3, ok3 = aehnlich(f3)
    sel1, ok1 = aehnlich(f1)
    if sel3 is not None:
        rang3 = pd.Series(f3).rank(pct=True).values
        info["kauf"] = {"wochen": int(len(sel3)), "von": r((np.exp(lr[sel3].min()) - 1) * 100, 0), "bis": r((np.exp(lr[sel3].max()) - 1) * 100, 0),
                        "plus": r(float((f3[sel3] > 0).mean()) * 100, 0), "plus_alle": r(float((f3[ok3] > 0).mean()) * 100, 0),
                        "median": r(float(np.median(f3[sel3])) * 100, 1), "median_alle": r(float(np.median(f3[ok3])) * 100, 1),
                        "top30": r(float((rang3[sel3] >= 0.7).mean()) * 100, 0), "schlecht10": r(float(np.percentile(f3[sel3], 10)) * 100, 0),
                        "phasen": int(1 + np.sum(np.diff(np.sort(sel3)) > 13))}
    if sel1 is not None:
        info["verkauf"] = {"wochen": int(len(sel1)), "richtig": r(float((f1[sel1] < 0).mean()) * 100, 0), "richtig_alle": r(float((f1[ok1] < 0).mean()) * 100, 0),
                           "median": r(float(np.median(f1[sel1])) * 100, 1), "median_alle": r(float(np.median(f1[ok1])) * 100, 1),
                           "phasen": int(1 + np.sum(np.diff(np.sort(sel1)) > 13))}
    # Probe ohne Zukunftswissen: alle 13 Wochen; Vorhersage = Median der ähnlichen früheren Wochen mit damals bekanntem Ergebnis
    treffer = gesamt = 0
    for t in range(260, n - KQ_H, 13):
        bekannt = np.arange(0, t - KQ_H + 1)
        bekannt = bekannt[~np.isnan(lr[bekannt]) & ~np.isnan(f3[bekannt])]
        if len(bekannt) < 104 or np.isnan(lr[t]):
            continue
        d = np.abs(lr[bekannt] - lr[t]); k = max(26, int(len(bekannt) * 0.10))
        vorher = np.median(f3[bekannt[np.argsort(d)[:k]]]); mitte = np.median(f3[bekannt])
        treffer += int((vorher > mitte) == (f3[t] > mitte)); gesamt += 1
    if gesamt >= 8:
        info["probe"] = {"richtig": r(treffer / gesamt * 100, 0), "zeitpunkte": gesamt}
    # beste Kauf- und Verkaufswochen im Rückblick (je höchstens eine pro Jahr Abstand)
    def beste(f, umgekehrt):
        o = np.argsort(np.where(np.isnan(f), np.inf, f)) if umgekehrt else np.argsort(np.where(np.isnan(f), -np.inf, f))[::-1]
        aus = []
        for j in o:
            if np.isnan(f[j]) or len(aus) >= 3:
                break
            if all(abs(j - g) > 52 for g in aus):
                aus.append(j)
        return [{"datum": idx[j].strftime("%Y-%m-%d"), "abstand": r((ratio[j] - 1) * 100, 0) if not np.isnan(ratio[j]) else None,
                 "danach": r(f[j] * 100, 0)} for j in aus]
    info["beste_kauf"] = beste(f3, False)
    info["beste_verkauf"] = beste(f1, True)
    info["heute_abstand"] = r((math.exp(jetzt) - 1) * 100, 0) if not math.isnan(jetzt) else None
    return kq, vq, info


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
    # AMPEL seit 22.11.2026 abends (Wunsch Marc): an der 200-Wochen-Linie verankert – an der Linie 70 (günstig), darunter
    # schnell sehr günstig, darüber nach Seltenheit des Abstands in der eigenen Geschichte (anker_ampel). Davor (22.11.):
    # Studien-Ampel (Mittel aus 3–4 Perzentilen je Gruppe), davor reine 200-Wochen-Perzentil-Ampel, bis 21.11. Mischung.
    # AMPEL seit 22.11.2026 spät (Wunsch Marc: „je Wert neu rechnen“, „überall das beste Modell“): Anker-Ampel, unter der Linie
    # jetzt nach Seltenheit der Tiefe statt +2 Punkte je % (100 nur noch bei Rekordtiefe). Bestes Modell in der Prüfung ohne
    # Zukunftswissen für alle Gruppen (Bitcoin ab 2018 gemessen, weil die frühen Jahre so nicht wiederkommen).
    art, score, kzv, rang_ueber, rang_unter = ampel_rechnen(c, krypto)
    # Vorläufige Ampel für die Anfangsjahre (ab 2 Jahren, nur Anzeige im Chart, nur wo die echte fehlt): gleiche Formel,
    # Linie aus allen bisherigen Wochen (mindestens 104), schon ab 26 früheren Wochen über der Linie.
    score_v = anker_ampel(c, VORL_WARMUP, min_ueber=26, min_linie=VORL_WARMUP, min_unter=13)[0]
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
    kz = None
    try:
        if not math.isnan(s_jetzt):
            kz = {"jetzt": r(s_jetzt, 1), **{str(z): (None if math.isnan(a[-1]) else float(f"{a[-1]:.4g}")) for z, a in kzv.items() if z in KZ_STUFEN}}
    except Exception as ex:
        print(f"Kaufzonen nicht berechenbar ({zeile['symbol']}): {ex.__class__.__name__}: {ex}", file=sys.stderr)
    nk = None
    try:   # Nachkauf-Preis je Titel mit Beleg aus der eigenen Geschichte
        if not math.isnan(s_jetzt):
            nk = nachkauf(c, score, kzv, float(tag_c.iloc[-1]))
    except Exception as ex:
        print(f"Nachkauf nicht berechenbar ({zeile['symbol']}): {ex.__class__.__name__}: {ex}", file=sys.stderr)
    r2 = trendguete(w["Close"])
    qualitaet = bool(cagr20 is not None and cagr20 > 0.03 and r2 >= 0.6 and jahre_daten >= E.MIN_JAHRE_RANGLISTE)
    umsatz = float((tag["Close"] * tag["Volume"]).tail(63).mean()) if "Volume" in tag else 0.0

    # Begruendung in Worten
    grund = []
    if not math.isnan(ratio[-1]):
        g = f"{abs(ratio[-1] - 1) * 100:.0f} % {'über' if ratio[-1] >= 1 else 'unter'} der 200-Wochen-Linie"
        if not math.isnan(rang_ueber[-1]):
            g += f" – weiter darüber als in {rang_ueber[-1] * 100:.0f} % der früheren Wochen über der Linie"
        elif not math.isnan(rang_unter[-1]):
            g += f" – tiefer als in {(1 - rang_unter[-1]) * 100:.0f} % der früheren Wochen unter der Linie"
        grund.append(g)
    grund.append(f"{abs(dd[-1]) * 100:.0f} % unter dem Allzeithoch")
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
        "score": r(s_jetzt, 1), "score_vor4w": r(vor4, 1), "zone": zone(r(s_jetzt, 1)),   # Stufe zur angezeigten (gerundeten) Ampel
        "ampel_art": art,                    # anker200s: an der 200-Wochen-Linie verankert, unter der Linie nach Seltenheit
        "rang_ueber": r(rang_ueber[-1] * 100, 0),   # über der Linie: Anteil früherer Wochen über der Linie, die näher an der Linie lagen
        "rang_unter": r(rang_unter[-1] * 100, 0),   # unter der Linie: Anteil früherer Wochen unter der Linie, die tiefer lagen
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
        "nk": nk,                            # Nachkauf: ab welcher Ampel sich Kaufen bei diesem Titel früher lohnte, Kurs dafür heute
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
    try:   # Kauf-/Verkaufsqualität im Rückblick und Vergleich mit heute
        kq, vq, kv_info = kauf_verkauf_qualitaet(w.index, c, ratio)
        chart["kq"] = [None if math.isnan(x) else int(round(x)) for x in kq]
        chart["vq"] = [None if math.isnan(x) else int(round(x)) for x in vq]
        zeile_out["kv"] = kv_info
    except Exception as ex:
        print(f"Kauf-/Verkaufsqualität nicht berechenbar ({zeile['symbol']}): {ex.__class__.__name__}: {ex}", file=sys.stderr)
    for z, arr in (kzv or {}).items():   # Kaufzonen je Woche (mitwandernde Linien im Chart)
        if z in KZ_STUFEN and not np.all(np.isnan(arr)):
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
    datei.write_text(json.dumps({"erstellt": dt.datetime.now().isoformat(timespec="seconds"), "ampel": "anker200s", "signale": eintraege}, ensure_ascii=False, indent=0))


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
        **{k: rund(woche(chart[k])) for k in ("kq", "vq") if k in chart},
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
    if erg is None and z["gruppe"] not in ("Krypto", "Rohstoffe"):
        erg = jung_wert(z, tag, seg)   # junge Werte (z. B. SpaceX): eigene Seite mit Chart, ohne Ampel
    if erg is not None:
        erg[0].update(beschreibung_fuer(z["id"]))   # ISIN, WKN, Kurzbeschreibung
    if erg is not None and mc_ab is not None:
        erg[2]["mc_ab"] = mc_ab
    return erg


def jung_wert(z: dict, tag: pd.DataFrame, segmente: list):
    """Junger Wert (mindestens 13, unter 156 Wochen Kurse, aktuell gehandelt, z. B. SpaceX seit 06/2026): eigene Seite mit
    Chart, aber OHNE Ampel (dafür fehlt die 200-Wochen-Linie). Statt der Ampel: Lage seit Börsengang (erster Kurs,
    Hoch, Tief, Durchschnitt). Rückgabe wie analysiere(): (Zeile, Chart, Rohdaten)."""
    c_tag = tag["Close"][tag["Close"] > 0]
    if len(c_tag) < 2 or (pd.Timestamp(dt.date.today()) - c_tag.index[-1]).days > 14:
        return None
    w = wochen(tag)
    if not (13 <= len(w) < 156):
        return None
    c = w["Close"].values.astype(float)
    hoch, tief = float(np.nanmax(w["High"].values)), float(np.nanmin(w["Low"].values))
    mittel = float(np.mean(c))
    def seit(versatz):
        t0 = c_tag.index[-1] - versatz
        return None if t0 < c_tag.index[0] else r((float(c_tag.iloc[-1]) / float(c_tag.asof(t0)) - 1) * 100, 1)
    jetzt = float(c_tag.iloc[-1])
    zeile = {
        **{k: z.get(k) for k in ("id", "symbol", "name", "gruppe", "land", "branche")},
        "datum": c_tag.index[-1].strftime("%Y-%m-%d"), "kurs": r(jetzt, 4),
        "score": None, "score_vor4w": None, "zone": "keine Daten", "jung": True,
        "seit": c_tag.index[0].strftime("%Y-%m-%d"), "wochen": int(len(w)),
        "erster_kurs": r(float(c_tag.iloc[0]), 4), "hoch_seit": r(hoch, 4), "tief_seit": r(tief, 4), "mittel_seit": r(mittel, 4),
        "dd": r((jetzt / hoch - 1) * 100, 1), "zu_mittel": r((jetzt / mittel - 1) * 100, 1),
        "seit_start": r((jetzt / float(c_tag.iloc[0]) - 1) * 100, 1),
        "jahre_daten": r((c_tag.index[-1] - c_tag.index[0]).days / 365.25, 2),
        "cagr20": None, "cagr_jahre": None, "cagr_max": None, "qualitaet": False, "p": {}, "kz": None, "sv": [],
        "perf": [r((jetzt / float(c_tag.iloc[-2]) - 1) * 100, 2), seit(pd.Timedelta(days=7)), seit(pd.DateOffset(months=1)), seit(pd.DateOffset(years=1))],
        "umsatz_usd": r(float((tag["Close"] * tag["Volume"]).tail(63).mean()), 0) if "Volume" in tag else 0.0,
        "grund": f"erst {len(w)} Wochen an der Börse (seit {c_tag.index[0].strftime('%d.%m.%Y')}) · {abs((jetzt / hoch - 1) * 100):.0f} % unter dem Hoch seit Börsengang",
        "segmente": [{"ab": s.strftime("%Y-%m-%d"), "art": QUELLEN_TEXT.get(a, (a,))[0], "symbol": sym} for s, a, sym in segmente],
    }
    t_unix = [int(x) for x in (w.index - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)]
    rund = lambda a, n=4: [None if (x is None or (isinstance(x, float) and math.isnan(x))) else float(f"{x:.{n}g}") for x in a]
    leer = [None] * len(w)
    chart = {"t": t_unix, "o": rund(w["Open"].values), "h": rund(w["High"].values), "l": rund(w["Low"].values), "c": rund(c),
             "sma200w": leer, "score": leer, "marken": [], "jung": True}
    return zeile, chart, {"w": w, "score": np.full(len(w), np.nan), "tag": tag, "mp": None}


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


_BESCHR = None


def beschreibung_fuer(wid: str) -> dict:
    """ISIN, WKN und Kurzbeschreibung aus daten/beschreibung.json (beschreibung.py); leer, wenn nicht vorhanden."""
    global _BESCHR
    if _BESCHR is None:
        try:
            _BESCHR = json.loads((E.DATEN / "beschreibung.json").read_text())
        except Exception:
            _BESCHR = {}
    e = _BESCHR.get(wid) or {}
    return {k: v for k, v in (("isin", e.get("isin")), ("isin_geprueft", e.get("geprueft")), ("wkn", e.get("wkn")),
                              ("beschreibung", e.get("text"))) if v}


NAMEN_ALIAS = {"SPCX": "SpaceX (Space Exploration Technologies)"}   # bekannter Name, damit Suche und Kopf ihn zeigen


def universum() -> pd.DataFrame:
    u = pd.read_csv(E.DATEN / "universum.csv").fillna("")
    for sym, name in NAMEN_ALIAS.items():
        u.loc[u["symbol"] == sym, "name"] = name
    return u


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
            if erg is not None and erg[0].get("jung"):   # junge Werte: zusätzlich Wochenkurse für die Depot-Prognose
                jz = jung_zeile(z, lade_lokal(z["symbol"]))
                if jz:
                    jung.append(jz)
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
                        erg[0]["f"] = fundamente.fuer_zeile(f, erg[0].get("kurs"), erg[0].get("score"), erg[2]["w"]) or None
                        if s2 is not None and not erg[0].get("jung"):
                            s2.fallen.add(z["symbol"], f, erg[2]["w"], erg[2]["score"])
                    except Exception as ex:
                        print(f"Geschäftszahlen-Fehler bei {z['symbol']}: {ex.__class__.__name__}: {ex}", file=sys.stderr)
                zeilen.append(erg[0])
                if s2 is not None and not erg[0].get("jung"):
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
