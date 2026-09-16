"""Der Seitenbaum.

Die Nummer ist der Weg: "2" ist ein Menuepunkt, "24" dessen vierter
Unterpunkt. Die leere Nummer ist die Startseite, im Chat als "0" erreichbar.

Aufbau wie beim Videotext: man fordert eine Seite an und bekommt sie. Kein
Sitzungszustand, jede Anfrage ist fuer sich vollstaendig.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Seite:
    code: str
    titel: str
    text: str = ""

    @property
    def anzeige_nr(self) -> str:
        return "0" if self.code == "" else self.code


STANDARD: List[Dict[str, str]] = [
    {"code": "",   "titel": "Start",       "text": "Bot Heiligenhaus. Nummer tippen.\n{menue}"},
    {"code": "1",  "titel": "Signal",      "text": ""},
    {"code": "2",  "titel": "Wetter",      "text": ""},
    {"code": "3",  "titel": "Info",        "text": ""},
    {"code": "31", "titel": "Anleitung",   "text": "{nr} primeschakal-png.github.io/Mesh-Bot"},
    {"code": "32", "titel": "Betreiber",   "text": "{nr} DE-NW Heiligenhaus, QRV seit 09/26"},
]


class Seitenbaum:
    def __init__(self, pfad: Path):
        self.pfad = Path(pfad)
        self.seiten: List[Seite] = []
        self.laden()

    # -- Datenhaltung --------------------------------------------------------

    def laden(self) -> None:
        if self.pfad.exists():
            try:
                roh = json.loads(self.pfad.read_text(encoding="utf-8"))
                self.seiten = [
                    Seite(str(s.get("code", "")), str(s.get("titel", "")), str(s.get("text", "")))
                    for s in roh
                ]
                return
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass
        self.seiten = [Seite(**s) for s in STANDARD]
        self.sichern()

    def sichern(self) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.pfad.write_text(
            json.dumps([asdict(s) for s in self.seiten], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def ersetzen(self, roh: List[dict]) -> None:
        self.seiten = [
            Seite(str(s.get("code", "")), str(s.get("titel", "")), str(s.get("text", "")))
            for s in roh
        ]
        self.sichern()

    def als_liste(self) -> List[dict]:
        return [asdict(s) for s in self.seiten]

    # -- Nachschlagen --------------------------------------------------------

    def finde(self, code: str) -> Optional[Seite]:
        for s in self.seiten:
            if s.code == code:
                return s
        return None

    def kinder(self, code: str) -> List[Seite]:
        treffer = [
            s for s in self.seiten
            if len(s.code) == len(code) + 1 and s.code.startswith(code)
        ]
        return sorted(treffer, key=lambda s: s.code)

    def menuezeile(self, code: str) -> str:
        k = self.kinder(code)
        if not k:
            return ""
        return "  ".join(f"{s.code[-1]} {s.titel}" for s in k)


# ---------------------------------------------------------------------------
# Platzhalter
# ---------------------------------------------------------------------------

_PLATZHALTER = re.compile(r"\{([a-z_]+)\}")


def fuellen(text: str, werte: Dict[str, object]) -> str:
    """Ersetzt {name} durch werte["name"]. Unbekanntes bleibt stehen."""
    def ersatz(m: re.Match) -> str:
        schluessel = m.group(1)
        if schluessel in werte:
            return str(werte[schluessel])
        return m.group(0)

    return _PLATZHALTER.sub(ersatz, text)
