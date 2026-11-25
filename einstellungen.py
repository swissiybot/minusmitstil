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
# Ausbau am 24.11.2026 abends auf 62 Produkte (Wunsch Marc: „viel mehr, 50 oder so“), gleiche Prüfung:
#   - 7 weitere WisdomTree-ETCs (Erdgas, Weizen, Mais, Kaffee, Zucker, Kakao, Platin): ISIN, WKN und Kürzel bei justETF; die
#     Yahoo-Suche führt dieselbe ISIN unter dem Produktnamen. In Mailand bis Ende 2014 viele Fehlkurse (einzelne Tage in
#     Dollar statt Euro) -> ab 02.01.2015; die Sprünge danach erklärt der Markt (Kakao 2024, Erdgas, Weizen 03/2022,
#     Edelmetall-Einbruch 30.01.2026). Agrarrohstoffe 2x bleibt draußen: Kurs an 39 % der Tage unverändert (kaum Handel)
#   - 27 weitere US-Produkte: ISIN aus der amtlichen Kennnummer (CUSIP, SEC-Liste) berechnet und von der Yahoo-Suche bestätigt;
#     Name bei Yahoo „ProShares Ultra …“ (Ultra = 2-fach; „UltraPro“ = 3-fach und „UltraShort“ bleiben draußen) bzw.
#     „Direxion Daily … Bull 2X“. Nur Direxion-Fonds, die seit Auflage 2-fach sind (Gold-Minen, Energie, Brasilien, Indien u. a.
#     waren bis 2020 3-fach – ihre Kursreihe mischt beides und bleibt draußen)
HEBEL_BRANCHE = "Hebel 2x"


