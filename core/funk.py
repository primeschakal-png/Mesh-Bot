"""Funktechnische Hilfsfunktionen.

Airtime nach Semtech AN1200.13. Wird fuer die Duty-Cycle-Statistik gebraucht,
damit sichtbar bleibt, wieviel Kanalzeit der Bot tatsaechlich verbraucht.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class Funkprofil:
    """LoRa-Parameter. Voreinstellung entspricht MeshCore LongFast in EU868."""

    name: str = "LongFast"
    bandbreite_khz: int = 250
    sf: int = 11
    coding_rate: int = 5          # 5 entspricht 4/5
    praeambel: int = 8
    duty_cycle: float = 0.10      # 10 % nach ETSI im SRD-Band

    @property
    def low_data_rate(self) -> bool:
        return (2 ** self.sf) / (self.bandbreite_khz * 1000.0) > 0.016


LONGFAST = Funkprofil()


def bytes_von(text: str) -> int:
    """Laenge in Byte, nicht in Zeichen. Umlaute zaehlen doppelt."""
    return len(text.encode("utf-8"))


def airtime(nutzlast_bytes: int, profil: Funkprofil = LONGFAST) -> float:
    """Sendezeit eines Pakets in Sekunden."""
    t_sym = (2 ** profil.sf) / (profil.bandbreite_khz * 1000.0)
    t_praeambel = (profil.praeambel + 4.25) * t_sym

    de = 1 if profil.low_data_rate else 0
    zaehler = 8 * nutzlast_bytes - 4 * profil.sf + 28 + 16
    nenner = 4 * (profil.sf - 2 * de)
    n_nutzlast = 8 + max(math.ceil(zaehler / nenner) * profil.coding_rate, 0)

    return t_praeambel + n_nutzlast * t_sym


@dataclass
class DutyCycleZaehler:
    """Gleitendes Stundenfenster ueber die eigene Sendezeit."""

    profil: Funkprofil = LONGFAST
    _log: List[Tuple[float, float]] = field(default_factory=list)

    def buchen(self, nutzlast_bytes: int) -> float:
        dauer = airtime(nutzlast_bytes, self.profil)
        self._log.append((time.time(), dauer))
        return dauer

    def verbraucht(self) -> float:
        """Anteil 0..1 der letzten Stunde."""
        grenze = time.time() - 3600.0
        self._log = [(t, d) for t, d in self._log if t + d > grenze]
        return sum(d for _, d in self._log) / 3600.0

    def prozent(self) -> float:
        return round(self.verbraucht() * 100, 2)

    def erlaubt(self, nutzlast_bytes: int) -> bool:
        dauer = airtime(nutzlast_bytes, self.profil)
        return self.verbraucht() + dauer / 3600.0 <= self.profil.duty_cycle
