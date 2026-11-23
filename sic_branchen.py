"""Deutsche Kurzbezeichnung der SEC-Branchencodes (Standard Industrial Classification, SIC).

Die SEC ordnet jede meldepflichtige Firma genau einem vierstelligen SIC-Code zu (data.sec.gov/submissions, Feld „sic“).
Hier steht eine feste deutsche Uebersetzung: zuerst die haeufigen vierstelligen Codes, sonst die zweistellige Hauptgruppe.
Unbekannte Codes bekommen keine Branche (nichts geraten).
"""

HAUPTGRUPPE = {
    "01": "Landwirtschaft", "02": "Landwirtschaft (Tierhaltung)", "07": "Agrardienste", "08": "Forstwirtschaft", "09": "Fischerei",
    "10": "Metallbergbau", "12": "Kohlebergbau", "13": "Öl und Gas", "14": "Bergbau (Steine und Erden)",
    "15": "Bauwirtschaft", "16": "Tiefbau", "17": "Bauhandwerk",
    "20": "Nahrungsmittel", "21": "Tabak", "22": "Textilien", "23": "Bekleidung", "24": "Holz", "25": "Möbel", "26": "Papier",
    "27": "Druck und Verlage", "28": "Chemie", "29": "Ölraffinerien", "30": "Gummi und Kunststoff", "31": "Leder und Schuhe",
    "32": "Glas, Stein und Beton", "33": "Metallerzeugung", "34": "Metallwaren", "35": "Maschinenbau", "36": "Elektrotechnik und Elektronik",
    "37": "Fahrzeugbau", "38": "Mess- und Medizintechnik", "39": "Sonstige Herstellung",
    "40": "Eisenbahn", "41": "Personenverkehr", "42": "Spedition und Lager", "44": "Schifffahrt", "45": "Luftfahrt", "46": "Pipelines",
    "47": "Reise- und Logistikdienste", "48": "Telekommunikation", "49": "Versorger",
    "50": "Großhandel", "51": "Großhandel", "52": "Baumärkte", "53": "Kaufhäuser und Discounter", "54": "Lebensmittelhandel",
    "55": "Autohandel", "56": "Bekleidungshandel", "57": "Möbel- und Elektronikhandel", "58": "Gastronomie", "59": "Einzelhandel",
    "60": "Banken", "61": "Kreditinstitute", "62": "Wertpapierhandel", "63": "Versicherungen", "64": "Versicherungsmakler",
    "65": "Immobilien", "67": "Beteiligungsgesellschaften",
    "70": "Hotels", "72": "Persönliche Dienstleistungen", "73": "Unternehmensdienste und IT", "75": "Autoservice",
    "76": "Reparaturdienste", "78": "Film und Fernsehen", "79": "Freizeit und Unterhaltung", "80": "Gesundheitswesen",
    "81": "Rechtsberatung", "82": "Bildung", "83": "Soziale Dienste", "86": "Organisationen",
    "87": "Ingenieur-, Forschungs- und Beratungsdienste", "89": "Dienstleistungen",
}