def _H(i, kuerzel, anbieter, produkt, isin, wkn, basis, art="ETF", eu=True, xetra=None, ab=None, einzel=False):
    """Anzeigename „Basiswert 2x (Anbieter)“: In der schmalen Liste muss der Anfang des Namens unterscheiden (nicht 13-mal
    „ProShares Ultra …“); der volle Produktname steht in „produkt“ und in der Kurzbeschreibung."""
    return {"id": i, "name": f"{basis} 2x ({anbieter})", "produkt": produkt, "etf": kuerzel, "index": None, "index_tr": None,
            "branche": HEBEL_BRANCHE, "isin": isin, "wkn": wkn,
            "hebel": {"fach": 2, "art": art, "eu": eu, "basis": basis} | ({"xetra": xetra} if xetra else {}) | ({"einzel": True} if einzel else {})} | ({"ab": ab} if ab else {})


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
    _H("LPLA.MI", "LPLA.MI", "WisdomTree", "WisdomTree Platinum 2x Daily Leveraged", "JE00B2NFV134", "A0V60A", "Platin", art="ETC", xetra="4RUM", ab="2015-01-02"),   # Kennung mit Endung: LPLA ist eine Nasdaq-Aktie
    _H("LNGA", "LNGA.MI", "WisdomTree", "WisdomTree Natural Gas 2x Daily Leveraged", "JE00BDD9Q956", "A2BC4J", "Erdgas", art="ETC", xetra="4RUC", ab="2015-01-02"),
    _H("LWEA", "LWEA.MI", "WisdomTree", "WisdomTree Wheat 2x Daily Leveraged", "JE00BDD9QC84", "A2BC84", "Weizen", art="ETC", xetra="4RUJ", ab="2015-01-02"),
    _H("LCOR", "LCOR.MI", "WisdomTree", "WisdomTree Corn 2x Daily Leveraged", "JE00B2NFTG43", "A0V6ZX", "Mais", art="ETC", xetra="4RT4", ab="2015-01-02"),
    _H("LCFE", "LCFE.MI", "WisdomTree", "WisdomTree Coffee 2x Daily Leveraged", "JE00B2NFTD12", "A0V5V4", "Kaffee", art="ETC", xetra="4RT2", ab="2015-01-02"),
    _H("LSUG", "LSUG.MI", "WisdomTree", "WisdomTree Sugar 2x Daily Leveraged", "JE00B2NFTW01", "A0V5V2", "Zucker", art="ETC", xetra="4RUH", ab="2015-01-02"),
    _H("LCOC", "LCOC.MI", "WisdomTree", "WisdomTree Cocoa 2x Daily Leveraged", "JE00B2NFV803", "A0V607", "Kakao", art="ETC", xetra="4RUP", ab="2015-01-02"),
    # Ausbau 25.11.2026 (Wunsch Marc: „nur Werte die in Europa handelbar sind aber mehr davon“, nie Knock-out): fünf weitere, alle
    # mit Euro-Kursen. ISIN, WKN und Kürzel aus der Xetra-Liste „alle handelbaren Instrumente“ der Deutschen Börse (Nickel: dazu
    # Borsa Italiana), Name, Kosten und „täglich gehebelt“ von justETF; Yahoo liefert unter dem Kürzel genau dieses Produkt in Euro.
    # ETP = börsengehandelte Schuldverschreibung (kein Fonds). „einzel“ = hängt an EINER Aktie (neu erlaubt, Hinweis im Kurztext).
    _H("2MUE", "2MUE.DE", "Leverage Shares", "Leverage Shares 2x Micron Technology ETP Securities", "IE00BKT66K01", "A3GUFU", "Micron Technology", art="ETP", einzel=True),
    _H("2CAR", "2CAR.DE", "WisdomTree", "WisdomTree STOXX Europe Automobiles 2x Daily Leveraged", "XS2427363895", "A3GWVR", "Europa Autoaktien", art="ETP"),
    _H("2FLY", "2FLY.DE", "WisdomTree", "WisdomTree STOXX Europe Travel & Leisure 2x Daily Leveraged", "XS2427363036", "A3GWVS", "Europa Reise- und Freizeitaktien", art="ETP"),
    _H("LNIK", "LNIK.MI", "WisdomTree", "WisdomTree Nickel 2x Daily Leveraged", "JE00BDD9QB77", "A2BC83", "Nickel", art="ETC", xetra="4RUD", ab="2022-03-25"),   # davor Fehlkurse und die Handelsaussetzung für Nickel im März 2022
    _H("SC2X", "SC2X.DE", "Xtrackers/Scalable", "Scalable MSCI AC World (2x) Leveraged Daily Swap Xtrackers UCITS ETF 1C", "LU3386643970", "DBX2SC", "MSCI ACWI (Welt mit Schwellenländern)"),   # erst seit 28.07.2026: noch ohne Ampel
    # USA (NYSE Arca oder Nasdaq, Kurse in Dollar) – für Privatanleger in der EU meist nicht kaufbar
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
    # Ausbau 24.11.2026 abends: Größenklassen, Regionen, Branchen
    _H("SAA", "SAA", "ProShares Ultra, USA", "ProShares Ultra SmallCap600", "US74347R8189", None, "S&P SmallCap 600", eu=False),
    _H("EZJ", "EZJ", "ProShares Ultra, USA", "ProShares Ultra MSCI Japan", "US74347X7084", None, "MSCI Japan", eu=False),
    _H("UPV", "UPV", "ProShares Ultra, USA", "ProShares Ultra FTSE Europe", "US74347X5260", None, "FTSE Europa", eu=False),
    _H("UBR", "UBR", "ProShares Ultra, USA", "ProShares Ultra MSCI Brazil Capped", "US74347B4905", None, "MSCI Brasilien", eu=False),
    _H("CHAU", "CHAU", "Direxion, USA", "Direxion Daily CSI 300 China A Share Bull 2X Shares", "US25490K8696", None, "China A-Aktien (CSI 300)", eu=False),
    _H("CWEB", "CWEB", "Direxion, USA", "Direxion Daily CSI China Internet Bull 2X Shares", "US25460G1875", None, "China-Internetaktien", eu=False),
    _H("USD_PROSHARES", "USD", "ProShares Ultra, USA", "ProShares Ultra Semiconductors", "US74347R6696", None, "US-Halbleiteraktien", eu=False),   # Kürzel USD: Kennung anders, damit nichts mit der Währung verwechselt
    _H("RXL", "RXL", "ProShares Ultra, USA", "ProShares Ultra Health Care", "US74347R7355", None, "US-Gesundheitsaktien", eu=False),
    _H("BIB", "BIB", "ProShares Ultra, USA", "ProShares Ultra Nasdaq Biotechnology", "US74347R2141", None, "Nasdaq Biotechnologie", eu=False),
    _H("URE", "URE", "ProShares Ultra, USA", "ProShares Ultra Real Estate", "US74347X6250", None, "US-Immobilienaktien", eu=False),
    _H("UPW", "UPW", "ProShares Ultra, USA", "ProShares Ultra Utilities", "US74347R6852", None, "US-Versorgeraktien", eu=False),
    _H("UYM", "UYM", "ProShares Ultra, USA", "ProShares Ultra Materials", "US74347R7769", None, "US-Grundstoffaktien", eu=False),
    _H("UCC", "UCC", "ProShares Ultra, USA", "ProShares Ultra Consumer Discretionary", "US74347R7504", None, "US-Konsumaktien (zyklisch)", eu=False),
    _H("UGE", "UGE", "ProShares Ultra, USA", "ProShares Ultra Consumer Staples", "US74347R7686", None, "US-Basiskonsumaktien", eu=False),
    _H("LTL", "LTL", "ProShares Ultra, USA", "ProShares Ultra Communication Services", "US74347R2638", None, "US-Kommunikationsaktien", eu=False),
    _H("SKYU", "SKYU", "ProShares Ultra, USA", "ProShares Ultra Cloud Computing", "US74347G7887", None, "Cloud-Computing-Aktien", eu=False),
    _H("FNGG", "FNGG", "Direxion, USA", "Direxion Daily NYSE FANG+ Bull 2X Shares", "US25460G1610", None, "NYSE FANG+", eu=False),
    _H("QQQU", "QQQU", "Direxion, USA", "Direxion Daily Magnificent 7 Bull 2X Shares", "US25461A6507", None, "Magnificent 7", eu=False),
    _H("AIBU", "AIBU", "Direxion, USA", "Direxion Daily AI And Big Data Bull 2X Shares", "US25461A7182", None, "KI- und Big-Data-Aktien", eu=False),
    _H("URAA", "URAA", "Direxion, USA", "Direxion Daily Uranium Bull 2X ETF", "US25461A6432", None, "Uran-Aktien", eu=False),
    # Anleihen, Rohstoff, Währungen, Krypto
    _H("UST", "UST", "ProShares Ultra, USA", "ProShares Ultra 7-10 Year Treasury", "US74347R1804", None, "US-Staatsanleihen 7–10 Jahre", eu=False),
    _H("UJB", "UJB", "ProShares Ultra, USA", "ProShares Ultra High Yield", "US74348A7072", None, "US-Hochzinsanleihen", eu=False),
    _H("BOIL", "BOIL", "ProShares Ultra, USA", "ProShares Ultra Bloomberg Natural Gas", "US74347Y6648", None, "Erdgas", eu=False),
    _H("ULE", "ULE", "ProShares Ultra, USA", "ProShares Ultra Euro", "US74347W8745", None, "Euro gegen Dollar", eu=False),
    _H("YCL", "YCL", "ProShares Ultra, USA", "ProShares Ultra Yen", "US74347W2706", None, "Yen gegen Dollar", eu=False),
    _H("BITU", "BITU", "ProShares Ultra, USA", "ProShares Ultra Bitcoin ETF", "US74349Y7040", None, "Bitcoin", eu=False),
    _H("ETHT", "ETHT", "ProShares Ultra, USA", "ProShares Ultra Ether ETF", "US74349Y5713", None, "Ether", eu=False),
]

