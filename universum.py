"""Baut die Liste aller Werte: Nasdaq- und NYSE-Aktien, wichtige Auslandsaktien (welt.py), FTSE All-World (aus Vanguard-Excel), ETFs, Krypto, Rohstoffe.

Krypto: die fünf Kernwerte plus die feste Top-200-Liste listen/krypto.csv (krypto_liste.py baut sie von Hand neu).
Hebel 2x: feste, geprüfte Liste in einstellungen.HEBEL_ETFS (Gruppe ETF, Art „Hebel 2x“).

Ergebnis: daten/universum.csv mit Spalten
    id, symbol, name, gruppe, land, branche, ftse (1 = steht in der Vanguard-Liste des FTSE All-World)
"""
import io
import sys
import glob
import pandas as pd
import requests

import einstellungen as E

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) aktien-kaufplan"}

# Yahoo-Endung je Land fuer FTSE-Werte (Bloomberg-Laendercode aus der Vanguard-Liste)
ENDUNG = {
    "US": "", "CA": ".TO", "GB": ".L", "DE": ".DE", "FR": ".PA", "NL": ".AS", "BE": ".BR",
    "CH": ".SW", "IT": ".MI", "ES": ".MC", "PT": ".LS", "SE": ".ST", "NO": ".OL", "DK": ".CO",
    "FI": ".HE", "AT": ".VI", "IE": ".IR", "JP": ".T", "HK": ".HK", "AU": ".AX", "NZ": ".NZ",
    "SG": ".SI", "KR": ".KS", "TW": ".TW", "IN": ".NS", "BR": ".SA", "MX": ".MX", "CL": ".SN",
    "ZA": ".JO", "IL": ".TA", "TR": ".IS", "SA": ".SR", "TH": ".BK", "MY": ".KL", "ID": ".JK",
    "PH": ".PS", "PL": ".WA", "GR": ".AT", "CZ": ".PR", "HU": ".BD", "AE": ".AE", "QA": ".QA",
    "KW": ".KW", "EG": ".CA", "CO": ".CL",
}


def nasdaq() -> pd.DataFrame:
    """Alle an der Nasdaq gelisteten Stammaktien (ohne ETFs, Testwerte, Optionsscheine, Vorzuege)."""
    t = requests.get("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", headers=UA, timeout=60).text
    df = pd.read_csv(io.StringIO(t), sep="|")
    df = df[df["Symbol"].notna() & ~df["Symbol"].astype(str).str.startswith("File Creation")]
    df = df[(df["ETF"] == "N") & (df["Test Issue"] == "N")]
    raus = r"Warrant|Right|Unit|Preferred|Depositary Shares? representing|Notes due|Debenture|% "
    df = df[~df["Security Name"].str.contains(raus, case=False, regex=True)]
    df = df[df["Financial Status"].fillna("N").isin(["N"])]  # keine Werte in Insolvenz/Verzug
    out = pd.DataFrame({
        "id": df["Symbol"].str.replace(".", "-", regex=False),
        "symbol": df["Symbol"].str.replace(".", "-", regex=False),
        "name": df["Security Name"].str.replace(r" - (Class [A-Z] )?Common Stock.*$| Common Stock.*$| - Ordinary Shares.*$| - American Depositary.*$", "", regex=True),
        "gruppe": "Nasdaq",
        "land": "US",
        "branche": "",
    })
    return out


