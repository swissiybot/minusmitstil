"""Dividenden je Wert (Aktien und ETFs) fuer die Titelseite – nur Ausschuettungen laut Yahoo, nichts geschaetzt.

Die Kurse in kurse.parquet sind um Dividenden bereinigt (auto_adjust): Renditen und Charts enthalten die Dividenden schon.
Hier werden sie NUR AUSGEWIESEN (wie viel, wie oft, seit wann), nirgends ein zweites Mal in Renditen gerechnet.

Laden:   python dividenden.py           hoechstens einmal pro Woche neu (sonst sofort fertig), alle Aktien und ETFs
         python dividenden.py --neu     jetzt neu laden
         python dividenden.py AAPL SPY  nur diese Symbole (zum Testen)
Quelle:  Yahoo ueber yfinance, Monatskerzen mit „actions“ (Ausschuettungen eines Monats zusammengezaehlt, je Aktie,
         um Aktiensplits bereinigt wie bei Yahoo). Ergebnis daten/dividenden.parquet (s, monat, betrag) – nicht im Repo.

Feld „div“ in der Kopfzeile eines Werts (fuer_wert): nur, wenn laut Yahoo je ausgeschuettet wurde.
  rendite     Summe der letzten 12 Monate in % zum heutigen Kurs (None, wenn die Waehrung nicht sicher passt)
  summe12     Summe der letzten 12 Monate je Anteil, in der Waehrung der Ausschuettung
  jahre       [[Jahr, Summe], ...] je Kalenderjahr; laufend = das noch nicht abgeschlossene Jahr
  wachstum5   Ø Wachstum pro Jahr der Jahressumme ueber 5 abgeschlossene Jahre in % (None ohne 5 Jahre Vorlauf)
  seit        erstes Jahr mit Ausschuettung in den Yahoo-Daten;  ohne_luecke_seit  seit wann jedes Jahr ausgeschuettet wurde
  letzte      [Monat, Betrag] der letzten Ausschuettung;  monate  Monate mit Ausschuettung im letzten abgeschlossenen Jahr
  stand       Tag, an dem die Ausschuettungen geladen wurden;  quelle
"""
import datetime as dt
import json
import os
import sys
import time
import pandas as pd

import einstellungen as E

DATEI = E.DATEN / "dividenden.parquet"
LAUF = E.DATEN / "dividenden_lauf.json"
ALTER_TAGE = 6            # so lange gilt der letzte Stand (Ausschuettungen aendern sich selten)
STAPEL = 40
ABBRUCH_NACH = 5          # Stapel in Folge ganz ohne Daten -> Yahoo sperrt, aufhoeren (alter Stand bleibt)
RENDITE_MAX = 25.0        # mehr als 25 % in 12 Monaten: Rendite nicht ausweisen (meist Datenfehler oder Sonderfall)
QUELLE = "Yahoo Finance (über yfinance), Ausschüttungen je Anteil"
_CACHE: dict | None = None


# ----------------------------------------------------------------- Laden
def symbole() -> list[str]:
    uni = pd.read_csv(E.DATEN / "universum.csv")
    uni = uni[~uni["gruppe"].isin(["Krypto", "Rohstoffe"])]
    return [s for s in dict.fromkeys(uni["symbol"]) if not str(s).startswith("^")]


def _stapel_laden(liste: list[str]) -> tuple[dict, set]:
    import yfinance as yf
    df = yf.download(liste, period="max", interval="1mo", actions=True, auto_adjust=True, group_by="ticker",
                     threads=True, progress=False)
    gefunden, mit_kursen = {}, set()
    if df is None or df.empty:
        return gefunden, mit_kursen
    for s in liste:
        try:
            teil = df[s] if isinstance(df.columns, pd.MultiIndex) else df
        except KeyError:
            continue
        if teil["Close"].dropna().empty:
            continue
        mit_kursen.add(s)   # Yahoo kennt den Wert (auch wenn er nie ausgeschuettet hat)
        if "Dividends" in teil:
            d = teil["Dividends"].dropna()
            d = d[d > 0]
            if len(d):
                idx = pd.to_datetime(d.index)
                idx = idx.tz_localize(None) if idx.tz is not None else idx
                gefunden[s] = pd.Series(d.values.astype(float), index=idx.to_period("M").to_timestamp())
    return gefunden, mit_kursen


