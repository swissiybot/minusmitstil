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
  - WKN: nur, wenn sie sich sicher ableiten lässt (deutsche ISIN: DE000 + WKN + Prüfziffer) oder fest bekannt ist.
    Für US-Aktien gibt es keine freie WKN-Quelle – dann bleibt sie leer (nicht raten).
Speicher: daten/beschreibung.json (höchstens einmal pro Woche neu, sonst bleibt die letzte Datei).
Aufruf: python beschreibung.py
"""
import json
import sys
import time
import collections
import pandas as pd
import requests

import einstellungen as E

ZIEL = E.DATEN / "beschreibung.json"
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


def satz(beschr: str | None, land: str | None, fallback: str) -> str:
    if beschr:
        t = beschr.strip()
        t = t[0].upper() + t[1:]
        if land and land.lower()[:5] not in t.lower() and "amerikan" not in t.lower():
            t += f", Sitz: {LAND_KURZ.get(land, land)}"
        return t.rstrip(".") + "."
    return fallback


def main():
    if ZIEL.exists() and time.time() - ZIEL.stat().st_mtime < 7 * 86400 and "--neu" not in sys.argv:
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
    us = collections.defaultdict(lambda: {"isin": set(), "beschr": None, "land": None})
    for b in sparql('''SELECT ?ticker ?isin ?beschr ?landLabel WHERE {
        VALUES ?boerse { wd:Q82059 wd:Q13677 } ?item p:P414 ?st . ?st ps:P414 ?boerse ; pq:P249 ?ticker .
        FILTER NOT EXISTS { ?st pq:P582 ?ende } OPTIONAL { ?item wdt:P946 ?isin }
        OPTIONAL { ?item schema:description ?beschr FILTER(LANG(?beschr) = "de") } OPTIONAL { ?item wdt:P17 ?land }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "de". } }'''):
        e = us[b["ticker"].upper()]
        if b.get("isin"): e["isin"].add(b["isin"])
        e["beschr"] = e["beschr"] or b.get("beschr"); e["land"] = e["land"] or b.get("landLabel")
    # ohne deutsche Kurzbeschreibung: Branche (P452), Land, Gründungsjahr aus Wikidata für einen Ersatzsatz
    for b in sparql('''SELECT ?ticker (GROUP_CONCAT(DISTINCT ?bl; separator="|") AS ?branchen) (SAMPLE(?ll) AS ?land) (MIN(YEAR(?gr)) AS ?jahr) WHERE {
        VALUES ?boerse { wd:Q82059 wd:Q13677 } ?item p:P414 ?st . ?st ps:P414 ?boerse ; pq:P249 ?ticker .
        FILTER NOT EXISTS { ?st pq:P582 ?ende } FILTER NOT EXISTS { ?item schema:description ?d FILTER(LANG(?d) = "de") }
        OPTIONAL { ?item wdt:P452 ?br . ?br rdfs:label ?bl FILTER(LANG(?bl) = "de") }
        OPTIONAL { ?item wdt:P17 ?l . ?l rdfs:label ?ll FILTER(LANG(?ll) = "de") }
        OPTIONAL { ?item wdt:P571 ?gr } } GROUP BY ?ticker'''):
        e = us[b["ticker"].upper()]
        if e["beschr"]:
            continue
        teile = [x for x in (b.get("branchen") or "").split("|") if x][:2]
        if teile or b.get("land"):
            e["ersatz"] = ("Unternehmen" + (f" aus {LAND.get(b['land'], b['land'])}" if b.get("land") else "") + (f", Branche: {' / '.join(teile)}" if teile else "")
                           + (f", gegründet {b['jahr']}" if b.get("jahr") else "") + ".")
    print(f"Wikidata USA: {len(us)} Kürzel")
    # Wikidata: Auslandsaktien per ISIN
    welt = {}
    isins = sorted(set(v for v in welt_isin.values() if v))
    for i in range(0, len(isins), 200):
        werte = " ".join(f'"{x}"' for x in isins[i:i + 200])
        for b in sparql(f'''SELECT ?isin ?beschr ?landLabel WHERE {{ VALUES ?isin {{ {werte} }} ?item wdt:P946 ?isin .
            OPTIONAL {{ ?item schema:description ?beschr FILTER(LANG(?beschr) = "de") }} OPTIONAL {{ ?item wdt:P17 ?land }}
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de". }} }}'''):
            welt.setdefault(b["isin"], b)
        time.sleep(1)
    print(f"Wikidata Ausland: {len(welt)} ISINs")
    out = {}
    for z in uni.to_dict("records"):
        wid, sym, g = z["id"], z["symbol"], z["gruppe"]
        e = {"isin": None, "geprueft": False, "wkn": None, "text": None}
        if wid in FEST_ISIN:
            e["isin"], e["wkn"] = FEST_ISIN[wid]; e["geprueft"] = True
        elif g in ("ETF", "Rohstoffe") and "=" not in sym and cusip.get(wid):   # Futures (GC=F …) haben keine ISIN
            e["isin"] = next((x for x in cusip[wid] if x.startswith("US")), None)   # US-Fonds: US-ISIN aus der CUSIP
            e["geprueft"] = bool(e["isin"])
        elif g in ("Nasdaq", "NYSE"):
            wd = us.get(sym.upper())
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
        elif g == "Welt":
            e["isin"] = welt_isin.get(sym) or None; e["geprueft"] = bool(e["isin"])
            b = welt.get(e["isin"] or "", {})
            e["text"] = satz(b.get("beschr"), b.get("landLabel"), "Aktie an ihrer Heimatbörse außerhalb der USA. Eine Kurzbeschreibung liegt für diesen Wert noch nicht vor.")
        if wid in TEXTE:
            e["text"] = TEXTE[wid]
        e["wkn"] = e["wkn"] or wkn_aus(e["isin"])
        if any(e.values()):
            out[wid] = e
    ZIEL.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    n_t = sum(1 for e in out.values() if e["text"] and "noch nicht vor" not in e["text"])
    print(f"Beschreibungen: {len(out)} Werte, {n_t} mit Kurzbeschreibung, {sum(1 for e in out.values() if e['isin'])} mit ISIN "
          f"({sum(1 for e in out.values() if e['geprueft'])} geprüft), {sum(1 for e in out.values() if e['wkn'])} mit WKN")


if __name__ == "__main__":
    main()
