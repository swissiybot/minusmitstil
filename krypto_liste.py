"""Baut die feste Krypto-Liste: die 200 größten Kryptowerte nach Marktwert, jeder mit geprüftem Yahoo-Kürzel.

Wird VON HAND gestartet (etwa einmal im Quartal), NIE im Online-Lauf. Ergebnis (beide eingecheckt):
    listen/krypto.csv              rang, id, symbol, name, coingecko_id, yahoo_name, kurse_seit, stand
    listen/krypto_weggelassen.csv  rang, name, kuerzel, coingecko_id, grund, stand
einstellungen.py liest listen/krypto.csv; universum.py macht daraus die Gruppe „Krypto“.

Warum eine feste, eingecheckte Liste und keine automatische Erneuerung je Lauf:
  - An der Kennung (id) hängen Signal-Tagebuch, Alarme, gemerkte Werte und Depots im Browser. Eine Rangliste, die sich
    täglich an den Rändern ändert, würde Werte kommen und gehen lassen.
  - Das Yahoo-Kürzel muss je Münze GEPRÜFT sein (siehe unten). Das soll ein Mensch nachlesen können (git diff), statt
    dass ein nächtlicher Lauf still ein anderes Kürzel wählt.
  - Der Online-Lauf hängt so von keinem weiteren fremden Dienst ab (die öffentliche CoinGecko-Schnittstelle drosselt stark).
  - Jede neue Münze kostet einmal eine volle Kurshistorie bei Yahoo; das soll nicht unbemerkt passieren.

Quelle der Rangliste: CoinGecko, öffentliche Marktliste (https://api.coingecko.com/api/v3/coins/markets), sortiert nach
Marktwert. Frei abrufbar ohne Schlüssel und ohne Anmeldung; die Anfragen enthalten keine persönlichen Angaben und einen
neutralen User-Agent. Gewählt, weil die Liste offen ist, Kategorien mitliefert (Stablecoin, verpackt, gestakt) und je
Münze Kurs, 30-Tage- und 1-Jahres-Veränderung nennt – genau das braucht die Kürzel-Prüfung. Kurse fürs Tool kommen
weiter nur von Yahoo; von CoinGecko stammen nur Rang, Name und die Vergleichszahlen der Prüfung.

Ausgeschlossen (steht mit Grund in krypto_weggelassen.csv):
  - Stablecoins (an Dollar, Euro … gebunden) – eine Ampel „günstig/teuer“ ergibt bei festem Kurs keinen Sinn
  - verpackte, gebrückte und gestakte Münzen (WBTC, stETH, cbBTC …) – das wäre dieselbe Münze ein zweites Mal
  - an Gold, Anleihen, Aktien oder Fonds gebundene Token (PAXG, BUIDL …) – kein eigener Kryptowert
  Grundlage sind die CoinGecko-Kategorien in AUSSCHLUSS, dazu Namensmuster (Wrapped, Staked, Bridged …) als zweites Netz.

Prüfung des Yahoo-Kürzels (Yahoo bezieht Kryptokurse von CoinMarketCap; viele Münzen heißen dort XYZ-USD, bei doppelt
vergebenen Kürzeln trägt das Kürzel eine Nummer, z. B. UNI7083-USD – und XYZ-USD gehört dann einer ANDEREN Münze):
  Kandidaten sind XYZ-USD und die Kryptowerte aus dem Yahoo-Verzeichnis zu Kürzel und Name. Ein Kandidat gilt nur, wenn
    1. der letzte Yahoo-Kurs höchstens KURS_TOL vom CoinGecko-Kurs abweicht,
    2. die Veränderung über 30 Tage zu CoinGecko passt (und über 1 Jahr, wenn beide sie haben),
    3. der letzte Kurs höchstens MAX_ALT_TAGE alt ist (alte Kürzel umbenannter Münzen fallen so heraus),
    4. die GANZE Yahoo-Reihe zur Münze passt: Höchst- und Tiefstkurs liegen nicht weit außerhalb von Allzeithoch und
       -tief laut CoinGecko, die Reihe ist nicht älter als die Münze und hat keinen Wochensprung über das 30-Fache.
       Yahoo vergibt frei gewordene Kürzel neu – dann hängt vorn die Geschichte einer ANDEREN Münze (gesehen 24.11.2026:
       MON-USD = früher „PocMon“, heute Monad; GRAM-USD mit Sprung um das 1.300-Fache). Solche Reihen sind unbrauchbar,
    5. Yahoo die Münze nicht als verpackt/gebrückt/gestakt/IOU führt (POL40910-USD = „Bridged Polygon“ hat denselben Kurs),
    6. die Kurse fein genug sind: Yahoo rundet Krypto-Tageskurse auf sechs Nachkommastellen. Bei Münzen unter etwa
       0,0001 $ (Shiba Inu, Pepe, Bonk …) bleibt eine Treppe aus ein, zwei Ziffern – daraus lässt sich keine Ampel rechnen.
  Kurs UND Kursverlauf zweier verschiedener Münzen stimmen nicht zufällig überein – so ist eine Verwechslung
  ausgeschlossen, auch wenn Yahoo die Münze anders schreibt (dann steht „Name bei Yahoo anders“ in der Ausgabe; der
  Yahoo-Name steht zum Nachlesen in der Liste). Passt kein Kandidat, wird die Münze weggelassen und aufgelistet
  (nichts geraten); passen mehrere, gilt der mit passendem Namen und der längsten Geschichte.

Kennung (id): „KÜRZEL-USD“. Sie kann nicht mit einem Aktienkürzel kollidieren (Aktien tragen kein „-USD“; der Kommentar
bei LINK in einstellungen.py). Bitcoin bleibt „BTC“, die bisherigen vier behalten ihre Kennung ohnehin. Tragen zwei
Münzen der Liste dasselbe Kürzel, bekommt die kleinere das volle Yahoo-Kürzel als Kennung.

Aufruf:  python krypto_liste.py            Liste neu bauen (dauert etwa 20–30 Minuten, gedrosselt)
         python krypto_liste.py --weiter   wie oben, aber Abrufe der letzten 6 Stunden wiederverwenden (nach einem Abbruch)
         python krypto_liste.py --pruefen  nur die vorhandene Liste gegen Yahoo prüfen (Kurse da, Name), nichts schreiben
"""
import csv
import datetime as dt
import difflib
import json
import re
import sys
import time

