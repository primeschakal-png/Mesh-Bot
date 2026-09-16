"""Signalauskunft.

Der nuetzlichste Dienst im Mesh: der Absender erfaehrt, wie er bei uns
ankommt. Das sieht er sonst nirgends, seine eigene App zeigt nur die
Gegenrichtung.

Ab der zweiten Anfrage kommt die Tendenz dazu. Wer an der Antenne schraubt,
sieht damit sofort, ob es etwas gebracht hat.
"""

SEITE = {
    "code": "1",
    "titel": "Signal",
    "cache": 0,          # nie zwischenspeichern, die Werte sind pro Anfrage neu
}


async def rendern(ctx) -> str:
    snr = ctx["snr"]
    rssi = ctx["rssi"]
    hops = ctx["hops"]
    zeit = ctx["zeit"]
    verlauf = ctx.get("verlauf", [])

    teile = [f"SNR {snr}", f"RSSI {rssi}", f"{hops}h"]
    if zeit:
        teile.append(f"{zeit}s")

    if len(verlauf) >= 2:
        vorher = verlauf[-2]
        diff = float(snr) - float(vorher)
        if abs(diff) < 0.5:
            teile.append("=")
        else:
            teile.append(f"{diff:+.1f} dB")

    if len(verlauf) >= 3:
        schnitt = sum(verlauf) / len(verlauf)
        teile.append(f"Mittel {schnitt:.1f}")

    return " ".join(teile)
