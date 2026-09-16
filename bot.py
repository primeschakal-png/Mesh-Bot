#!/usr/bin/env python3
"""Mesh-Bot.

Ein Python-Prozess mit drei Schichten: Transport unten, Logik in der Mitte,
Weboberflaeche oben. Der Browser ist nur ein Fenster auf den laufenden
Prozess. Tab zumachen heisst nicht, dass der Bot aufhoert.

    python bot.py                      offline, nur Tastatur
    python bot.py --port COM7          echter Node, Modus in der Oberflaeche
    python bot.py --port COM7 --scharf sofort scharf

Oberflaeche danach unter http://localhost:8080
"""

from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional, Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from core.bot import Bot, Modus
from core.transport import DummyTransport, Eingang, SerialTransport, Transport

WURZEL = Path(__file__).parent


# ---------------------------------------------------------------------------
# Rueckkanal zur Oberflaeche
# ---------------------------------------------------------------------------

class Rueckkanal:
    """Verteilt Ereignisse an alle offenen Browser-Tabs."""

    def __init__(self) -> None:
        self.verbindungen: Set[WebSocket] = set()
        self.verlauf: List[dict] = []

    async def anmelden(self, ws: WebSocket) -> None:
        await ws.accept()
        self.verbindungen.add(ws)
        for eintrag in self.verlauf[-80:]:
            await ws.send_json(eintrag)

    def abmelden(self, ws: WebSocket) -> None:
        self.verbindungen.discard(ws)

    async def senden(self, nachricht: dict) -> None:
        if nachricht.get("typ") in ("rx", "tx", "log"):
            self.verlauf.append(nachricht)
            del self.verlauf[:-300]
        tot = []
        for ws in self.verbindungen:
            try:
                await ws.send_json(nachricht)
            except Exception:                        # noqa: BLE001
                tot.append(ws)
        for ws in tot:
            self.verbindungen.discard(ws)

    def leeren(self) -> None:
        self.verlauf.clear()


# ---------------------------------------------------------------------------
# Verdrahtung
# ---------------------------------------------------------------------------

