"""Geschaeftszahlen der US-Aktien aus SEC EDGAR (gemeinfrei): Gewinn, Umsatz, Aktienzahl -> KGV, KUV, Trend, Fallen-Warnung.

Warum: Die Ampel schaut nur auf den Kurs. Ein gefallener Kurs ist aber nicht billig, wenn das Geschaeft mitfaellt.
Die Fallen-Warnung markiert Aktien, deren Ampel guenstig steht, deren Gewinn oder Umsatz aber deutlich sinkt
(oder die Verlust machen). Sie ersetzt keine Analyse und ist kein Verkaufssignal.

Daten: SEC "frames"-Schnittstelle (data.sec.gov/api/xbrl/frames): je Kennzahl und Zeitraum ein Abruf fuer ALLE Firmen.
  Gewinn:   us-gaap NetIncomeLoss (USD)
  Umsatz:   us-gaap Revenues, RevenueFromContractWithCustomerExcludingAssessedTax, SalesRevenueNet (erste vorhandene)
  Aktien:   dei EntityCommonStockSharesOutstanding (Stichtag); bei mehreren Aktiengattungen fehlt sie –
            dann us-gaap WeightedAverageNumberOfDilutedSharesOutstanding (verwaessert, Quartal)
Jahre (CY2009 ...) und Quartale (CY2009Q1 ...). Das letzte Quartal eines Geschaeftsjahrs fehlt oft und wird aus
Jahr minus die drei Quartale davor gebildet – zugeordnet ueber die Enddaten (auch bei Geschaeftsjahr bis Juni o. ae.).
US-Firmen: Bilanzierung nach US-GAAP in US-Dollar (frames, Jahre und Quartale).
Auslaendische Firmen an US-Boersen (Formulare 20-F/40-F): die frames-Schnittstelle kennt die IFRS-Taxonomie nicht. Fuer sie
werden die Firmendaten einzeln geholt (data.sec.gov/api/xbrl/companyfacts, hoechstens alle 4 Wochen je Firma) und nur die
Geschaeftsjahre ausgewertet: ifrs-full ProfitLossAttributableToOwnersOfParent (sonst ProfitLoss), Revenue (sonst
RevenueFromContractsWithCustomers, RevenueFromSaleOfGoods) – oder US-GAAP in einer anderen Waehrung als Dollar. Angegeben wird die Berichtswaehrung.
Ein KGV gibt es fuer sie nicht: Der US-Kurs gilt je ADR (oft mehrere oder Bruchteile von Aktien) und in Dollar, die Zahlen
je Stammaktie in der Berichtswaehrung – ohne sicheres ADR-Verhaeltnis waere es geraten.

Die SEC verlangt bei automatischen Abrufen eine Kontaktangabe im User-Agent. Sie kommt aus der Umgebungsvariable
SEC_KONTAKT (auf GitHub als geheime Einstellung) und steht nie im Code. Ohne SEC_KONTAKT wird nichts geladen;
vorhandene Daten werden trotzdem ausgewertet.

Speicher: daten/sec/fakten.parquet (kompakt, wenige MB) und daten/sec/abrufe.json (wann welcher Zeitraum geholt wurde).
Neu geholt werden nur fehlende Zeitraeume und die der letzten 15 Monate (hoechstens einmal pro Woche).

Aufruf:  python fundamente.py          laedt/aktualisiert (nur mit SEC_KONTAKT)
         FUND_AB=2021 python ...        nur Zeitraeume ab diesem Jahr (fuer kurze Tests)
"""
import io
import json
import math
import os
import sys
import time
import datetime as dt
import numpy as np
import pandas as pd
import requests

import einstellungen as E

