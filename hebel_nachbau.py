"""Nachgebaute Vorgeschichte für Hebel-2x-Produkte (Wunsch Marc 25.11.2026) und der Vergleich „Hebel-Produkt gegen Basiswert“.

Idee: Aus den Tageskursen des Basiswerts nachrechnen, wie das 2x-Produkt früher gelaufen wäre – für die Zeit VOR seinem
ersten (fehlerfreien) echten Kurs. Die Ampel-Formel bleibt unverändert; sie bekommt nur mehr Geschichte.

Rechnung je Handelstag (d = Kalendertage seit dem vorigen Handelstag):
    Faktor = 1 + 2 × Tagesrendite des Basiswerts − Zins × d/360 − laufende Kosten × d/365
  - Basiswert MIT wiederangelegten Erträgen (ETF-Kurse bereinigt bzw. Performance-Index) – ein reiner Kursindex ohne Dividenden
    lief in der Prüfung 4,7 bis 6,8 Prozentpunkte pro Jahr zu schlecht und wird nicht verwendet.
  - Zins = Tagesgeldzins der Währung, in der gehebelt wird (der geliehene Teil ist 1 × das eigene Geld):
    Dollar FRED DFF (Fed Funds, täglich seit 1954); Euro FRED IRSTCI01DEM156N (Tagesgeld Deutschland, bis 1993),
    IRSTCI01EZM156N (Tagesgeld Euroraum, 1994 bis 09/2019), ECBESTRVOLWGTTRMDMNRT (€STR, täglich ab 10/2019).
  - Kosten = nur die BELEGTEN laufenden Kosten des Produkts (justETF bzw. Yahoo/Morningstar). Nichts wird an die echten Kurse
    angepasst. Was der Anbieter zusätzlich zahlt (Tauschgeschäft, Zinsaufschlag), fehlt deshalb: Bei den bestandenen Produkten
    auf Aktienindizes läuft der Nachbau 0,1 bis 1,2 Prozentpunkte pro Jahr BESSER als das echte Produkt (Tabelle in der README).
    Die laufenden Kosten eines Basis-ETFs stecken dafür doppelt im Nachbau (z. B. QQQ 0,2 % -> 0,4 %).
  - Währung: Der Hebel wirkt in der Währung des Index („hebel_in“). Euro-Kurse auf Dollar-Indizes werden erst NACH dem Hebeln
    mit dem Tageskurs EUR/USD umgerechnet (web/daten/eurusd.json aus waehrung.py: FRED DEXUSEU + letzte Tage Yahoo; vor 1999
    gibt es keinen Euro, also auch keinen Nachbau in Euro). Ausnahme laut Prüfung: Amundi MSCI USA 2x hebelt die EURO-Rendite.
  - Der Hebel rechnet mit den AMTLICHEN Tagesschlüssen des Index. Für US-Indizes heißt das: Basis = US-ETF (Schluss New York).
    Ein europäischer ETF auf denselben Index (Schluss 17:30 Uhr) schwankt von Tag zu Tag messbar weniger (Nasdaq-100 2015–2026:
    Varianz 4,0 gegen 4,9 Prozent² pro Jahr) – damit gerechnet fiele der Schwankungsverlust des Hebels rund 0,9 Prozentpunkte
    pro Jahr zu klein aus.
  - „Marke“: Europäische Produkte auf US-Indizes handeln, wenn New York noch offen ist. Für die Prüfung (und den Anschluss)
    wird der Nachbau deshalb zur Handelszeit des Produkts bewertet: Vortagesschluss × (1 + 2 × Index-Bewegung seit dem
    Vortagesschluss, gemessen an einem europäischen ETF auf denselben Index). Die Vorgeschichte selbst bleibt beim US-Schluss.

Prüfung je Produkt an der gemeinsamen Zeit mit echten Kursen (nur Kurse nach „ab“) – Grenzen am 25.11.2026 VOR der ersten
Rechnung festgelegt (GRENZEN):
    Abweichung der Jahresrendite höchstens 1,5 Prozentpunkte · Korrelation der Wochenrenditen mindestens 0,98 ·
    größte Abweichung über 12 Monate höchstens 6 % · gemeinsame Zeit mindestens 3 Jahre · Glieder der Basis-Kette und Marke
    höchstens 0,5 Prozentpunkte pro Jahr auseinander.
Besteht ein Produkt nicht, bleibt es ohne Nachbau. Welche Produkte bestanden haben, steht fest in einstellungen.NACHBAU
(„aktiv“) – so kommt und geht keine Geschichte von Lauf zu Lauf. Zusätzlich lässt jeder Lauf den Nachbau weg, wenn die
frische Prüfung grob danebenliegt (ALARM: z. B. fehlerhafte Basis-Kurse bei Yahoo); pruefe_regeln.py prüft den Anschluss.

Aufruf:  python hebel_nachbau.py          Prüftabelle aller Rezepte (auch der nicht bestandenen)
         python hebel_nachbau.py --md     dieselbe Tabelle für die README
"""
import json
import sys
import numpy as np
import pandas as pd

