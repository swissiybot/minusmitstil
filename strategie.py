"""Strategie-Vergleich je Wert: gleicher Monatsbetrag, drei Vorgehen, echte Kurse.

  A  Sparplan:   jeden Monat den ganzen Betrag kaufen.
  B  Staffelkauf: der Betrag kommt aufs Tagesgeld (Zins = US-Geldmarkt 3 Monate, FRED TB3MS,
                 versteuert). Gekauft wird nach Ampel: unter 60 nichts, 60–75 ein Drittel des
                 wartenden Geldes, 75–90 zwei Drittel, ab 90 alles.
  C  wie B, zusaetzlich Teilverkauf: faellt die Ampel auf 15 oder tiefer, wird ein Viertel des
                 Bestands verkauft (einmal je teurer Phase; neue Phase erst, wenn die Ampel wieder
                 ueber 40 war). Der Erloes wartet wieder auf dem Tagesgeld.

Ablauf je Monat: Entscheidung mit der Ampel vom letzten Wochenschluss (nur damals bekanntes Wissen),
Ausfuehrung zum Eroeffnungskurs der ersten Woche des Monats.
Kosten: fester Betrag + Prozent je Order (zaehlen zu den Anschaffungskosten bzw. mindern den Erloes).
Steuer: Abgeltungssteuer 26,375 % (25 % + Soli) auf realisierte Gewinne (FIFO, Verlusttopf) und auf Zinsen.
Endvermoegen "nach Steuer" = alles am Ende verkauft. Seit 22.11.2026 fuer den einzelnen Wert (Lohnt-sich-Check,
Strategie-Vergleich je Wert): Sparerpauschbetrag 1.000 je Kalenderjahr (auf Kursgewinne und Zinsen, vereinfacht in der
Waehrung des Werts) und Teilfreistellung 30 % fuer Aktien-ETFs (Gewinne und Verluste nur zu 70 % steuerwirksam; nicht
fuer Anleihen-ETFs, Rohstoffe, Krypto, Einzelaktien und Zinsen). Laufende Fondskosten (TER) stecken schon im ETF-Kurs.
Die Pruefung ueber viele Werte (analyse.py) rechnet weiter ohne beides, damit sie mit frueheren Staenden vergleichbar bleibt.
Nicht beruecksichtigt: Kirchensteuer, Vorabpauschale, Waehrungen; Dividenden stecken steuerfrei im bereinigten Kurs
(fuer alle drei Vorgehen gleich).
"""
import math
import numpy as np
import pandas as pd

STEUER = 0.26375
STUFEN = [(90, 1.0), (75, 2 / 3), (60, 1 / 3)]
VERKAUF_AB = 15
VERKAUF_ANTEIL = 0.25
WIEDER_FREI_AB = 40
PAUSCHBETRAG = 1000.0
TEILFREI_AKTIENFONDS = 0.30


def teilfreistellung(zeile: dict) -> float:
    """30 % fuer Aktien-ETFs (Index-, Themen-, Branchen-, Faktor-, Laender-ETFs), sonst 0."""
    return TEILFREI_AKTIENFONDS if zeile.get("gruppe") == "ETF" and zeile.get("branche") not in ("Anleihen", "Rohstoff") else 0.0


NAMEN = {"spar": "Sparplan", "staffel": "Staffelkauf 60/75/90", "staffel_vk": "Staffelkauf + Teilverkauf ≤ 15",
         "warten60": "Warten auf günstig (Ampel ab 60)", "warten80": "Warten auf sehr günstig (Ampel ab 80)",
         "misch": "Mischung: halb Sparplan, halb Warten auf günstig"}
# Wunsch Marc 23.11.2026: je Titel monatlich kaufen, auf günstig bzw. sehr günstig warten oder mischen – [Schlüssel, Ampel-Grenze, Anteil sofort]
WARTE_WEGE = (("warten60", 60, 0.0), ("warten80", 80, 0.0), ("misch", 60, 0.5))


def _xirr(fluesse: list[tuple[float, float]]) -> float | None:
    """Interner Zinsfuss (p.a.) fuer (Jahre ab Start, Betrag)."""
    t = np.array([f[0] for f in fluesse]); b = np.array([f[1] for f in fluesse])
    npv = lambda r: float(np.sum(b / (1 + r) ** t))
    lo, hi = -0.99, 5.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


