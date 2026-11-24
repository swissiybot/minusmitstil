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

# Themen-, Branchen-, Länder- und Anleihen-ETFs (US-gelistet, lange Historie). Dienen vor allem als echter Wert bzw.
# passender Ersatz beim Depot-Import (z. B. Uran-ETF aus Europa -> URA). Kein Index-Vorlauf.
_T = lambda i, n, b: {"id": i, "name": n, "etf": i, "index": None, "index_tr": None, "branche": b}
THEMEN_ETFS = [
    _T("URA", "Uran", "Thema"), _T("LIT", "Lithium & Batterien", "Thema"), _T("TAN", "Solar", "Thema"),
    _T("ICLN", "Saubere Energie", "Thema"), _T("SMH", "Halbleiter", "Branche"), _T("SOXX", "Halbleiter (iShares)", "Branche"),
    _T("IGV", "Software", "Branche"), _T("SKYY", "Cloud Computing", "Thema"), _T("CIBR", "Cybersicherheit", "Thema"),
    _T("BOTZ", "Robotik & KI", "Thema"), _T("ARKK", "Disruptive Innovation (ARK)", "Thema"), _T("KWEB", "China Internet", "Thema"),
    _T("IBB", "Biotechnologie", "Branche"), _T("XBI", "Biotechnologie (gleichgewichtet)", "Branche"),
    _T("ITA", "Luft- und Raumfahrt, Rüstung", "Branche"), _T("GDX", "Goldminen", "Branche"), _T("COPX", "Kupferminen", "Branche"),
    _T("REMX", "Seltene Erden", "Thema"), _T("PHO", "Wasser", "Thema"), _T("IGF", "Infrastruktur weltweit", "Thema"),
    _T("VNQ", "Immobilien (REITs USA)", "Branche"), _T("XLK", "Technologie (S&P 500)", "Branche"), _T("XLF", "Finanzen (S&P 500)", "Branche"),
    _T("XLE", "Energie (S&P 500)", "Branche"), _T("XLV", "Gesundheit (S&P 500)", "Branche"), _T("XLI", "Industrie (S&P 500)", "Branche"),
    _T("XLP", "Basiskonsum (S&P 500)", "Branche"), _T("XLY", "Zyklischer Konsum (S&P 500)", "Branche"), _T("XLU", "Versorger (S&P 500)", "Branche"),
    _T("XLB", "Rohstoffe/Grundstoffe (S&P 500)", "Branche"), _T("KBE", "Banken USA", "Branche"),
    _T("RSP", "S&P 500 gleichgewichtet", "Faktor"), _T("MTUM", "Momentum (MSCI USA)", "Faktor"), _T("QUAL", "Qualität (MSCI USA)", "Faktor"),
    _T("USMV", "Minimum Volatility (MSCI USA)", "Faktor"), _T("IWD", "Value (Russell 1000)", "Faktor"), _T("IWF", "Growth (Russell 1000)", "Faktor"),
    _T("VYM", "Hohe Dividende (USA)", "Faktor"), _T("VIG", "Dividendenwachstum (USA)", "Faktor"), _T("IJH", "Mid Caps USA (S&P 400)", "Faktor"),
    _T("VSS", "Small Caps weltweit ohne USA", "Faktor"), _T("EFA", "Industrieländer ohne USA (MSCI EAFE)", "Region"),
    _T("VGK", "Europa (FTSE Developed Europe)", "Region"), _T("MCHI", "China (MSCI China)", "Land"), _T("FXI", "China Large Caps", "Land"),
    _T("INDA", "Indien (MSCI India)", "Land"), _T("EWZ", "Brasilien", "Land"), _T("EWG", "Deutschland (MSCI)", "Land"),
    _T("EWU", "Großbritannien (MSCI)", "Land"), _T("EWT", "Taiwan", "Land"), _T("EWY", "Südkorea", "Land"), _T("EWC", "Kanada", "Land"),
    _T("EWA", "Australien", "Land"), _T("EWL", "Schweiz", "Land"),
    _T("AGG", "Anleihen USA gesamt", "Anleihen"), _T("IEF", "US-Staatsanleihen 7-10 Jahre", "Anleihen"), _T("TLT", "US-Staatsanleihen 20+ Jahre", "Anleihen"),
    _T("SHY", "US-Staatsanleihen 1-3 Jahre", "Anleihen"), _T("LQD", "Unternehmensanleihen USA", "Anleihen"), _T("HYG", "Hochzinsanleihen USA", "Anleihen"),
    _T("EMB", "Schwellenländer-Anleihen", "Anleihen"), _T("TIP", "Inflationsgeschützte US-Anleihen", "Anleihen"), _T("BNDX", "Anleihen weltweit ohne USA", "Anleihen"),
    _T("SLV", "Silber (ETF)", "Rohstoff"), _T("GLD", "Gold (ETF)", "Rohstoff"),
]
ETFS = ETFS + THEMEN_ETFS

