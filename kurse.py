"""Laedt Tageskurse von Yahoo (ueber yfinance), gedrosselt, und speichert sie platzsparend.

Speicher: EINE Datei daten/kurse.parquet (alle Werte untereinander, nach Symbol sortiert,
float32, zstd-komprimiert). Einzelne Werte lassen sich trotzdem schnell lesen, weil die Datei
in Bloecke je Symbol geteilt ist und nur der passende Block gelesen wird.

- Erster Lauf: komplette Historie je Wert ("max").
- Folgelaeufe: nur der letzte Monat, wird angehaengt.
Kurse sind um Splits und Dividenden bereinigt (auto_adjust), damit Renditen Dividenden enthalten.
Indizes (^GSPC usw.) haben keine Dividenden – das wird im Dashboard gekennzeichnet.

Aufruf:  python kurse.py            (alle Werte)
         python kurse.py SPY AAPL   (nur diese Symbole)

Umgebungsvariablen (fuer den Online-Lauf auf GitHub):
  KURSE_NEU_LADEN=1      auch heute schon geladene Werte neu holen (mehrere Laeufe am Tag)
  KURSE_ABBRUCH_NACH=5   nach so vielen Stapeln in Folge ganz ohne Daten aufhoeren (Yahoo sperrt);
                         der bisherige Stand bleibt erhalten und wird trotzdem ausgewertet
"""
import os
import sys
import time
import datetime as dt
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import einstellungen as E

# yfinance oeffnet je Stapel viele Verbindungen; als Hintergrunddienst ist das Limit sonst zu knapp.
try:
    import resource
    _weich, _hart = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(_hart, 65536), _hart))
except Exception:
    pass

DATEI = E.DATEN / "kurse.parquet"
SPALTEN = ["Open", "High", "Low", "Close", "Volume"]
_SPEICHER: dict[str, pd.DataFrame] | None = None   # alle Werte im Arbeitsspeicher (nur fuer Laeufe)


# ----------------------------------------------------------------- Lesen
def alle_laden() -> dict[str, pd.DataFrame]:
    """Liest die ganze Kursdatei einmal ein (fuer Download und Auswertung)."""
    global _SPEICHER
    if _SPEICHER is None:
        _SPEICHER = {}
        if DATEI.exists():
            t = pq.read_table(DATEI).to_pandas()
            for s, teil in t.groupby("s", sort=False, observed=True):
                _SPEICHER[str(s)] = teil.set_index("datum")[SPALTEN].astype("float64")
    return _SPEICHER


def lade_lokal(symbol: str) -> pd.DataFrame | None:
    """Kurse eines Werts. Nutzt den Arbeitsspeicher, sonst wird nur der passende Block gelesen."""
    if _SPEICHER is not None:
        return _SPEICHER.get(symbol)
    if not DATEI.exists():
        return None
    t = pq.read_table(DATEI, filters=[("s", "==", symbol)]).to_pandas()
    if t.empty:
        return None
    return t.set_index("datum")[SPALTEN].astype("float64")


# ----------------------------------------------------------------- Schreiben
def speichern_alle():
    """Schreibt alle Werte als eine komprimierte Datei (erst in Zwischendatei, dann umbenennen)."""
    teile = []
    for s in sorted(_SPEICHER):
        d = _SPEICHER[s]
        if d is None or d.empty:
            continue
        x = d[SPALTEN].astype("float32").copy()
        x.index.name = "datum"
        x = x.reset_index()
        x.insert(0, "s", s)
        teile.append(x)
    df = pd.concat(teile, ignore_index=True)
    df["datum"] = pd.to_datetime(df["datum"]).astype("datetime64[ms]")
    tabelle = pa.Table.from_pandas(df, preserve_index=False)
    tmp = DATEI.with_suffix(".tmp")
    pq.write_table(tabelle, tmp, compression="zstd", compression_level=9, row_group_size=20000,
                   use_dictionary=["s"], write_statistics=True)
    tmp.replace(DATEI)


def _einfuegen(symbol: str, neu: pd.DataFrame) -> bool:
    neu = neu.dropna(subset=["Close"])
    if neu.empty:
        return False
    neu = neu[SPALTEN].astype("float64")
    neu.index = pd.to_datetime(neu.index).tz_localize(None).normalize()
    alt = _SPEICHER.get(symbol)
    if alt is not None and not alt.empty:
        neu = pd.concat([alt[alt.index < neu.index.min()], neu])
    _SPEICHER[symbol] = neu[~neu.index.duplicated(keep="last")].sort_index()
    return True