class Depot:
    def __init__(self, kfix, kproz, pausch=0.0, teilfrei=0.0):
        self.kfix, self.kproz = kfix, kproz
        self.pausch, self.teilfrei = pausch, teilfrei
        self.jahr, self.frei_rest = None, pausch
        self.lose: list[list[float]] = []   # [Stueck, Einstand je Stueck inkl. Kosten]
        self.bar = 0.0
        self.verlusttopf = 0.0
        self.steuer = self.kosten = 0.0
        self.kaeufe = self.verkaeufe = 0
        self.n = 0.0                         # Stueck gesamt (laufend mitgezaehlt, schneller)

    def stueck(self):
        return self.n

    def kaufen(self, betrag, kurs):
        k = self.kfix + self.kproz * betrag
        if betrag <= k * 2:      # lohnt nicht (Kosten wuerden den Betrag auffressen)
            return
        menge = (betrag - k) / kurs
        self.lose.append([menge, betrag / menge])
        self.n += menge
        self.kosten += k; self.kaeufe += 1

    def jahr_setzen(self, jahr):
        """Neues Kalenderjahr: Sparerpauschbetrag steht wieder voll zur Verfuegung."""
        if jahr != self.jahr:
            self.jahr, self.frei_rest = jahr, self.pausch

    def _nach_freibetrag(self, betrag):
        ab = min(betrag, self.frei_rest)
        self.frei_rest -= ab
        return betrag - ab

    def _versteuern(self, gewinn):
        gewinn *= 1 - self.teilfrei            # Teilfreistellung: nur dieser Teil ist steuerwirksam (auch bei Verlust)
        if gewinn < 0:
            self.verlusttopf += -gewinn
            return 0.0
        verrechnet = min(gewinn, self.verlusttopf)
        self.verlusttopf -= verrechnet
        st = self._nach_freibetrag(gewinn - verrechnet) * STEUER
        self.steuer += st
        return st

    def verkaufen(self, anteil, kurs, buchen=True):
        """Verkauft 'anteil' des Bestands (FIFO). Gibt Netto-Erloes zurueck."""
        menge = self.stueck() * anteil
        if menge <= 0:
            return 0.0
        brutto = menge * kurs
        k = self.kfix + self.kproz * brutto
        einstand, rest = 0.0, menge
        while rest > 1e-12 and self.lose:
            los = self.lose[0]
            nimm = min(rest, los[0])
            einstand += nimm * los[1]
            los[0] -= nimm; rest -= nimm
            if los[0] <= 1e-12:
                self.lose.pop(0)
        self.n = sum(l[0] for l in self.lose)
        st = self._versteuern(brutto - k - einstand)
        self.kosten += k
        if buchen:
            self.verkaeufe += 1
        return brutto - k - st

    def zins(self, satz_pa):
        z = self.bar * satz_pa / 100 / 12
        if z > 0:
            st = self._nach_freibetrag(z) * STEUER
            self.steuer += st
            z -= st
        self.bar += z

    def wert(self, kurs):
        return self.n * kurs + self.bar


