"""ISIN, WKN und Kurzbeschreibung (1–2 Sätze) je Wert – Wunsch Marc 22.11.2026: statt des Börsenkürzels ISIN/WKN zeigen
und kurz sagen, worum es sich handelt.

Quellen:
  - ETFs, Rohstoffe, Krypto: eigene, feste Texte (TEXTE unten) und nur sicher bekannte ISINs/WKNs (FEST_ISIN).
    US-ETFs bekommen ihre ISIN aus der CUSIP (web/daten/isin.json von isin.py).
  - Aktien USA: Wikidata (gemeinfrei, CC0) über die Börsennotierung an Nasdaq/NYSE mit Kürzel: deutsche
    Kurzbeschreibung, Land, ISIN. Die ISIN wird mit den CUSIP-ISINs aus isin.json abgeglichen; nur wenn beide
    übereinstimmen, gilt sie als „geprüft“. Sonst die aus der CUSIP berechnete ISIN (bei kanadischen Firmen „CA…“)
    mit dem Vermerk „berechnet“.
  - Auslandsaktien: ISIN aus welt.csv (Wikidata), Beschreibung per ISIN aus Wikidata.
  - Was die Firma macht (Wunsch Marc 23.11.2026): erster Satz des Artikels der deutschen Wikipedia (Lizenz CC BY-SA 4.0,
    deshalb mit Quelle und Link: text_quelle, text_url); ohne Artikel die Kurzbeschreibung aus Wikidata wie bisher.
  - Branche: für US-gelistete Firmen der SEC-Branchencode (fundamente.stammdaten, deutsch über sic_branchen.py),
    sonst die Branche aus Wikidata (P452, deutsche Bezeichnung). Sitzland: Geschäftsadresse laut SEC, sonst Wikidata (P17).
  - WKN: nur, wenn sie sich sicher ableiten lässt (deutsche ISIN: DE000 + WKN + Prüfziffer) oder fest bekannt ist.
    Für US-Aktien gibt es keine freie WKN-Quelle – dann bleibt sie leer (nicht raten).
Speicher: daten/beschreibung.json (höchstens einmal pro Woche neu, sonst bleibt die letzte Datei).
Aufruf: python beschreibung.py
"""
import json
import re
import sys
import time
import collections
import pandas as pd
import requests

import einstellungen as E

ZIEL = E.DATEN / "beschreibung.json"
VERSION = 7   # bei neuen Feldern oder geänderten Kennungen erhöhen: dann wird sofort neu gebaut, nicht erst nach 7 Tagen (4: Krypto Top 200, 5: Hebel 2x, 6: Hebel 2x auf 62 Produkte, 7: Hebel-Texte mit Nachbau-Hinweis)
WIKIDATA = "https://query.wikidata.org/sparql"
KOPF = {"User-Agent": "minusmitstil-kaufplan/1.0 (Lernprojekt, GitHub swissiybot/minusmitstil)", "Accept": "application/sparql-results+json"}
BOERSE = {"Q82059": "Nasdaq", "Q13677": "NYSE"}

# Sicher bekannte ISIN/WKN der europäischen Börsenplätze (UCITS-ETFs); US-ETFs kommen aus der CUSIP.
FEST_ISIN = {
    "IWDA": ("IE00B4L5Y983", "A0RPWH"), "VWRL": ("IE00B3RBWM25", "A1JX52"),
    "EXS1": ("DE0005933931", None), "SX5E": ("DE0005933956", None),
}

