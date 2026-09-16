"""Transportschicht.

Der Bot kennt nur diese Schnittstelle, nicht den Funk. Dadurch laeuft
dieselbe Logik im Offline-Test und am echten Node.

Wichtig: die genauen Methodennamen von meshcore_py koennen sich zwischen
Versionen unterscheiden. SerialTransport kapselt das an genau einer Stelle,
damit eine Anpassung nur hier noetig ist.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional


@dataclass
class Eingang:
    """Eine eingehende Direktnachricht mit allem, was der Funk mitliefert."""

    absender_key: str
    absender_name: str
    text: str
    snr: float = 0.0
    rssi: int = 0
    hops: int = 0
    empfangen: float = field(default_factory=time.time)


Handler = Callable[[Eingang], Awaitable[None]]


class Transport:
    """Basisklasse. Nicht direkt verwenden."""

    name = "basis"

    def __init__(self) -> None:
        self._handler: Optional[Handler] = None
        self.verbunden = False

    def bei_nachricht(self, handler: Handler) -> None:
        self._handler = handler

    async def _zustellen(self, e: Eingang) -> None:
        if self._handler:
            await self._handler(e)

    async def starten(self) -> None:
        self.verbunden = True

    async def stoppen(self) -> None:
        self.verbunden = False

    async def senden(self, ziel_key: str, text: str) -> bool:
        raise NotImplementedError


class DummyTransport(Transport):
    """Attrappe fuer den Offline-Betrieb.

    Nachrichten kommen aus der Weboberflaeche statt aus dem Funk. Gesendetes
    geht nicht raus, sondern wird ueber den Rueckkanal angezeigt.
    """

    name = "offline"

    def __init__(self, ausgabe: Optional[Callable[[str, str], None]] = None) -> None:
        super().__init__()
        self._ausgabe = ausgabe

    async def starten(self) -> None:
        self.verbunden = True

    async def senden(self, ziel_key: str, text: str) -> bool:
        if self._ausgabe:
            self._ausgabe(ziel_key, text)
        return True

    async def einspeisen(self, text: str, absender_key: str = "TESTUSER",
                         absender_name: str = "Testnutzer",
                         snr: float = 6.5, rssi: int = -88, hops: int = 2) -> None:
        """Von der Oberflaeche aufgerufen: tut so, als kaeme das aus dem Funk."""
        await self._zustellen(Eingang(
            absender_key=absender_key, absender_name=absender_name,
            text=text, snr=snr, rssi=rssi, hops=hops,
        ))


class SerialTransport(Transport):
    """Echte Anbindung an einen Companion-Node per USB.

    Beim Heltec V4 stellt die Firmware den USB-Port selbst bereit, es gibt
    keinen eigenen Bruecken-Chip. Faellt die Firmware aus, verschwindet der
    Port, deshalb die Wiederverbindungsschleife.
    """

    name = "seriell"

    def __init__(self, port: str, baud: int = 115200) -> None:
        super().__init__()
        self.port = port
        self.baud = baud
        self._mc = None
        self._task: Optional[asyncio.Task] = None
        self._laeuft = False

    async def starten(self) -> None:
        self._laeuft = True
        self._task = asyncio.create_task(self._schleife())

    async def stoppen(self) -> None:
        self._laeuft = False
        if self._task:
            self._task.cancel()
        await self._trennen()
        self.verbunden = False

    async def _schleife(self) -> None:
        while self._laeuft:
            try:
                await self._verbinden()
                while self._laeuft and self.verbunden:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as fehler:            # noqa: BLE001
                print(f"[transport] Verbindung verloren: {fehler}")
            self.verbunden = False
            if self._laeuft:
                await asyncio.sleep(3)
                print("[transport] neuer Verbindungsversuch")

    async def _verbinden(self) -> None:
        # Import erst hier, damit der Offline-Betrieb ohne meshcore_py laeuft.
        from meshcore import MeshCore, EventType     # type: ignore

        self._mc = await MeshCore.create_serial(self.port, self.baud)
        self.verbunden = True
        print(f"[transport] verbunden mit {self.port}")

        async def weiterreichen(event) -> None:
            nutz = getattr(event, "payload", event) or {}
            text = str(nutz.get("text", "") or "")
            if not text:
                return
            await self._zustellen(Eingang(
                absender_key=str(nutz.get("pubkey_prefix", nutz.get("pubkey", "")) or ""),
                absender_name=str(nutz.get("sender_name", nutz.get("name", "?")) or "?"),
                text=text,
                snr=float(nutz.get("snr", 0) or 0),
                rssi=int(nutz.get("rssi", 0) or 0),
                hops=int(nutz.get("path_len", nutz.get("hops", 0)) or 0),
            ))

        self._mc.subscribe(EventType.CONTACT_MSG_RECV, weiterreichen)
        await self._mc.start_auto_message_fetching()

    async def _trennen(self) -> None:
        if self._mc is not None:
            try:
                await self._mc.disconnect()
            except Exception:                        # noqa: BLE001
                pass
            self._mc = None

    async def senden(self, ziel_key: str, text: str) -> bool:
        if not self.verbunden or self._mc is None:
            print("[transport] senden nicht moeglich, keine Verbindung")
            return False
        try:
            await self._mc.commands.send_msg(ziel_key, text)
            return True
        except Exception as fehler:                  # noqa: BLE001
            print(f"[transport] Senden fehlgeschlagen: {fehler}")
            self.verbunden = False
            return False