def main(argv):
    neu = "--neu" in argv
    nur = [a for a in argv if not a.startswith("--")]
    if not nur and not neu and DATEI.exists() and time.time() - DATEI.stat().st_mtime < ALTER_TAGE * 86400:
        print(f"Dividenden: Stand vom {dt.date.fromtimestamp(DATEI.stat().st_mtime):%d.%m.%Y} gilt noch (wöchentlich neu)")
        return
    liste = nur or symbole()
    alt = pd.read_parquet(DATEI) if DATEI.exists() else pd.DataFrame(columns=["s", "monat", "betrag"])
    neu_teile, geprueft, leer_folge, abgebrochen = [], set(), 0, False
    for i in range(0, len(liste), STAPEL):
        stapel = liste[i:i + STAPEL]
        for versuch in range(3):
            try:
                gef, mit = _stapel_laden(stapel)
                break
            except Exception as ex:
                print(f"  Dividenden: Fehler ({ex.__class__.__name__}: {ex}); warte {30 * (versuch + 1)} s", flush=True)
                time.sleep(30 * (versuch + 1))
        else:
            gef, mit = {}, set()
        geprueft |= mit
        for s, ser in gef.items():
            neu_teile.append(pd.DataFrame({"s": s, "monat": ser.index, "betrag": ser.values}))
        leer_folge = leer_folge + 1 if not mit else 0
        if (i // STAPEL) % 10 == 0 or i + STAPEL >= len(liste):
            print(f"  Dividenden: {min(i + STAPEL, len(liste))}/{len(liste)}", flush=True)
        if leer_folge >= ABBRUCH_NACH:
            print("  Dividenden: ABBRUCH – mehrere Stapel ohne Daten (Yahoo sperrt vermutlich); alter Stand bleibt", flush=True)
            abgebrochen = True
            break
        time.sleep(E.PAUSE_SEKUNDEN)
    # neu geprüfte Werte ersetzen, alle anderen behalten ihren alten Stand
    behalten = alt[~alt["s"].isin(geprueft)] if len(alt) else alt
    gesamt = pd.concat([behalten] + neu_teile, ignore_index=True) if neu_teile or len(behalten) else behalten
    if len(gesamt):
        gesamt["monat"] = pd.to_datetime(gesamt["monat"]).astype("datetime64[ms]")
        gesamt = gesamt.groupby(["s", "monat"], as_index=False)["betrag"].sum().sort_values(["s", "monat"])
        tmp = DATEI.with_suffix(".tmp")
        gesamt.to_parquet(tmp, index=False, compression="zstd")
        tmp.replace(DATEI)
    stand = json.loads(LAUF.read_text()) if LAUF.exists() else {}
    stand.update({"stand": dt.date.today().isoformat(), "geprueft": len(geprueft), "von": len(liste),
                  "mit_dividende": int(gesamt["s"].nunique()) if len(gesamt) else 0, "abgebrochen": abgebrochen})
    if not nur:
        LAUF.write_text(json.dumps(stand))
    print(f"Dividenden: {len(geprueft)} von {len(liste)} Werten bei Yahoo gefunden, "
          f"{stand['mit_dividende']} mit Ausschüttungen" + (" – abgebrochen, alter Stand ergänzt" if abgebrochen else ""))


# ----------------------------------------------------------------- Auswerten
def _laden() -> dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = {"reihen": {}, "stand": None}
        if DATEI.exists():
            t = pd.read_parquet(DATEI)
            for s, teil in t.groupby("s", sort=False):
                _CACHE["reihen"][str(s)] = pd.Series(teil["betrag"].values, index=pd.to_datetime(teil["monat"]))
            try:
                _CACHE["stand"] = json.loads(LAUF.read_text()).get("stand")
            except Exception:
                _CACHE["stand"] = dt.date.fromtimestamp(DATEI.stat().st_mtime).isoformat()
    return _CACHE


def waehrung_sicher(symbol: str) -> bool:
    """Rendite nur, wo Kurs und Ausschuettung sicher in derselben Waehrung stehen. London (.L) nicht: dort notieren
    Kurse oft in Pence und manche ETFs schuetten in Dollar aus (z. B. VWRL)."""
    return not str(symbol).upper().endswith(".L")


def fuer_wert(symbol: str, kurs: float | None, datum: str | None) -> dict | None:
    c = _laden()
    d = c["reihen"].get(symbol)
    if d is None or d.empty or not datum:
        return None
    heute = pd.Timestamp(datum)
    ab = (heute - pd.DateOffset(months=12)).to_period("M").to_timestamp() + pd.DateOffset(months=1)
    d = d[d.index <= heute]
    if d.empty:
        return None
    summe12 = float(d[d.index >= ab].sum())
    je_jahr = d.groupby(d.index.year).sum()
    laufend = int(heute.year)
    alle_jahre = range(int(je_jahr.index[0]), laufend + 1)   # Jahre ohne Ausschuettung als 0 (z. B. Apple 1996–2011)
    jahre = [[j, round(float(je_jahr.get(j, 0.0)), 4)] for j in alle_jahre]
    ohne_luecke = None   # erstes Jahr der laufenden Reihe ohne Jahr ganz ohne Ausschuettung (bis zum letzten vollen Jahr)
    j = laufend - 1 if je_jahr.get(laufend - 1, 0) > 0 else (laufend if je_jahr.get(laufend, 0) > 0 and laufend - 1 < je_jahr.index[0] else None)
    while j is not None and je_jahr.get(j, 0) > 0:
        ohne_luecke, j = j, j - 1
    voll = [j for j in je_jahr.index if j < laufend]
    wachstum5 = None
    if voll:
        j1 = max(voll)
        if (j1 - 5) in je_jahr.index and je_jahr[j1 - 5] > 0 and je_jahr[j1] > 0:
            wachstum5 = round(float((je_jahr[j1] / je_jahr[j1 - 5]) ** (1 / 5) - 1) * 100, 1)
    rendite, hinweis = None, None
    if kurs and kurs > 0 and waehrung_sicher(symbol):
        rendite = summe12 / kurs * 100
        if rendite > RENDITE_MAX:
            rendite, hinweis = None, f"Ausschüttungen der letzten 12 Monate über {RENDITE_MAX:.0f} % des Kurses – Rendite nicht ausgewiesen (Sonderausschüttung oder Datenfehler möglich)"
        else:
            rendite = round(rendite, 2)
    elif not waehrung_sicher(symbol):
        hinweis = "Rendite nicht ausgewiesen: an der Londoner Börse können Kurs und Ausschüttung in verschiedenen Währungen stehen"
    out = {"rendite": rendite, "summe12": round(summe12, 4), "jahre": jahre, "laufend": laufend, "wachstum5": wachstum5,
           "seit": int(je_jahr.index[0]), "ohne_luecke_seit": ohne_luecke, "letzte": [d.index[-1].strftime("%Y-%m"), round(float(d.iloc[-1]), 4)],
           "monate": int((d.index.year == max(voll)).sum()) if voll else None,
           "stand": c["stand"], "quelle": QUELLE}
    if hinweis:
        out["hinweis"] = hinweis
    return out


def kurz(div: dict | None) -> dict | None:
    """Kleine Fassung fuer die Rangliste (ohne Jahresliste)."""
    if not div:
        return None
    return {k: div.get(k) for k in ("rendite", "summe12", "wachstum5", "seit")}


if __name__ == "__main__":
    main(sys.argv[1:])