# Nachgebaute Vorgeschichte und Vergleich mit dem Basiswert (hebel_nachbau.py, Wunsch Marc 25.11.2026).
# _N(Kette, Hebel-Währung, laufende Kosten % p. a., Name des Basiswerts, aktiv, vgl)
#   Kette: Glieder (Yahoo-Kürzel, Währung[, Kurse erst ab]) vom ältesten zum jüngsten; alle mit wiederangelegten Erträgen
#   aktiv: Prüfung nach den festen Grenzen bestanden -> die Zeit vor dem ersten echten Kurs wird nachgebaut
#   vgl:   Basiswert liegt sauber vor -> Karte „Hebel-Produkt gegen Basiswert“ (info.hebel_vgl)
# Kosten: europäische Produkte laut justETF (Gesamtkostenquote), US-Produkte laut Yahoo/Morningstar – abgerufen am 25.11.2026.
# Prüfzahlen je Produkt: python hebel_nachbau.py (Tabelle in der README).
#   marke: europäischer ETF auf denselben Index (gleiche Handelszeit wie das Produkt) – nur für Prüfung und Anschluss
def _N(kette, hebel_in, kosten, name, aktiv=False, vgl=False, marke=None):
    return {"kette": kette, "hebel_in": hebel_in, "kosten": kosten, "name": name, "aktiv": aktiv, "vgl": vgl} | ({"marke": marke} if marke else {})


