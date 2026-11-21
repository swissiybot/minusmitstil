"""Zentrale Einstellungen des Aktien-Kaufplans."""
from pathlib import Path

BASIS = Path(__file__).resolve().parent
DATEN = BASIS / "daten"
KURSE = DATEN / "kurse"          # alt: Einzeldateien (nur noch fuer die einmalige Uebernahme)
EINGANG = DATEN / "eingang"      # hier die Vanguard-Excel (FTSE All-World) ablegen
WEB = BASIS / "web"
WEB_DATEN = WEB / "daten"

for p in (DATEN, EINGANG, WEB_DATEN):
    p.mkdir(parents=True, exist_ok=True)

# Pause zwischen Abfragen bei Yahoo (Sekunden), damit wir nicht gesperrt werden.
PAUSE_SEKUNDEN = 1.5
STAPEL_GROESSE = 40

# Mindestens so viele Jahre Daten, damit "historisch guenstig" ueberhaupt messbar ist.
MIN_JAHRE_RANGLISTE = 10

# Index-ETFs: ETF-Kurs (mit Dividenden, bereinigt) und davor die Index-Historie als Vorlauf.
# "index" = Yahoo-Symbol des Index, "index_tr" = Index mit Dividenden (falls vorhanden).
ETFS = [
    {"id": "SPY",  "name": "S&P 500",            "etf": "SPY",      "index": "^GSPC",     "index_tr": "^SP500TR"},
    {"id": "QQQ",  "name": "Nasdaq-100",         "etf": "QQQ",      "index": "^NDX",      "index_tr": None},
    {"id": "ONEQ", "name": "Nasdaq Composite",   "etf": "ONEQ",     "index": "^IXIC",     "index_tr": None},
    {"id": "DIA",  "name": "Dow Jones",          "etf": "DIA",      "index": "^DJI",      "index_tr": None},
    {"id": "IWM",  "name": "Russell 2000",       "etf": "IWM",      "index": "^RUT",      "index_tr": None},
    {"id": "URTH", "name": "MSCI World",         "etf": "URTH",     "index": None,        "index_tr": None},
    {"id": "IWDA", "name": "MSCI World (EUR-Handel, Amsterdam)", "etf": "IWDA.AS", "index": None, "index_tr": None},
    {"id": "VWRL", "name": "FTSE All-World",     "etf": "VWRL.L",   "index": None,        "index_tr": None, "vorlauf_etf": "VT"},
    {"id": "ACWI", "name": "MSCI ACWI",          "etf": "ACWI",     "index": None,        "index_tr": None},
    {"id": "EEM",  "name": "Schwellenlaender (MSCI EM)", "etf": "EEM", "index": None,     "index_tr": None},
    {"id": "EXS1", "name": "DAX",                "etf": "EXS1.DE",  "index": None,        "index_tr": "^GDAXI"},  # DAX ist ein Performance-Index (mit Dividenden)
    {"id": "SX5E", "name": "Euro Stoxx 50",      "etf": "EXW1.DE",  "index": "^STOXX50E", "index_tr": None},
    {"id": "ISF",  "name": "FTSE 100",           "etf": "ISF.L",    "index": "^FTSE",     "index_tr": None},
    {"id": "EWJ",  "name": "Japan (Nikkei 225)", "etf": "EWJ",      "index": "^N225",     "index_tr": None},
]

# Kryptowaehrungen (Yahoo, Kurse in USD). Pi Cycle ist nur fuer Bitcoin geeicht und wird nur dort berechnet.
# Daten bei Yahoo: BTC ab 2014, ETH/LINK/XLM ab 11/2017, SOL ab 04/2020 (Ampel braucht 5 Jahre Vorlauf).
KRYPTO = [
    {"id": "BTC", "name": "Bitcoin", "symbol": "BTC-USD"},
    {"id": "ETH-USD", "name": "Ethereum", "symbol": "ETH-USD"},
    {"id": "SOL-USD", "name": "Solana", "symbol": "SOL-USD"},
    {"id": "LINK-USD", "name": "Chainlink", "symbol": "LINK-USD"},   # Kuerzel LINK ist bei der Nasdaq schon vergeben
    {"id": "XLM-USD", "name": "Stellar", "symbol": "XLM-USD"},
]
BITCOIN = KRYPTO[0]