def vergleich(w: pd.DataFrame, score: np.ndarray, zins: pd.Series | None, betrag=500.0, jahre=20,
              kfix=1.0, kproz=0.0, fester_zins: float | None = None, reihe=True, pausch=0.0, teilfrei=0.0) -> dict | None:
    """w = Wochenkerzen (Index Freitag), score = Ampel je Woche (gleich lang)."""
    c = w["Close"].values.astype(float)
    o = w["Open"].values.astype(float)
    idx = w.index
    n = len(c)
    start_soll = idx[-1] - pd.DateOffset(years=jahre)
    # Monatsanfaenge: erste Woche eines neuen Monats, Ampel der Vorwoche bekannt
    neu_monat = np.flatnonzero(np.r_[False, idx.month[1:] != idx.month[:-1]])
    tage = [i for i in neu_monat if idx[i] >= start_soll and i >= 1 and not math.isnan(score[i - 1])]
    if len(tage) < 24:
        return None
    t0 = idx[tage[0]]

    def satz(datum):
        if fester_zins is not None:
            return fester_zins
        if zins is None or zins.empty:
            return 0.0
        m = pd.Timestamp(datum.year, datum.month, 1)
        return float(zins.asof(m)) if m >= zins.index[0] else float(zins.iloc[0])

    depots = {k: Depot(kfix, kproz, pausch, teilfrei) for k in NAMEN}
    frei = True
    eingezahlt = 0.0
    fluesse = []
    verlauf = {k: [] for k in NAMEN}
    verlauf_t, verlauf_ein = [], []
    hoch = {k: 0.0 for k in NAMEN}
    max_dd = {k: 0.0 for k in NAMEN}
    max_unter = {k: 0.0 for k in NAMEN}
    tage_set = set(tage)
    letzter_satz = 0.0
    for i in range(tage[0], n):
        if i in tage_set:
            kurs = o[i] if not math.isnan(o[i]) and o[i] > 0 else c[i - 1]
            s = score[i - 1]
            letzter_satz = satz(idx[i])
            for d in depots.values():
                d.jahr_setzen(idx[i].year)
            eingezahlt += betrag
            fluesse.append(((idx[i] - t0).days / 365.25, -betrag))
            depots["spar"].kaufen(betrag, kurs)
            if s > WIEDER_FREI_AB:
                frei = True
            for k in ("staffel", "staffel_vk"):
                d = depots[k]
                d.zins(letzter_satz)
                d.bar += betrag
                if k == "staffel_vk" and frei and s <= VERKAUF_AB and d.stueck() > 0:
                    d.bar += d.verkaufen(VERKAUF_ANTEIL, kurs)
                anteil = next((a for grenze, a in STUFEN if s >= grenze), 0.0)
                if anteil > 0 and d.bar > 0:
                    invest = d.bar * anteil
                    vorher = d.kaeufe
                    d.kaufen(invest, kurs)
                    if d.kaeufe > vorher:
                        d.bar -= invest
            for k, grenze, sofort in WARTE_WEGE:
                d = depots[k]
                d.zins(letzter_satz)               # Wartegeld wird verzinst (wie beim Staffelkauf)
                if sofort > 0:
                    vorher = d.kaeufe
                    d.kaufen(betrag * sofort, kurs)
                    if d.kaeufe == vorher:         # Kauf zu klein: Geld bleibt als Bargeld
                        d.bar += betrag * sofort
                d.bar += betrag * (1 - sofort)
                if s >= grenze and d.bar > 0:      # Ampel der Vorwoche erreicht die Grenze: alles Wartegeld anlegen
                    invest = d.bar
                    vorher = d.kaeufe
                    d.kaufen(invest, kurs)
                    if d.kaeufe > vorher:
                        d.bar -= invest
            if s <= VERKAUF_AB:
                frei = False
        for k, d in depots.items():
            v = d.wert(c[i])
            hoch[k] = max(hoch[k], v)
            if hoch[k] > 0:
                max_dd[k] = min(max_dd[k], v / hoch[k] - 1)
            max_unter[k] = min(max_unter[k], v - eingezahlt)
        if reihe and (i in tage_set or i == n - 1):
            verlauf_t.append(int((idx[i] - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)))
            verlauf_ein.append(round(eingezahlt))
            for k, d in depots.items():
                verlauf[k].append(round(d.wert(c[i])))

    jahre_ist = (idx[-1] - t0).days / 365.25
    erg = {}
    for k, d in depots.items():
        brutto = d.wert(c[-1])
        bar_anteil = round(d.bar / brutto * 100, 1) if brutto > 0 else 0.0
        steuer_vorher, kosten_vorher = d.steuer, d.kosten
        netto = d.bar + (d.verkaufen(1.0, c[-1], buchen=False) if d.stueck() > 0 else 0.0)
        irr = _xirr(fluesse + [(jahre_ist, netto)])
        erg[k] = {
            "name": NAMEN[k], "brutto": round(brutto), "netto": round(netto),
            "irr": None if irr is None else round(irr * 100, 2),
            "max_verlust": round(max_dd[k] * 100, 1), "max_unter_einzahlung": round(max_unter[k]),
            "steuer_laufend": round(steuer_vorher), "steuer_ende": round(d.steuer - steuer_vorher),
            "kosten": round(d.kosten), "kaeufe": d.kaeufe, "verkaeufe": d.verkaeufe,
            "bar_anteil_ende": bar_anteil,
        }
    return {
        "von": t0.strftime("%Y-%m-%d"), "bis": min(idx[-1], pd.Timestamp.today().normalize()).strftime("%Y-%m-%d"), "jahre": round(jahre_ist, 1),
        "monate": len(tage), "eingezahlt": round(eingezahlt), "betrag": betrag, "kfix": kfix, "kproz": kproz,
        "pausch": pausch, "teilfrei": teilfrei,
        "zins": "fest " + f"{fester_zins:g}".replace(".", ",") + " % p.a." if fester_zins is not None else (("US-Geldmarkt 3 Monate (FRED TB3MS), zuletzt %.2f %%" % letzter_satz).replace(".", ",") if zins is not None else "kein Zins (FRED-Daten fehlen)"),
        "ergebnis": erg,
        "reihe": {"t": verlauf_t, "ein": verlauf_ein, **verlauf} if reihe else None,
    }