CODE = {
    "1000": "Metallbergbau", "1040": "Goldbergbau", "1090": "Metallbergbau", "1220": "Kohlebergbau",
    "1311": "Öl- und Gasförderung", "1381": "Öl- und Gasbohrungen", "1382": "Öl- und Gas-Erkundung", "1389": "Öl- und Gasdienste",
    "2000": "Nahrungsmittel", "2011": "Fleischverarbeitung", "2080": "Getränke", "2082": "Bier", "2086": "Erfrischungsgetränke",
    "2090": "Nahrungsmittel", "2111": "Zigaretten",
    "2800": "Chemie", "2810": "Industriechemikalien", "2821": "Kunststoffe", "2833": "Arzneigrundstoffe", "2834": "Pharma",
    "2835": "Diagnostika", "2836": "Biotechnologie", "2840": "Körperpflege und Reinigungsmittel", "2844": "Kosmetik",
    "2851": "Farben und Lacke", "2860": "Industriechemikalien", "2870": "Agrarchemie", "2890": "Spezialchemie", "2911": "Ölraffinerien",
    "3011": "Reifen", "3086": "Kunststoffprodukte", "3089": "Kunststoffprodukte",
    "3310": "Stahl", "3334": "Aluminium", "3350": "Metallverarbeitung", "3420": "Werkzeuge", "3490": "Metallwaren",
    "3510": "Motoren und Turbinen", "3523": "Landmaschinen", "3530": "Baumaschinen", "3531": "Baumaschinen", "3550": "Spezialmaschinen",
    "3559": "Spezialmaschinen", "3560": "Industriemaschinen", "3561": "Pumpen", "3562": "Kugellager", "3564": "Lüftungstechnik",
    "3570": "Computer und Büromaschinen", "3571": "Computer", "3572": "Datenspeicher", "3575": "Computerterminals",
    "3576": "Netzwerktechnik", "3577": "Computerzubehör", "3578": "Kassen- und Zahlungssysteme", "3580": "Kühl- und Klimatechnik",
    "3585": "Kühl- und Klimatechnik", "3590": "Industriemaschinen",
    "3600": "Elektrotechnik", "3612": "Transformatoren", "3613": "Schaltanlagen", "3620": "Elektrische Ausrüstung",
    "3621": "Elektromotoren und Generatoren", "3630": "Haushaltsgeräte", "3634": "Elektrische Haushaltsgeräte", "3640": "Beleuchtung",
    "3651": "Unterhaltungselektronik", "3661": "Telekommunikationsausrüstung", "3663": "Funk- und Sendetechnik",
    "3669": "Kommunikationstechnik", "3670": "Elektronische Bauteile", "3672": "Leiterplatten", "3674": "Halbleiter",
    "3677": "Elektronische Bauteile", "3678": "Steckverbinder", "3679": "Elektronische Bauteile", "3690": "Elektrotechnik",
    "3695": "Speichermedien",
    "3711": "Autohersteller", "3713": "Nutzfahrzeugaufbauten", "3714": "Autozulieferer", "3715": "Anhänger", "3716": "Wohnmobile",
    "3720": "Luftfahrt", "3721": "Flugzeugbau", "3724": "Flugzeugtriebwerke", "3728": "Luftfahrtzulieferer", "3730": "Schiffbau",
    "3743": "Schienenfahrzeuge", "3751": "Motorräder und Fahrräder", "3760": "Raketen und Raumfahrt", "3790": "Fahrzeugbau",
    "3812": "Navigation und Rüstungselektronik", "3821": "Laborausstattung", "3822": "Steuerungstechnik", "3823": "Prozessmesstechnik",
    "3824": "Zähler", "3825": "Elektrische Messgeräte", "3826": "Laboranalysegeräte", "3827": "Optische Instrumente",
    "3829": "Messgeräte", "3841": "Medizintechnik", "3842": "Medizinische Hilfsmittel", "3843": "Zahnmedizin-Bedarf",
    "3844": "Röntgentechnik", "3845": "Elektromedizin", "3851": "Augenoptik", "3861": "Foto- und Kopiertechnik",
    "3910": "Schmuck", "3942": "Spielwaren", "3944": "Spiele und Spielwaren", "3949": "Sportartikel", "3990": "Sonstige Herstellung",
    "4011": "Eisenbahn", "4100": "Personenverkehr", "4213": "Spedition", "4400": "Schifffahrt", "4412": "Hochseeschifffahrt",
    "4512": "Fluggesellschaften", "4513": "Luftfracht und Kurierdienste", "4522": "Charterflüge", "4581": "Flughafendienste",
    "4610": "Pipelines", "4700": "Reisedienste", "4731": "Logistikvermittlung",
    "4812": "Mobilfunk", "4813": "Telekommunikation", "4822": "Nachrichtendienste", "4832": "Hörfunk", "4833": "Fernsehsender",
    "4841": "Kabelfernsehen", "4899": "Kommunikationsdienste",
    "4900": "Versorger", "4911": "Stromversorger", "4922": "Gaspipelines", "4923": "Gasversorger", "4924": "Gasversorger",
    "4931": "Strom- und Gasversorger", "4932": "Strom- und Gasversorger", "4941": "Wasserversorger", "4950": "Entsorgung",
    "4953": "Entsorgung", "4955": "Entsorgung", "4991": "Kraftwerksbetreiber",
    "5000": "Großhandel", "5013": "Großhandel Autoteile", "5031": "Großhandel Baustoffe", "5045": "Großhandel Computer",
    "5047": "Großhandel Medizinbedarf", "5065": "Großhandel Elektronik", "5070": "Großhandel Eisenwaren", "5080": "Großhandel Maschinen",
    "5090": "Großhandel", "5110": "Großhandel Papier", "5122": "Großhandel Arzneimittel", "5140": "Großhandel Lebensmittel",
    "5171": "Tanklager", "5172": "Großhandel Mineralöl", "5180": "Großhandel Getränke",
    "5200": "Baumärkte", "5211": "Baumärkte", "5311": "Kaufhäuser", "5331": "Discounter", "5399": "Warenhäuser",
    "5400": "Lebensmittelhandel", "5411": "Supermärkte", "5412": "Nachbarschaftsläden", "5500": "Autohandel", "5531": "Autoteilehandel",
    "5600": "Bekleidungshandel", "5621": "Bekleidungshandel", "5651": "Bekleidungshandel", "5661": "Schuhhandel",
    "5700": "Möbel- und Elektronikhandel", "5712": "Möbelhandel", "5731": "Elektronikhandel", "5734": "Computerhandel",
    "5810": "Gastronomie", "5812": "Restaurants", "5900": "Einzelhandel", "5912": "Apotheken", "5940": "Fachhandel",
    "5945": "Spielwarenhandel", "5961": "Versand- und Onlinehandel", "5990": "Einzelhandel",
    "6021": "Banken", "6022": "Banken", "6029": "Banken", "6035": "Sparkassen", "6036": "Sparkassen", "6099": "Finanzdienste",
    "6111": "Staatliche Kreditinstitute", "6141": "Konsumentenkredite", "6153": "Kreditkarten und Händlerfinanzierung",
    "6159": "Kreditinstitute", "6162": "Hypothekenfinanzierung", "6163": "Kreditvermittlung", "6172": "Kreditinstitute",
    "6189": "Verbriefungen", "6199": "Finanzdienste", "6200": "Wertpapierhandel", "6211": "Broker und Investmentbanken",
    "6221": "Rohstoffhandel", "6282": "Vermögensverwaltung", "6311": "Lebensversicherungen", "6321": "Unfall- und Krankenversicherungen",
    "6324": "Krankenversicherungen", "6331": "Sachversicherungen", "6351": "Kreditversicherungen", "6361": "Rechtstitelversicherungen",
    "6399": "Versicherungen", "6411": "Versicherungsmakler", "6500": "Immobilien", "6510": "Immobilienvermietung",
    "6512": "Gewerbeimmobilien", "6513": "Wohnimmobilien", "6519": "Immobilienvermietung", "6531": "Immobilienmakler",
    "6532": "Immobilienmakler", "6552": "Projektentwicklung", "6770": "Mantelgesellschaft (SPAC)", "6792": "Öl- und Gasrechte",
    "6794": "Lizenz- und Patentverwertung", "6795": "Rohstoffrechte", "6798": "Immobilienfonds (REIT)", "6799": "Beteiligungsgesellschaften",
    "7011": "Hotels", "7200": "Persönliche Dienstleistungen", "7310": "Werbung", "7311": "Werbeagenturen", "7320": "Auskunfteien und Inkasso",
    "7331": "Direktmarketing", "7340": "Gebäudedienste", "7350": "Vermietung von Ausrüstung", "7359": "Vermietung von Ausrüstung",
    "7361": "Personaldienstleister", "7363": "Zeitarbeit", "7370": "IT-Dienste", "7371": "Softwareentwicklung",
    "7372": "Software", "7373": "IT-Systemintegration", "7374": "Datenverarbeitung und Cloud", "7377": "Computervermietung",
    "7380": "Unternehmensdienste", "7381": "Sicherheitsdienste", "7384": "Fotolabore", "7385": "Telefondienste",
    "7389": "Unternehmensdienste", "7500": "Autoservice", "7510": "Autovermietung", "7812": "Film- und Videoproduktion",
    "7819": "Filmdienste", "7822": "Filmverleih", "7830": "Kinos", "7841": "Videoverleih", "7900": "Freizeit und Unterhaltung",
    "7948": "Rennsport", "7990": "Freizeit und Unterhaltung", "7997": "Sport- und Freizeitclubs",
    "8000": "Gesundheitsdienste", "8011": "Arztpraxen", "8050": "Pflegeheime", "8051": "Pflegeheime", "8060": "Krankenhäuser",
    "8062": "Krankenhäuser", "8071": "Medizinische Labore", "8082": "Häusliche Pflege", "8090": "Gesundheitsdienste",
    "8093": "Ambulante Kliniken", "8111": "Rechtsberatung", "8200": "Bildung", "8300": "Soziale Dienste", "8351": "Kinderbetreuung",
    "8600": "Organisationen", "8700": "Ingenieur- und Beratungsdienste", "8711": "Ingenieurdienste", "8731": "Auftragsforschung",
    "8734": "Prüflabore", "8741": "Unternehmensberatung", "8742": "Unternehmensberatung", "8744": "Betriebsführung im Auftrag",
    "8880": "Dienstleistungen", "8900": "Dienstleistungen", "9995": "Mantelgesellschaft",
}


def branche(sic) -> str | None:
    """Deutsche Kurzbezeichnung zu einem SIC-Code (z. B. 3674 -> „Halbleiter“) oder None."""
    s = str(sic or "").strip()
    if not s.isdigit() or s in ("0", "0000"):
        return None
    s = s.zfill(4)
    return CODE.get(s) or HAUPTGRUPPE.get(s[:2])