def migrieren():
    """Einmalig: alte Einzeldateien aus daten/kurse/ uebernehmen."""
    alte = sorted(E.KURSE.glob("*.parquet"))
    if not alte or DATEI.exists():
        return
    print(f"Uebernehme {len(alte)} alte Einzeldateien in {DATEI.name} ...")
    global _SPEICHER
    _SPEICHER = {}
    for f in alte:
        sym = f.stem.replace("_", "^", 1) if f.stem.startswith("_") else f.stem
        _SPEICHER[sym] = pd.read_parquet(f)
    speichern_alle()
    print("Fertig uebernommen.")


# ----------------------------------------------------------------- Download
def alle_symbole() -> list[str]:
    uni = pd.read_csv(E.DATEN / "universum.csv")
    s = list(uni["symbol"])
    for e in E.ETFS:  # Index-Vorlaeufe
        s += [x for x in (e.get("index"), e.get("index_tr"), e.get("vorlauf_etf")) if x]
    s += ["^VIX"]  # fuer Stufe 2 (Marktumfeld)
    return list(dict.fromkeys(s))


def lade_stapel(symbole: list[str], zeitraum: str) -> tuple[int, list[str]]:
    import yfinance as yf
    df = yf.download(symbole, period=zeitraum, interval="1d", auto_adjust=True, group_by="ticker",
                     threads=True, progress=False)
    ok, fehlt = 0, []
    for s in symbole:
        try:
            teil = df[s] if isinstance(df.columns, pd.MultiIndex) else df
            if _einfuegen(s, teil.copy()):
                ok += 1
            else:
                fehlt.append(s)
        except KeyError:
            fehlt.append(s)
    return ok, fehlt


def main(argv):
    migrieren()
    alle_laden()
    symbole = argv or alle_symbole()
    heute = pd.Timestamp(dt.date.today())
    neu_laden, nachladen = [], []
    for s in symbole:
        lokal = _SPEICHER.get(s)
        if lokal is None or lokal.empty:
            neu_laden.append(s)
        elif (heute - lokal.index.max()).days >= 1 or os.environ.get("KURSE_NEU_LADEN") == "1":
            nachladen.append(s)
    print(f"{len(neu_laden)} Werte komplett laden, {len(nachladen)} Werte aktualisieren")
    fehler, stapel_nr = [], 0
    abbruch_nach = int(os.environ.get("KURSE_ABBRUCH_NACH", "0") or 0)
    leer_in_folge, abgebrochen, geladen = 0, False, 0
    for liste, zeitraum in ((neu_laden, "max"), (nachladen, "1mo")):
        if abgebrochen:
            fehler += liste
            continue
        for i in range(0, len(liste), E.STAPEL_GROESSE):
            if abgebrochen:
                fehler += liste[i:i + E.STAPEL_GROESSE]
                continue
            stapel = liste[i:i + E.STAPEL_GROESSE]
            for versuch in range(4):
                try:
                    ok, fehlt = lade_stapel(stapel, zeitraum)
                    break
                except Exception as ex:  # Sperre oder Netzfehler: warten und erneut
                    warte = 30 * (versuch + 1)
                    print(f"  Fehler ({ex.__class__.__name__}: {ex}); warte {warte}s")
                    time.sleep(warte)
            else:
                ok, fehlt = 0, stapel
            fehler += fehlt
            geladen += ok
            leer_in_folge = leer_in_folge + 1 if ok == 0 else 0
            print(f"  {zeitraum}: {min(i + E.STAPEL_GROESSE, len(liste))}/{len(liste)} – ok {ok}, ohne Daten {len(fehlt)}", flush=True)
            if abbruch_nach and leer_in_folge >= abbruch_nach:
                print(f"ABBRUCH: {leer_in_folge} Stapel in Folge ohne Daten (Yahoo sperrt vermutlich). "
                      "Es wird mit dem letzten gespeicherten Stand weitergearbeitet.", flush=True)
                abgebrochen = True
            stapel_nr += 1
            if zeitraum == "max" and stapel_nr % 25 == 0:
                speichern_alle()   # Zwischenstand bei langen Erstladungen sichern
            time.sleep(E.PAUSE_SEKUNDEN)
    if geladen:
        speichern_alle()
    (E.DATEN / "ohne_daten.txt").write_text("\n".join(fehler))
    (E.DATEN / "kurse_lauf.json").write_text(__import__("json").dumps({
        "zeit": dt.datetime.now().isoformat(timespec="minutes"), "gesamt": len(symbole), "geladen": geladen,
        "ohne_daten": len(fehler), "abgebrochen": abgebrochen}))
    print(f"Fertig. Geladen: {geladen}, ohne Daten: {len(fehler)} von {len(symbole)} (Liste in daten/ohne_daten.txt)"
          + (" – ABGEBROCHEN, alter Stand bleibt" if abgebrochen else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
