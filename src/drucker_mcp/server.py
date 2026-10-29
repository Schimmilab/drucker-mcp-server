"""Drucker-MCP-Server: Etiketten und Dokumente ueber CUPS drucken.

Etiketten (Brother QL & Co.): vor jedem Druck wird per IPP gelesen, welche Rolle eingelegt ist,
und das Layout danach gebaut. Endlosrolle -> Laenge ergibt sich aus dem Text; vorgestanzt ->
feste Groesse; passt der Auftrag nicht zur Rolle, wird nicht gedruckt.
Dokumente: PDF direkt, Markdown/HTML ueber Chrome headless nach PDF.

Konfiguration ueber Umgebungsvariablen, nichts ist fest verdrahtet:
  DRUCKER_ETIKETT       CUPS-Queue des Etikettendruckers (Pflicht fuer Etiketten)
  DRUCKER_ETIKETT_URI   ipp://host:631/ipp/print, falls die Queue keine dnssd/ipp-Adresse hat
  DRUCKER_DOKUMENT      CUPS-Queue fuer Dokumente (sonst CUPS-Standarddrucker)
  DRUCKER_AUSGABE       Ordner fuer Vorschauen/PDFs (Standard: ~/.cache/drucker-mcp)
  DRUCKER_SCHRIFT       TTF-Datei fuer Etiketten
  DRUCKER_CHROME        Pfad zu Chrome/Chromium fuer Markdown -> PDF
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from fastmcp import FastMCP

from drucker_mcp import cups, ipp, logik

AUSGABE = Path(os.environ.get("DRUCKER_AUSGABE") or Path.home() / ".cache" / "drucker-mcp")

mcp = FastMCP(
    "drucker",
    instructions=(
        "Druckt über CUPS: Etiketten auf einem Etikettendrucker (z. B. Brother QL) und Dokumente "
        "(PDF, Markdown) auf einem normalen Drucker. "
        "⛔ Drucken verbraucht Material und ist nicht rückgängig zu machen: drucke nur auf ausdrücklichen "
        "Auftrag. Bei Etiketten zuerst etikett_vorschau aufrufen, die PNG-Datei zeigen bzw. beschreiben, "
        "und erst nach Bestätigung etikett_drucken. "
        "Die eingelegte Etikettenrolle wird vor jedem Druck vom Drucker gelesen; passt der Auftrag nicht "
        "zur Rolle, bricht der Server ab. In Zeilen wird {datum} durch das heutige Datum ersetzt."
    ),
)


def _etikett_queue() -> str:
    q = os.environ.get("DRUCKER_ETIKETT")
    if not q:
        raise RuntimeError("DRUCKER_ETIKETT ist nicht gesetzt (CUPS-Queue des Etikettendruckers, "
                           "siehe drucker_liste).")
    return q


def _etikett_uri() -> str:
    if os.environ.get("DRUCKER_ETIKETT_URI"):
        return os.environ["DRUCKER_ETIKETT_URI"]
    dev = cups.device_uri(_etikett_queue())
    if dev.startswith(("ipp://", "ipps://")):
        return dev
    dienst = ipp.dnssd_dienstname(dev)
    if dienst:
        return ipp.dnssd_aufloesen(dienst)
    raise RuntimeError(f"Queue-Adresse {dev!r} ist weder ipp noch dnssd; DRUCKER_ETIKETT_URI setzen.")


def _medium() -> logik.Medium:
    attrs = ipp.drucker_attribute(_etikett_uri(), ["media-ready", "printer-state-reasons"])
    bereit = attrs.get("media-ready") or []
    if not bereit:
        gruende = ", ".join(map(str, attrs.get("printer-state-reasons", []))) or "keine Angabe"
        raise RuntimeError(f"Drucker meldet keine eingelegte Rolle (Status: {gruende}).")
    return logik.medium_aus_ipp(str(bereit[0]))


_zaehler = 0


def _vorschau(zeilen, laenge_mm, qr, rahmen, groesse, quer=False) -> tuple[logik.Medium, logik.Layout, Path]:
    medium = _medium()
    # Millisekunden + Prozess-Zaehler: mehrere Vorschauen in derselben Sekunde ueberschrieben sich (29.10.)
    global _zaehler
    _zaehler += 1
    ziel = AUSGABE / f"etikett-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}-{_zaehler}.png"
    lay = logik.rendern(zeilen, medium, ziel, laenge_mm=laenge_mm, qr_text=qr or None, groesse=groesse, quer=quer,
                        rahmen=rahmen, schrift=os.environ.get("DRUCKER_SCHRIFT"))
    return medium, lay, ziel


def _beschreibung(medium: logik.Medium, lay: logik.Layout, ziel: Path) -> str:
    return (f"Rolle: {medium.text()}\nEtikett: {medium.breite_mm:g} × {lay.laenge_mm:g} mm{', Text quer' if lay.quer else ''}, "
            f"Schrift {lay.schriftgroesse} px\nVorschau: file://{ziel}")


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def drucker_liste() -> str:
    """Alle CUPS-Drucker mit Status; beim Etikettendrucker zusätzlich die eingelegte Rolle."""
    zeilen = ["| Drucker | Status | Rolle |", "|---|---|---|"]
    etikett = os.environ.get("DRUCKER_ETIKETT")
    for d in cups.drucker():
        rolle = ""
        if d["name"] == etikett:
            try:
                rolle = _medium().text()
            except Exception as e:  # Drucker aus: Liste trotzdem zeigen
                rolle = f"nicht lesbar: {e}"
        name = d["name"] + (" (Standard)" if d["standard"] else "")
        zeilen.append(f"| {name} | {d['status']} | {rolle} |")
    return "\n".join(zeilen)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def etikett_rolle() -> str:
    """Liest vom Etikettendrucker, welche Rolle gerade eingelegt ist (Breite, endlos oder vorgestanzt)."""
    m = _medium()
    return f"{m.text()} (Drucker meldet: {m.roh})"


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def etikett_vorschau(zeilen: list[str], groesse: str = "mittel", laenge_mm: float | None = None,
                     quer: bool = False, qr: str = "",
                     rahmen: bool = False) -> str:
    """Rendert ein Etikett passend zur eingelegten Rolle als PNG, OHNE zu drucken.

    zeilen: 1–6 Textzeilen. {datum} = heute.
    groesse: Schrift-Obergrenze 'klein' (~4 mm), 'mittel' (~7 mm, Standard) oder 'gross' (füllt die
      Rollenbreite). Auf Endlosrollen bestimmt sie damit auch die Länge des Etiketts.
    laenge_mm: feste Länge, nur bei Endlosrolle; die Schrift wird dann so groß wie hineinpasst.
    quer: Text quer zur Rolle, für kurze Etiketten, die quer aufgeklebt werden. laenge_mm ist dann
      die Etikett-Höhe (z. B. 25 → 25 × 38 mm auf der 38-mm-Rolle), kein Abschneiden nötig.
    qr: optionaler Inhalt für einen QR-Code links (z. B. eine URL).
    """
    return _beschreibung(*_vorschau(zeilen, laenge_mm, qr, rahmen, groesse, quer))


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False})
def etikett_drucken(zeilen: list[str], kopien: int = 1, groesse: str = "mittel",
                    laenge_mm: float | None = None, quer: bool = False, qr: str = "",
                    rahmen: bool = False) -> str:
    """Druckt ein Etikett auf dem Etikettendrucker – nur auf ausdrücklichen Auftrag, vorher etikett_vorschau.

    Gleiche Parameter wie etikett_vorschau, dazu kopien (1–20). Die Rolle wird vor dem Druck gelesen.
    """
    if not 1 <= kopien <= 20:
        raise ValueError("kopien muss zwischen 1 und 20 liegen.")
    medium, lay, ziel = _vorschau(zeilen, laenge_mm, qr, rahmen, groesse, quer)
    opt = logik.cups_optionen_etikett(medium, lay) + ["-n", str(kopien)]
    auftrag = cups.drucken(_etikett_queue(), str(logik.druckdatei(ziel)), opt, titel="Etikett: " + zeilen[0][:40])
    return f"Gedruckt: Auftrag {auftrag}, {kopien}×\n" + _beschreibung(medium, lay, ziel)


def _chrome() -> str:
    for p in [os.environ.get("DRUCKER_CHROME"),
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium",
              shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser")]:
        if p and Path(p).exists():
            return p
    raise RuntimeError("Kein Chrome/Chromium gefunden – DRUCKER_CHROME setzen.")


_CSS = """@page { size: A4; margin: 18mm 16mm; }
body { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.45; }
h1 { font-size: 18pt; } h2 { font-size: 14pt; margin-top: 1.2em; } table { border-collapse: collapse; }
td, th { border: 1px solid #999; padding: 3px 6px; } code, pre { font-size: 9.5pt; } img { max-width: 100%; }"""


def markdown_zu_pdf(quelle: Path, ziel: Path) -> Path:
    import markdown

    html = markdown.markdown(quelle.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, dir=quelle.parent,
                                     encoding="utf-8") as f:
        f.write(f"<!doctype html><meta charset='utf-8'><style>{_CSS}</style><body>{html}</body>")
        html_pfad = Path(f.name)
    try:
        return html_zu_pdf(html_pfad, ziel)
    finally:
        html_pfad.unlink(missing_ok=True)


def html_zu_pdf(quelle: Path, ziel: Path) -> Path:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([_chrome(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={ziel}", quelle.resolve().as_uri()],
                   capture_output=True, timeout=60, check=True)
    if not ziel.exists() or ziel.stat().st_size == 0:
        raise RuntimeError("Chrome hat kein PDF erzeugt.")
    return ziel


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False})
def datei_drucken(pfad: str, farbe: bool = False, duplex: bool = False, seiten: str = "",
                  kopien: int = 1, drucker: str = "") -> str:
    """Druckt PDF, Markdown (.md) oder HTML – nur auf ausdrücklichen Auftrag.

    Markdown/HTML wird vorher per Chrome headless zu einem A4-PDF. farbe=False druckt schwarz-weiß.
    seiten z. B. '1-3,5'. drucker leer = DRUCKER_DOKUMENT bzw. CUPS-Standard.
    """
    quelle = Path(pfad).expanduser()
    if not quelle.is_file():
        raise ValueError(f"Datei nicht gefunden: {quelle}")
    opt = logik.cups_optionen_dokument(farbe, duplex, seiten or None, kopien)
    endung = quelle.suffix.lower()
    if endung == ".pdf":
        druck = quelle
    elif endung in (".md", ".markdown"):
        druck = markdown_zu_pdf(quelle, AUSGABE / (quelle.stem + ".pdf"))
    elif endung in (".html", ".htm"):
        druck = html_zu_pdf(quelle, AUSGABE / (quelle.stem + ".pdf"))
    else:
        raise ValueError(f"Nicht unterstützt: {endung} (PDF, Markdown oder HTML).")
    queue = drucker or os.environ.get("DRUCKER_DOKUMENT") or None
    auftrag = cups.drucken(queue, str(druck), opt, titel=quelle.name)
    return (f"Gedruckt: Auftrag {auftrag} auf {queue or 'Standarddrucker'} "
            f"({'Farbe' if farbe else 'SW'}, {'duplex' if duplex else 'einseitig'}, {kopien}×)\n"
            f"Datei: file://{druck}")


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def druckauftraege() -> str:
    """Offene Druckaufträge aller Drucker (hängende Aufträge z. B. bei ausgeschaltetem Drucker)."""
    a = cups.auftraege()
    return "\n".join(a) if a else "Keine offenen Aufträge."


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
def druckauftrag_abbrechen(auftrag: str) -> str:
    """Bricht einen offenen Druckauftrag ab (ID aus druckauftraege, z. B. 'Brother_QL_820NWB-109')."""
    cups.abbrechen(auftrag)
    return f"Abgebrochen: {auftrag}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