def nyse() -> pd.DataFrame:
    """Stammaktien und ADRs der New York Stock Exchange (ohne ETFs, Vorzüge, Fonds, Anleihen, Optionsscheine)."""
    t = requests.get("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt", headers=UA, timeout=60).text
    df = pd.read_csv(io.StringIO(t), sep="|")
    df = df[df["ACT Symbol"].notna() & ~df["ACT Symbol"].astype(str).str.startswith("File Creation")]
    df = df[(df["Exchange"] == "N") & (df["ETF"] == "N") & (df["Test Issue"] == "N") & ~df["ACT Symbol"].astype(str).str.contains(r"\$")]
    raus = r"Warrant|Right|Unit|Preferred|Depositary Shares? representing|Notes due|Debenture|% |Pfd|Fund|Trust Units|Senior|Subordinated|Perpetual"
    df = df[~df["Security Name"].str.contains(raus, case=False, regex=True)]
    sym = df["ACT Symbol"].astype(str).str.replace(".", "-", regex=False)
    name = df["Security Name"].str.replace(r" (New )?Common Stock.*$| Ordinary Shares.*$| American [Dd]epositary.*$| \(The\)", "", regex=True)
    out = pd.DataFrame({"id": sym, "symbol": sym, "name": name.str.strip(), "gruppe": "NYSE", "land": "US", "branche": ""})
    print(f"NYSE: {len(out)} Werte")
    return out


def welt() -> pd.DataFrame:
    """Wichtige Aktien außerhalb der USA an ihrer Heimatbörse (aus welt.py / Wikidata, daten/welt.csv)."""
    datei = E.DATEN / "welt.csv"
    if not datei.exists():
        print("Hinweis: keine daten/welt.csv (welt.py) – Auslandsaktien werden übersprungen.")
        return pd.DataFrame(columns=["id", "symbol", "name", "gruppe", "land", "branche"])
    d = pd.read_csv(datei, dtype=str).dropna(subset=["symbol"])
    d = d[d["symbol"].str.len() > 0].drop_duplicates("symbol")
    out = pd.DataFrame({"id": d["symbol"], "symbol": d["symbol"], "name": d["name"], "gruppe": "Welt", "land": d["land"], "branche": ""})
    print(f"Welt: {len(out)} Werte")
    return out


def _yahoo_symbol(ticker: str, land: str) -> str | None:
    t = str(ticker).strip().upper().replace("/", "-").replace(" ", "-")
    if land not in ENDUNG or not t or t == "NAN":
        return None
    if land == "HK":
        t = t.zfill(4)
    if land == "CN":  # A-Aktien: 6xxxxx Shanghai, sonst Shenzhen
        return t + (".SS" if t.startswith("6") else ".SZ")
    if land == "GB":
        t = t.rstrip(".")
    return t + ENDUNG[land]


def ftse_all_world() -> pd.DataFrame:
    """Liest die von Hand heruntergeladene Vanguard-Bestandsliste (Excel/CSV) aus daten/eingang/.

    Erwartet: eine Datei *.xlsx, *.xls oder *.csv direkt in daten/eingang/ (Name egal; bei mehreren gilt die alphabetisch
    letzte). Irgendwo steht eine Kopfzeile mit der Spalte „Ticker“; dazu eine Namensspalte („Holding name“ oder „Name“) und
    eine Länderspalte („Country“, „Land“ oder „Region“) mit Zwei-Buchstaben-Codes (US, GB, JP …) – daraus wird die
    Yahoo-Endung (ENDUNG). Zeilen mit unbekanntem Land fallen weg (auch „CN“: solange nicht an der echten Datei geprüft ist,
    ob dort A-Aktien oder Hongkong-Kürzel stehen, wird nichts geraten). Optional eine Branchenspalte („Sector“, „Sektor“).
    STAND 24.11.2026: noch nie mit einer echten Vanguard-Datei gelaufen – beim ersten Mal die Ausgabe (Anzahl, Länder ohne
    Endung, daten/ohne_daten.txt nach dem Kursabruf) prüfen. Online wirkt die Datei nicht: daten/eingang/ ist in .gitignore
    (Vanguard-Datei nicht weitergeben) und liegt nicht im Zwischenspeicher der Online-Läufe.
    Eine unlesbare Datei wird mit Warnung übersprungen (sie darf nicht die ganze Werteliste einfrieren)."""
    leer = pd.DataFrame(columns=["id", "symbol", "name", "gruppe", "land", "branche"])
    dateien = sorted(glob.glob(str(E.EINGANG / "*.xls*")) + glob.glob(str(E.EINGANG / "*.csv")))
    if not dateien:
        print("Hinweis: keine Vanguard-Liste in daten/eingang/ - FTSE All-World wird uebersprungen.")
        return leer
    datei = dateien[-1]
    if len(dateien) > 1:
        print(f"Hinweis: {len(dateien)} Dateien in daten/eingang/ – verwendet wird {datei}")
    try:
        return _ftse_lesen(datei)
    except Exception as ex:
        print(f"WARNUNG: Vanguard-Liste {datei} nicht lesbar ({ex.__class__.__name__}: {ex}) – FTSE All-World wird übersprungen.", file=sys.stderr)
        return leer