from curl_cffi import requests   # wie yfinance; das gewöhnliche requests hängt hier minutenlang an IPv6-Adressen von CoinGecko

import einstellungen as E

ANZAHL = 200
ORDNER = E.BASIS / "listen"
DATEI = ORDNER / "krypto.csv"
DATEI_WEG = ORDNER / "krypto_weggelassen.csv"
ROH = E.DATEN / "krypto_roh"          # Zwischenspeicher der Abrufe (nicht im Repo), nur für diesen einen Bau
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)", "Accept": "application/json"}   # neutral, keine Kontaktangabe
CG = "https://api.coingecko.com/api/v3/coins/markets"
CG_PAUSE = 7.0                         # Sekunden zwischen CoinGecko-Abrufen (öffentliche Schnittstelle drosselt)
YAHOO_PAUSE = 0.4
KURS_TOL = 0.03                        # Yahoo-Kurs höchstens 3 % neben CoinGecko
V30_TOL, V1J_TOL = 0.15, 0.25          # Verhältnis der Veränderungen (1 + Yahoo) / (1 + CoinGecko) höchstens so weit von 1
MAX_ALT_TAGE = 3
HIST_TOL = 2.0                         # Yahoo-Höchstkurs höchstens das 2-Fache des Allzeithochs laut CoinGecko (Tiefstkurs entsprechend);
                                       # gemessen am 0,5-%-Rand der Reihe, damit einzelne Fehlkurse (Bittensor: 1. Tag 0,13 $) nicht stören.
                                       # Nicht enger: Yahoos Reihe (CoinMarketCap) beginnt manchmal früher als die Aufzeichnung bei CoinGecko.
