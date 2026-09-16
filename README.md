# Mesh-Bot

Ein Bot für [MeshCore](https://meshcore.co.uk) auf 868 MHz, Standort Heiligenhaus.

Er antwortet ausschließlich auf Direktnachrichten. Im öffentlichen Kanal
schweigt er, abgesehen von einer seltenen Ansage, dass es ihn gibt. Vorbild
sind die alten XDCC-Bots im IRC: einmal melden, danach läuft alles privat.

## Warum das so gebaut ist

LoRa hat zwei harte Grenzen, und die bestimmen jede Entscheidung im Code.

Eine Nachricht fasst rund **200 Byte**. Das ist keine Empfehlung, sondern eine
Wand. Jede Ausgabe wird deshalb beim Entwerfen gegen dieses Limit geprüft.

Der Kanal ist geteilt. In EU868 gilt **10 % Duty Cycle**, und auf LongFast
belegt ein volles Paket rund zwei Sekunden Luftzeit. Ein einzelner Knoten kann
damit knapp 36 kB pro Stunde senden, das ganze Netz zusammen nicht viel mehr.
Deshalb: Antworten statt Senden. Wer etwas wissen will, fragt.

Bedient wird wie Videotext. Man fordert eine Nummer an und bekommt sie. Wie
bei den alten Handy-Menüs kann man sich durchklicken oder die Ziffernfolge
direkt eingeben, also `2`, dann `1`, oder gleich `21`. Es gibt keinen
Sitzungszustand, jede Anfrage steht für sich.

## Start

```bash
pip install -r requirements.txt

python bot.py                       # offline, nur Tastatur
python bot.py --port COM7           # echter Node, startet im Mitlesen
python bot.py --port COM7 --scharf  # sofort scharf
```

Oberfläche danach unter <http://localhost:8080>.

Auf dem Node muss die **Unified-Companion-Firmware** laufen, nicht Repeater.
Die Bibliothek spricht nur mit Companions. Unter Linux ist der Port meist
`/dev/ttyACM0` oder `/dev/ttyUSB0`.

## Betriebsarten

| Modus | Empfang | Senden |
|---|---|---|
| offline | nur aus der Oberfläche | nichts geht raus |
| mitlesen | echt | wird nur protokolliert |
| scharf | echt | geht raus |

Umschalten im Browser, ohne Neustart. **Mitlesen** ist der letzte Test vor dem
Scharfschalten: echte Absender, echte Signalwerte, aber niemand im Netz merkt
etwas.

## Aufbau

```
bot.py              Einstieg, Modi, Webserver, WebSocket
core/bot.py         die Logik, kennt weder Funk noch Browser
core/seiten.py      Seitenbaum, Nummern, Platzhalter
core/transport.py   Attrappe und serielle Anbindung
core/plugins.py     Plugin-Lader mit Cache und Fehlerabfang
core/funk.py        Airtime und Duty Cycle
plugins/            ein Thema pro Datei
web/index.html      die Oberfläche
seiten.json         die Menüstruktur
```

Der Browser ist nur ein Fenster auf den laufenden Prozess. Tab zumachen heißt
nicht, dass der Bot aufhört.

## Seiten

Statische Seiten stehen in `seiten.json` und lassen sich in der Oberfläche
bearbeiten. Die Nummer ist der Weg: `2` ist ein Menüpunkt, `24` sein vierter
Unterpunkt. Bleibt der Text leer, baut der Bot automatisch die Liste der
Unterpunkte.

In jeden Text lassen sich Platzhalter setzen:

`{snr}` `{rssi}` `{hops}` `{zeit}` `{uhr}` `{name}` `{nr}` `{menue}`

## Plugins

Dynamische Seiten kommen aus `plugins/`, eine Datei pro Thema, ähnlich einem
Userscript in Tampermonkey. Ein Kopfblock mit den Metadaten, darunter die
Funktion:

```python
SEITE = {
    "code":  "23",       # Nummer im Seitenbaum
    "titel": "Pegel",    # erscheint in der Menüzeile
    "cache": 900,        # Sekunden, 0 heißt nicht zwischenspeichern
}

async def rendern(ctx) -> str:
    return "23 Ruhr 1.24m, steigend"
```

Ein Plugin hat Vorrang vor der statischen Seite mit derselben Nummer. Stürzt
es ab, weil eine API nicht antwortet, fängt der Lader das ab und gibt den
letzten zwischengespeicherten Wert aus, sonst eine kurze Fehlerzeile. Der Bot
fällt nicht um.

Der Cache ist kein Luxus. Drei Anfragen hintereinander sollen nicht drei
Abrufe auslösen.

Mitgeliefert sind drei:

**`signal.py`** auf `1` meldet SNR, RSSI, Hops und Laufzeit zurück, ab der
zweiten Anfrage mit Tendenz. Das ist der nützlichste Dienst im Mesh, weil der
Absender diese Richtung sonst nirgends sieht. Wer an der Antenne schraubt,
merkt damit sofort, ob es etwas gebracht hat.

**`wetter.py`** auf `21` holt aktuelle Lage und Morgen von Open-Meteo.

**`warnung.py`** auf `22` holt die DWD-Unwetterwarnung über Bright Sky. Für
jemanden ohne Mobilfunkempfang ist das die nützlichste Zeile überhaupt.

Beide Wetterquellen sind frei und brauchen keinen Schlüssel.

## Stand

Die Logik, die Oberfläche und das Signal-Plugin sind getestet. Die beiden
Wetter-Plugins sind gegen die dokumentierten Schnittstellen geschrieben, aber
noch nicht gegen die echten Endpunkte gelaufen.

Ebenfalls ungetestet ist `SerialTransport`, weil dafür Hardware nötig ist. Die
Anbindung an `meshcore_py` ist bewusst an genau einer Stelle gekapselt: weichen
die Methodennamen in deiner Version ab, reicht eine Anpassung in
`core/transport.py`.

## Lizenz

MIT