# Rohstoffe: Endlos-Futures von Yahoo (Spruenge beim Kontraktwechsel, keine Anlegerrendite) und ein breiter Korb-ETF.
# Daten bei Yahoo meist ab 2000 (Platin 1997, Palladium 1998, Brent 2007, DBC 2006).
ROHSTOFFE = [
    {"id": "GOLD", "name": "Gold", "symbol": "GC=F", "art": "rohstoff"},
    {"id": "SILBER", "name": "Silber", "symbol": "SI=F", "art": "rohstoff"},
    {"id": "PLATIN", "name": "Platin", "symbol": "PL=F", "art": "rohstoff"},
    {"id": "PALLADIUM", "name": "Palladium", "symbol": "PA=F", "art": "rohstoff"},
    {"id": "KUPFER", "name": "Kupfer", "symbol": "HG=F", "art": "rohstoff"},
    {"id": "WTI", "name": "Rohoel WTI", "symbol": "CL=F", "art": "rohstoff"},
    {"id": "BRENT", "name": "Rohoel Brent", "symbol": "BZ=F", "art": "rohstoff"},
    {"id": "ERDGAS", "name": "Erdgas (Henry Hub)", "symbol": "NG=F", "art": "rohstoff"},
    {"id": "WEIZEN", "name": "Weizen", "symbol": "ZW=F", "art": "rohstoff"},
    {"id": "MAIS", "name": "Mais", "symbol": "ZC=F", "art": "rohstoff"},
    {"id": "SOJA", "name": "Sojabohnen", "symbol": "ZS=F", "art": "rohstoff"},
    {"id": "KAFFEE", "name": "Kaffee", "symbol": "KC=F", "art": "rohstoff"},
    {"id": "ZUCKER", "name": "Zucker", "symbol": "SB=F", "art": "rohstoff"},
    {"id": "KAKAO", "name": "Kakao", "symbol": "CC=F", "art": "rohstoff"},
    {"id": "DBC", "name": "Rohstoff-Korb (ETF DBC)", "symbol": "DBC", "art": "etf"},
]

# TradingView-Symbole fuer das Chart-Widget der Online-Seite (Kurse kommen dort von TradingView, nicht von uns).
# Unbekannt = None -> online kein Chart (nicht raten). Nasdaq-Aktien: "NASDAQ:<Kuerzel>".
TV_SYMBOLE = {
    # Index-ETFs
    "SPY": "AMEX:SPY", "QQQ": "NASDAQ:QQQ", "ONEQ": "NASDAQ:ONEQ", "DIA": "AMEX:DIA", "IWM": "AMEX:IWM",
    "URTH": "AMEX:URTH", "IWDA": "EURONEXT:IWDA", "VWRL": None,   # LSE im Gratis-Widget gesperrt (getestet)
    "ACWI": "NASDAQ:ACWI", "EEM": "AMEX:EEM",
    "EXS1": "XETR:EXS1", "SX5E": "XETR:EXW1", "ISF": None, "EWJ": "AMEX:EWJ",
    # Krypto
    "BTC": "BITSTAMP:BTCUSD", "ETH-USD": "BITSTAMP:ETHUSD", "SOL-USD": "COINBASE:SOLUSD",
    "LINK-USD": "COINBASE:LINKUSD", "XLM-USD": "BITSTAMP:XLMUSD",
    # Rohstoffe: Futures von CME/ICE sind im Gratis-Widget gesperrt (getestet 21.11.2026), deshalb
    # TradingView-Referenzkurse (TVC) bzw. CFD-Kurse von Capital.com; das Widget nennt die Quelle selbst
    "GOLD": "TVC:GOLD", "SILBER": "TVC:SILVER", "PLATIN": "TVC:PLATINUM", "PALLADIUM": "TVC:PALLADIUM",
    "KUPFER": "CAPITALCOM:COPPER", "WTI": "TVC:USOIL", "BRENT": "TVC:UKOIL", "ERDGAS": "CAPITALCOM:NATURALGAS",
    "WEIZEN": "CAPITALCOM:WHEAT", "MAIS": "CAPITALCOM:CORN", "SOJA": "CAPITALCOM:SOYBEAN",
    "KAFFEE": "CAPITALCOM:COFFEEARABICA", "ZUCKER": "CAPITALCOM:SUGAR", "KAKAO": "CAPITALCOM:COCOA", "DBC": "AMEX:DBC",
}


def tv_symbol(wid: str, symbol: str, gruppe: str) -> str | None:
    if wid in TV_SYMBOLE:
        return TV_SYMBOLE[wid]
    if gruppe == "Nasdaq":
        return "NASDAQ:" + symbol.replace("-", ".")
    return None