import einstellungen as E

GRENZEN = {"abw_pa": 1.5, "korr_w": 0.98, "max12": 6.0, "jahre": 3.0, "kette_pa": 0.5}
ALARM = {"abw_pa": 3.0, "korr_w": 0.95}     # frische Prüfung grob daneben -> in diesem Lauf kein Nachbau (Schutz vor Fehlkursen der Basis)
ZINS_REIHEN = {"USD": [("DFF", None, None)],
               "EUR": [("IRSTCI01DEM156N", None, "1993-12-31"), ("IRSTCI01EZM156N", "1994-01-01", "2019-09-30"),
                       ("ECBESTRVOLWGTTRMDMNRT", "2019-10-01", None)]}
FRED_REIHEN = {"DFF": "US-Tagesgeld (Fed Funds, täglich)", "IRSTCI01DEM156N": "Tagesgeld Deutschland (monatlich, bis 1993 verwendet)",
               "IRSTCI01EZM156N": "Tagesgeld Euroraum (monatlich, 1994 bis 09/2019 verwendet)",
               "ECBESTRVOLWGTTRMDMNRT": "€STR (täglich, ab 10/2019)"}
ART_TEXT = "nachgebaut aus dem Basiswert (2-fach täglich, Kosten abgezogen)"

_ZINS: dict = {}
_X = None
INFO: dict = {}   # id -> Ergebnis des letzten Laufs (nachbau_bis, Prüfung, Vergleich); analyse.werte_eines liest das


def waehrung(etf: dict) -> str:
    return "EUR" if etf["hebel"]["eu"] else "USD"


def zins(w: str) -> pd.Series | None:
    """Tagesgeldzins in % p. a. (aus daten/fred, geladen von umfeld.py)."""
    if w not in _ZINS:
        import umfeld
        teile = []
        for reihe, von, bis in ZINS_REIHEN[w]:
            s = umfeld.fred_reihe(reihe)
            if s is None or s.empty:
                _ZINS[w] = None
                return None
            teile.append(s[(s.index >= (von or "1900")) & (s.index <= (bis or "2200"))])
        _ZINS[w] = pd.concat(teile).sort_index()
    return _ZINS[w]


def eurusd() -> pd.Series | None:
    """Dollar je Euro, täglich ab 1999 (web/daten/eurusd.json aus waehrung.py)."""
    global _X
    if _X is None:
        try:
            d = json.loads((E.WEB_DATEN / "eurusd.json").read_text())
            _X = pd.Series(d["k"], index=pd.Timestamp(d["tag0"]) + pd.to_timedelta(d["d"], unit="D"), dtype="float64")
        except Exception:
            _X = pd.Series(dtype="float64")
    return _X if len(_X) else None


def _um(s: pd.Series, von: str, nach: str) -> pd.Series | None:
    """Reihe von einer Währung in die andere (nur EUR/USD); Tage ohne Wechselkurs davor fallen weg."""
    if von == nach:
        return s
    x = eurusd()
    if x is None:
        return None
    x = x.reindex(s.index, method="ffill", limit=7)   # höchstens eine Woche fortschreiben (Feiertage), nie über Lücken hinweg
    return (s / x if nach == "EUR" else s * x).dropna()


def _glied(glied, lade) -> pd.Series | None:
    sym, _, ab = (list(glied) + [None])[:3]
    d = lade(sym)
    if d is None or d.empty:
        return None
    c = d["Close"].astype(float)
    c = c[c > 0].dropna()
    return c[c.index >= pd.Timestamp(ab)] if ab else c