def _ftse_tabelle(datei: str) -> pd.DataFrame:
    """Rohtabelle ohne Kopf. CSV: Trennzeichen ausprobieren (Komma, Semikolon, Tabulator), Vorspann-Zeilen dürfen kürzer sein."""
    if not datei.lower().endswith(".csv"):
        return pd.read_excel(datei, header=None)
    for sep in (",", ";", "\t"):
        try:
            roh = pd.read_csv(datei, header=None, sep=sep, names=range(40), dtype=str, engine="python", encoding="utf-8-sig")
        except Exception:
            continue
        if roh.apply(lambda r: r.astype(str).str.fullmatch(r"\s*Ticker\s*", case=False).any(), axis=1).any():
            return roh.dropna(axis=1, how="all")
    raise ValueError("keine Kopfzeile mit der Spalte „Ticker“ gefunden")


def _ftse_lesen(datei: str) -> pd.DataFrame:
    roh = _ftse_tabelle(datei)
    # Kopfzeile suchen (Zeile, in der "Ticker" steht)
    kopf = next((i for i, r in roh.iterrows() if r.astype(str).str.contains("Ticker", case=False).any()), None)
    if kopf is None:
        raise ValueError("keine Kopfzeile mit der Spalte „Ticker“ gefunden")
    df = roh.loc[roh.index > kopf].copy()
    df.columns = [str(c).strip() for c in roh.loc[kopf]]
    spalte = lambda *namen: next((c for c in df.columns if any(n.lower() in c.lower() for n in namen)), None)
    c_tick, c_name, c_land = spalte("Ticker"), spalte("Holding name", "Name"), spalte("Country", "Land", "Region")
    c_branche = spalte("Sector", "Sektor", "Industry")
    if c_name is None:
        raise ValueError(f"keine Namensspalte gefunden (Spalten: {list(df.columns)})")
    df = df[df[c_tick].notna() & (df[c_tick].astype(str).str.strip() != "")]
    land = df[c_land].astype(str).str.strip().str.upper() if c_land else pd.Series("US", index=df.index)
    sym = [_yahoo_symbol(t, l) for t, l in zip(df[c_tick], land)]
    out = pd.DataFrame({
        "id": sym, "symbol": sym, "name": df[c_name].astype(str).str.strip().values,
        "gruppe": "FTSE All-World", "land": list(land),
        "branche": df[c_branche].astype(str).values if c_branche else "",
    })
    ohne = out[out["symbol"].isna()]
    out = out[out["symbol"].notna()].drop_duplicates("symbol")
    print(f"FTSE All-World aus {datei}: {len(out)} Werte" + (f"; {len(ohne)} Zeilen ohne Yahoo-Endung (Länder: {ohne['land'].value_counts().head(12).to_dict()})" if len(ohne) else ""))
    if not c_land:
        print("Hinweis: keine Länderspalte gefunden – alle Kürzel als US-Kürzel behandelt (bitte prüfen).")
    return out