TEXTE = {
    # breite Indizes
    "SPY": "ETF auf den S&P 500, die 500 großen börsennotierten US-Unternehmen. Der Standard für „den US-Aktienmarkt“.",
    "QQQ": "ETF auf den Nasdaq-100, die 100 größten Nicht-Finanzunternehmen der Nasdaq-Börse. Stark technologielastig (Apple, Microsoft, Nvidia & Co.).",
    "ONEQ": "ETF auf den Nasdaq Composite, alle an der Nasdaq notierten Aktien. Breiter als der Nasdaq-100, aber ebenfalls technologielastig.",
    "DIA": "ETF auf den Dow Jones Industrial Average, 30 große US-Konzerne. Der älteste US-Aktienindex, gewichtet nach Aktienkurs statt nach Börsenwert.",
    "IWM": "ETF auf den Russell 2000, rund 2.000 kleinere US-Unternehmen (Small Caps). Schwankt meist stärker als der S&P 500.",
    "URTH": "ETF auf den MSCI World, rund 1.400 große und mittlere Unternehmen aus 23 Industrieländern. Etwa 70 % davon sind US-Firmen.",
    "IWDA": "iShares Core MSCI World, ein in Europa zugelassener ETF auf rund 1.400 Unternehmen aus 23 Industrieländern. Thesaurierend, Kurs hier in Euro-Handel (Amsterdam).",
    "VWRL": "Vanguard FTSE All-World, ein in Europa zugelassener ETF auf rund 3.700 Unternehmen aus Industrie- und Schwellenländern. Schüttet Dividenden aus.",
    "ACWI": "ETF auf den MSCI ACWI, große und mittlere Unternehmen aus Industrie- und Schwellenländern. Praktisch „die ganze Welt“ in einem Wert.",
    "EEM": "ETF auf den MSCI Emerging Markets, Unternehmen aus Schwellenländern wie China, Indien, Taiwan, Südkorea und Brasilien.",
    "EXS1": "iShares Core DAX, ein ETF auf die 40 größten deutschen Unternehmen. Der DAX enthält die Dividenden (Performance-Index).",
    "SX5E": "ETF auf den Euro Stoxx 50, die 50 größten Unternehmen der Eurozone (z. B. ASML, LVMH, SAP, Siemens).",
    "ISF": "ETF auf den FTSE 100, die 100 größten Unternehmen an der Londoner Börse. Viel Energie, Rohstoffe, Banken und Konsumgüter.",
    "EWJ": "ETF auf große und mittlere japanische Unternehmen (MSCI Japan). Die lange Vorgeschichte im Chart stammt vom Nikkei 225.",
    # Themen
    "URA": "ETF auf Unternehmen aus Uranbergbau und Kernbrennstoff-Herstellung. Hängt stark vom Uranpreis und der Atompolitik ab.",
    "LIT": "ETF auf Unternehmen aus Lithiumförderung und Batterieherstellung. Abhängig von Elektroautos und Rohstoffpreisen, sehr schwankungsreich.",
    "TAN": "ETF auf Solarunternehmen weltweit (Modulhersteller, Wechselrichter, Solarparks). Sehr schwankungsreich, stark zinsabhängig.",
    "ICLN": "ETF auf Unternehmen aus erneuerbaren Energien weltweit (Wind, Solar, Wasserstoff, Versorger mit grünem Strom).",
    "SMH": "ETF auf die größten Halbleiterunternehmen (Chips), z. B. Nvidia, TSMC, Broadcom und ASML. Sehr zyklisch.",
    "SOXX": "ETF auf US-notierte Halbleiterunternehmen (Chipentwickler, -hersteller und Ausrüster). Sehr zyklisch.",
    "IGV": "ETF auf nordamerikanische Softwareunternehmen, z. B. Microsoft, Oracle, Salesforce und Adobe.",
    "SKYY": "ETF auf Unternehmen aus Cloud-Computing (Rechenzentren, Software-Dienste aus dem Internet).",
    "CIBR": "ETF auf Unternehmen aus der Cybersicherheit (Schutz von Netzwerken, Daten und Geräten).",
    "BOTZ": "ETF auf Unternehmen aus Robotik und künstlicher Intelligenz, z. B. Industrieroboter, Automatisierung und KI-Chips.",
    "ARKK": "Aktiv gemanagter Fonds von ARK Invest auf „disruptive“ Technologien (z. B. Tesla, Krypto, Genomik). Extrem schwankungsreich.",
    "KWEB": "ETF auf chinesische Internetunternehmen wie Alibaba, Tencent und PDD. Hängt stark von der Politik in China ab.",
    "IBB": "ETF auf Biotechnologie-Unternehmen an US-Börsen, gewichtet nach Börsenwert (große Firmen dominieren).",
    "XBI": "ETF auf US-Biotechnologie-Unternehmen, alle gleich gewichtet – dadurch viele kleine Forschungsfirmen, sehr schwankungsreich.",
    "ITA": "ETF auf US-Unternehmen aus Luft- und Raumfahrt sowie Rüstung (z. B. Boeing, Lockheed Martin, RTX).",
    "GDX": "ETF auf Goldminen-Unternehmen weltweit. Bewegt sich mit dem Goldpreis, aber meist deutlich stärker in beide Richtungen.",
    "COPX": "ETF auf Kupferminen-Unternehmen weltweit. Hängt stark vom Kupferpreis und der Weltkonjunktur ab.",
    "REMX": "ETF auf Unternehmen aus Förderung und Verarbeitung Seltener Erden und strategischer Metalle. Sehr schwankungsreich.",
    "PHO": "ETF auf Unternehmen rund ums Wasser (Versorgung, Aufbereitung, Leitungen, Messtechnik).",
    "IGF": "ETF auf Infrastrukturunternehmen weltweit (Versorger, Pipelines, Flughäfen, Mautstraßen).",
    "VNQ": "ETF auf US-Immobiliengesellschaften (REITs): Büros, Wohnungen, Lager, Rechenzentren. Zinsabhängig.",
    # Branchen S&P 500
    "XLK": "ETF auf die Technologie-Unternehmen im S&P 500 (z. B. Apple, Microsoft, Nvidia).",
    "XLF": "ETF auf die Finanzunternehmen im S&P 500 (Banken, Versicherungen, Zahlungsdienstleister).",
    "XLE": "ETF auf die Energieunternehmen im S&P 500 (Öl und Gas, z. B. ExxonMobil, Chevron).",
    "XLV": "ETF auf die Gesundheitsunternehmen im S&P 500 (Pharma, Medizintechnik, Krankenversicherer).",
    "XLI": "ETF auf die Industrieunternehmen im S&P 500 (Maschinenbau, Luftfahrt, Transport).",
    "XLP": "ETF auf Basiskonsumgüter im S&P 500 (Lebensmittel, Getränke, Drogerie) – eher ruhig in Krisen.",
    "XLY": "ETF auf zyklischen Konsum im S&P 500 (z. B. Amazon, Tesla, Autohersteller, Handel, Restaurants).",
    "XLU": "ETF auf die Versorger im S&P 500 (Strom, Gas, Wasser) – eher ruhig, zinsabhängig.",
    "XLB": "ETF auf Grundstoff-Unternehmen im S&P 500 (Chemie, Metalle, Verpackung, Baustoffe).",
    "KBE": "ETF auf US-Banken, alle etwa gleich gewichtet (auch viele Regionalbanken).",
    # Faktoren
    "RSP": "ETF auf den S&P 500, aber alle 500 Unternehmen gleich gewichtet – große Konzerne zählen nicht mehr als kleine.",
    "MTUM": "ETF auf US-Aktien, die zuletzt besonders stark gestiegen sind (Momentum-Faktor, MSCI USA Momentum).",
    "QUAL": "ETF auf US-Unternehmen mit hoher Qualität: hohe Eigenkapitalrendite, stabile Gewinne, wenig Schulden.",
    "USMV": "ETF auf US-Aktien mit möglichst geringer Schwankung (Minimum Volatility).",
    "IWD": "ETF auf günstig bewertete große US-Unternehmen (Value, Russell 1000 Value).",
    "IWF": "ETF auf wachstumsstarke große US-Unternehmen (Growth, Russell 1000 Growth).",
    "VYM": "ETF auf US-Unternehmen mit überdurchschnittlich hoher Dividende.",
    "VIG": "ETF auf US-Unternehmen, die ihre Dividende seit vielen Jahren regelmäßig erhöhen.",
    "IJH": "ETF auf den S&P 400, mittelgroße US-Unternehmen (Mid Caps).",
    "VSS": "ETF auf kleinere Unternehmen weltweit ohne die USA (Small Caps aus Industrie- und Schwellenländern).",
    # Regionen und Länder
    "EFA": "ETF auf große Unternehmen der Industrieländer ohne USA und Kanada (MSCI EAFE: Europa, Australien, Fernost).",
    "VGK": "ETF auf große und mittlere europäische Unternehmen (FTSE Developed Europe).",
    "MCHI": "ETF auf chinesische Unternehmen (MSCI China), z. B. Tencent und Alibaba.",
    "FXI": "ETF auf die 50 größten chinesischen Unternehmen, die in Hongkong gehandelt werden.",
    "INDA": "ETF auf große und mittlere indische Unternehmen (MSCI India).",
    "EWZ": "ETF auf große brasilianische Unternehmen (MSCI Brazil), viel Rohstoffe, Energie und Banken.",
    "EWG": "ETF auf große deutsche Unternehmen (MSCI Germany).",
    "EWU": "ETF auf große britische Unternehmen (MSCI United Kingdom).",
    "EWT": "ETF auf taiwanische Unternehmen (MSCI Taiwan), stark geprägt von TSMC.",
    "EWY": "ETF auf südkoreanische Unternehmen (MSCI Korea), stark geprägt von Samsung.",
    "EWC": "ETF auf große kanadische Unternehmen (MSCI Canada), viel Banken, Energie und Rohstoffe.",
    "EWA": "ETF auf große australische Unternehmen (MSCI Australia), viel Banken und Bergbau.",
    "EWL": "ETF auf große Schweizer Unternehmen (MSCI Switzerland), z. B. Nestlé, Novartis, Roche.",
    # Anleihen
    "AGG": "ETF auf den gesamten US-Anleihenmarkt mit guter Bonität (Staats-, Hypotheken- und Unternehmensanleihen).",
    "IEF": "ETF auf US-Staatsanleihen mit 7 bis 10 Jahren Restlaufzeit. Steigt meist, wenn die Zinsen fallen.",
    "TLT": "ETF auf US-Staatsanleihen mit mehr als 20 Jahren Restlaufzeit. Reagiert sehr stark auf Zinsänderungen.",
    "SHY": "ETF auf US-Staatsanleihen mit 1 bis 3 Jahren Restlaufzeit – sehr schwankungsarm, fast wie Tagesgeld.",
    "LQD": "ETF auf US-Unternehmensanleihen mit guter Bonität (Investment Grade).",
    "HYG": "ETF auf US-Hochzinsanleihen (Firmen mit schwächerer Bonität) – höhere Zinsen, höheres Ausfallrisiko.",
    "EMB": "ETF auf Staatsanleihen von Schwellenländern in US-Dollar.",
    "TIP": "ETF auf inflationsgeschützte US-Staatsanleihen (TIPS) – Kapital und Zinsen steigen mit der Inflation.",
    "BNDX": "ETF auf Anleihen guter Bonität weltweit ohne die USA, gegen Währungsschwankungen zum Dollar abgesichert.",
    "SLV": "ETF, der physisches Silber hält. Der Kurs folgt dem Silberpreis.",
    "GLD": "ETF, der physisches Gold in Tresoren hält. Der Kurs folgt dem Goldpreis.",
    # Krypto
    "BTC": "Bitcoin, die erste und größte Kryptowährung (seit 2009). Die Menge ist auf 21 Millionen begrenzt; sehr schwankungsreich.",
    "ETH-USD": "Ethereum, die zweitgrößte Kryptowährung. Plattform für Smart Contracts und viele andere Kryptoprojekte.",
    "SOL-USD": "Solana, eine Kryptowährung und Blockchain-Plattform mit sehr schnellen, günstigen Transaktionen.",
    "LINK-USD": "Chainlink, eine Kryptowährung für „Orakel“: Sie liefert Daten von außen (z. B. Kurse) an Blockchains.",
    "XLM-USD": "Stellar, eine Kryptowährung für schnelle und günstige Überweisungen, auch über Ländergrenzen.",
    # Rohstoffe
    "GOLD": "Goldpreis über den vordersten Terminkontrakt (Future) an der Comex. Gilt als Krisenwährung, bringt aber keine Zinsen.",
    "SILBER": "Silberpreis über den vordersten Terminkontrakt (Future). Teils Edelmetall, teils Industriemetall – schwankt stärker als Gold.",
    "PLATIN": "Platinpreis über den vordersten Terminkontrakt (Future). Wichtig für Autokatalysatoren und Schmuck.",
    "PALLADIUM": "Palladiumpreis über den vordersten Terminkontrakt (Future). Vor allem für Katalysatoren von Benzinautos.",
    "KUPFER": "Kupferpreis über den vordersten Terminkontrakt (Future). Gilt als Konjunkturbarometer („Dr. Copper“).",
    "WTI": "Ölpreis der US-Sorte West Texas Intermediate über den vordersten Terminkontrakt (Future).",
    "BRENT": "Ölpreis der Nordsee-Sorte Brent über den vordersten Terminkontrakt (Future) – der Maßstab für Europa.",
    "ERDGAS": "US-Erdgaspreis (Henry Hub) über den vordersten Terminkontrakt (Future). Extrem schwankungsreich.",
    "WEIZEN": "Weizenpreis über den vordersten Terminkontrakt (Future) in Chicago.",
    "MAIS": "Maispreis über den vordersten Terminkontrakt (Future) in Chicago.",
    "SOJA": "Sojabohnenpreis über den vordersten Terminkontrakt (Future) in Chicago.",
    "KAFFEE": "Kaffeepreis (Arabica) über den vordersten Terminkontrakt (Future) in New York.",
    "ZUCKER": "Zuckerpreis (Rohzucker) über den vordersten Terminkontrakt (Future) in New York.",
    "KAKAO": "Kakaopreis über den vordersten Terminkontrakt (Future) in New York.",
    "DBC": "ETF auf einen Korb aus Rohstoff-Futures (Energie, Metalle, Agrar). Enthält Rollkosten, also nahe an der Anlegerrendite.",
    "NICKEL": "WisdomTree Nickel, ein börsengehandeltes Wertpapier (ETC) auf Nickel-Futures, gehandelt in London in US-Dollar. Nickel steckt vor allem in Edelstahl und Batterien.",
}