def basis_kette(rezept: dict, in_w: str, lade=None, pruefung: list | None = None) -> pd.Series | None:
    """Basiswert (Tagesschluss, mit Erträgen) in der Währung in_w: Glieder der Kette aneinandergehängt (ältere skaliert).
    Fehlt ein Glied, endet die Kette dort (jüngere Glieder bleiben). pruefung: nimmt je Übergang die Abweichung der Glieder auf."""
    if lade is None:
        from kurse import lade_lokal as lade
    akt = None
    for glied in reversed(rezept["kette"]):
        c = _glied(glied, lade)
        c = None if c is None else _um(c, glied[1], in_w)
        if c is None or c.empty:
            break
        if akt is None:
            akt = c
            continue
        if pruefung is not None:   # gemeinsame Zeit der beiden Glieder: Unterschied der Jahresrendite
            g = pd.concat([c, akt], axis=1, keys=["alt", "neu"], sort=True).dropna()
            j = (g.index[-1] - g.index[0]).days / 365.25 if len(g) > 1 else 0
            if j >= 1:
                pa = lambda s: (s.iloc[-1] / s.iloc[0]) ** (1 / j) - 1
                pruefung.append({"alt": glied[0], "jahre": round(j, 1), "abw_pa": round((pa(g["alt"]) - pa(g["neu"])) * 100, 2)})
        vor = c[c.index < akt.index[0]]
        ref = c.asof(akt.index[0])
        if vor.empty or not ref or np.isnan(ref):
            continue
        akt = pd.concat([vor * (akt.iloc[0] / ref), akt])
    return akt


def faktoren(b: pd.Series, z: pd.Series, kosten: float) -> pd.Series:
    """Nachbau als Wertreihe (Start 1): täglich 2 × Rendite des Basiswerts − Zins auf den geliehenen Teil − laufende Kosten."""
    rendite = b.pct_change()
    tage = pd.Series(b.index, index=b.index).diff().dt.days
    zt = z.reindex(b.index, method="ffill").shift(1)   # Zins des Vortags gilt bis heute
    f = 1 + 2 * rendite - zt / 100 * tage / 360 - kosten / 100 * tage / 365
    f.iloc[0] = 1.0
    return f.clip(lower=0.0).cumprod()


def _zeitgleich(n: pd.Series, b: pd.Series, m: pd.Series, pruefung: list | None, name: str) -> pd.Series | None:
    """Wert des Nachbaus zur Handelszeit des Produkts (alles in der Hebel-Währung). n, b: Nachbau und Basiswert zum amtlichen
    Schluss (z. B. New York, 22 Uhr); m: „Marke“ = ETF auf denselben Index an einer europäischen Börse (Schluss 17:30 Uhr).
    Ein täglich gehebeltes Produkt bewegt sich innerhalb des Tages mit dem Doppelten der Index-Bewegung seit dem letzten
    amtlichen Schluss: Wert(t) = Nachbau(Vortag) × (1 + 2 × (Index zur Marken-Zeit / Index am Vortagesschluss − 1)).
    Das Niveau der Marke wird über den Median der letzten 60 gemeinsamen Tage auf den Basiswert umgerechnet."""
    g = pd.concat([b, m], axis=1, keys=["b", "m"], sort=True).dropna()
    if len(g) < 120:
        return None
    if pruefung is not None:
        j = (g.index[-1] - g.index[0]).days / 365.25
        pa = lambda s: (s.iloc[-1] / s.iloc[0]) ** (1 / j) - 1
        pruefung.append({"alt": name, "jahre": round(j, 1), "abw_pa": round((pa(g["b"]) - pa(g["m"])) * 100, 2)})
    k = (g["b"] / g["m"]).rolling(60, min_periods=20).median()
    vortag = pd.DataFrame({"n": n, "b": b, "k": k.reindex(b.index, method="ffill"), "tag": b.index}, index=b.index).dropna()
    v = vortag.reindex(m.index - pd.Timedelta(days=1), method="ffill")   # letzter amtlicher Schluss VOR dem Tag der Marke
    v.index = m.index
    alter = pd.Series((m.index - pd.DatetimeIndex(v["tag"])).days, index=m.index)   # Tage seit dem letzten amtlichen Schluss
    return (v["n"] * (1 + 2 * (m * v["k"] / v["b"] - 1)))[alter <= 5].dropna()


