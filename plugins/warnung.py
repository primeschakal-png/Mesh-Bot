"""Unwetterwarnung des DWD.

Bezogen ueber Bright Sky, einen freien Zugang zu den offenen DWD-Daten ohne
Schluessel und ohne Registrierung.

Fuer jemanden ohne Mobilfunkempfang ist das die nuetzlichste Zeile, die ein
Mesh-Bot liefern kann. Deshalb bewusst knapp: Stufe, Ereignis, Ende.
"""

import httpx

SEITE = {
    "code": "22",
    "titel": "Warnung",
    "cache": 300,
}

BREITE = 51.3267
LAENGE = 6.9722

# DWD-Warnstufen
STUFE = {
    1: "Wetterwarnung",
    2: "Markantes Wetter",
    3: "Unwetter",
    4: "Extremes Unwetter",
}


def _uhrzeit(iso: str) -> str:
    """2026-09-16T18:00:00+02:00 -> 18:00"""
    if not iso or "T" not in iso:
        return ""
    return iso.split("T", 1)[1][:5]


async def rendern(ctx) -> str:
    url = "https://api.brightsky.dev/alerts"
    async with httpx.AsyncClient(timeout=10) as client:
        antwort = await client.get(url, params={"lat": BREITE, "lon": LAENGE})
        antwort.raise_for_status()
        daten = antwort.json()

    warnungen = daten.get("alerts") or []
    if not warnungen:
        return f"{ctx['nr']} Keine Warnung fuer Heiligenhaus."

    # Schwerste zuerst
    warnungen.sort(key=lambda w: w.get("severity_level", 0) or 0, reverse=True)
    w = warnungen[0]

    stufe = STUFE.get(int(w.get("severity_level", 1) or 1), "Warnung")
    ereignis = (w.get("event_de") or w.get("event_en") or "?").strip()
    bis = _uhrzeit(w.get("expires") or "")

    zeile = f"{ctx['nr']} {stufe}: {ereignis}"
    if bis:
        zeile += f" bis {bis}"
    if len(warnungen) > 1:
        zeile += f" (+{len(warnungen) - 1})"

    return zeile