class Anwendung:
    def __init__(self, argumente: argparse.Namespace):
        self.args = argumente
        self.kanal = Rueckkanal()

        start_modus = Modus.OFFLINE
        if argumente.port:
            start_modus = Modus.SCHARF if argumente.scharf else Modus.MITLESEN

        self.bot = Bot(
            seiten_datei=WURZEL / "seiten.json",
            plugin_ordner=WURZEL / "plugins",
            byte_limit=argumente.limit,
            ratenlimit_s=argumente.ratenlimit,
            modus=start_modus,
        )

        self.transport: Transport
        if argumente.port:
            self.transport = SerialTransport(argumente.port, argumente.baud)
        else:
            self.transport = DummyTransport()

        self.transport.bei_nachricht(self._eingang)

    # -- Kern ---------------------------------------------------------------

    async def _eingang(self, e: Eingang) -> None:
        await self.kanal.senden({
            "typ": "rx",
            "absender": e.absender_name,
            "key": e.absender_key,
            "text": e.text,
            "snr": e.snr,
            "rssi": e.rssi,
            "hops": e.hops,
            "bytes": len(e.text.encode("utf-8")),
        })

        antwort = await self.bot.verarbeiten(e)
        if antwort is None:
            return

        for zeile in antwort.spur:
            await self.kanal.senden({"typ": "log", "text": zeile})

        if not antwort.text:
            return

        gesendet = False
        if self.bot.modus is Modus.SCHARF:
            gesendet = await self.transport.senden(e.absender_key, antwort.text)
            if gesendet:
                self.bot.buchen(antwort)
        elif self.bot.modus is Modus.OFFLINE:
            self.bot.buchen(antwort)
            gesendet = True

        await self.kanal.senden({
            "typ": "tx",
            "an": e.absender_name,
            "text": antwort.text,
            "bytes": antwort.bytes,
            "pakete": antwort.pakete,
            "zu_lang": antwort.zu_lang,
            "quelle": antwort.quelle,
            "gesendet": gesendet,
            "modus": self.bot.modus.value,
        })
        await self._status()

    async def _status(self) -> None:
        await self.kanal.senden({
            "typ": "status",
            "modus": self.bot.modus.value,
            "transport": self.transport.name,
            "verbunden": self.transport.verbunden,
            "limit": self.bot.byte_limit,
            "ratenlimit": self.bot.ratenlimit_s,
            "statistik": self.bot.statistik.als_dict(self.bot.duty.prozent()),
            "plugins": self.bot.plugins.uebersicht(),
        })

    # -- Befehle aus der Oberflaeche ----------------------------------------

    async def _befehl(self, daten: dict) -> None:
        typ = daten.get("typ")

        if typ == "test":
            e = Eingang(
                absender_key=str(daten.get("key", "TESTUSER")),
                absender_name=str(daten.get("name", "Testnutzer")),
                text=str(daten.get("text", "")),
                snr=float(daten.get("snr", 6.5)),
                rssi=int(daten.get("rssi", -88)),
                hops=int(daten.get("hops", 2)),
            )
            await self._eingang(e)

        elif typ == "modus":
            wert = str(daten.get("wert", "offline"))
            if wert == "scharf" and not self.args.port:
                await self.kanal.senden({
                    "typ": "log",
                    "text": "Scharf geht nicht ohne --port. Bot laeuft ohne Node.",
                })
                return
            self.bot.modus = Modus(wert)
            await self.kanal.senden({"typ": "log", "text": f"Modus jetzt {wert}"})
            await self._status()

        elif typ == "seiten_holen":
            await self.kanal.senden({"typ": "seiten", "seiten": self.bot.baum.als_liste()})

        elif typ == "seiten_speichern":
            self.bot.baum.ersetzen(daten.get("seiten", []))
            await self.kanal.senden({"typ": "log", "text": "Seiten gespeichert"})
            await self.kanal.senden({"typ": "seiten", "seiten": self.bot.baum.als_liste()})

        elif typ == "limit":
            self.bot.byte_limit = max(20, int(daten.get("wert", 200)))
            await self._status()

        elif typ == "ratenlimit":
            self.bot.ratenlimit_s = max(0, int(daten.get("wert", 20)))
            await self._status()

        elif typ == "neu_laden":
            self.bot.neu_laden()
            await self.kanal.senden({"typ": "log", "text": "Seiten und Plugins neu geladen"})
            await self.kanal.senden({"typ": "seiten", "seiten": self.bot.baum.als_liste()})
            await self._status()

        elif typ == "leeren":
            self.kanal.leeren()
            await self.kanal.senden({"typ": "leeren"})


# ---------------------------------------------------------------------------
# Webserver
# ---------------------------------------------------------------------------

def app_bauen(anwendung: Anwendung) -> FastAPI:

    @asynccontextmanager
    async def lebenszyklus(app: FastAPI):
        await anwendung.transport.starten()
        print(f"[bot] Modus {anwendung.bot.modus.value}, "
              f"Transport {anwendung.transport.name}")
        yield
        await anwendung.transport.stoppen()

    app = FastAPI(title="Mesh-Bot", lifespan=lebenszyklus)

    @app.get("/")
    async def seite() -> FileResponse:
        return FileResponse(WURZEL / "web" / "index.html")

    @app.websocket("/ws")
    async def ws_endpunkt(ws: WebSocket) -> None:
        await anwendung.kanal.anmelden(ws)
        await anwendung._status()
        await ws.send_json({"typ": "seiten", "seiten": anwendung.bot.baum.als_liste()})
        try:
            while True:
                roh = await ws.receive_text()
                try:
                    await anwendung._befehl(json.loads(roh))
                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            anwendung.kanal.abmelden(ws)

    return app


def hauptprogramm() -> None:
    p = argparse.ArgumentParser(description="Mesh-Bot fuer MeshCore")
    p.add_argument("--port", help="serieller Port des Companion-Node, z.B. COM7")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--scharf", action="store_true",
                   help="sofort scharf schalten, sonst nur mitlesen")
    p.add_argument("--limit", type=int, default=200, help="Byte pro Nachricht")
    p.add_argument("--ratenlimit", type=int, default=20,
                   help="Sekunden zwischen zwei Anfragen je Nutzer")
    p.add_argument("--web-port", type=int, default=8080)
    args = p.parse_args()

    anwendung = Anwendung(args)
    app = app_bauen(anwendung)

    print(f"\n  Oberflaeche: http://localhost:{args.web_port}\n")
    uvicorn.run(app, host="127.0.0.1", port=args.web_port, log_level="warning")


if __name__ == "__main__":
    hauptprogramm()
