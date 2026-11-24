"""Alarme aufs Handy (ntfy.sh): Meldung, wenn ein Wert historisch sehr guenstig (Ampel >= 80) oder historisch sehr
teuer (Ampel <= 15) wird. Laeuft nur im GitHub-Online-Lauf nach analyse.py, nicht auf dem PC.

Geheime Einstellungen (GitHub-Secrets, nie im Repo):
  NTFY_THEMA   geheimer Themenname bei ntfy.sh, den die ntfy-App abonniert (wirkt wie ein Passwort) – Pflicht
  ALARM_WERTE  optional: nur diese Werte beobachten, z. B. "BTC, QQQ, NVDA" (Knopf „Alarm-Liste kopieren“ in Mein Depot).
               Fehlt sie oder steht dort „alle“, werden ALLE Werte beobachtet (Wunsch Marc, 22.11.2026).
Optional: NTFY_SERVER (Standard https://ntfy.sh).

Damit das Handy nicht ueberlaeuft:
  - ETFs, Rohstoffe, die fuenf Krypto-Kernwerte (Bitcoin, Ethereum, Solana, Chainlink, Stellar) und Werte aus ALARM_WERTE:
    je Wechsel eine eigene Meldung, sofort (hoechstens 8 je Lauf).
  - Aktien, die uebrigen Kryptowerte der Top-200-Liste und Hebel-Produkte (2x) im Modus „alle“: gesammelt hoechstens einmal am Tag als
    Zusammenfassung (Aktien zuerst, die bekanntesten nach Handelsumsatz).
Stufe je Wert = sehr guenstig (>= 80), sehr teuer (<= 15) oder normal; mit Puffer gegen Hin-und-her-Springen
(sehr guenstig endet erst unter 75, sehr teuer erst ueber 20). Gemeldet wird nur ein Wechsel IN eine der beiden Stufen.
Beim allerersten Lauf kommt eine Startmeldung mit dem aktuellen Stand.

Datenschutz: Protokolle der Online-Laeufe sind oeffentlich – das Skript schreibt nur Anzahlen hinein, nie den Themennamen
oder eine eigene Werteliste. Der Zwischenstand liegt im GitHub-Zwischenspeicher; Werte darin als HMAC-Pruefsumme
(Schluessel = Themenname), nur die noch nicht gemeldeten Aktien des Tages im Klartext (im Modus „alle“ ohnehin oeffentlich).

Ausfall-Alarm (gleicher Kanal): Kurse älter als 3 Tage (höchstens einmal am Tag) und – über `--ausfall URL` im
Workflow-Schritt mit if: failure() – wenn der Online-Lauf scheitert (z. B. weil pruefe_regeln.py eine Regel verletzt sieht).

Aufruf: python alarm.py                 senden (nur mit NTFY_THEMA)
        python alarm.py --ausfall URL   Ausfall-Alarm „Online-Lauf gescheitert“ (nur Standardbibliothek)
        python alarm.py --probe [WERTE] nichts senden, Startmeldung nur anzeigen (zum Testen am PC)
"""
import hashlib
import hmac
import json
import os
import re
import sys
import datetime as dt


import einstellungen as E

STAND = E.DATEN / "alarm_stand.json"
SEITE = "https://swissiybot.github.io/minusmitstil/"
GUENSTIG_AB, GUENSTIG_BIS = 80, 75     # Stufe beginnt ab 80, endet erst unter 75
TEUER_AB, TEUER_BIS = 15, 20           # Stufe beginnt ab 15 abwaerts, endet erst ueber 20
MAX_MELDUNGEN = 8
VERALTET_TAGE = 3                      # Kurse älter als 3 Tage -> Ausfall-Alarm (höchstens einmal am Tag)
SONDER = ("ETF", "Krypto", "Rohstoffe")


def meldet_einzeln(w: dict) -> bool:
    """Eigene Meldung je Wechsel: ETFs, Rohstoffe und die fünf Krypto-Kernwerte. Die übrigen Kryptowerte der Top-200-Liste
    (seit 24.11.2026) kommen wie Aktien gesammelt einmal am Tag – sonst liefe das Handy über."""
    if w.get("gruppe") == "Krypto":
        return w.get("id") in E.KRYPTO_KERN_IDS
    if w.get("branche") == E.HEBEL_BRANCHE:
        return False   # Hebel-Produkte: gesammelt wie Aktien
    return w.get("gruppe") in SONDER