LAND = {"Vereinigte Staaten": "den USA", "Vereinigtes Königreich": "Großbritannien", "Niederlande": "den Niederlanden",
        "Schweiz": "der Schweiz", "Volksrepublik China": "China", "Republik China": "Taiwan", "Türkei": "der Türkei"}
LAND_KURZ = {"Vereinigte Staaten": "USA", "Volksrepublik China": "China", "Republik China": "Taiwan"}


def hebel_text(e: dict) -> str:
    """Kurzbeschreibung eines Hebel-Produkts aus der geprüften Liste (einstellungen.HEBEL_ETFS) – keine Empfehlung."""
    h = e["hebel"]
    platz = {".PA": "Paris", ".MI": "Mailand", ".MC": "Madrid", ".DE": "Xetra", ".AS": "Amsterdam"}.get(e["etf"][-3:] if "." in e["etf"] else "", "in den USA (NYSE Arca oder Nasdaq)")
    was = ("Besicherte Schuldverschreibung (ETC, kein Fonds)" if h["art"] == "ETC" else
           "Börsengehandelte Schuldverschreibung (ETP, kein Fonds: Ausfallrisiko des Anbieters)" if h["art"] == "ETP" else
           "Börsengehandelter Fonds (ETF)" if h["eu"] else "US-ETF")
    text = (f"{was} mit täglichem 2-fachem Hebel auf {h['basis']}: Ziel ist das Doppelte der Veränderung an EINEM Tag – über Wochen und Jahre "
            f"ist das nicht das Doppelte. Kein Knock-out. Voller Name: {e['produkt']}. Kurse hier von der Börse {platz}")
    text += f"; auf Xetra dieselben Anteile unter dem Kürzel {h['xetra']}." if h.get("xetra") else "."
    if not h["eu"]:
        text += " Für Privatanleger in der EU meist nicht kaufbar (es fehlt das vorgeschriebene EU-Basisinformationsblatt)."
    if h.get("einzel"):
        text += (" Einzelwert-Risiko: Das Produkt hängt an EINER Aktie – fällt sie an einem Tag um 50 % oder mehr, ist der Einsatz"
                 " praktisch verloren; schon wenige schwache Tage hintereinander kosten überproportional.")
    if e.get("ab"):
        text += f" Kurse vor dem {'.'.join(reversed(e['ab'].split('-')))} bleiben weg: Sie sind bei Yahoo fehlerhaft."
    if (e.get("nachbau") or {}).get("aktiv"):
        text += (" Die Zeit vor dem ersten echten Kurs ist NACHGEBAUT (aus den Tageskursen des Basiswerts: täglich das Doppelte, abzüglich"
                 " Zins und laufender Kosten) – das sind keine echten Kurse; im Chart ist der Abschnitt gekennzeichnet.")
    return text


