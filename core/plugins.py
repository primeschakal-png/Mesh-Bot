"""Plugin-Lader.

Jede Datei in plugins/ meldet eine Seitennummer an und liefert dafuer einen
Text. Aehnlich wie ein Userscript in Tampermonkey: ein Kopfblock mit den
Metadaten, darunter die Funktion.

Erwartet werden in jedem Plugin:

    SEITE = {
        "code":  "2",       # Nummer im Seitenbaum
        "titel": "Wetter",  # erscheint in der Menuezeile der Elternseite
        "cache": 600,       # Sekunden, 0 heisst nicht zwischenspeichern
    }

    async def rendern(ctx) -> str:
        return "..."

ctx ist ein Wertebeutel mit snr, rssi, hops, name, nr, uhr und statistik.
Faellt ein Plugin auf die Nase, faengt der Lader das ab und der Bot gibt eine
kurze Fehlerzeile aus, statt umzufallen.
"""

from __future__ import annotations

import importlib.util
import inspect
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Plugin:
    code: str
    titel: str
    cache: int
    rendern: object
    datei: str
    _wert: Optional[str] = None
    _zeit: float = 0.0
    fehler: Optional[str] = None
    aufrufe: int = 0

    @property
    def frisch(self) -> bool:
        return (
            self._wert is not None
            and self.cache > 0
            and time.time() - self._zeit < self.cache
        )

    def merken(self, wert: str) -> None:
        self._wert = wert
        self._zeit = time.time()

    @property
    def zwischenspeicher(self) -> Optional[str]:
        return self._wert


class Pluginlader:
    def __init__(self, ordner: Path):
        self.ordner = Path(ordner)
        self.plugins: Dict[str, Plugin] = {}
        self.laden()

    def laden(self) -> None:
        self.plugins.clear()
        if not self.ordner.is_dir():
            return

        for datei in sorted(self.ordner.glob("*.py")):
            if datei.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"meshbot_plugin_{datei.stem}", datei
                )
                if spec is None or spec.loader is None:
                    continue
                modul = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(modul)

                meta = getattr(modul, "SEITE", None)
                funktion = getattr(modul, "rendern", None)
                if not isinstance(meta, dict) or funktion is None:
                    print(f"[plugins] {datei.name} uebersprungen, SEITE oder rendern fehlt")
                    continue

                code = str(meta.get("code", ""))
                self.plugins[code] = Plugin(
                    code=code,
                    titel=str(meta.get("titel", datei.stem)),
                    cache=int(meta.get("cache", 0)),
                    rendern=funktion,
                    datei=datei.name,
                )
                print(f"[plugins] {datei.name} -> Seite {code or '0'} ({meta.get('titel')})")
            except Exception:                        # noqa: BLE001
                print(f"[plugins] {datei.name} konnte nicht geladen werden:")
                traceback.print_exc()

    def hat(self, code: str) -> bool:
        return code in self.plugins

    async def ausfuehren(self, code: str, ctx: dict) -> str:
        p = self.plugins[code]
        p.aufrufe += 1

        if p.frisch:
            return p.zwischenspeicher or ""

        try:
            ergebnis = p.rendern(ctx)
            if inspect.isawaitable(ergebnis):
                ergebnis = await ergebnis
            text = str(ergebnis).strip()
            p.merken(text)
            p.fehler = None
            return text
        except Exception as fehler:                  # noqa: BLE001
            p.fehler = f"{type(fehler).__name__}: {fehler}"
            print(f"[plugins] {p.datei} Fehler: {p.fehler}")
            if p.zwischenspeicher:
                return p.zwischenspeicher
            return "Gerade nicht verfuegbar."

    def uebersicht(self) -> List[dict]:
        return [
            {
                "code": p.code,
                "titel": p.titel,
                "datei": p.datei,
                "cache": p.cache,
                "aufrufe": p.aufrufe,
                "fehler": p.fehler,
            }
            for p in sorted(self.plugins.values(), key=lambda x: x.code)
        ]