def reihe(etf: dict, lade=None, kette_pruefung: list | None = None):
    """Nachbau des Produkts in seiner Handelswährung über die ganze Zeit der Basis-Kette (nicht skaliert).
    Rückgabe (n, nz) oder None: n = Nachbau zum amtlichen Schluss des Basiswerts; nz = derselbe Nachbau zur Handelszeit des
    Produkts (nur mit „marke“ im Rezept, sonst nz = n) – für die Prüfung gegen echte Kurse und für den Anschluss."""
    rz = etf.get("nachbau")
    if not rz:
        return None
    if lade is None:
        from kurse import lade_lokal as lade
    hw, pw = rz["hebel_in"], waehrung(etf)
    b = basis_kette(rz, hw, lade, kette_pruefung)
    z = zins(hw)
    if b is None or z is None or len(b) < 30:
        return None
    b = b[b.index >= z.index[0]]
    n = faktoren(b, z, rz["kosten"])
    nz = n
    if rz.get("marke"):
        m = _glied(rz["marke"], lade)
        m = None if m is None else _um(m, rz["marke"][1], hw)
        nz = None if m is None else _zeitgleich(n, b, m, kette_pruefung, rz["kette"][-1][0])
        if nz is None:
            return None
    n, nz = _um(n, hw, pw), _um(nz, hw, pw)
    return None if n is None or nz is None else (n, nz)


def pruefen(n: pd.Series, echt: pd.Series) -> dict | None:
    """Nachbau gegen echte Kurse an den gemeinsamen Tagen."""
    g = pd.concat([n, echt], axis=1, keys=["n", "e"], sort=True).dropna()
    if len(g) < 30:
        return None
    j = (g.index[-1] - g.index[0]).days / 365.25
    pa = lambda s: (s.iloc[-1] / s.iloc[0]) ** (1 / j) - 1
    wk = g.resample("W-FRI").last().dropna()
    w = np.log(wk).diff().dropna()
    t = np.log(g).diff().dropna()
    q = (wk["n"] / wk["n"].shift(52)) / (wk["e"] / wk["e"].shift(52)) - 1
    rund = lambda x, k: None if x is None or not np.isfinite(x) else round(float(x), k)
    return {"von": g.index[0].strftime("%Y-%m-%d"), "bis": g.index[-1].strftime("%Y-%m-%d"), "jahre": rund(j, 1),
            "abw_pa": rund((pa(g["n"]) - pa(g["e"])) * 100, 2), "echt_pa": rund(pa(g["e"]) * 100, 1),
            "korr_w": rund(w["n"].corr(w["e"]), 4), "korr_t": rund(t["n"].corr(t["e"]), 3),
            "max12": rund(q.abs().max() * 100, 1) if q.notna().any() else None}


def urteil(p: dict | None, kette: list) -> tuple[bool, str]:
    """Bestanden nach den festen Grenzen? Rückgabe (ja/nein, Grund)."""
    if p is None:
        return False, "keine gemeinsame Zeit von Nachbau und echten Kursen"
    gruende = []
    de = lambda x: str(x).replace(".", ",")
    if p["abw_pa"] is None or abs(p["abw_pa"]) > GRENZEN["abw_pa"]:
        gruende.append(f"Abweichung {de(p['abw_pa'])} Prozentpunkte pro Jahr")
    if p["korr_w"] is None or p["korr_w"] < GRENZEN["korr_w"]:
        gruende.append(f"Gleichlauf der Wochenrenditen nur {de(p['korr_w'])}")
    if p["max12"] is not None and p["max12"] > GRENZEN["max12"]:
        gruende.append(f"über 12 Monate bis {de(p['max12'])} % auseinander")
    if p["jahre"] < GRENZEN["jahre"]:
        gruende.append(f"nur {de(p['jahre'])} Jahre gemeinsame Zeit")
    for k in kette:
        if abs(k["abw_pa"]) > GRENZEN["kette_pa"]:
            gruende.append(f"Basis-Kette: {k['alt']} weicht {de(k['abw_pa'])} Prozentpunkte pro Jahr vom jüngeren Glied bzw. der Marke ab")
    return (not gruende), "; ".join(gruende)


def _echt(etf: dict, lade) -> pd.Series | None:
    d = lade(etf["etf"])
    if d is None or d.empty:
        return None
    c = d["Close"].astype(float)
    c = c[c > 0].dropna()
    return c[c.index >= pd.Timestamp(etf["ab"])] if etf.get("ab") else c