WEITER = "--weiter" in sys.argv[1:]    # Abrufe der letzten 6 Stunden wiederverwenden
MAX_WOCHENSPRUNG = 30.0                # größerer Sprung von Woche zu Woche = zwei Münzen unter einem Kürzel
MIN_FEINHEIT = 0.6                     # Anteil verschiedener Tageskurse im letzten Jahr; darunter ist die Reihe zu grob gerundet
MIN_KURS = 5e-5                        # tiefste Kurse der Reihe (1 %-Quantil): darunter rundet Yahoo zu grob (6 Nachkommastellen)
VERPACKT_YAHOO = re.compile(r"\b(bridged|wrapped|staked|restaked|iou|derivatives|tokenized)\b", re.I)

# CoinGecko-Kategorie -> Grund in Laiensprache
AUSSCHLUSS = {
    "stablecoins": "Stablecoin (an eine Währung gebunden)",
    "yield-bearing-stablecoins": "Stablecoin mit Zinsen",
    "synthetic-dollar": "Stablecoin (künstlicher Dollar)",
    "wrapped-tokens": "verpackte Münze (gibt es schon als Original)",
    "bridged-tokens": "gebrückte Münze (gibt es schon als Original)",
    "binance-peg-tokens": "verpackte Münze (Binance-Peg)",
    "tokenized-btc": "verpackter Bitcoin",
    "asset-backed-tokens": "verpackte Münze (durch eine andere Münze gedeckt)",
    "liquid-staking-tokens": "gestakte Münze (gibt es schon als Original)",
    "liquid-restaking-tokens": "gestakte Münze (Restaking)",
    "tokenized-gold": "an Gold gebunden (kein eigener Kryptowert)",
    "tokenized-commodities": "an einen Rohstoff gebunden (kein eigener Kryptowert)",
    "tokenized-treasuries": "an Staatsanleihen gebunden (kein eigener Kryptowert)",
    "tokenized-t-bills": "an Staatsanleihen gebunden (kein eigener Kryptowert)",
    "tokenized-money-market-fund-mmfs": "Geldmarktfonds als Token (kein eigener Kryptowert)",
    "tokenized-stock": "Aktie als Token (kein eigener Kryptowert)",
    "tokenized-exchange-traded-funds-etfs": "ETF als Token (kein eigener Kryptowert)",
    "tokenized-private-credit": "Kredit als Token (kein eigener Kryptowert)",
    "tokenized-products": "an einen anderen Wert gebunden (Tokenized Asset)",
    "yield-bearing-tokens": "Zins-Token auf eine andere Münze",
}
NAMENSMUSTER = re.compile(r"\b(wrapped|bridged|staked|restaked|staking|binance-peg|tokenized|usd[a-z0-9]?|dollar|eur[a-z]?|stablecoin|"
                          r"vault|receipt|treasury|t-bill|money market|fund|securitize|midas)\b", re.I)
BEHALTEN = {"BTC": "BTC"}              # Kürzel -> feste Kennung (Bitcoin heißt im Tool seit jeher BTC)


def _json(datei, url, params, frisch=False):
    """Abruf mit Zwischenspeicher je Datei (ein Bau = ein Stand)."""
    ROH.mkdir(parents=True, exist_ok=True)
    f = ROH / datei
    if f.exists() and time.time() - f.stat().st_mtime < (6 * 3600 if frisch else 86400) and (WEITER or not frisch):
        return json.loads(f.read_text())
    for versuch in range(5):
        r = requests.get(url, params=params, headers=UA, timeout=60)
        if r.status_code == 200:
            f.write_text(r.text)
            time.sleep(CG_PAUSE)
            return r.json()
        time.sleep(30 * (versuch + 1))   # 429 = gedrosselt: warten
    raise SystemExit(f"CoinGecko nicht erreichbar ({url}, Status {r.status_code})")


