"""Baut die Liste aller Werte: Nasdaq-Aktien, FTSE All-World (aus Vanguard-Excel), ETFs, Krypto, Rohstoffe.

Ergebnis: daten/universum.csv mit Spalten
    id, symbol, name, gruppe, land, branche
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
    """Liest die von Marc heruntergeladene Vanguard-Bestandsliste (Excel/CSV) aus daten/eingang/."""
    dateien = sorted(glob.glob(str(E.EINGANG / "*.xls*")) + glob.glob(str(E.EINGANG / "*.csv")))
    if not dateien:
        print("Hinweis: keine Vanguard-Liste in daten/eingang/ - FTSE All-World wird uebersprungen.")
        return pd.DataFrame(columns=["id", "symbol", "name", "gruppe", "land", "branche"])
    datei = dateien[-1]
    roh = pd.read_csv(datei, header=None) if datei.endswith(".csv") else pd.read_excel(datei, header=None)
    # Kopfzeile suchen (Zeile, in der "Ticker" steht)
    kopf = next(i for i, r in roh.iterrows() if r.astype(str).str.contains("Ticker", case=False).any())
    df = roh.iloc[kopf + 1:].copy()
    df.columns = [str(c).strip() for c in roh.iloc[kopf]]
    spalte = lambda *namen: next((c for c in df.columns if any(n.lower() in c.lower() for n in namen)), None)
    c_tick, c_name, c_land = spalte("Ticker"), spalte("Holding name", "Name"), spalte("Country", "Land", "Region")
    c_branche = spalte("Sector", "Sektor", "Industry")
    df = df[df[c_tick].notna()]
    land = df[c_land].astype(str).str.strip().str.upper() if c_land else "US"
    sym = [_yahoo_symbol(t, l) for t, l in zip(df[c_tick], land)]
    out = pd.DataFrame({
        "id": sym, "symbol": sym, "name": df[c_name].astype(str).str.strip(),
        "gruppe": "FTSE All-World", "land": list(land),
        "branche": df[c_branche].astype(str) if c_branche else "",
    })
    out = out[out["symbol"].notna()]
    print(f"FTSE All-World aus {datei}: {len(out)} Werte")
    return out


def etfs_und_bitcoin() -> pd.DataFrame:
    zeilen = [{"id": e["id"], "symbol": e["etf"], "name": e["name"] + " (ETF)", "gruppe": "ETF", "land": "", "branche": "Index"} for e in E.ETFS]
    for k in E.KRYPTO:
        zeilen.append({"id": k["id"], "symbol": k["symbol"], "name": k["name"], "gruppe": "Krypto", "land": "", "branche": "Krypto"})
    for r in E.ROHSTOFFE:
        zeilen.append({"id": r["id"], "symbol": r["symbol"], "name": r["name"], "gruppe": "Rohstoffe", "land": "",
                       "branche": "Future" if r["art"] == "rohstoff" else "Rohstoff-ETF"})
    return pd.DataFrame(zeilen)


def main():
    teile = [etfs_und_bitcoin(), nasdaq(), ftse_all_world()]
    df = pd.concat(teile, ignore_index=True)
    # Doppelte (z. B. Apple in Nasdaq und FTSE) zusammenfassen, Gruppen merken
    df["gruppe"] = df.groupby("symbol")["gruppe"].transform(lambda g: " + ".join(dict.fromkeys(g)))
    df = df.drop_duplicates("symbol", keep="first")
    df.to_csv(E.DATEN / "universum.csv", index=False)
    print(df["gruppe"].value_counts().to_string())
    print("Gesamt:", len(df))


if __name__ == "__main__":
    sys.exit(main())
