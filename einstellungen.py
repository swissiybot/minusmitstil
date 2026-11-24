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

# Hebel-Produkte mit TÄGLICHEM 2-fachem Hebel, ohne Knock-out (Wunsch Marc 24.11.2026: „2x … ohne Knockout, z. B. Amundi
# NASDAQ 100 ETF 2x“). Nur 2x und nur „long“: keine 3x/5x, keine Short-Produkte, keine Knock-out-Zertifikate, keine
# Hebel-Produkte auf einzelne Aktien. Sie stehen in der Gruppe ETF mit der Art „Hebel 2x“ (eigener Reiter in der Liste).
# Geprüft am 24.11.2026, nichts aus dem Gedächtnis übernommen:
#   - ISIN: europäische alle bei justETF (Name, ISIN, WKN, Kürzel); dazu nennt die Yahoo-Suche nach der ISIN genau dieses
#     Produkt (alle US-Produkte und alle europäischen außer Amundi LevDAX und IBEX, deren ISIN Yahoo nicht kennt)
#   - Kürzel: Yahoo liefert unter dem Kürzel den Produktnamen, die erwartete Währung und Tageskurse bis heute
# Europäische Produkte: Börsenplatz mit der längsten FEHLERFREIEN Euro-Kursreihe bei Yahoo (Paris, Mailand, Madrid oder
# Xetra). In Deutschland werden dieselben Anteile auf Xetra gehandelt – das Kürzel dort steht in „xetra“, wenn es abweicht.
# „eu“: False = US-Produkt; für Privatanleger in der EU meist nicht kaufbar (es fehlt das EU-Basisinformationsblatt).
# „art“: ETF = Fonds; ETC = besicherte Schuldverschreibung auf Rohstoff-Terminkontrakte, kein Fonds (Ausfallrisiko des Anbieters).
# „ab“: Kurse erst ab diesem Tag verwenden. Jede Reihe wurde auf Fehlkurse geprüft (Tagessprünge über 25 %, die der Markt nicht
#   erklärt). Gefunden am 24.11.2026 – deshalb der Börsenplatz bzw. der Schnitt:
#   - Amundi Nasdaq-100 2x: in Paris bis 31.12.2014 um den Faktor 200 falsch skaliert (Aktiensplit nicht zurückgerechnet);
#     Xetra (L8I7) und Mailand haben den Split vom 09.07.2026 gar nicht eingerechnet -> Paris ab 02.01.2015
#   - Amundi MSCI USA 2x: Paris mit 19 Fehlkursen (einzelne Tage im alten Maßstab, Faktor 300), Mailand ohne den Split vom
#     10.10.2023; Xetra (18MF) nur bis 31.12.2012 falsch skaliert -> Xetra ab 02.01.2013
#   - Xtrackers S&P 500 2x: Xetra (DBPG) mit 16 Fehlkursen 2010/2011 -> Mailand (XS2L), dort keine
#   - WisdomTree-ETCs in Mailand: bis 05/2009 in Dollar statt Euro, Fehlkurse im Juni 2009 und am 18.07.2011 -> ab 19.07.2011
HEBEL_BRANCHE = "Hebel 2x"


def _H(i, kuerzel, anbieter, produkt, isin, wkn, basis, art="ETF", eu=True, xetra=None, ab=None):
    """Anzeigename „Basiswert 2x (Anbieter)“: In der schmalen Liste muss der Anfang des Namens unterscheiden (nicht 13-mal
    „ProShares Ultra …“); der volle Produktname steht in „produkt“ und in der Kurzbeschreibung."""
    return {"id": i, "name": f"{basis} 2x ({anbieter})", "produkt": produkt, "etf": kuerzel, "index": None, "index_tr": None,
            "branche": HEBEL_BRANCHE, "isin": isin, "wkn": wkn,
            "hebel": {"fach": 2, "art": art, "eu": eu, "basis": basis} | ({"xetra": xetra} if xetra else {})} | ({"ab": ab} if ab else {})


