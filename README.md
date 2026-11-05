# drucker-mcp-server

MCP-Server für CUPS-Drucker. Er druckt **Etiketten passend zur eingelegten Rolle** (getestet mit Brother QL-820NWB) und **Dokumente** (PDF, Markdown, HTML) auf einem normalen Drucker. Ein Satz wie „Druck mir ein Etikett *Salz-Dillgurken* mit Datum“ reicht.

Vor jedem Etikettendruck fragt der Server den Drucker per IPP, welche Rolle eingelegt ist, und baut das Layout danach:

| Rolle (Drucker meldet) | Layout |
|---|---|
| Endlos, z. B. `roll_current_38x0mm` | Höhe = Rollenbreite, Länge ergibt sich aus dem Text (oder `laenge_mm`) |
| Vorgestanzt, z. B. `…_38x90mm` | feste Größe; ein Auftrag mit anderer Länge wird **nicht** gedruckt |

Die Schriftgröße wählt man über `groesse`: `klein` (~4 mm), `mittel` (~7 mm, Standard) oder `gross` (füllt die Rollenbreite). Auf einer Endlosrolle legt sie damit auch die Länge fest. Mit `laenge_mm` gibt man stattdessen eine feste Länge vor, die Schrift passt sich dann an. Mit `quer=true` läuft der Text quer zur Rolle; `laenge_mm` ist dann die Höhe des Etiketts. So entstehen kurze Etiketten wie 25 × 38 mm für schmale Klebeflächen (z. B. Steckdosen), ohne Nachschneiden. Ein QR-Code wächst mit dem Text, ist aber nie kleiner als 15 mm. In jeder Zeile wird `{datum}` durch das heutige Datum ersetzt.

## Werkzeuge

| Tool | Wirkung |
|---|---|
| `drucker_liste` | alle CUPS-Drucker mit Status, beim Etikettendrucker die eingelegte Rolle |
| `etikett_rolle` | liest die eingelegte Rolle (Breite, endlos/vorgestanzt) |
| `etikett_vorschau` | rendert das Etikett als PNG, **ohne zu drucken** |
| `etikett_drucken` | druckt 1–20 Kopien; Zeilen, Größe, optional feste Länge, QR-Code und Rahmen |
| `datei_drucken` | PDF/Markdown/HTML, Farbe oder SW, Duplex, Seitenbereich, Kopien; Markdown/HTML wird per Chrome headless zu A4-PDF. Über 20 Druckseiten (Seiten × Kopien) nur mit `bestaetigt=True` |
| `druckauftraege` | offene Aufträge (z. B. wenn ein Drucker aus ist) |
| `druckauftrag_abbrechen` | offenen Auftrag abbrechen |

Die Server-Anweisung verlangt: Drucken nur auf ausdrücklichen Auftrag, bei Etiketten zuerst die Vorschau.

## Voraussetzungen

- CUPS mit eingerichteten Druckern (`lp`, `lpstat`, `cancel`). Unter macOS ist das eingebaut.
- Etikettendrucker mit IPP (Brother QL-8xxNWB und die meisten Netzwerk-Etikettendrucker). Ist die CUPS-Queue eine Bonjour-Adresse (`dnssd://…`), löst der Server sie selbst auf.
- Für Markdown/HTML: Google Chrome oder Chromium.

## Betrieb

```
uv sync
uv run pytest            # Tests, darunter Muss-rot-Fälle (falsche Rolle, unlesbares Medium, Collection-Parsing)
claude mcp add drucker -s user \
  -e DRUCKER_ETIKETT=Brother_QL_820NWB \
  -e DRUCKER_DOKUMENT=HP_Color_LaserJet_Pro_MFP_3302 \
  -- uv run --directory <pfad> drucker-mcp
```

Die Queue-Namen zeigt `lpstat -p`.

| Variable | Bedeutung |
|---|---|
| `DRUCKER_ETIKETT` | CUPS-Queue des Etikettendruckers (Pflicht für Etiketten) |
| `DRUCKER_ETIKETT_URI` | `ipp://host:631/ipp/print`, falls die Queue keine ipp/dnssd-Adresse hat |
| `DRUCKER_DOKUMENT` | Queue für Dokumente (sonst CUPS-Standarddrucker) |
| `DRUCKER_AUSGABE` | Ordner für Vorschauen und PDFs (Standard `~/.cache/drucker-mcp`) |
| `DRUCKER_SCHRIFT` | TTF für Etiketten (Standard: Arial Bold bzw. DejaVu Sans Bold) |
| `DRUCKER_CHROME` | Pfad zu Chrome/Chromium |

## Warum IPP und nicht der Brother-Rasterstatus

Der Brother-Rasterbefehl `ESC i S` über Port 9100 bleibt im Netzwerkbetrieb stumm. Auch CUPS liefert `media-ready` für eine Bonjour-Queue nicht. Der Drucker selbst beantwortet `Get-Printer-Attributes` aber sauber (`media-ready`, `media-col-ready`). Der Server spricht das mit einem kleinen IPP-Client in reinem Python, ohne `ipptool`.

Kein Docker-Image: Der Server braucht das CUPS des Hosts.

## Lizenz

MIT