# Kryptowaehrungen (Yahoo, Kurse in USD). Pi Cycle und MVRV sind nur fuer Bitcoin geeicht und werden nur dort berechnet.
# Daten bei Yahoo: BTC ab 2014, ETH/LINK/XLM ab 11/2017, SOL ab 04/2020 (Ampel braucht 5 Jahre Vorlauf).
# Die fünf Kernwerte stehen fest hier: Ihre Kennung ändert sich nie (Signal-Tagebuch, Alarme, gemerkte Werte), sie melden sich
# einzeln aufs Handy und gehen als „Krypto“ in Trendstudie, Kegelprüfung und Gegenprobe der Vorhersage ein.
KRYPTO_KERN = [
    {"id": "BTC", "name": "Bitcoin", "symbol": "BTC-USD"},
    {"id": "ETH-USD", "name": "Ethereum", "symbol": "ETH-USD"},
    {"id": "SOL-USD", "name": "Solana", "symbol": "SOL-USD"},
    {"id": "LINK-USD", "name": "Chainlink", "symbol": "LINK-USD"},   # Kuerzel LINK ist bei der Nasdaq schon vergeben
    {"id": "XLM-USD", "name": "Stellar", "symbol": "XLM-USD"},
]
KRYPTO_KERN_IDS = {k["id"] for k in KRYPTO_KERN}


def _krypto_liste() -> list[dict]:
    """Kernwerte plus die feste, eingecheckte Liste der 200 größten Kryptowerte (listen/krypto.csv; Wunsch Marc 24.11.2026).
    Die Liste baut krypto_liste.py von Hand neu (Quelle, Ausschlüsse und Prüfung der Yahoo-Kürzel stehen dort) – bewusst
    nicht bei jedem Lauf, damit keine Werte kommen und gehen. Kennung „KÜRZEL-USD“: kann mit keinem Aktienkürzel kollidieren."""
    import csv
    aus, symbole, ids = [dict(k) for k in KRYPTO_KERN], {k["symbol"] for k in KRYPTO_KERN}, set(KRYPTO_KERN_IDS)
    datei = BASIS / "listen" / "krypto.csv"
    if datei.exists():
        with open(datei, newline="", encoding="utf-8") as f:
            for z in csv.DictReader(f):
                if z["symbol"] in symbole or z["id"] in ids:
                    for k in aus[:len(KRYPTO_KERN)]:   # Kernwert: Kennung und Name bleiben, nur der Rang kommt aus der Liste
                        if k["symbol"] == z["symbol"]:
                            k.update(rang=int(z["rang"]), stand=z["stand"])
                    continue
                symbole.add(z["symbol"]); ids.add(z["id"])
                aus.append({"id": z["id"], "name": z["name"], "symbol": z["symbol"], "rang": int(z["rang"]), "stand": z["stand"]})
    return aus


KRYPTO = _krypto_liste()
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
    # Nickel (Wunsch Marc 22.11.2026): kein Nickel-Future bei Yahoo; WisdomTree Nickel ETC (London, USD, seit 2008) auf Nickel-Futures
    {"id": "NICKEL", "name": "Nickel (ETC WisdomTree)", "symbol": "NICK.L", "art": "etc"},
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