_SP500 = [("^SP500TR", "USD"), ("SPY", "USD")]
NACHBAU = {
    # Europa, Index-Produkte
    "LQQ": _N([("QQQ", "USD")], "USD", 0.60, "Nasdaq-100 (ETF Invesco QQQ, mit Erträgen)", marke=("SXRV.DE", "EUR", "2010-11-02"), aktiv=True, vgl=True),
    "18MF": _N([("SPY", "USD")], "EUR", 0.50, "S&P 500 als Ersatz für den MSCI USA (ETF SPDR S&P 500, mit Erträgen)", marke=("SXR4.DE", "EUR", "2010-11-03"), vgl=True),
    "DBPG": _N(_SP500, "USD", 0.60, "S&P 500 (ETF SPDR S&P 500 mit Erträgen, davor S&P 500 Total Return)", marke=("CSSPX.MI", "EUR"), vgl=True),
    "LVWC": _N([("EUNL.DE", "EUR")], "USD", 0.60, "MSCI World (ETF iShares Core MSCI World auf Xetra, mit Erträgen)", vgl=True),
    "DBPE": _N([("^GDAXI", "EUR")], "EUR", 0.35, "DAX (Performance-Index, mit Dividenden)", aktiv=True, vgl=True),
    "LYY8": _N([("^GDAXI", "EUR")], "EUR", 0.35, "DAX (Performance-Index, mit Dividenden)", aktiv=True, vgl=True),
    "DEL2": _N([("^GDAXI", "EUR")], "EUR", 0.40, "DAX (Performance-Index, mit Dividenden)", vgl=True),
    "LVE": _N([("EXW1.DE", "EUR")], "EUR", 0.40, "Euro Stoxx 50 (ETF iShares Core EURO STOXX 50, mit Ausschüttungen)"),
    "LVC": _N([("CAC.PA", "EUR")], "EUR", 0.40, "CAC 40 (ETF Amundi CAC 40, mit Ausschüttungen)", vgl=True),
    "LEVMIB": _N([("ETFMIB.MI", "EUR")], "EUR", 0.60, "FTSE MIB (ETF Amundi FTSE MIB, mit Ausschüttungen)"),
    "IBEXA": _N([("LYXIB.MC", "EUR")], "EUR", 0.40, "IBEX 35 (ETF Amundi IBEX 35, mit Ausschüttungen)"),
    # Europa, ETCs: ungehebeltes Gegenstück desselben Anbieters in Mailand (gleiche Handelszeit), davor der Future in Dollar
    "LBUL": _N([("GC=F", "USD"), ("PHAU.MI", "EUR")], "USD", 0.98, "Gold (ETC WisdomTree Physical Gold in Mailand, davor Gold-Future)"),
    "LSIL": _N([("SI=F", "USD"), ("PHAG.MI", "EUR")], "USD", 0.98, "Silber (ETC WisdomTree Physical Silver in Mailand, davor Silber-Future)"),
    "LPLA.MI": _N([("PL=F", "USD"), ("PHPT.MI", "EUR")], "USD", 0.98, "Platin (ETC WisdomTree Physical Platinum in Mailand, davor Platin-Future)"),
    "LOIL": _N([("CRUD.MI", "EUR", "2009-01-05")], "USD", 0.98, "Rohöl WTI (ETC WisdomTree WTI Crude Oil in Mailand)"),
    "LCOP": _N([("COPA.MI", "EUR", "2008-09-23")], "USD", 0.98, "Kupfer (ETC WisdomTree Copper in Mailand)", vgl=True),
    "LNGA": _N([("NGAS.MI", "EUR", "2013-01-03")], "USD", 0.98, "Erdgas (ETC WisdomTree Natural Gas in Mailand)"),
    "LWEA": _N([("WEAT.MI", "EUR", "2013-01-03")], "USD", 0.98, "Weizen (ETC WisdomTree Wheat in Mailand)", vgl=True),
    "LCOR": _N([("CORN.MI", "EUR", "2013-01-03")], "USD", 0.98, "Mais (ETC WisdomTree Corn in Mailand)", aktiv=True, vgl=True),
    "LCFE": _N([("COFF.MI", "EUR", "2013-01-03")], "USD", 0.98, "Kaffee (ETC WisdomTree Coffee in Mailand)", aktiv=True, vgl=True),
    # Nickel: Prüfung ab 03/2022 bestanden, trotzdem KEIN Nachbau – in der Handelsaussetzung im März 2022 fiel das echte Produkt
    # auf 26 % seines Werts, die Rechnung aus dem ungehebelten ETC nur auf 41 %: Der Nachbau zeigte genau diese Zeit falsch.
    "LNIK": _N([("NICK.MI", "EUR")], "USD", 0.98, "Nickel (ETC WisdomTree Nickel in Mailand)", vgl=True),
    "2CAR": _N([("EXV5.DE", "EUR")], "EUR", 0.80, "Europa Autoaktien (ETF iShares STOXX Europe 600 Automobiles & Parts, mit Ausschüttungen)"),
    "2FLY": _N([("EXV9.DE", "EUR")], "EUR", 0.80, "Europa Reise- und Freizeitaktien (ETF iShares STOXX Europe 600 Travel & Leisure, mit Ausschüttungen)"),
    "2MUE": _N([("MU", "USD")], "USD", 0.75, "Micron Technology (Aktie in New York, mit Dividenden)", marke=("MTE.DE", "EUR")),
    "LSUG": _N([("SUGA.MI", "EUR")], "USD", 0.98, "Zucker (ETC WisdomTree Sugar in Mailand)", vgl=True),
    # USA: Basis = US-ETF auf denselben Index (gleiche Handelszeit, Dollar)
    "SSO": _N(_SP500, "USD", 0.84, "S&P 500 (SPDR S&P 500 mit Erträgen, davor S&P 500 Total Return)", aktiv=True, vgl=True),
    "SPUU": _N(_SP500, "USD", 0.60, "S&P 500 (SPDR S&P 500 mit Erträgen, davor S&P 500 Total Return)", vgl=True),
    "QLD": _N([("QQQ", "USD")], "USD", 0.89, "Nasdaq-100 (ETF Invesco QQQ, mit Erträgen)", aktiv=True, vgl=True),
    "DDM": _N([("DIA", "USD")], "USD", 0.95, "Dow Jones (ETF SPDR Dow Jones, mit Erträgen)", vgl=True),
    "UWM": _N([("IWM", "USD")], "USD", 0.95, "Russell 2000 (ETF iShares Russell 2000, mit Erträgen)", aktiv=True, vgl=True),
    "MVV": _N([("MDY", "USD")], "USD", 0.95, "S&P MidCap 400 (ETF SPDR S&P MidCap 400, mit Erträgen)", aktiv=True, vgl=True),
    "SAA": _N([("IJR", "USD")], "USD", 0.95, "S&P SmallCap 600 (ETF iShares Core S&P Small-Cap, mit Erträgen)", vgl=True),
    "EZJ": _N([("EWJ", "USD")], "USD", 1.18, "MSCI Japan (ETF iShares MSCI Japan, mit Erträgen)", vgl=True),
    "UPV": _N([("VGK", "USD")], "USD", 0.95, "FTSE Europa (ETF Vanguard FTSE Europe, mit Erträgen)", vgl=True),
    "UBR": _N([("EWZ", "USD")], "USD", 0.95, "MSCI Brasilien (ETF iShares MSCI Brazil, mit Erträgen)", vgl=True),
    "CHAU": _N([("ASHR", "USD")], "USD", 1.19, "China A-Aktien CSI 300 (ETF Xtrackers CSI 300 China A, mit Erträgen)"),
    "CWEB": _N([("KWEB", "USD")], "USD", 1.27, "China-Internetaktien (ETF KraneShares CSI China Internet, mit Erträgen)", vgl=True),
    "ROM": _N([("IYW", "USD")], "USD", 0.93, "US-Technologieaktien (ETF iShares U.S. Technology, mit Erträgen)"),
    "UYG": _N([("IYF", "USD")], "USD", 0.93, "US-Finanzaktien (ETF iShares U.S. Financials, mit Erträgen)"),
    "DIG": _N([("IYE", "USD")], "USD", 0.95, "US-Energieaktien (ETF iShares U.S. Energy, mit Erträgen)", vgl=True),
    "RXL": _N([("IYH", "USD")], "USD", 0.95, "US-Gesundheitsaktien (ETF iShares U.S. Healthcare, mit Erträgen)", aktiv=True, vgl=True),
    "URE": _N([("IYR", "USD")], "USD", 0.95, "US-Immobilienaktien (ETF iShares U.S. Real Estate, mit Erträgen)"),
    "UPW": _N([("IDU", "USD")], "USD", 0.95, "US-Versorgeraktien (ETF iShares U.S. Utilities, mit Erträgen)", vgl=True),
    "UYM": _N([("IYM", "USD")], "USD", 0.95, "US-Grundstoffaktien (ETF iShares U.S. Basic Materials, mit Erträgen)"),
    "UCC": _N([("IYC", "USD")], "USD", 0.95, "US-Konsumaktien zyklisch (ETF iShares U.S. Consumer Discretionary, mit Erträgen)"),
    "UGE": _N([("IYK", "USD")], "USD", 0.95, "US-Basiskonsumaktien (ETF iShares U.S. Consumer Staples, mit Erträgen)"),
    "USD_PROSHARES": _N([("SOXX", "USD")], "USD", 0.94, "US-Halbleiteraktien (ETF iShares Semiconductor, mit Erträgen)"),
    "BIB": _N([("IBB", "USD")], "USD", 0.95, "Nasdaq Biotechnologie (ETF iShares Biotechnology, mit Erträgen)", vgl=True),
    "LTL": _N([("XLC", "USD")], "USD", 0.95, "US-Kommunikationsaktien (ETF Communication Services Select Sector SPDR, mit Erträgen)"),
    "SKYU": _N([("SKYY", "USD")], "USD", 0.95, "Cloud-Computing-Aktien (ETF First Trust Cloud Computing, mit Erträgen)", vgl=True),
    "FNGG": _N([("FNGS", "USD")], "USD", 0.97, "NYSE FANG+ (ETN MicroSectors FANG+)"),
    "QQQU": _N([("MAGS", "USD")], "USD", 0.98, "Magnificent 7 (ETF Roundhill Magnificent Seven)", vgl=True),
    "URAA": _N([("URA", "USD")], "USD", 1.30, "Uran-Aktien (ETF Global X Uranium, mit Erträgen)"),
    "UGL": _N([("GLD", "USD")], "USD", 1.19, "Gold (ETF SPDR Gold Shares)", vgl=True),
    "AGQ": _N([("SLV", "USD")], "USD", 1.29, "Silber (ETF iShares Silver Trust)"),
    "UCO": _N([("USO", "USD")], "USD", 1.47, "Rohöl WTI (ETF United States Oil Fund)"),
    "BOIL": _N([("UNG", "USD")], "USD", 1.39, "Erdgas (ETF United States Natural Gas Fund)"),
    "UBT": _N([("TLT", "USD")], "USD", 0.95, "US-Staatsanleihen 20+ Jahre (ETF iShares 20+ Year Treasury Bond, mit Erträgen)", aktiv=True, vgl=True),
    "UST": _N([("IEF", "USD")], "USD", 0.95, "US-Staatsanleihen 7–10 Jahre (ETF iShares 7-10 Year Treasury Bond, mit Erträgen)", aktiv=True, vgl=True),
    "UJB": _N([("HYG", "USD")], "USD", 0.95, "US-Hochzinsanleihen (ETF iShares iBoxx High Yield, mit Erträgen)"),
    "ULE": _N([("FXE", "USD")], "USD", 0.98, "Euro gegen Dollar (ETF Invesco CurrencyShares Euro)", aktiv=True, vgl=True),
    "YCL": _N([("FXY", "USD")], "USD", 0.98, "Yen gegen Dollar (ETF Invesco CurrencyShares Japanese Yen)", aktiv=True, vgl=True),
    "BITU": _N([("BTC-USD", "USD")], "USD", 0.95, "Bitcoin (Kurs in Dollar)"),
    "ETHT": _N([("ETH-USD", "USD")], "USD", 0.96, "Ether (Kurs in Dollar)"),
}
NACHBAU_OHNE = {   # ohne Rezept: warum
    "LCOC": "kein sauberer Basiswert: der ungehebelte ETC WisdomTree Cocoa (COCO.MI) hat bei Yahoo 164 Fehlkurse",
    "AIBU": "kein ETF auf denselben Index (Solactive US AI & Big Data) gefunden",
    "SC2X": "erst seit 28.07.2026 an der Börse: zu wenig gemeinsame Zeit für eine Prüfung",
}
for _e in HEBEL_ETFS:
    if _e["id"] in NACHBAU:
        _e["nachbau"] = NACHBAU[_e["id"]]
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