def etfs_und_bitcoin() -> pd.DataFrame:
    # Hebel-Produkte (einstellungen.HEBEL_ETFS): Gruppe ETF, Art „Hebel 2x“; ETCs und ETPs heißen auch so
    zeilen = [{"id": e["id"], "symbol": e["etf"], "name": e["name"] + f" ({(e.get('hebel') or {}).get('art') or 'ETF'})",
               "gruppe": "ETF", "land": "", "branche": e.get("branche", "Index")} for e in E.ETFS]
    for k in E.KRYPTO:
        zeilen.append({"id": k["id"], "symbol": k["symbol"], "name": k["name"], "gruppe": "Krypto", "land": "", "branche": "Krypto"})
    for r in E.ROHSTOFFE:
        zeilen.append({"id": r["id"], "symbol": r["symbol"], "name": r["name"], "gruppe": "Rohstoffe", "land": "",
                       "branche": "Future" if r["art"] == "rohstoff" else "Rohstoff-ETC" if r["art"] == "etc" else "Rohstoff-ETF"})
    return pd.DataFrame(zeilen)


def kennungen_eindeutig(df: pd.DataFrame) -> pd.DataFrame:
    """Jede Kennung (id) nur einmal. ETFs, Krypto und Rohstoffe stehen vorn und behalten ihre Kennung (Signal-Tagebuch,
    Alarme, gemerkte Werte und Depots im Browser hängen daran). Ein Börsenkürzel, das mit einer früheren Kennung
    kollidiert (z. B. NYSE „GOLD“ gegen den Rohstoff Gold, NYSE „WTI“ gegen Rohöl WTI), bekommt die Börse als Zusatz:
    GOLD_NYSE. Das Kürzel (symbol) bleibt unverändert, damit die Kurse weiter passen."""
    gesehen, neu = set(), []
    for wid, g in zip(df["id"].astype(str), df["gruppe"].astype(str)):
        if wid in gesehen:
            boerse = "NYSE" if "NYSE" in g else "NASDAQ" if "Nasdaq" in g else g.split()[0].upper().replace("-", "")
            kand, n = f"{wid}_{boerse}", 2
            while kand in gesehen:
                kand, n = f"{wid}_{boerse}{n}", n + 1
            print(f"Kennung doppelt: {wid} ({g}) heißt jetzt {kand}")
            wid = kand
        gesehen.add(wid)
        neu.append(wid)
    df = df.copy()
    df["id"] = neu
    if not df["id"].is_unique:   # darf nach dem Umbenennen nicht vorkommen
        raise SystemExit("Werteliste: Kennungen nicht eindeutig – abgebrochen")
    return df


def main():
    ziel = E.DATEN / "universum.csv"
    try:
        teile = [etfs_und_bitcoin(), nasdaq(), nyse(), welt(), ftse_all_world()]
    except Exception as ex:
        # Netzfehler: die zwischengespeicherte Liste weiterverwenden, aber auch dort die Kennungen eindeutig machen
        if not ziel.exists():
            raise
        print(f"Werteliste nicht ladbar ({ex.__class__.__name__}: {ex}) – nutze die zwischengespeicherte", file=sys.stderr)
        alt = pd.read_csv(ziel, dtype=str, keep_default_na=False)
        kennungen_eindeutig(alt).to_csv(ziel, index=False)
        return 0
    df = pd.concat(teile, ignore_index=True)
    # Doppelte (z. B. Apple in Nasdaq und FTSE All-World) zusammenfassen. Die Gruppe bleibt die der ersten Fundstelle
    # (Nasdaq, NYSE, Welt …): Viele Stellen vergleichen die Gruppe genau (Beschreibung und ISIN, $/€-Umschalter,
    # TradingView-Kürzel) – eine zusammengesetzte Gruppe „Nasdaq + FTSE All-World“ hätte dort rund 1.500 vorhandene Werte
    # verschlechtert. Die Zugehörigkeit zum FTSE All-World steht stattdessen in der eigenen Spalte „ftse“ (1 oder leer).
    df["ftse"] = df.groupby("symbol")["gruppe"].transform(lambda g: "1" if "FTSE All-World" in set(g) else "")
    df = df.drop_duplicates("symbol", keep="first")
    df = kennungen_eindeutig(df)
    df.to_csv(ziel, index=False)
    print(df["gruppe"].value_counts().to_string())
    print("Gesamt:", len(df))


if __name__ == "__main__":
    sys.exit(main())