ORDNER = E.DATEN / "sec"
FAKTEN = ORDNER / "fakten.parquet"
ABRUFE = ORDNER / "abrufe.json"
AUSLAND = ORDNER / "ausland.parquet"          # Geschaeftsjahre auslaendischer Firmen (companyfacts)
AUSLAND_ABRUFE = ORDNER / "ausland_abrufe.json"
AUSLAND_NEU_TAGE = 27
AUSLAND_MAX_JE_LAUF = 400
AUSLAND_FORMULARE = {"20-F", "20-F/A", "40-F", "40-F/A", "10-K", "10-K/A"}
AUSLAND_KONZEPTE = {   # Code: [(Taxonomie, Kennzahl), ...] in dieser Reihenfolge
    "ni": [("ifrs-full", "ProfitLossAttributableToOwnersOfParent"), ("ifrs-full", "ProfitLoss"), ("us-gaap", "NetIncomeLoss")],
    "rv": [("ifrs-full", "Revenue"), ("ifrs-full", "RevenueFromContractsWithCustomers"), ("ifrs-full", "RevenueFromSaleOfGoods"),
           ("us-gaap", "Revenues"),
           ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"), ("us-gaap", "SalesRevenueNet")],
}
TICKER = ORDNER / "company_tickers.json"
BASIS = "https://data.sec.gov/api/xbrl/frames"
START_JAHR = 2009
PAUSE = 0.15                      # hoechstens etwa 7 Abrufe pro Sekunde (SEC erlaubt 10)
NEU_NACH_TAGEN = 6
KONZEPTE = {                      # Code: (Taxonomie, Kennzahl, Einheit, Art)
    "ni": ("us-gaap", "NetIncomeLoss", "USD", "dauer"),
    "r1": ("us-gaap", "Revenues", "USD", "dauer"),
    "r2": ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD", "dauer"),
    "r3": ("us-gaap", "SalesRevenueNet", "USD", "dauer"),
    "sh": ("dei", "EntityCommonStockSharesOutstanding", "shares", "stichtag"),
    "sd": ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding", "shares", "quartal"),
}
UMSATZ = ("r1", "r2", "r3")
LAG_TAGE = 90                     # Zahlen gelten erst 90 Tage nach Periodenende als bekannt (Pruefung ohne Zukunftswissen)
# Fallen-Warnung: Ampel guenstig UND Geschaeft schwach
FALLE_AMPEL = 60
FALLE_GEWINN = -25.0              # Gewinn (12 Monate) mind. 25 % unter Vorjahr
FALLE_UMSATZ = -10.0              # oder Umsatz (12 Monate) mind. 10 % unter Vorjahr, oder Verlust


# ----------------------------------------------------------------- Laden
def _zeitraeume(ab: int) -> list[tuple[str, str, pd.Timestamp]]:
    """(Code-Art, Periode, Periodenende) bis heute."""
    heute = pd.Timestamp(dt.date.today())
    out = []
    for j in range(ab, heute.year + 1):
        ende = pd.Timestamp(j, 12, 31)
        if ende - pd.Timedelta(days=330) <= heute:
            out.append(("jahr", f"CY{j}", ende))
        for q in range(1, 5):
            qe = pd.Timestamp(j, 3 * q, 1) + pd.offsets.MonthEnd(0)
            if qe <= heute:
                out.append(("quartal", f"CY{j}Q{q}", qe))
    return out


def _holen(sitzung, url) -> dict | None:
    for versuch in range(4):
        try:
            a = sitzung.get(url, timeout=60)
            if a.status_code == 404:
                return {}
            if a.status_code in (403, 429):
                raise RuntimeError(f"HTTP {a.status_code} (gesperrt oder zu schnell)")
            a.raise_for_status()
            return a.json()
        except Exception as ex:
            print(f"  SEC: {ex.__class__.__name__}: {ex} – {url.rsplit('/', 3)[-3:]}")
            time.sleep(5 * (versuch + 1))
    return None


def laden() -> bool:
    kontakt = os.environ.get("SEC_KONTAKT", "").strip()
    if not kontakt:
        print("SEC: keine Kontaktangabe (SEC_KONTAKT) – nichts geladen" + (", nutze vorhandene Daten." if FAKTEN.exists() else "."))
        return FAKTEN.exists()
    ORDNER.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers.update({"User-Agent": kontakt, "Accept-Encoding": "gzip, deflate"})
    ab = int(os.environ.get("FUND_AB", START_JAHR))
    abrufe = json.loads(ABRUFE.read_text()) if ABRUFE.exists() else {}
    alt = pd.read_parquet(FAKTEN) if FAKTEN.exists() else None
    heute = pd.Timestamp(dt.date.today())

    # Tickerliste (Tickersymbol -> CIK), einmal pro Woche
    if not TICKER.exists() or time.time() - TICKER.stat().st_mtime > NEU_NACH_TAGEN * 86400:
        a = s.get("https://www.sec.gov/files/company_tickers.json", timeout=60)
        if a.ok:
            TICKER.write_bytes(a.content)
        time.sleep(PAUSE)

    neu, geholt, fehler = [], 0, 0
    for art, periode, ende in _zeitraeume(ab):
        for code, (tax, name, einheit, typ) in KONZEPTE.items():
            if typ in ("stichtag", "quartal") and art == "jahr":
                continue
            p = periode + ("I" if typ == "stichtag" else "")
            schluessel = f"{code}:{p}"
            zuletzt = abrufe.get(schluessel)
            frisch = zuletzt and (heute - pd.Timestamp(zuletzt)).days < NEU_NACH_TAGEN
            alt_genug = zuletzt and ende < heute - pd.Timedelta(days=460)
            if frisch or alt_genug:
                continue
            d = _holen(s, f"{BASIS}/{tax}/{name}/{einheit}/{p}.json")
            time.sleep(PAUSE)
            if d is None:
                fehler += 1
                if fehler >= 5 and geholt == 0:
                    print("SEC: mehrere Abrufe gescheitert – Abbruch, vorhandene Daten bleiben.")
                    break
                continue
            geholt += 1
            abrufe[schluessel] = heute.strftime("%Y-%m-%d")
            zeilen = d.get("data", []) if d else []
            if zeilen:
                df = pd.DataFrame(zeilen)[["cik", "end", "val"]]
                df["k"] = code; df["p"] = p
                neu.append(df)
        else:
            continue
        break
    if neu:
        df = pd.concat(neu, ignore_index=True)
        if alt is not None:
            schon = set(zip(df["k"], df["p"]))
            alt = alt[[(k, p) not in schon for k, p in zip(alt["k"], alt["p"])]]
            df = pd.concat([alt, df], ignore_index=True)
        df["cik"] = df["cik"].astype("int32")
        df["end"] = pd.to_datetime(df["end"]).astype("datetime64[ms]")
        df["val"] = df["val"].astype("float64")
        df["k"] = df["k"].astype("category"); df["p"] = df["p"].astype("category")
        df = df.sort_values(["cik", "k", "p"]).reset_index(drop=True)
        tmp = FAKTEN.with_suffix(".tmp")
        df.to_parquet(tmp, compression="zstd", index=False)
        tmp.replace(FAKTEN)
    ABRUFE.write_text(json.dumps(abrufe, indent=0, sort_keys=True))
    print(f"SEC: {geholt} Abrufe, {fehler} gescheitert; Datei {FAKTEN.stat().st_size / 1e6:.1f} MB" if FAKTEN.exists() else "SEC: keine Daten")
    try:
        ausland_laden(s)
    except Exception as ex:
        print(f"SEC Ausland: {ex.__class__.__name__}: {ex} – vorhandene Daten bleiben")
    return FAKTEN.exists()


def _ausland_kandidaten() -> list[int]:
    """CIKs der US-gelisteten Aktien aus der Werteliste, fuer die es keine US-GAAP-Dollar-Zahlen gibt (meist 20-F/40-F)."""
    uni = pd.read_csv(E.DATEN / "universum.csv")
    uni = uni[uni["gruppe"].astype(str).str.contains("Nasdaq|NYSE")]
    tick = _ticker_zu_cik()
    ciks = {tick[s.upper().replace(".", "-")] for s in uni["symbol"].astype(str) if s.upper().replace(".", "-") in tick}
    mit_us = set()
    if FAKTEN.exists():
        df = pd.read_parquet(FAKTEN, columns=["cik", "k"])
        mit_us = set(df.loc[df["k"].astype(str) == "ni", "cik"].astype(int))
    return sorted(c for c in ciks if c not in mit_us)


def _ausland_auszug(d: dict) -> list[dict]:
    """Geschaeftsjahre (Gewinn, Umsatz) aus companyfacts: IFRS oder US-GAAP in Fremdwaehrung, Hauptwaehrung der Firma."""
    fakten = d.get("facts", {})
    zeilen = []
    for code, liste in AUSLAND_KONZEPTE.items():
        for tax, name in liste:
            einheiten = fakten.get(tax, {}).get(name, {}).get("units", {})
            jahre = {}
            for einheit, eintraege in einheiten.items():
                if "/" in einheit or len(einheit) != 3 or (tax == "us-gaap" and einheit == "USD"):
                    continue   # US-GAAP in Dollar kommt schon ueber die frames
                for x in eintraege:
                    if x.get("fp") != "FY" or x.get("form") not in AUSLAND_FORMULARE or not x.get("start"):
                        continue
                    tage = (pd.Timestamp(x["end"]) - pd.Timestamp(x["start"])).days
                    if not 340 <= tage <= 380:
                        continue
                    alt = jahre.get((einheit, x["end"]))
                    if alt is None or x.get("filed", "") > alt[1]:   # neueste Meldung (Korrekturen) gewinnt
                        jahre[(einheit, x["end"])] = (float(x["val"]), x.get("filed", ""))
            if not jahre:
                continue
            je_einheit = {}
            for (einheit, _), _w in jahre.items():
                je_einheit[einheit] = je_einheit.get(einheit, 0) + 1
            neuestes = max(ende for _, ende in jahre)   # Berichtswaehrung = Waehrung des neuesten Geschaeftsjahrs (z. B. Genmab
            aktuell = [e for (e, ende) in jahre if ende == neuestes]   # 2025 von DKK auf USD); gibt es dort mehrere (Umrechnung
            haupt = max(aktuell, key=lambda e: (je_einheit[e], e != "USD"))   # zur Info), die mit den meisten Jahren
            for (einheit, ende), (val, _) in jahre.items():
                if einheit == haupt:
                    zeilen.append({"k": code, "end": ende, "val": val, "waehrung": haupt,
                                   "standard": "IFRS" if tax == "ifrs-full" else "US-GAAP"})
            break   # erste vorhandene Kennzahl je Code
    return zeilen


def ausland_laden(s) -> None:
    abrufe = json.loads(AUSLAND_ABRUFE.read_text()) if AUSLAND_ABRUFE.exists() else {}
    heute = pd.Timestamp(dt.date.today())
    kand = _ausland_kandidaten()
    faellig = [c for c in kand if not abrufe.get(str(c)) or (heute - pd.Timestamp(abrufe[str(c)])).days >= AUSLAND_NEU_TAGE]
    faellig = sorted(faellig, key=lambda c: abrufe.get(str(c), ""))[:AUSLAND_MAX_JE_LAUF]   # nie geholte zuerst
    alt = pd.read_parquet(AUSLAND) if AUSLAND.exists() else None
    neu, geholt, fehler, mit = [], 0, 0, 0
    for c in faellig:
        d = _holen(s, f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c:010d}.json")
        time.sleep(PAUSE)
        if d is None:
            fehler += 1
            if fehler >= 5 and geholt == 0:
                print("SEC Ausland: mehrere Abrufe gescheitert – Abbruch, vorhandene Daten bleiben.")
                break
            continue
        geholt += 1
        abrufe[str(c)] = heute.strftime("%Y-%m-%d")
        z = _ausland_auszug(d) if d else []
        if z:
            mit += 1
            df = pd.DataFrame(z); df["cik"] = c
            neu.append(df)
    geholte = {int(c) for c in faellig if abrufe.get(str(c)) == heute.strftime("%Y-%m-%d")}
    teile = ([alt[~alt["cik"].isin(geholte)]] if alt is not None else []) + neu
    if teile:
        df = pd.concat(teile, ignore_index=True)
        df["cik"] = df["cik"].astype("int32"); df["val"] = df["val"].astype("float64")
        df["end"] = pd.to_datetime(df["end"]).astype("datetime64[ms]")
        tmp = AUSLAND.with_suffix(".tmp")
        df.sort_values(["cik", "k", "end"]).to_parquet(tmp, compression="zstd", index=False)
        tmp.replace(AUSLAND)
    AUSLAND_ABRUFE.write_text(json.dumps(abrufe, indent=0, sort_keys=True))
    print(f"SEC Ausland: {len(kand)} Firmen ohne US-GAAP-Dollar-Zahlen, {geholt} abgerufen ({mit} mit Geschäftsjahren), "
          f"{fehler} gescheitert, noch fällig {max(0, len([c for c in kand if not abrufe.get(str(c))]))}")


# ----------------------------------------------------------------- Auswerten
def _ticker_zu_cik() -> dict[str, int]:
    if not TICKER.exists():
        return {}
    d = json.loads(TICKER.read_text())
    out = {}
    for v in d.values():
        t = str(v["ticker"]).upper().replace(".", "-")
        out.setdefault(t, int(v["cik_str"]))
    return out


def _nahe(liste_enden: np.ndarray, ziel: pd.Timestamp, tage: int = 20) -> int:
    """Index des Eintrags, dessen Enddatum hoechstens 'tage' Tage von ziel entfernt ist, sonst -1."""
    if len(liste_enden) == 0:
        return -1
    i = int(np.argmin(np.abs(liste_enden - ziel.value)))
    return i if abs(liste_enden[i] - ziel.value) <= tage * 86400e9 else -1


def _quartale(jahr: list, quartal: list) -> list:
    """Quartale [(ende, wert)] nach Enddatum; fehlendes letztes Quartal eines Geschaeftsjahrs = Jahr - 3 Quartale davor."""
    q = sorted(quartal)
    enden = np.array([e.value for e, _ in q], dtype=np.int64)
    neu = []
    for e, v in jahr:
        if _nahe(enden, e) >= 0:
            continue
        idx = [_nahe(enden, e - pd.DateOffset(months=m)) for m in (3, 6, 9)]
        if all(i >= 0 for i in idx):
            neu.append((e, v - sum(q[i][1] for i in idx)))
    return sorted(q + neu)


def _ttm(q: list) -> list:
    """[(ende, Summe der 4 Quartale bis ende)] – nur, wo alle 4 Quartale lueckenlos vorhanden sind."""
    enden = np.array([e.value for e, _ in q], dtype=np.int64)
    out = []
    for e, v in q:
        idx = [_nahe(enden, e - pd.DateOffset(months=m)) for m in (3, 6, 9)]
        if all(i >= 0 for i in idx):
            out.append((e, v + sum(q[i][1] for i in idx)))
    return out


def _vorjahr(reihe: list, e: pd.Timestamp, tage: int = 40):
    """Wert der Reihe etwa 12 Monate vor e (oder None)."""
    enden = np.array([x.value for x, _ in reihe], dtype=np.int64)
    i = _nahe(enden, e - pd.DateOffset(months=12), tage)
    return reihe[i][1] if i >= 0 else None


def kennzahlen() -> dict:
    """{Yahoo-Symbol: Geschaeftszahlen} fuer alle Firmen mit SEC-Daten."""
    if not FAKTEN.exists() and not AUSLAND.exists():
        return {}
    df = pd.read_parquet(FAKTEN) if FAKTEN.exists() else pd.DataFrame({"cik": [], "k": [], "p": [], "end": [], "val": []})
    df["k"] = df["k"].astype(str); df["p"] = df["p"].astype(str)
    tick = _ticker_zu_cik()
    cik_zu = {}
    for t, c in tick.items():
        cik_zu.setdefault(c, []).append(t)
    out = {}
    for cik, teil in df.groupby("cik", sort=False):
        if cik not in cik_zu:
            continue
        roh = {}
        for k, p, ende, val in zip(teil["k"], teil["p"], teil["end"], teil["val"]):
            roh.setdefault(k, {})[p] = (pd.Timestamp(ende), float(val))

        def reihen(codes):
            jahr, quartal = {}, {}
            for code in codes:                   # erste vorhandene Kennzahl je Zeitraum
                for p, (ende, val) in roh.get(code, {}).items():
                    (quartal if "Q" in p else jahr).setdefault(p, (ende, val))
            dedup = lambda d: sorted({e: (e, v) for e, v in d.values()}.values())
            return dedup(jahr), dedup(quartal)
        ni_j, ni_q = reihen(["ni"])
        rv_j, rv_q = reihen(list(UMSATZ))
        if not ni_j and not ni_q:
            continue
        kand = [x for x in (sorted(roh.get("sh", {}).values())[-1:] + sorted(roh.get("sd", {}).values())[-1:])]
        aktien = max(kand, key=lambda x: x[0]) if kand else None
        sd = sorted(roh.get("sd", {}).values()); sh = sorted(roh.get("sh", {}).values())
        f = {"cik": int(cik), "ni_jahr": ni_j, "rv_jahr": rv_j,
             "ni_ttm": _ttm(_quartale(ni_j, ni_q)), "rv_ttm": _ttm(_quartale(rv_j, rv_q)), "aktien": aktien,
             "aktien_reihe": _aktien_bereinigt(sd if len(sd) >= 8 else sh)}
        for t in cik_zu[cik]:
            out[t] = f
    for cik, f in _ausland_kennzahlen().items():   # auslaendische Firmen (nur Geschaeftsjahre, ohne Aktienzahl)
        for t in cik_zu.get(cik, []):
            out.setdefault(t, f)
    return out


def _ausland_kennzahlen() -> dict:
    if not AUSLAND.exists():
        return {}
    df = pd.read_parquet(AUSLAND)
    out = {}
    for cik, teil in df.groupby("cik", sort=False):
        reihe = lambda k: sorted({pd.Timestamp(e): (pd.Timestamp(e), float(v)) for e, v in
                                  zip(teil.loc[teil["k"] == k, "end"], teil.loc[teil["k"] == k, "val"])}.values())
        ni = reihe("ni")
        if not ni:
            continue
        w = teil.loc[teil["k"] == "ni", "waehrung"].iloc[-1]; st = teil.loc[teil["k"] == "ni", "standard"].iloc[-1]
        rv = reihe("rv") if (teil.loc[teil["k"] == "rv", "waehrung"] == w).all() else []   # Umsatz nur in derselben Waehrung
        out[int(cik)] = {"cik": int(cik), "ni_jahr": ni, "rv_jahr": rv, "ni_ttm": [], "rv_ttm": [], "aktien": None,
                         "aktien_reihe": None, "waehrung": w, "standard": st}
    return out


SPLIT_FAKTOREN = (1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 30, 40, 50)
KGV_LAG_TAGE = 60                 # KGV-Geschichte: Quartalszahlen gelten 60 Tage nach Quartalsende als bekannt (Berichtsfrist 40–90 Tage)


def _aktien_bereinigt(reihe: list) -> list | None:
    """Aktienzahl der letzten gut 11 Jahre, um Aktiensplits bereinigt (auf heutige Stueckelung).
    Ein Sprung um mehr als 40 % gilt nur dann als Split, wenn er bis auf 4 % einem ueblichen Verhaeltnis entspricht
    (2:1, 3:2, 10:1 … oder umgekehrt); sonst ist die Reihe unklar -> None (dann keine KGV-Geschichte, nicht raten)."""
    ab = pd.Timestamp(dt.date.today()) - pd.DateOffset(years=11, months=6)
    reihe = [(e, v) for e, v in reihe if e >= ab and v and v > 0]
    if len(reihe) < 8:
        return None
    out, faktor = [list(x) for x in reihe], 1.0
    for i in range(len(reihe) - 1, 0, -1):
        q = reihe[i][1] / reihe[i - 1][1]
        if not 0.7 < q < 1.4:
            r = q if q >= 1 else 1 / q
            split = min(SPLIT_FAKTOREN, key=lambda x: abs(r / x - 1))
            if abs(r / split - 1) > 0.04:
                return None
            faktor *= split if q >= 1 else 1 / split
        out[i - 1][1] = reihe[i - 1][1] * faktor
    return [(e, v) for e, v in out]


def _kgv_geschichte(f: dict, w, kgv_heute) -> dict:
    """KGV Woche fuer Woche in den letzten 10 Jahren (Wochenkurs x damalige Aktienzahl / damals bekannter Gewinn der
    letzten 12 Monate) und der Rang des heutigen KGV darin. Nur bei mind. 5 Jahren Daten und wenn die Rechnung fuer die
    letzte Woche zum heutigen KGV passt (sonst stimmt etwas mit Aktienzahl oder Gattung nicht -> nichts zeigen)."""
    reihe = f.get("aktien_reihe")
    if w is None or kgv_heute is None or not reihe or "Close" not in w:
        return {}
    gewinn = sorted({e: (e, v) for e, v in list(f["ni_jahr"]) + list(f["ni_ttm"])}.values())
    if not gewinn:
        return {}
    lag = pd.Timedelta(days=KGV_LAG_TAGE).value
    g_ab = np.array([e.value + lag for e, _ in gewinn], dtype=np.int64)
    a_ab = np.array([e.value + lag for e, _ in reihe], dtype=np.int64)
    c = w["Close"]
    c = c[c.index >= c.index[-1] - pd.DateOffset(years=10)]
    kgvs, verlust, letzte = [], 0, None
    for t, p in zip(c.index.values.astype("datetime64[ns]").astype(np.int64), c.values.astype(float)):
        k = int(np.searchsorted(g_ab, t, "right")) - 1; j = int(np.searchsorted(a_ab, t, "right")) - 1
        if k < 0 or j < 0 or t - gewinn[k][0].value > pd.Timedelta(days=550).value or not p > 0:
            continue
        ni = gewinn[k][1]
        if ni <= 0:
            verlust += 1; letzte = None
            continue
        letzte = p * reihe[j][1] / ni
        kgvs.append(letzte)
    if len(kgvs) + verlust < 260 or len(kgvs) < 52:
        return {}
    if letzte is None or not 0.7 <= letzte / kgv_heute <= 1.4:   # Plausibilitaet: letzte Woche muss zum heutigen KGV passen
        return {}
    a = np.array(kgvs)
    r = lambda x: round(float(x), 1)
    return {"kgv_rang": round(float((a < kgv_heute).mean()) * 100), "kgv_min": r(a.min()), "kgv_median": r(np.median(a)),
            "kgv_max": r(a.max()), "kgv_jahre": round((len(kgvs) + verlust) / 52.18, 1), "kgv_verlust_anteil": round(verlust / (len(kgvs) + verlust) * 100)}


def _wachstum_pa(jahr: list, n: int = 5):
    """Durchschnittliches Wachstum pro Jahr ueber die letzten n Geschaeftsjahre (mind. 3 Jahre Abstand, beide Werte positiv)."""
    j = jahr[-(n + 1):]
    if len(j) < 4 or j[0][1] <= 0 or j[-1][1] <= 0:
        return None, None
    jahre = (j[-1][0] - j[0][0]).days / 365.25
    if jahre < 2.5:
        return None, None
    return (math.pow(j[-1][1] / j[0][1], 1 / jahre) - 1) * 100, round(jahre)


def _veraenderung(neu, alt):
    if neu is None or alt is None or alt <= 0:
        return None
    return (neu / alt - 1) * 100


def fuer_zeile(f: dict, kurs: float | None, score: float | None, w=None) -> dict:
    """Kennzahlen fuer die Rangliste: KGV, KUV, Trend, Fallen-Warnung (alles mit dem heutigen Stand)."""
    def letzte_zwei(ttm, jahr):
        """Neuester Stand (12 Monate aus Quartalen oder letztes Geschaeftsjahr) und der Wert ein Jahr davor."""
        kand = []
        if ttm:
            e, v = ttm[-1]
            kand.append((e, v, _vorjahr(ttm, e) if _vorjahr(ttm, e) is not None else _vorjahr(jahr, e), "12 Monate"))
        if jahr:
            e, v = jahr[-1]
            kand.append((e, v, _vorjahr(jahr, e), "Geschäftsjahr"))
        if not kand:
            return None, None, None, None
        return max(kand, key=lambda x: (x[0], x[3] == "12 Monate"))
    stand, ni, ni_vor, art = letzte_zwei(f["ni_ttm"], f["ni_jahr"])
    _, rv, rv_vor, _ = letzte_zwei(f["rv_ttm"], f["rv_jahr"])
    if ni is None:
        return {}
    alt = stand is not None and stand < pd.Timestamp(dt.date.today()) - pd.Timedelta(days=550)
    mw = kurs * f["aktien"][1] if kurs and f.get("aktien") and f["aktien"][1] > 0 else None
    kgv = mw / ni if mw and ni > 0 else None
    kuv = mw / rv if mw and rv and rv > 0 else None
    d_ni, d_rv = _veraenderung(ni, ni_vor), _veraenderung(rv, rv_vor)
    if ni <= 0 or (ni_vor is not None and ni_vor <= 0):
        d_ni = None   # Verlust jetzt oder vorher: Prozent nicht sinnvoll
    jahre = f["ni_jahr"][-5:]
    schwach = ni <= 0 or (d_ni is not None and d_ni <= FALLE_GEWINN) or (d_rv is not None and d_rv <= FALLE_UMSATZ)
    gruende = []
    if ni <= 0: gruende.append("macht Verlust")
    elif d_ni is not None and d_ni <= FALLE_GEWINN: gruende.append(f"Gewinn {d_ni:+.0f} %")
    if d_rv is not None and d_rv <= FALLE_UMSATZ: gruende.append(f"Umsatz {d_rv:+.0f} %")
    r = lambda x, n=1: None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), n)
    kgv_out = r(kgv, 1) if kgv is not None and kgv < 1000 else None
    try:
        hist = _kgv_geschichte(f, w, kgv_out) if not alt else {}
    except Exception:
        hist = {}
    u_pa, u_j = _wachstum_pa(f["rv_jahr"]); g_pa, g_j = _wachstum_pa(f["ni_jahr"])
    ausland = {"waehrung": f["waehrung"], "standard": f["standard"],
               "kgv_fehlt": "Kein KGV: Der Kurs an der US-Börse gilt je ADR in Dollar, die Zahlen je Stammaktie in "
                            f"{f['waehrung']} – das Verhältnis ist nicht sicher bekannt."} if f.get("waehrung") else {}
    return {**hist, **ausland, "umsatz_pa": r(u_pa, 0), "umsatz_pa_jahre": u_j, "gewinn_pa": r(g_pa, 0), "gewinn_pa_jahre": g_j,
        "stand": stand.strftime("%Y-%m-%d") if stand is not None else None, "art": art, "veraltet": bool(alt),
        "gewinn": r(ni / 1e6, 1), "umsatz": r(rv / 1e6, 1) if rv else None,
        "mw": r(mw / 1e6, 0) if mw else None,   # Boersenwert in Mio. USD (fehlt bei auslaendischen Firmen) (Kurs x Aktienzahl laut SEC), Groesse der Heatmap-Kacheln
        "kgv": kgv_out, "kuv": r(kuv, 2) if kuv is not None and kuv < 1000 else None,
        "d_gewinn": r(d_ni, 0), "d_umsatz": r(d_rv, 0), "verlust": bool(ni <= 0),
        "jahre_gewinn": sum(1 for _, v in jahre if v > 0), "jahre": len(jahre),
        "schwach": bool(schwach and not alt), "falle": bool(schwach and not alt and score is not None and score >= FALLE_AMPEL),
        "gruende": gruende,
    }