FEST_ISIN.update({e["id"]: (e["isin"], e["wkn"]) for e in E.HEBEL_ETFS})   # geprüfte ISIN/WKN der Hebel-Produkte (einstellungen.py)
TEXTE.update({e["id"]: hebel_text(e) for e in E.HEBEL_ETFS})


def wkn_aus(isin: str | None) -> str | None:
    return isin[5:11] if isin and isin.startswith("DE") and len(isin) == 12 else None


def sparql(q: str) -> list[dict]:
    for versuch in range(3):
        try:
            r = requests.get(WIKIDATA, params={"query": q}, headers=KOPF, timeout=180)
            r.raise_for_status()
            return [{k: v["value"] for k, v in b.items()} for b in r.json()["results"]["bindings"]]
        except Exception as ex:
            print(f"Wikidata-Abfrage fehlgeschlagen ({ex.__class__.__name__}), Versuch {versuch + 1}", file=sys.stderr)
            time.sleep(10)
    return []


ALLGEMEIN = {"inc", "corp", "corporation", "ltd", "limited", "company", "co", "holdings", "holding", "group", "plc", "the",
             "and", "sa", "nv", "ag", "se", "llc", "lp", "class", "ordinary", "shares", "common", "stock", "international", "com"}


def _woerter(name: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9äöüß]+", str(name).lower()) if w not in ALLGEMEIN]


