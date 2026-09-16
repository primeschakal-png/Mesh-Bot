"""Wetter fuer Heiligenhaus.

Quelle ist Open-Meteo, frei und ohne Schluessel. Der eigentliche Mehrwert
eines Mesh-Bots: wer ueber Funk fragt, hat meistens gerade kein Internet.

Zwischengespeichert wird zehn Minuten. Drei Anfragen hintereinander sollen
nicht drei Abrufe ausloesen.
"""

import httpx

SEITE = {
    "code": "21",
    "titel": "Jetzt",
    "cache": 600,
}

BREITE = 51.3267
LAENGE = 6.9722

# Open-Meteo WMO-Codes, auf kurze deutsche Begriffe eingedampft
WETTERLAGE = {
    0: "klar", 1: "heiter", 2: "wolkig", 3: "bedeckt",
    45: "Nebel", 48: "Reifnebel",
    51: "Spruehregen", 53: "Spruehregen", 55: "Spruehregen",
    56: "gefr Spruehregen", 57: "gefr Spruehregen",
    61: "Regen leicht", 63: "Regen", 65: "Regen stark",
    66: "gefr Regen", 67: "gefr Regen stark",
    71: "Schnee leicht", 73: "Schnee", 75: "Schnee stark", 77: "Schneegriesel",
    80: "Schauer", 81: "Schauer", 82: "Schauer stark",
    85: "Schneeschauer", 86: "Schneeschauer",
    95: "Gewitter", 96: "Gewitter Hagel", 99: "Gewitter Hagel",
}

WINDRICHTUNG = ["N", "NO", "O", "SO", "S", "SW", "W", "NW"]


def _richtung(grad: float) -> str:
    return WINDRICHTUNG[int((grad + 22.5) // 45) % 8]


async def rendern(ctx) -> str:
    url = "https://api.open-meteo.com/v1/forecast"
    parameter = {
        "latitude": BREITE,
        "longitude": LAENGE,
        "current": "temperature_2m,weather_code,wind_speed_10m,wind_direction_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "Europe/Berlin",
        "forecast_days": 2,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        antwort = await client.get(url, params=parameter)
        antwort.raise_for_status()
        daten = antwort.json()

    jetzt = daten["current"]
    tag = daten["daily"]

    lage = WETTERLAGE.get(int(jetzt["weather_code"]), "?")
    temp = round(jetzt["temperature_2m"])
    wind = round(jetzt["wind_speed_10m"])
    ri = _richtung(jetzt["wind_direction_10m"])

    morgen_max = round(tag["temperature_2m_max"][1])
    morgen_min = round(tag["temperature_2m_min"][1])
    regen = tag["precipitation_probability_max"][1]

    return (
        f"{ctx['nr']} {temp}C {lage} Wind {wind}km/h {ri}\n"
        f"Morgen {morgen_min}/{morgen_max}C Regen {regen}%"
    )
