"""Die Bot-Logik.

Kennt weder Funk noch Browser. Rein kommt ein Eingang, raus geht ein
Antworttext oder nichts.

Drei Betriebsarten:
    offline   nur die Attrappe, nichts geht auf den Funk
    mitlesen  echter Empfang, Antworten werden nur protokolliert
    scharf    Antworten gehen raus
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from .funk import DutyCycleZaehler, bytes_von
from .plugins import Pluginlader
from .seiten import Seitenbaum, fuellen
from .transport import Eingang


class Modus(str, Enum):
    OFFLINE = "offline"
    MITLESEN = "mitlesen"
    SCHARF = "scharf"


@dataclass
class Antwort:
    text: str
    bytes: int
    pakete: int
    zu_lang: bool
    quelle: str                  # "seite", "plugin", "sonder", "fehler"
    spur: List[str] = field(default_factory=list)


@dataclass
class Statistik:
    anfragen: int = 0
    antworten: int = 0
    abgelehnt_limit: int = 0
    zu_lang: int = 0
    unbekannt: int = 0
    sendezeit: float = 0.0
    seiten_zaehler: Dict[str, int] = field(default_factory=dict)
    nutzer: Dict[str, int] = field(default_factory=dict)

    def als_dict(self, duty: float) -> dict:
        top = sorted(self.seiten_zaehler.items(), key=lambda x: -x[1])[:8]
        return {
            "anfragen": self.anfragen,
            "antworten": self.antworten,
            "abgelehnt_limit": self.abgelehnt_limit,
            "zu_lang": self.zu_lang,
            "unbekannt": self.unbekannt,
            "sendezeit_s": round(self.sendezeit, 1),
            "duty_cycle_prozent": duty,
            "nutzer": len(self.nutzer),
            "top_seiten": [{"code": c or "0", "anzahl": n} for c, n in top],
        }


class Bot:
    def __init__(
        self,
        seiten_datei: Path,
        plugin_ordner: Path,
        byte_limit: int = 200,
        ratenlimit_s: int = 20,
        modus: Modus = Modus.OFFLINE,
    ):
        self.baum = Seitenbaum(seiten_datei)
        self.plugins = Pluginlader(plugin_ordner)
        self.byte_limit = byte_limit
        self.ratenlimit_s = ratenlimit_s
        self.modus = modus

        self.duty = DutyCycleZaehler()
        self.statistik = Statistik()
        self._letzte_anfrage: Dict[str, float] = {}
        self._signal_verlauf: Dict[str, List[float]] = {}

    # -- Menuezeile inklusive Plugins ----------------------------------------

    def menuezeile(self, code: str) -> str:
        eintraege = []
        for s in self.baum.kinder(code):
            eintraege.append((s.code, s.titel))
        for p in self.plugins.plugins.values():
            if len(p.code) == len(code) + 1 and p.code.startswith(code):
                if not any(c == p.code for c, _ in eintraege):
                    eintraege.append((p.code, p.titel))
        eintraege.sort()
        return "  ".join(f"{c[-1]} {t}" for c, t in eintraege)

    # -- Kontext -------------------------------------------------------------

    def _kontext(self, e: Eingang, code: str) -> dict:
        verlauf = self._signal_verlauf.get(e.absender_key, [])
        return {
            "snr": e.snr,
            "rssi": e.rssi,
            "hops": e.hops,
            "name": e.absender_name,
            "nr": code if code else "0",
            "uhr": time.strftime("%H:%M"),
            "zeit": int(time.time() - e.empfangen),
            "menue": self.menuezeile(code),
            "verlauf": verlauf,
            "statistik": self.statistik,
            "bot": self,
        }

    # -- Hauptweg ------------------------------------------------------------

    async def verarbeiten(self, e: Eingang) -> Optional[Antwort]:
        self.statistik.anfragen += 1
        self.statistik.nutzer[e.absender_key] = self.statistik.nutzer.get(e.absender_key, 0) + 1

        verlauf = self._signal_verlauf.setdefault(e.absender_key, [])
        verlauf.append(e.snr)
        del verlauf[:-10]

        roh = e.text.strip()
        if not roh:
            return None

        # Ratenlimit. Schweigen kostet weniger als eine Absage zu senden.
        jetzt = time.time()
        letzte = self._letzte_anfrage.get(e.absender_key, 0.0)
        if jetzt - letzte < self.ratenlimit_s:
            self.statistik.abgelehnt_limit += 1
            return Antwort(
                text="", bytes=0, pakete=0, zu_lang=False, quelle="fehler",
                spur=[f"Ratenlimit, noch {int(self.ratenlimit_s - (jetzt - letzte))} s, keine Antwort"],
            )
        self._letzte_anfrage[e.absender_key] = jetzt

        spur: List[str] = []
        klein = roh.lower()

        # Sonderbefehle vor der Nummernlogik
        if klein in ("?", "hilfe", "help"):
            spur.append("Sonderbefehl Hilfe")
            return self._fertig("Nummer tippen. 0 = Start. ping = Signal.", "sonder", spur)

        if klein == "ping":
            spur.append("Sonderbefehl ping")
            code = "1"
            if self.plugins.hat(code):
                text = await self.plugins.ausfuehren(code, self._kontext(e, code))
                return self._fertig(text, "plugin", spur)
            return self._fertig(f"SNR {e.snr} RSSI {e.rssi} {e.hops}h", "sonder", spur)

        # Nummernweg
        code = "" if roh == "0" else "".join(z for z in roh if z.isdigit())
        if not code and roh != "0":
            self.statistik.unbekannt += 1
            spur.append(f"Eingabe {roh!r} enthaelt keine Nummer")
            return self._fertig("Unbekannt. 0 = Start.", "fehler", spur)

        self.statistik.seiten_zaehler[code] = self.statistik.seiten_zaehler.get(code, 0) + 1

        # Plugin hat Vorrang vor der statischen Seite
        if self.plugins.hat(code):
            spur.append(f"Nummer {code or '0'} von Plugin {self.plugins.plugins[code].datei}")
            text = await self.plugins.ausfuehren(code, self._kontext(e, code))
            return self._fertig(fuellen(text, self._kontext(e, code)), "plugin", spur)

        seite = self.baum.finde(code)
        if seite is None:
            self.statistik.unbekannt += 1
            spur.append(f"Nummer {code or '0'} unbekannt")
            return self._fertig("Unbekannt. 0 = Start.", "fehler", spur)

        spur.append(f"Nummer {seite.anzeige_nr} gefunden: {seite.titel}")
        text = seite.text.strip()

        if not text:
            menue = self.menuezeile(code)
            if menue:
                spur.append("keine eigene Ausgabe, zeige Unterpunkte")
                text = f"{seite.anzeige_nr} {seite.titel}\n{menue}"
            else:
                spur.append("keine Ausgabe und keine Unterpunkte")
                text = "Seite leer."

        return self._fertig(fuellen(text, self._kontext(e, code)), "seite", spur)

    def _fertig(self, text: str, quelle: str, spur: List[str]) -> Antwort:
        b = bytes_von(text)
        pakete = max(1, -(-b // self.byte_limit))
        zu_lang = b > self.byte_limit
        if zu_lang:
            self.statistik.zu_lang += 1
            spur.append(f"{b} B ueber Limit {self.byte_limit} B, {b - self.byte_limit} B zu viel")
        return Antwort(text=text, bytes=b, pakete=pakete, zu_lang=zu_lang,
                       quelle=quelle, spur=spur)

    def buchen(self, antwort: Antwort) -> None:
        """Nach dem tatsaechlichen Senden aufrufen."""
        self.statistik.antworten += 1
        self.statistik.sendezeit += self.duty.buchen(antwort.bytes)

    def neu_laden(self) -> None:
        self.baum.laden()
        self.plugins.laden()