def stufe(score, alt: str) -> str:
    if score is None:
        return alt
    if score >= GUENSTIG_AB or (alt == "guenstig" and score >= GUENSTIG_BIS):
        return "guenstig"
    if score <= TEUER_AB or (alt == "teuer" and score <= TEUER_BIS):
        return "teuer"
    return "normal"


def werte_lesen(text: str) -> list[str]:
    return list(dict.fromkeys(t for t in re.split(r"[\s,;]+", text.strip()) if t))


def schluessel(thema: str, wid: str) -> str:
    return hmac.new(thema.encode(), wid.encode(), hashlib.sha256).hexdigest()[:16]


def name(w: dict) -> str:
    return str(w.get("name") or w["id"]).replace(" (ETF)", "").strip()


def lage(w: dict) -> str:
    z = w.get("zu200w")
    if z is None:
        return ""
    return f"Kurs {abs(z):.0f} % {'über' if z >= 0 else 'unter'} der 200-Wochen-Linie (Stand {dt.date.fromisoformat(w['datum']).strftime('%d.%m.%Y')})."


def meldung(w: dict, neu: str, vorher) -> dict:
    s = w["score"]
    wort = "historisch sehr günstig" if neu == "guenstig" else "historisch sehr teuer"
    satz = f"Die Ampel ist von {vorher:.0f} auf {s:.0f} {'gestiegen' if s > vorher else 'gefallen'}. " if vorher is not None else f"Die Ampel steht bei {s:.0f}. "
    schwach = " Achtung: Geschäft schwach (" + ", ".join((w.get("f") or {}).get("gruende") or []) + ")." if (w.get("f") or {}).get("schwach") else ""
    return {"title": f"{name(w)}: {wort} (Ampel {s:.0f})",
            "message": satz + lage(w) + schwach + " Beschreibt die Lage – keine Kaufempfehlung.",
            "tags": ["green_circle" if neu == "guenstig" else "red_circle"], "click": f"{SEITE}#w={w['id']}"}


def aktien_text(ws: list[dict], n: int = 12) -> str:
    ws = sorted(ws, key=lambda w: (w.get("gruppe") in SONDER, -(w.get("umsatz_usd") or 0)))   # Aktien zuerst; Krypto-Umsätze sind nicht vergleichbar
    teile = [f"{name(w)} ({w['score']:.0f}{', Geschäft schwach' if (w.get('f') or {}).get('schwach') else ''})" for w in ws[:n]]
    return ", ".join(teile) + (f" und {len(ws) - n} weitere" if len(ws) > n else "")


def senden(server: str, thema: str, m: dict, probe: bool):
    if probe:
        print(json.dumps(m, ensure_ascii=False))
        return
    import requests
    r = requests.post(server.rstrip("/"), json={"topic": thema, **m}, timeout=30)
    r.raise_for_status()