def name_passt(listenname: str, wikidata_name: str | None) -> bool:
    """Gehört der Wikidata-Eintrag zur Firma in unserer Liste? Kürzel werden neu vergeben (z. B. NYSE „GOLD“: früher Barrick,
    heute Gold.com) – dann nicht die Beschreibung der alten Firma zeigen. Passt, wenn das erste markante Wort des Wikidata-Namens
    in unserem Namen steht oder der Wikidata-Name die Anfangsbuchstaben des Listennamens bildet (z. B. TSMC)."""
    if not wikidata_name or re.fullmatch(r"Q\d+", str(wikidata_name)):   # ohne deutschen Namen liefert Wikidata nur die Nummer
        return True
    a, b = _woerter(listenname), _woerter(wikidata_name)
    erstes = next((w for w in b if len(w) >= 3), None) or next((w for w in b if len(w) >= 2), None)
    if erstes and erstes in a:   # das erste markante Wort des Wikidata-Namens steht in unserem Namen
        return True              # („Barrick Gold“ passt nicht zu „Gold.com“, „The Coca-Cola Company“ passt zu „Coca-Cola“)
    kurz = "".join(w[0] for w in re.findall(r"[a-z0-9]+", str(listenname).lower()) if w not in {"the", "and", "of"})
    return any(len(w) >= 2 and kurz.startswith(w) for w in re.findall(r"[a-z0-9]+", str(wikidata_name).lower()))


def satz(beschr: str | None, land: str | None, fallback: str) -> str:
    if beschr:
        t = beschr.strip()
        t = t[0].upper() + t[1:]
        if land and land.lower()[:5] not in t.lower() and "amerikan" not in t.lower():
            t += f", Sitz: {LAND_KURZ.get(land, land)}"
        return t.rstrip(".") + "."
    return fallback


ABKUERZUNGEN = {"inc", "co", "corp", "ltd", "plc", "n.v", "s.a", "a.g", "z", "b", "u", "a", "bzw", "etc", "st", "dr", "nr", "ca",
                "d", "h", "i", "e", "sog", "jh", "mio", "mrd", "bspw", "vgl", "ggf", "usw", "evtl", "hl", "gegr", "kt", "fa"}


def erster_satz(text: str) -> str:
    """Erster Satz eines Absatzes; Punkte nach Abkürzungen (Inc., Co., z. B. …) und Zahlen beenden keinen Satz."""
    for m in re.finditer(r"\.\s+(?=[A-ZÄÖÜ])", text):
        wort = re.split(r"[\s(]", text[:m.start()])[-1].lower().rstrip(".")
        if wort in ABKUERZUNGEN or len(wort) <= 1 or wort.isdigit() or re.fullmatch(r"([a-zäöü]\.)+[a-zäöü]?", wort):
            continue
        return text[:m.start() + 1]
    return text


WP_CACHE = E.DATEN / "wikipedia_saetze.json"   # {Titel: [Satz oder None, Abruftag]} – nicht im Repo
WP_NEU_TAGE = 90
WP_MINUTEN = float(__import__("os").environ.get("WP_MINUTEN", "10"))   # online 5 (Workflow), der Rest folgt im nächsten Lauf