def vorhaengen(etf: dict, akt: pd.DataFrame, lade=None):
    """Hängt den Nachbau vor den ersten echten Kurs (skaliert auf den Anschluss). Rückgabe (Tagesdaten, erster Nachbau-Tag,
    Kürzel des ältesten Basis-Glieds) oder None (kein aktives Rezept, Daten fehlen, frische Prüfung grob daneben)."""
    INFO.pop(etf["id"], None)
    rz = etf.get("nachbau")
    if not rz or akt is None or akt.empty:
        return None
    paar = reihe(etf, lade)
    if paar is None:
        return None
    n, nz = paar
    echt = akt["Close"].astype(float)
    p = pruefen(nz, echt[echt > 0])
    INFO[etf["id"]] = {"pruefung": p, "nachbau_bis": None}
    if not rz.get("aktiv"):
        return None
    if p is None or p["abw_pa"] is None or abs(p["abw_pa"]) > ALARM["abw_pa"] or (p["korr_w"] or 0) < ALARM["korr_w"]:
        print(f"Nachbau {etf['id']}: frische Prüfung grob daneben ({p}) – in diesem Lauf ohne Nachbau", file=sys.stderr)
        return None
    start = akt.index[0]
    vor = n[n.index < start]
    # Anschluss am ersten Tag, an dem echter Kurs und zeitgleicher Nachbau beide vorliegen (sonst steckte der Zeitunterschied
    # eines Tages im Niveau); beginnt die Marke erst kurz nach dem Produkt, gilt dieser spätere Tag (höchstens 45 Tage).
    gemeinsam = nz.index.intersection(echt[echt > 0].index)
    if vor.empty or len(vor) < 30 or not len(gemeinsam) or (gemeinsam[0] - start).days > 45:
        return None
    vor = vor * (float(echt[gemeinsam[0]]) / float(nz[gemeinsam[0]]))
    block = pd.DataFrame({"Open": vor, "High": vor, "Low": vor, "Close": vor, "Volume": 0.0})   # nur Schlusskurse: Kerze = ein Strich
    INFO[etf["id"]]["nachbau_bis"] = vor.index[-1].strftime("%Y-%m-%d")
    return pd.concat([block, akt]), vor.index[0], rz["kette"][0][0]


def _tief(s: pd.Series) -> float:
    return float((s / s.cummax() - 1).min()) * 100


def vergleich(etf: dict, tag: pd.DataFrame, lade=None) -> dict | None:
    """Karte „Hebel-Produkt gegen Basiswert“: gleicher Zeitraum, gleiche Währung (die des Produkts), vor Steuern und Kaufkosten.
    Hebel-Seite = die Reihe des Werts (Nachbau + echt), Basis-Seite = Basis-Kette mit Erträgen. Nur mit „vgl“ im Rezept."""
    rz = etf.get("nachbau")
    if not rz or not rz.get("vgl") or tag is None or tag.empty:
        return None
    b = basis_kette(rz, waehrung(etf), lade)
    if b is None:
        return None
    g = pd.concat([tag["Close"].astype(float), b], axis=1, keys=["h", "b"], sort=True).dropna()
    g = g[(g["h"] > 0) & (g["b"] > 0)]
    if len(g) < 250:
        return None
    j = (g.index[-1] - g.index[0]).days / 365.25
    pa = lambda s: float(((s.iloc[-1] / s.iloc[0]) ** (1 / j) - 1) * 100)
    info = INFO.get(etf["id"]) or {}
    nb = info.get("nachbau_bis")
    return {"basis_name": rz["name"], "von": g.index[0].strftime("%Y-%m-%d"), "bis": g.index[-1].strftime("%Y-%m-%d"), "jahre": round(j, 1),
            "waehrung": waehrung(etf),
            "hebel_pa": round(pa(g["h"]), 1), "basis_pa": round(pa(g["b"]), 1),
            "hebel_end": int(round(10000 * g["h"].iloc[-1] / g["h"].iloc[0])), "basis_end": int(round(10000 * g["b"].iloc[-1] / g["b"].iloc[0])),
            "hebel_tief": round(_tief(g["h"]), 1), "basis_tief": round(_tief(g["b"]), 1),
            "nachbau_bis": nb if nb and nb >= g.index[0].strftime("%Y-%m-%d") else None,
            "nachbau_abw_pa": (info.get("pruefung") or {}).get("abw_pa") if nb else None}