def rangliste(frisch=True) -> list[dict]:
    """Die 500 größten nach Marktwert (2 Seiten), mit 30-Tage- und 1-Jahres-Veränderung."""
    aus = []
    for seite in (1, 2):
        aus += _json(f"markt_{seite}.json", CG, {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": seite,
                                                 "price_change_percentage": "30d,1y"}, frisch)
    return [m for m in aus if m.get("market_cap")]


def ausschluss_ids(frisch=False) -> dict[str, str]:
    """coingecko_id -> Grund, aus den Kategorien in AUSSCHLUSS (je Kategorie die 250 größten – reicht weit unter Rang 500)."""
    aus = {}
    for kat, grund in AUSSCHLUSS.items():
        for m in _json(f"kat_{kat}.json", CG, {"vs_currency": "usd", "category": kat, "order": "market_cap_desc", "per_page": 250, "page": 1}, frisch):
            aus.setdefault(m["id"], grund)
    return aus


STOPP = {"usd", "token", "coin", "network", "protocol", "finance", "dao", "the", "official", "new", "prev", "ex", "chain", "classic"}


def _woerter(s: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", str(s).lower()) if len(w) >= 3 and w not in STOPP}


def _norm(s: str) -> str:
    return "".join(w for w in re.split(r"[^a-z0-9]+", re.sub(r"\(.*?\)|\[.*?\]", " ", str(s).lower())) if w and w not in STOPP)


def name_aehnlich(a: str, b: str) -> bool:
    """Gleicher Name (ohne Füllwörter), ein gemeinsames tragendes Wort (auch aus Klammern: „POL (ex-MATIC)“ und
    „Polygon (prev. MATIC)“) oder fast gleiche Schreibweise."""
    x, y = _norm(a), _norm(b)
    if not x or not y:
        return False
    if x == y or (min(len(x), len(y)) >= 4 and (x in y or y in x)):
        return True
    return bool(_woerter(a) & _woerter(b)) or difflib.SequenceMatcher(None, x, y).ratio() >= 0.8


def yahoo_reihe(symbol: str):
    """Tagesschlusskurse und Name laut Yahoo (oder None). Merkt sich den Abruf auf Platte (für --weiter)."""
    import pandas as pd
    f = ROH / "yahoo" / f"{symbol}.json"
    if WEITER and f.exists() and time.time() - f.stat().st_mtime < 6 * 3600:
        d = json.loads(f.read_text())
        return (pd.Series(d["c"], index=pd.to_datetime(d["t"]), dtype="float64"), d["name"]) if d else None
    import yfinance as yf
    t = yf.Ticker(symbol)
    try:
        h = t.history(period="max", interval="1d", auto_adjust=True)
    except Exception:
        h = None
    time.sleep(YAHOO_PAUSE)
    f.parent.mkdir(parents=True, exist_ok=True)
    c = None
    if h is not None and not h.empty:
        c = h["Close"].dropna()
        c = c[c > 0]
        c.index = c.index.tz_localize(None).normalize()
    if c is None or len(c) < 2:
        f.write_text("null")
        return None
    try:
        meta = t.get_history_metadata() or {}
    except Exception:
        meta = {}
    name = re.sub(r"\s+USD$", "", str(meta.get("longName") or meta.get("shortName") or ""))
    f.write_text(json.dumps({"t": [d.strftime("%Y-%m-%d") for d in c.index], "c": [float(x) for x in c.values], "name": name}))
    return c, name


def yahoo_stand(symbol: str) -> dict | None:
    """Letzter Kurs, Veränderung 30 Tage / 1 Jahr, erster Kurstag, Name und Kennzahlen der ganzen Reihe – oder None ohne Kurse."""
    r = yahoo_reihe(symbol)
    if r is None:
        return None
    c, name = r
    def seit(tage):
        t0 = c.index[-1] - dt.timedelta(days=tage)
        return None if t0 < c.index[0] else float(c.iloc[-1] / c.asof(t0) - 1)
    wo = c.resample("W")
    w = wo.median()[wo.count() >= 4].dropna()   # Wochenmitte aus vollen Wochen: ein einzelner Fehlkurs (Bittensor, 1. Tag) zählt nicht als Sprung
    q = (w / w.shift(1)).dropna()
    jahr = c[c.index >= c.index[-1] - dt.timedelta(days=365)].iloc[:-1]   # ohne den laufenden Tag (der ist ungerundet)
    return {"symbol": symbol, "kurs": float(c.iloc[-1]), "datum": c.index[-1].date(), "seit": c.index[0].date(),
            "v30": seit(30), "v1j": seit(365), "name": name, "tage": int((c.index[-1] - c.index[0]).days),
            "hoch": float(c.quantile(0.995)), "tief": float(c.quantile(0.005)), "tief_q1": float(c.quantile(0.01)),
            "sprung": float(max(q.max(), 1 / q.min())) if len(q) else 1.0,
            "feinheit": float(jahr.nunique() / len(jahr)) if len(jahr) >= 30 else 1.0}


def yahoo_suche(text: str) -> list[tuple[str, str]]:
    """Krypto-Kürzel (…-USD) samt Yahoo-Namen aus dem Yahoo-Verzeichnis, nur Kryptowerte. Findet auch die Kürzel mit
    Nummer (MNT27075-USD), die die allgemeine Suche oft nicht zeigt."""
    import yfinance as yf
    try:
        df = yf.Lookup(text).get_cryptocurrency(count=40)
    except Exception:
        return []
    time.sleep(YAHOO_PAUSE)
    return [(str(i), str(z.get("shortName") or "")) for i, z in df.iterrows() if str(i).endswith("-USD")]


def passt(m: dict, y: dict, heute: dt.date) -> tuple[bool, str]:
    """Gehört das Yahoo-Kürzel zu dieser CoinGecko-Münze? (Regeln siehe Kopf)"""
    if (heute - y["datum"]).days > MAX_ALT_TAGE:
        return False, f"letzter Kurs {y['datum']} (veraltet)"
    if abs(y["kurs"] / m["current_price"] - 1) > KURS_TOL:
        return False, f"Kurs {y['kurs']:.6g} statt {m['current_price']:.6g}"
    for feld, yk, tol, text in (("price_change_percentage_30d_in_currency", "v30", V30_TOL, "30 Tage"),
                                ("price_change_percentage_1y_in_currency", "v1j", V1J_TOL, "1 Jahr")):
        cg = m.get(feld)
        if cg is None or y[yk] is None:
            if text == "30 Tage" and y["tage"] >= 35 and cg is not None:
                return False, "30-Tage-Vergleich fehlt"
            continue
        if abs((1 + y[yk]) / (1 + cg / 100) - 1) > tol:
            return False, f"Veränderung {text} {y[yk] * 100:.0f} % statt {cg:.0f} %"
    if VERPACKT_YAHOO.search(y["name"]) and not VERPACKT_YAHOO.search(m["name"]):
        return False, f"Yahoo führt das Kürzel als „{y['name']}“ (verpackt/gebrückt/IOU)"
    if m.get("price_change_percentage_1y_in_currency") is None and y["tage"] > 400:
        return False, f"Yahoo-Reihe (seit {y['seit']}) ist älter als die Münze – vorn hängt eine andere Münze gleichen Kürzels"
    ath, atl = m.get("ath"), m.get("atl")
    if (ath and y["hoch"] > ath * HIST_TOL) or (atl and y["tief"] < atl / HIST_TOL):
        return False, (f"Yahoo-Reihe passt nicht zur Geschichte der Münze (Yahoo {y['tief']:.3g}–{y['hoch']:.3g}, CoinGecko {atl:.3g}–{ath:.3g}) "
                       "– vermutlich mit einer anderen Münze gleichen Kürzels vermischt")
    if y["sprung"] > MAX_WOCHENSPRUNG:
        return False, f"Yahoo-Reihe mit Wochensprung um das {y['sprung']:.0f}-Fache (zwei Münzen unter einem Kürzel?)"
    if y["feinheit"] < MIN_FEINHEIT or y["tief_q1"] < MIN_KURS:
        return False, "Kurse bei Yahoo zu grob gerundet (sechs Nachkommastellen bei einem Kurs unter etwa 0,0001 $) – keine Ampel möglich"
    return True, ""


def zuordnen(m: dict, heute: dt.date, cache: dict) -> tuple[dict | None, str]:
    """Sucht das eine Yahoo-Kürzel, das nachweislich zu der Münze gehört. Rückgabe (Yahoo-Stand oder None, Grund)."""
    kuerzel = m["symbol"].upper()
    def pruefe(kandidaten):
        treffer, gruende = [], []
        for k in kandidaten:
            if k not in cache:
                cache[k] = yahoo_stand(k)
            y = cache[k]
            if y is None:
                gruende.append(f"{k}: keine Kurse")
                continue
            ok, grund = passt(m, y, heute)
            (treffer if ok else gruende).append(y if ok else f"{k}: {grund}")
        return treffer, gruende
    direkt = [f"{kuerzel}-USD"] if re.fullmatch(r"[A-Z0-9]+", kuerzel) else []
    treffer, gruende = pruefe(direkt)
    if not treffer:   # Kürzel bei Yahoo anders (Nummer!) oder an eine andere Münze vergeben: Yahoo-Verzeichnis nach Kürzel und Name
        begriffe = [kuerzel, m["name"], re.sub(r"\(.*?\)", " ", m["name"]).strip()]
        begriffe += [re.sub(r"^(ex|prev\.?|formerly)[\s-]+", "", x.strip(), flags=re.I) for x in re.findall(r"\((.*?)\)", m["name"])]   # „(ex-MATIC)“
        funde = {}
        for b in dict.fromkeys(x for x in begriffe if x):
            if "?" + b not in cache:
                cache["?" + b] = yahoo_suche(b)
            funde.update({k: n for k, n in cache["?" + b]})
        muster = re.compile(re.escape(kuerzel) + r"\d*-USD")   # übliche Yahoo-Form: Kürzel + Nummer
        gesucht = [k for k in funde if muster.fullmatch(k)] + [k for k, n in funde.items() if not muster.fullmatch(k) and name_aehnlich(m["name"], n)]
        t2, g2 = pruefe([k for k in gesucht if k not in direkt][:10])
        treffer, gruende = t2, gruende + g2
    if len(treffer) > 1:   # dieselbe Münze unter mehreren Kürzeln: passender Name zuerst, dann die längste Geschichte
        treffer.sort(key=lambda y: (not name_aehnlich(m["name"], y["name"]), y["seit"]))
    if treffer:
        return treffer[0], ""
    return None, "bei Yahoo nicht sicher zuzuordnen (" + ("; ".join(gruende) or "kein Kürzel gefunden") + ")"


def bauen():
    heute = dt.date.today()
    raus = ausschluss_ids()
    markt = rangliste()   # zuletzt holen: die Kurse darin werden gleich mit Yahoo verglichen
    liste, weg, cache, ids, symbole = [], [], {}, set(), set()
    f_suche = ROH / "suche.json"
    if WEITER and f_suche.exists() and time.time() - f_suche.stat().st_mtime < 6 * 3600:
        cache.update(json.loads(f_suche.read_text()))
    aktien = set()
    uni = E.DATEN / "universum.csv"
    if uni.exists():   # Sicherheitsnetz: keine Kennung, die es als Aktie/ETF/Rohstoff schon gibt
        with open(uni, newline="") as f:
            aktien = {z["id"] for z in csv.DictReader(f) if z.get("gruppe") != "Krypto"} | set()
    platz = 0
    for m in markt:
        if platz >= ANZAHL:
            break
        m["name"] = re.sub(r"[\u200b-\u200f\u2060\ufeff]", "", m["name"]).strip()   # unsichtbare Zeichen (gesehen bei „Stable“)
        kuerzel = m["symbol"].upper()
        grund = raus.get(m["id"])
        if not grund and NAMENSMUSTER.search(m["name"]):
            grund = "Name deutet auf Stablecoin/verpackte Münze (nicht aufgenommen, im Zweifel weglassen)"
        if grund:
            weg.append({"rang": m["market_cap_rank"], "name": m["name"], "kuerzel": kuerzel, "coingecko_id": m["id"], "grund": grund})
            continue
        platz += 1   # zählt zu den 200 größten echten Kryptowerten – auch wenn Yahoo sie nicht hat
        y, grund = zuordnen(m, heute, cache)
        if platz % 10 == 0:
            f_suche.write_text(json.dumps({k: v for k, v in cache.items() if k.startswith("?")}))
        if y is not None and y["symbol"] in symbole:
            y, grund = None, f"Yahoo-Kürzel {y['symbol']} schon einer größeren Münze zugeordnet"
        if y is None:
            weg.append({"rang": m["market_cap_rank"], "name": m["name"], "kuerzel": kuerzel, "coingecko_id": m["id"], "grund": grund})
            print(f"  – {m['name']} ({kuerzel}): {grund}", flush=True)
            continue
        wid = BEHALTEN.get(kuerzel) if y["symbol"] == f"{kuerzel}-USD" and kuerzel in BEHALTEN else f"{kuerzel}-USD"
        if wid in ids or wid in aktien:
            wid = y["symbol"]
        if wid in ids or wid in aktien:
            weg.append({"rang": m["market_cap_rank"], "name": m["name"], "kuerzel": kuerzel, "coingecko_id": m["id"], "grund": f"Kennung {wid} schon vergeben"})
            continue
        ids.add(wid); symbole.add(y["symbol"])
        liste.append({"rang": m["market_cap_rank"], "id": wid, "symbol": y["symbol"], "name": m["name"], "coingecko_id": m["id"],
                      "yahoo_name": y["name"], "kurse_seit": y["seit"].isoformat()})
        print(f"{platz:3d} {m['name']} -> {y['symbol']} ({y['name']}, seit {y['seit']})"
              + ("" if name_aehnlich(m["name"], y["name"]) else "   ? Name bei Yahoo anders – bitte nachlesen"), flush=True)
    ORDNER.mkdir(exist_ok=True)
    for datei, zeilen, felder in ((DATEI, liste, ["rang", "id", "symbol", "name", "coingecko_id", "yahoo_name", "kurse_seit"]),
                                  (DATEI_WEG, weg, ["rang", "name", "kuerzel", "coingecko_id", "grund"])):
        with open(datei, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=felder + ["stand"])
            w.writeheader()
            for z in zeilen:
                w.writerow(z | {"stand": heute.isoformat()})
    ohne_yahoo = sum(1 for z in weg if "Yahoo" in z["grund"] or "Kennung" in z["grund"])
    print(f"Krypto-Liste: {len(liste)} aufgenommen von den {platz} größten; {ohne_yahoo} ohne sicheres Yahoo-Kürzel, "
          f"{len(weg) - ohne_yahoo} ausgeschlossen (Stablecoins, verpackt, gestakt …). Stand {heute.isoformat()}")


def pruefen() -> int:
    """Vorhandene Liste gegen Yahoo: Kurse da und aktuell, Name unverändert. Schreibt nichts."""
    heute, fehler = dt.date.today(), 0
    with open(DATEI, newline="") as f:
        zeilen = list(csv.DictReader(f))
    for z in zeilen:
        y = yahoo_stand(z["symbol"])
        if y is None or (heute - y["datum"]).days > MAX_ALT_TAGE:
            fehler += 1; print(f"✗ {z['id']} ({z['symbol']}): " + ("keine Kurse" if y is None else f"letzter Kurs {y['datum']}"))
        elif y["name"] != z["yahoo_name"]:   # Yahoo hat das Kürzel umbenannt oder neu vergeben
            fehler += 1; print(f"✗ {z['id']} ({z['symbol']}): Yahoo-Name jetzt „{y['name']}“ statt „{z['yahoo_name']}“")
    print(f"{len(zeilen)} Münzen geprüft, {fehler} Auffälligkeiten")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(pruefen() if "--pruefen" in sys.argv[1:] else bauen())