def wp_saetze(titel: list[str]) -> tuple[dict, int]:
    """Erster Satz der Einleitung je Artikel der deutschen Wikipedia. Wikipedia drosselt schnelle Abrufe (HTTP 429):
    je Abruf 20 Artikel, Pause dazwischen, bei 429 die verlangte Wartezeit. Bereits geholte Saetze bleiben 90 Tage im
    Zwischenspeicher; je Lauf hoechstens WP_MINUTEN Minuten, der Rest folgt im naechsten Lauf.
    Rueckgabe: ({Titel: Satz}, Anzahl noch offener Artikel)."""
    import datetime as dt
    t0, heute = time.time(), dt.date.today()
    cache = json.loads(WP_CACHE.read_text()) if WP_CACHE.exists() else {}
    titel = sorted(set(x for x in titel if x))
    faellig = [x for x in titel if x not in cache or (heute - dt.date.fromisoformat(cache[x][1])).days >= WP_NEU_TAGE]
    s = requests.Session(); s.headers.update({"User-Agent": KOPF["User-Agent"]})
    i = 0
    while i < len(faellig) and time.time() - t0 < WP_MINUTEN * 60:
        teil = faellig[i:i + 20]
        try:
            r = s.get("https://de.wikipedia.org/w/api.php", timeout=60, params={
                "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "exlimit": "max",
                "titles": "|".join(teil), "format": "json", "redirects": 1})
            if r.status_code == 429:
                time.sleep(min(60, int(r.headers.get("retry-after") or 10)) + 1)
                continue
            r.raise_for_status()
            q = r.json().get("query", {})
        except Exception as ex:
            print(f"Wikipedia-Abruf fehlgeschlagen ({ex.__class__.__name__}) – nächster Versuch", file=sys.stderr)
            time.sleep(10)
            continue
        um = {x["from"]: x["to"] for x in q.get("normalized", []) + q.get("redirects", [])}
        texte = {p_.get("title"): p_.get("extract") for p_ in q.get("pages", {}).values()}
        for x in teil:
            ziel = um.get(um.get(x, x), um.get(x, x))
            cache[x] = [satz_bereinigen(erster_satz(texte.get(ziel) or "")), heute.isoformat()]
        i += 20
        tmp = WP_CACHE.with_suffix(".tmp"); tmp.write_text(json.dumps(cache, ensure_ascii=False)); tmp.replace(WP_CACHE)
        time.sleep(2)
    offen = len(faellig) - min(i, len(faellig))
    return {x: cache[x][0] for x in titel if x in cache and cache[x][0]}, offen


def satz_bereinigen(x: str | None) -> str | None:
    """Aussprache, Klammern und Trennzeichen raus; nur ein Satz, nicht zu lang (sonst nichts)."""
    if not x:
        return None
    s = x.replace("\u00ad", "").split("\n")[0].strip()
    for _ in range(2):
        s = re.sub(r"\s*\[[^\[\]]*\]", "", s)
        s = re.sub(r"\s*\([^()]*\)", "", s)
    s = re.sub(r"\s+([,.;:])", r"\1", re.sub(r"\s{2,}", " ", s)).strip()
    if len(s) < 30 or len(s) > 420 or " ist " not in f" {s} " and " war " not in f" {s} " and " sind " not in f" {s} ":
        return None
    return s if s.endswith(".") else s + "."