# ----------------------------------------------------------------- Pruefung: Hilft die Warnung?
class Pruefung:
    """Wochen mit guenstiger Ampel (>= 60): Geschaeft damals schwach (nach den damals bekannten Jahreszahlen)
    gegen solide – wie lief der Kurs danach? Jahreszahlen gelten erst 90 Tage nach Geschaeftsjahresende als bekannt."""
    HOR = {"1": 52, "3": 156}

    def __init__(self):
        self.g = {grp: {h: [] for h in self.HOR} for grp in ("schwach", "solide", "alle")}
        self.aktien = {grp: set() for grp in self.g}

    def add(self, symbol: str, f: dict, w: pd.DataFrame, score: np.ndarray):
        rv = f["rv_jahr"]
        rv_enden = np.array([e.value for e, _ in rv], dtype=np.int64)
        jahre = [(e, v, rv[i][1] if (i := _nahe(rv_enden, e)) >= 0 else None) for e, v in f["ni_jahr"]]
        if len(jahre) < 2:
            return
        enden = np.array([pd.Timestamp(e).value for e, _, _ in jahre])
        bekannt_ab = enden + pd.Timedelta(days=LAG_TAGE).value
        c = w["Close"].values.astype(float)
        t = w.index.values.astype("datetime64[ns]").astype(np.int64)
        n = len(c)
        for i in range(0, n, 4):               # alle 4 Wochen (weniger Ueberlappung)
            s = score[i]
            if math.isnan(s):
                continue
            k = int(np.searchsorted(bekannt_ab, t[i], "right")) - 1
            if k < 1 or t[i] - enden[k] > pd.Timedelta(days=550).value:
                continue
            e1, ni, rv1 = jahre[k]; e0, ni0, rv0 = jahre[k - 1]
            if not (300 <= (e1 - e0).days <= 430):
                continue                        # Vorjahr fehlt
            d_ni = _veraenderung(ni, ni0) if ni > 0 and ni0 > 0 else None
            d_rv = _veraenderung(rv1, rv0) if rv1 is not None and rv0 is not None else None
            schwach = ni <= 0 or (d_ni is not None and d_ni <= FALLE_GEWINN) or (d_rv is not None and d_rv <= FALLE_UMSATZ)
            gruppen = ["alle"] + ([("schwach" if schwach else "solide")] if s >= FALLE_AMPEL else [])
            for h, wo in self.HOR.items():
                if i + wo >= n:
                    continue
                fwd = c[i + wo] / c[i] - 1
                for grp in gruppen:
                    self.g[grp][h].append(fwd)
                    self.aktien[grp].add(symbol)

    def ergebnis(self) -> dict:
        out = {"ampel_ab": FALLE_AMPEL, "regel": f"Verlust oder Gewinn ≤ {FALLE_GEWINN:.0f} % oder Umsatz ≤ {FALLE_UMSATZ:.0f} % gegenüber Vorjahr",
               "hinweis": "Jahreszahlen der SEC (gültig ab 90 Tage nach Geschäftsjahresende), Stichprobe alle 4 Wochen; nur heute noch gelistete Aktien"}
        for grp, hs in self.g.items():
            out[grp] = {"aktien": len(self.aktien[grp])}
            for h, x in hs.items():
                a = np.array(x)
                if len(a) < 20:
                    out[grp][h] = None
                    continue
                out[grp][h] = {"n": int(len(a)), "hoeher": round(float((a > 0).mean()) * 100, 1),
                               "median": round(float(np.median(a)) * 100, 1),
                               "absturz": round(float((a <= -0.5).mean()) * 100, 1),
                               "pa": round((math.exp(np.log1p(a).mean() * 52 / self.HOR[h]) - 1) * 100, 1)}
        return out


if __name__ == "__main__":
    laden()
    k = kennzahlen()
    print(f"Geschäftszahlen für {len(k)} Tickersymbole")
    sys.exit(0)   # Netz- oder SEC-Fehler sollen den Tageslauf nicht stoppen