HEBEL_ETFS = [
    # in Europa handelbar (UCITS-ETFs und ETCs), Kurse in Euro
    _H("LQQ", "LQQ.PA", "Amundi", "Amundi Nasdaq-100 Daily (2x) Leveraged UCITS ETF", "FR0010342592", "A0LC12", "Nasdaq-100", xetra="L8I7", ab="2015-01-02"),
    _H("18MF", "18MF.DE", "Amundi", "Amundi MSCI USA Daily (2x) Leveraged UCITS ETF", "FR0010755611", "A0X8ZS", "MSCI USA", ab="2013-01-02"),
    _H("DBPG", "XS2L.MI", "Xtrackers", "Xtrackers S&P 500 2x Leveraged Daily Swap UCITS ETF", "LU0411078552", "DBX0B5", "S&P 500", xetra="DBPG"),
    _H("LVWC", "LVWC.DE", "Amundi", "Amundi MSCI World (2x) Leveraged UCITS ETF", "FR0014010HV4", "ETF888", "MSCI World"),   # erst seit 10/2025: noch ohne Ampel
    _H("DBPE", "DBPE.DE", "Xtrackers LevDAX", "Xtrackers LevDAX Daily Swap UCITS ETF", "LU0411075376", "DBX0BZ", "DAX"),
    _H("LYY8", "LYY8.DE", "Amundi LevDAX", "Amundi LevDax Daily (2x) leveraged UCITS ETF", "LU0252634307", "LYX0AD", "DAX"),
    _H("DEL2", "DEL2.DE", "L&G", "L&G DAX Daily 2x Long UCITS ETF", "IE00B4QNHH68", "A0X895", "DAX"),
    _H("LVE", "LVE.PA", "Amundi", "Amundi EURO STOXX 50 Daily (2x) Leveraged UCITS ETF", "FR0010468983", "LYX0BZ", "Euro Stoxx 50", xetra="LYMZ"),
    _H("LVC", "LVC.PA", "Amundi", "Amundi CAC 40 Daily (2x) Leveraged UCITS ETF", "FR0010592014", "LYX0C6", "CAC 40"),
    _H("LEVMIB", "LEVMIB.MI", "Amundi", "Amundi FTSE MIB Daily (2x) Leveraged UCITS ETF", "FR0010446658", "A0NEUQ", "FTSE MIB"),
    _H("IBEXA", "IBEXA.MC", "Amundi", "Amundi IBEX 35 Doble Apalancado Diario (2x) UCITS ETF", "FR0011042753", "LYX0M1", "IBEX 35"),
    _H("LBUL", "LBUL.MI", "WisdomTree", "WisdomTree Gold 2x Daily Leveraged", "JE00B2NFTL95", "A0V6Z0", "Gold", art="ETC", xetra="4RT8", ab="2011-07-19"),
    _H("LSIL", "LSIL.MI", "WisdomTree", "WisdomTree Silver 2x Daily Leveraged", "JE00B2NFTS64", "A0V5BA", "Silber", art="ETC", xetra="4RUE", ab="2011-07-19"),
    _H("LOIL", "LOIL.MI", "WisdomTree", "WisdomTree WTI Crude Oil 2x Daily Leveraged", "JE00BDD9Q840", "A2BC41", "Rohöl WTI", art="ETC", xetra="4RT6", ab="2011-07-19"),
    _H("LCOP", "LCOP.MI", "WisdomTree", "WisdomTree Copper 2x Daily Leveraged", "JE00B2NFTF36", "A0V6ZW", "Kupfer", art="ETC", xetra="4RT3", ab="2011-07-19"),
    # USA (NYSE Arca, Kurse in Dollar) – für Privatanleger in der EU meist nicht kaufbar
    _H("SSO", "SSO", "ProShares Ultra, USA", "ProShares Ultra S&P500", "US74347R1077", None, "S&P 500", eu=False),
    _H("QLD", "QLD", "ProShares Ultra, USA", "ProShares Ultra QQQ", "US74347R2067", None, "Nasdaq-100", eu=False),
    _H("DDM", "DDM", "ProShares Ultra, USA", "ProShares Ultra Dow30", "US74347R3057", None, "Dow Jones", eu=False),
    _H("UWM", "UWM", "ProShares Ultra, USA", "ProShares Ultra Russell2000", "US74347R8429", None, "Russell 2000", eu=False),
    _H("MVV", "MVV", "ProShares Ultra, USA", "ProShares Ultra MidCap400", "US74347R4048", None, "S&P MidCap 400", eu=False),
    _H("SPUU", "SPUU", "Direxion, USA", "Direxion Daily S&P 500 Bull 2X Shares", "US25459Y1652", None, "S&P 500", eu=False),
    _H("ROM", "ROM", "ProShares Ultra, USA", "ProShares Ultra Technology", "US74347R6936", None, "US-Technologieaktien", eu=False),
    _H("UYG", "UYG", "ProShares Ultra, USA", "ProShares Ultra Financials", "US74347X6334", None, "US-Finanzaktien", eu=False),
    _H("DIG", "DIG", "ProShares Ultra, USA", "ProShares Ultra Energy", "US74347R7199", None, "US-Energieaktien", eu=False),
    _H("UGL", "UGL", "ProShares Ultra, USA", "ProShares Ultra Gold", "US74347W6012", None, "Gold", eu=False),
    _H("AGQ", "AGQ", "ProShares Ultra, USA", "ProShares Ultra Silver", "US74347W3530", None, "Silber", eu=False),
    _H("UCO", "UCO", "ProShares Ultra, USA", "ProShares Ultra Bloomberg Crude Oil", "US74347Y8883", None, "Rohöl WTI", eu=False),
    _H("UBT", "UBT", "ProShares Ultra, USA", "ProShares Ultra 20+ Year Treasury", "US74347R1721", None, "US-Staatsanleihen 20+ Jahre", eu=False),
]
ETFS = ETFS + HEBEL_ETFS

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