def symbole() -> list[str]:
    """Alle Kürzel der Basis-Ketten (kurse.alle_symbole lädt sie mit)."""
    return list(dict.fromkeys(g[0] for e in E.HEBEL_ETFS if e.get("nachbau")
                              for g in list(e["nachbau"]["kette"]) + ([e["nachbau"]["marke"]] if e["nachbau"].get("marke") else [])))


def tabelle() -> list[dict]:
    """Prüfung aller Rezepte (auch nicht aktiver) – für die README und zum Nachrechnen."""
    from kurse import lade_lokal, alle_laden
    alle_laden()
    aus = []
    for e in E.HEBEL_ETFS:
        rz = e.get("nachbau")
        if not rz:
            aus.append({"id": e["id"], "name": e["name"], "rezept": False, "grund": E.NACHBAU_OHNE.get(e["id"], "")})
            continue
        kp: list = []
        paar = reihe(e, lade_lokal, kp)
        n, nz = paar if paar else (None, None)
        echt = _echt(e, lade_lokal)
        p = pruefen(nz, echt) if n is not None and echt is not None else None
        ok, grund = urteil(p, kp)
        vor = n[n.index < echt.index[0]] if p else None
        aus.append({"id": e["id"], "name": e["name"], "rezept": True, "aktiv": bool(rz.get("aktiv")), "bestanden": ok, "grund": grund,
                    "kette": " → ".join(g[0] for g in rz["kette"]) + (f" · Marke {rz['marke'][0]}" if rz.get("marke") else ""), "hebel_in": rz["hebel_in"], "kosten": rz["kosten"], "pruefung": p,
                    "kette_pruefung": kp, "nachbau_von": vor.index[0].strftime("%Y-%m-%d") if vor is not None and len(vor) else None,
                    "echt_ab": echt.index[0].strftime("%Y-%m-%d") if echt is not None and len(echt) else None})
    return aus


def main(argv):
    zeilen = tabelle()
    de = lambda x, k=2: "–" if x is None else f"{x:.{k}f}".replace(".", ",")
    if "--md" in argv:
        print("| Kennung | Basis-Kette (Hebel in) | Kosten | gemeinsame Zeit | Abweichung pro Jahr | Gleichlauf Woche | größte 12-Monats-Abweichung | Basis reicht zurück bis | Ergebnis |")
        print("|---|---|---|---|---|---|---|---|---|")
    for z in zeilen:
        if not z["rezept"]:
            if "--md" not in argv:
                print(f"{z['id']:14s} ohne Rezept: {z['grund']}")
            continue
        p = z["pruefung"] or {}
        erg = ("Nachbau" if z["aktiv"] else "bestanden, nicht aktiv") if z["bestanden"] else ("AKTIV TROTZ: " if z["aktiv"] else "kein Nachbau: ") + z["grund"]
        if "--md" in argv:
            print(f"| {z['id']} | {z['kette']} ({z['hebel_in']}) | {de(z['kosten'])} % | {de(p.get('jahre'), 1)} J. ab {p.get('von', '–')} | {de(p.get('abw_pa'))} | {de(p.get('korr_w'), 4)} | "
                  f"{de(p.get('max12'), 1)} % | {z['nachbau_von'] or '–'} | {erg} |")
        else:
            kp = " ".join(f"[{k['alt']}: {k['abw_pa']:+.2f}/J über {k['jahre']} J]" for k in z["kette_pruefung"])
            print(f"{z['id']:14s} {z['kette']:28s} {z['hebel_in']} {z['kosten']:4.2f}  J {de(p.get('jahre'), 1):>5s}  abw {de(p.get('abw_pa')):>6s}  kW {de(p.get('korr_w'), 4)}  kT {de(p.get('korr_t'), 3)}"
                  f"  12M {de(p.get('max12'), 1):>5s}  ab {z['nachbau_von'] or '–':10s} {'OK  ' if z['bestanden'] else 'NEIN'} {'aktiv' if z['aktiv'] else '     '} {kp} {z['grund']}")
    ja = [z for z in zeilen if z.get("aktiv")]
    print(f"\n{len(zeilen)} Hebel-Produkte: {len(ja)} mit Nachbau, {sum(1 for z in zeilen if z['rezept'] and not z.get('aktiv'))} mit Rezept ohne Nachbau, "
          f"{sum(1 for z in zeilen if not z['rezept'])} ohne Rezept")


if __name__ == "__main__":
    main(sys.argv[1:])