def main():
    offen_datei = E.DATEN / "beschreibung_offen.txt"   # noch fehlende Wikipedia-Sätze: dann nicht 7 Tage warten
    try:
        alt = json.loads(ZIEL.read_text()) if ZIEL.exists() else {}
        alte_version = alt.get("_version")
    except Exception:
        alt, alte_version = {}, None
    # Werte der festen Listen (Hebel-Produkte), die in der vorhandenen Datei noch fehlen: dann sofort neu bauen. Am 24.11.2026 wurde die
    # Hebel-Liste von 28 auf 62 erweitert, die Datei war aber schon frisch gebaut – die 34 neuen standen online ohne ISIN, WKN und Kurztext.
    fehlt = [e["id"] for e in E.HEBEL_ETFS if e["id"] not in alt]
    if fehlt and ZIEL.exists():
        print(f"Beschreibungen: {len(fehlt)} Werte der festen Listen fehlen noch (z. B. {fehlt[0]}) – wird neu gebaut")
    if (ZIEL.exists() and time.time() - ZIEL.stat().st_mtime < 7 * 86400 and "--neu" not in sys.argv and alte_version == VERSION and not fehlt
            and not (offen_datei.exists() and offen_datei.read_text().strip() not in ("", "0"))):
        print("Beschreibungen: jünger als 7 Tage, nicht neu geladen")
        return
    uni = pd.read_csv(E.DATEN / "universum.csv").fillna("")
    cusip = collections.defaultdict(list)
    try:
        for isin_, wid in json.loads((E.WEB_DATEN / "isin.json").read_text()).items():
            cusip[wid].append(isin_)
    except Exception:
        pass
    welt_isin = {}
    try:
        w = pd.read_csv(E.DATEN / "welt.csv").fillna("")
        welt_isin = dict(zip(w["symbol"], w["isin"]))
    except Exception:
        pass
    # Wikidata: US-Börsennotierungen (Nasdaq, NYSE) mit Kürzel
    # je Kürzel alle Wikidata-Einträge getrennt sammeln (ein Kürzel kann früher einer anderen Firma gehört haben)
    items = collections.defaultdict(dict)
    neu_e = lambda: {"isin": set(), "beschr": None, "land": None, "wp": None, "label": None}
    for b in sparql('''SELECT ?ticker ?item ?isin ?beschr ?landLabel ?wp ?itemLabel WHERE {
        VALUES ?boerse { wd:Q82059 wd:Q13677 } ?item p:P414 ?st . ?st ps:P414 ?boerse ; pq:P249 ?ticker .
        FILTER NOT EXISTS { ?st pq:P582 ?ende } OPTIONAL { ?item wdt:P946 ?isin }
        OPTIONAL { ?item schema:description ?beschr FILTER(LANG(?beschr) = "de") } OPTIONAL { ?item wdt:P17 ?land }
        OPTIONAL { ?art schema:about ?item ; schema:isPartOf <https://de.wikipedia.org/> ; schema:name ?wp }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "de". } }'''):
        e = items[b["ticker"].upper()].setdefault(b["item"], neu_e())
        if b.get("isin"): e["isin"].add(b["isin"])
        e["beschr"] = e["beschr"] or b.get("beschr"); e["land"] = e["land"] or b.get("landLabel"); e["wp"] = e["wp"] or b.get("wp")
        e["label"] = e["label"] or b.get("itemLabel")
    for b in sparql('''SELECT ?ticker ?item (GROUP_CONCAT(DISTINCT ?bl; separator="|") AS ?branchen) WHERE {
        VALUES ?boerse { wd:Q82059 wd:Q13677 } ?item p:P414 ?st . ?st ps:P414 ?boerse ; pq:P249 ?ticker .
        FILTER NOT EXISTS { ?st pq:P582 ?ende } ?item wdt:P452 ?br . ?br rdfs:label ?bl FILTER(LANG(?bl) = "de") } GROUP BY ?ticker ?item'''):
        items[b["ticker"].upper()].setdefault(b["item"], neu_e())["branchen_wd"] = [x for x in (b.get("branchen") or "").split("|") if x]
    # ohne deutsche Kurzbeschreibung: Branche (P452), Land, Gründungsjahr aus Wikidata für einen Ersatzsatz
    for b in sparql('''SELECT ?ticker ?item (GROUP_CONCAT(DISTINCT ?bl; separator="|") AS ?branchen) (SAMPLE(?ll) AS ?land) (MIN(YEAR(?gr)) AS ?jahr) WHERE {
        VALUES ?boerse { wd:Q82059 wd:Q13677 } ?item p:P414 ?st . ?st ps:P414 ?boerse ; pq:P249 ?ticker .
        FILTER NOT EXISTS { ?st pq:P582 ?ende } FILTER NOT EXISTS { ?item schema:description ?d FILTER(LANG(?d) = "de") }
        OPTIONAL { ?item wdt:P452 ?br . ?br rdfs:label ?bl FILTER(LANG(?bl) = "de") }
        OPTIONAL { ?item wdt:P17 ?l . ?l rdfs:label ?ll FILTER(LANG(?ll) = "de") }
        OPTIONAL { ?item wdt:P571 ?gr } } GROUP BY ?ticker ?item'''):
        e = items[b["ticker"].upper()].setdefault(b["item"], neu_e())
        if e["beschr"]:
            continue
        teile = [x for x in (b.get("branchen") or "").split("|") if x][:2]
        if teile or b.get("land"):
            e["ersatz"] = ("Unternehmen" + (f" aus {LAND.get(b['land'], b['land'])}" if b.get("land") else "") + (f", Branche: {' / '.join(teile)}" if teile else "")
                           + (f", gegründet {b['jahr']}" if b.get("jahr") else "") + ".")
    print(f"Wikidata USA: {len(items)} Kürzel")
    # passenden Eintrag je Wert der Liste wählen: der Name muss zur Firma passen
    us, verworfen = {}, []
    for s_, n_, g_ in zip(uni["symbol"].astype(str), uni["name"].astype(str), uni["gruppe"].astype(str)):
        if g_ not in ("Nasdaq", "NYSE") or s_.upper() not in items:
            continue
        kand = list(items[s_.upper()].values())
        passend = [e for e in kand if name_passt(n_, e.get("label"))]
        if passend:
            us[s_.upper()] = passend[0]
        else:
            verworfen.append(f"{s_}: {n_} ≠ {', '.join(str(e.get('label')) for e in kand)}")
    # Wikidata: Auslandsaktien per ISIN
    welt = {}
    isins = sorted(set(v for v in welt_isin.values() if v))
    for i in range(0, len(isins), 200):
        werte = " ".join(f'"{x}"' for x in isins[i:i + 200])
        for b in sparql(f'''SELECT ?isin ?beschr ?landLabel ?wp (GROUP_CONCAT(DISTINCT ?bl; separator="|") AS ?branchen) WHERE {{
            VALUES ?isin {{ {werte} }} ?item wdt:P946 ?isin .
            OPTIONAL {{ ?item schema:description ?beschr FILTER(LANG(?beschr) = "de") }} OPTIONAL {{ ?item wdt:P17 ?land }}
            OPTIONAL {{ ?art schema:about ?item ; schema:isPartOf <https://de.wikipedia.org/> ; schema:name ?wp }}
            OPTIONAL {{ ?item wdt:P452 ?br . ?br rdfs:label ?bl FILTER(LANG(?bl) = "de") }}
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de". }} }} GROUP BY ?isin ?beschr ?landLabel ?wp'''):
            welt.setdefault(b["isin"], b)
        time.sleep(1)
    print(f"Wikidata Ausland: {len(welt)} ISINs")
    # Wikipedia: erster Satz der Einleitung (nur Werte der Liste)
    us_sym = {str(s).upper() for s, g in zip(uni["symbol"], uni["gruppe"]) if g in ("Nasdaq", "NYSE")}
    titel = [e.get("wp") for s, e in us.items() if s in us_sym] + [b.get("wp") for b in welt.values()]
    wp, wp_offen = wp_saetze(titel)
    print(f"Wikipedia: {len(wp)} von {len(set(x for x in titel if x))} Artikeln mit erstem Satz"
          + (f", {wp_offen} folgen im nächsten Lauf" if wp_offen else ""))
    try:
        import fundamente
        sec = fundamente.stammdaten()   # Branchencode und Sitz laut SEC (US-gelistete Firmen)
    except Exception as ex:
        print(f"SEC-Stammdaten nicht lesbar: {ex.__class__.__name__}: {ex}", file=sys.stderr)
        sec = {}
    wp_url = lambda titel_: "https://de.wikipedia.org/wiki/" + requests.utils.quote(titel_.replace(" ", "_"))
    krypto_rang = {k["id"]: k for k in E.KRYPTO if k.get("rang")}
    out = {}
    for z in uni.to_dict("records"):
        wid, sym, g = z["id"], z["symbol"], z["gruppe"]
        e = {"isin": None, "geprueft": False, "wkn": None, "text": None, "text_quelle": None, "text_url": None, "branche": None, "sitz": None}
        if wid in FEST_ISIN:
            e["isin"], e["wkn"] = FEST_ISIN[wid]; e["geprueft"] = True
        elif g in ("ETF", "Rohstoffe") and "=" not in sym and cusip.get(wid):   # Futures (GC=F …) haben keine ISIN
            e["isin"] = next((x for x in cusip[wid] if x.startswith("US")), None)   # US-Fonds: US-ISIN aus der CUSIP
            e["geprueft"] = bool(e["isin"])
        elif g in ("Nasdaq", "NYSE"):
            wd = us.get(sym.upper())   # nur ein Eintrag, dessen Name zur Firma passt (sonst keiner)
            kand = cusip.get(wid, [])
            treffer = [x for x in kand if wd and x in wd["isin"]]
            kanada = bool(wd and wd["land"] == "Kanada")
            if treffer:
                e["isin"] = next((x for x in treffer if x.startswith("CA" if kanada else "US")), treffer[0]); e["geprueft"] = True
            elif kand:
                e["isin"] = next((x for x in kand if x.startswith("CA" if kanada else "US")), kand[0])
            boerse = "Nasdaq" if g == "Nasdaq" else "New Yorker Börse (NYSE)"
            e["text"] = satz(wd["beschr"] if wd else None, wd["land"] if wd else None,
                             (wd.get("ersatz") if wd else None) or f"Aktie, gehandelt an der {boerse}{(', Branche ' + z['branche']) if z.get('branche') else ''}. Eine Kurzbeschreibung liegt für diesen Wert noch nicht vor.")
            if wd and wd.get("beschr"):
                e["text_quelle"] = "Wikidata"
            if wd and wp.get(wd.get("wp")):
                e["text"], e["text_quelle"], e["text_url"] = wp[wd["wp"]], "Wikipedia (CC BY-SA 4.0)", wp_url(wd["wp"])
            s_ = sec.get(sym.upper().replace(".", "-")) or {}
            e["branche"] = s_.get("branche") or ((wd or {}).get("branchen_wd") or [None])[0]
            e["sitz"] = s_.get("sitz") or LAND_KURZ.get((wd or {}).get("land"), (wd or {}).get("land"))   # SEC-Geschäftsadresse vor Wikidata
        elif g == "Welt":
            e["isin"] = welt_isin.get(sym) or None; e["geprueft"] = bool(e["isin"])
            b = welt.get(e["isin"] or "", {})
            e["text"] = satz(b.get("beschr"), b.get("landLabel"), "Aktie an ihrer Heimatbörse außerhalb der USA. Eine Kurzbeschreibung liegt für diesen Wert noch nicht vor.")
            if b.get("beschr"):
                e["text_quelle"] = "Wikidata"
            if wp.get(b.get("wp")):
                e["text"], e["text_quelle"], e["text_url"] = wp[b["wp"]], "Wikipedia (CC BY-SA 4.0)", wp_url(b["wp"])
            e["branche"] = ([x for x in (b.get("branchen") or "").split("|") if x] or [None])[0]
            e["sitz"] = LAND_KURZ.get(b.get("landLabel"), b.get("landLabel"))
        if wid in TEXTE:
            e["text"], e["text_quelle"], e["text_url"] = TEXTE[wid], None, None
        elif g == "Krypto" and krypto_rang.get(wid):   # Top-200-Liste (24.11.2026): kein eigener Text – nur, was die Liste sicher sagt
            k = krypto_rang[wid]
            e["text"] = (f"Kryptowert, am {'.'.join(reversed(k['stand'].split('-')))} auf Rang {k['rang']} nach Marktwert "
                         "(Rangliste: CoinGecko). Eine Kurzbeschreibung liegt für diesen Wert noch nicht vor.")
        e["wkn"] = e["wkn"] or wkn_aus(e["isin"])
        if any(e.values()):
            out[wid] = e
    ZIEL.write_text(json.dumps({**out, "_version": VERSION}, ensure_ascii=False, separators=(",", ":")))
    offen_datei.write_text(str(wp_offen))
    n_t = sum(1 for e in out.values() if e["text"] and "noch nicht vor" not in e["text"])
    print(f"Wikidata-Treffer verworfen, weil der Name nicht passt: {len(verworfen)} (z. B. {'; '.join(verworfen[:5])})")
    print(f"Wikipedia-Satz: {sum(1 for e in out.values() if e.get('text_url'))}, Branche: {sum(1 for e in out.values() if e.get('branche'))}, "
          f"Sitz: {sum(1 for e in out.values() if e.get('sitz'))}")
    print(f"Beschreibungen: {len(out)} Werte, {n_t} mit Kurzbeschreibung, {sum(1 for e in out.values() if e['isin'])} mit ISIN "
          f"({sum(1 for e in out.values() if e['geprueft'])} geprüft), {sum(1 for e in out.values() if e['wkn'])} mit WKN")


if __name__ == "__main__":
    main()