def ausfall(url: str):
    """Ausfall-Alarm, wenn der Online-Lauf scheitert (Schritt mit if: failure() im Workflow). Nur Standardbibliothek,
    damit er auch meldet, wenn schon die Paket-Installation gescheitert ist."""
    import urllib.request
    thema = os.environ.get("NTFY_THEMA", "").strip()
    if not thema:
        print("Ausfall-Alarm: NTFY_THEMA fehlt – nichts gesendet.")
        return
    m = {"topic": thema, "title": "Aktien-Kaufplan: Online-Lauf gescheitert", "tags": ["rotating_light"], "priority": 4, "click": url,
         "message": "Der Online-Lauf ist abgebrochen (z. B. Fehler in einer Rechenregel oder beim Herunterladen). Die Seite zeigt weiter den letzten guten Stand. Details: Link antippen."}
    req = urllib.request.Request(os.environ.get("NTFY_SERVER", "https://ntfy.sh").strip().rstrip("/"), data=json.dumps(m).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()
    print("Ausfall-Alarm gesendet.")


def main(argv):
    if "--ausfall" in argv:
        i = argv.index("--ausfall")
        return ausfall(argv[i + 1] if len(argv) > i + 1 else SEITE)
    probe = "--probe" in argv
    thema = os.environ.get("NTFY_THEMA", "").strip() or ("probe" if probe else "")
    liste = os.environ.get("ALARM_WERTE", "").strip()
    if probe and not liste and len(argv) > 1:
        liste = " ".join(a for a in argv[1:] if a != "--probe")
    if not thema:
        print("Alarme: nicht eingerichtet (NTFY_THEMA fehlt) – nichts gesendet.")
        return
    alle_modus = not liste or liste.lower() == "alle"
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").strip()
    rl = json.loads((E.WEB_DATEN / "rangliste.json").read_text())
    werte = {w["id"]: w for w in rl["werte"]}
    unbekannt = []
    if alle_modus:
        beobachtet = [w for w in rl["werte"] if w.get("score") is not None]
    else:
        nach_symbol = {w.get("symbol"): w for w in rl["werte"]}   # auch Kürzel annehmen (z. B. "IWDA.AS")
        ids = werte_lesen(liste)
        beobachtet = [werte.get(i) or nach_symbol.get(i) for i in ids if i in werte or i in nach_symbol]
        unbekannt = [i for i in ids if i not in werte and i not in nach_symbol]
    einzeln = lambda w: not alle_modus or meldet_einzeln(w)
    stand = json.loads(STAND.read_text()) if STAND.exists() and not probe else {}
    if stand.get("modus") != ("alle" if alle_modus else "liste"):
        stand = {}                                   # Modus gewechselt: neu anfangen (mit Startmeldung)
    erstlauf = not stand.get("werte")
    alt_werte, neu_werte, meldungen = stand.get("werte", {}), {}, []
    offen = {k: list(v) for k, v in (stand.get("offen") or {"guenstig": [], "teuer": []}).items()}
    for w in beobachtet:
        k = schluessel(thema, w["id"])
        alt = alt_werte.get(k, {})
        neu = stufe(w.get("score"), alt.get("s", "normal"))
        neu_werte[k] = {"s": neu, "a": w.get("score")}
        if erstlauf or neu == alt.get("s", "normal") or neu not in ("guenstig", "teuer"):
            continue
        if einzeln(w):
            meldungen.append(meldung(w, neu, alt.get("a")))
        else:
            for st in ("guenstig", "teuer"):          # Aktie: für die Tageszusammenfassung vormerken
                if w["id"] in offen[st]:
                    offen[st].remove(w["id"])
            offen[neu].append(w["id"])
    heute = dt.date.today().isoformat()
    # Ausfall-Alarm: Kurse zu alt (Krypto hat täglich Kurse, deshalb das neueste Datum aller Werte)
    neuester = max((w["datum"] for w in rl["werte"] if w.get("datum")), default=None)
    alter = (dt.date.today() - dt.date.fromisoformat(neuester)).days if neuester else 999
    veraltet = None
    if alter > VERALTET_TAGE and stand.get("veraltet_tag") != heute:
        veraltet = {"title": "Aktien-Kaufplan: Kurse veraltet",
                    "message": (f"Die neuesten Kurse auf der Seite sind vom {dt.date.fromisoformat(neuester).strftime('%d.%m.%Y')} ({alter} Tage alt). " if neuester else "Keine Kurse gefunden. ")
                               + "Wahrscheinlich liefert Yahoo gerade keine Daten; die Seite zeigt den letzten Stand. Alarme beziehen sich auf diesen alten Stand.",
                    "tags": ["warning"], "priority": 4, "click": "https://github.com/swissiybot/minusmitstil/actions"}
    sammel = None
    if alle_modus and not erstlauf and stand.get("sammel_tag") != heute:
        # nur Aktien, die noch in der gemeldeten Stufe stehen
        g = [werte[i] for i in offen["guenstig"] if i in werte and neu_werte.get(schluessel(thema, i), {}).get("s") == "guenstig"]
        t = [werte[i] for i in offen["teuer"] if i in werte and neu_werte.get(schluessel(thema, i), {}).get("s") == "teuer"]
        if g or t:
            text = ((f"Neu historisch sehr günstig (Ampel ab 80): {len(g)} – {aktien_text(g)}.\n" if g else "")
                    + (f"Neu historisch sehr teuer (Ampel bis 15): {len(t)} – {aktien_text(t)}.\n" if t else "")
                    + "Bei Einzelaktien heißt sehr günstig oft: Die Firma steckt in Schwierigkeiten. Keine Kaufempfehlung.")
            sammel = {"title": f"Aktien, weitere Kryptowerte, Hebel-Produkte heute: {len(g)} neu sehr günstig, {len(t)} neu sehr teuer", "message": text, "tags": ["bar_chart"], "click": SEITE}
    try:
        if veraltet:
            senden(server, thema, veraltet, probe)
        if erstlauf:
            gs = [w for w in beobachtet if neu_werte[schluessel(thema, w['id'])]["s"] == "guenstig"]
            ts = [w for w in beobachtet if neu_werte[schluessel(thema, w['id'])]["s"] == "teuer"]
            kurz = lambda ws: ", ".join(f"{name(w)} ({w['score']:.0f})" for w in ws) or "keiner"
            if alle_modus:
                gs_s, ts_s = [w for w in gs if meldet_einzeln(w)], [w for w in ts if meldet_einzeln(w)]
                text = (f"Alarme sind eingerichtet: alle {len(beobachtet):,} Werte mit Ampel werden beobachtet.".replace(",", ".")
                        + " ETFs, Rohstoffe und die fünf großen Kryptowerte melden sich einzeln, sobald einer neu historisch sehr günstig (ab 80) oder sehr teuer (bis 15) wird; "
                        + "Aktien und die übrigen Kryptowerte kommen gesammelt einmal am Tag.\n"
                        + f"ETFs/Rohstoffe/große Kryptowerte gerade sehr günstig: {kurz(gs_s)}.\nGerade sehr teuer: {kurz(ts_s)}.\n"
                        + f"Aktien und übrige Kryptowerte gerade sehr günstig: {len(gs) - len(gs_s)}, sehr teuer: {len(ts) - len(ts_s)}.")
            else:
                text = (f"Alarme sind eingerichtet: {len(beobachtet)} Werte werden beobachtet. Du bekommst eine Meldung, wenn einer "
                        f"historisch sehr günstig (Ampel ab 80) oder sehr teuer (bis 15) wird.\n"
                        f"Gerade sehr günstig: {kurz(gs)}.\nGerade sehr teuer: {kurz(ts)}."
                        + (f"\nNicht gefunden (Schreibweise prüfen): {', '.join(unbekannt[:15])}." if unbekannt else ""))
            senden(server, thema, {"title": "Aktien-Kaufplan: Alarme aktiv", "message": text, "tags": ["bell"], "click": SEITE}, probe)
        else:
            for m in meldungen[:MAX_MELDUNGEN]:
                senden(server, thema, m, probe)
            if len(meldungen) > MAX_MELDUNGEN:
                senden(server, thema, {"title": "Aktien-Kaufplan: weitere Alarme",
                                       "message": f"Noch {len(meldungen) - MAX_MELDUNGEN} weitere Werte haben die Stufe gewechselt – siehe Dashboard.",
                                       "tags": ["bell"], "click": SEITE}, probe)
            if sammel:
                senden(server, thema, sammel, probe)
    except Exception as ex:   # Stand nicht speichern, damit die Meldung beim nächsten Lauf erneut versucht wird
        print(f"Alarme: Senden fehlgeschlagen ({ex.__class__.__name__}) – nächster Lauf versucht es erneut.", file=sys.stderr)
        return
    neu_stand = {"stand": dt.datetime.now().isoformat(timespec="seconds"), "modus": "alle" if alle_modus else "liste", "werte": neu_werte,
                 "offen": {"guenstig": [], "teuer": []} if sammel or erstlauf else offen,
                 "sammel_tag": heute if sammel or erstlauf else stand.get("sammel_tag"),
                 "veraltet_tag": heute if veraltet else stand.get("veraltet_tag")}
    if not probe:
        STAND.write_text(json.dumps(neu_stand))
    # nur Anzahlen ins (oeffentliche) Protokoll
    print(f"Alarme: {len(beobachtet)} Werte beobachtet ({'alle' if alle_modus else 'eigene Liste'}), {len(unbekannt)} unbekannt, "
          + ("Startmeldung" if erstlauf else f"{min(len(meldungen), MAX_MELDUNGEN)} Einzelmeldung(en), Tageszusammenfassung: {'ja' if sammel else 'nein'}")
          + (f", Kurse {alter} Tage alt – Ausfall-Alarm" if veraltet else "") + (" angezeigt." if probe else " gesendet."))


if __name__ == "__main__":
    main(sys.argv)
