"""Reine Logik ohne Geraetezugriff: Medium aus IPP lesen, Etikett layouten und rendern.

Alles hier ist ohne Drucker testbar. Der Geraetezugriff liegt in ipp.py und cups.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DPI = 300
RAND_PX = 18          # Innenabstand zum Rand des Etiketts
ZEILENABSTAND = 0.22  # Anteil der Schrifthoehe
MAX_ZEILEN = 6

# Obergrenze der Schrift (px bei 300 dpi). "gross" fuellt die Rollenbreite ganz aus;
# auf einer Endlosrolle wird das Etikett dann entsprechend lang (Schimmi 29.10.: „Riesenetikett").
GROESSEN = {"klein": 50, "mittel": 80, "gross": 10_000}  # ~4 mm / ~7 mm Versalhoehe / unbegrenzt

# Schriften in dieser Reihenfolge versuchen; DRUCKER_SCHRIFT (Umgebung) hat Vorrang.
SCHRIFTEN = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


@dataclass(frozen=True)
class Medium:
    breite_mm: float
    laenge_mm: float | None  # None = Endlosrolle, Laenge frei
    roh: str

    @property
    def endlos(self) -> bool:
        return self.laenge_mm is None

    def text(self) -> str:
        if self.endlos:
            return f"{self.breite_mm:g} mm endlos (Länge frei)"
        return f"{self.breite_mm:g} × {self.laenge_mm:g} mm vorgestanzt"


_MASS = re.compile(r"(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)mm$")


def medium_aus_ipp(media_ready: str) -> Medium:
    """IPP-Keyword media-ready -> Medium.

    Beispiele (Brother QL-820NWB): 'roll_current_38x0mm' = 38 mm endlos,
    'om_brother-label-29x90mm_29x90mm' bzw. '..._38x90mm' = vorgestanzt.
    Laenge 0 bedeutet Endlosrolle.
    """
    m = _MASS.search(media_ready.strip())
    if not m:
        raise ValueError(f"Unbekanntes Medienformat vom Drucker: {media_ready!r}")
    breite, laenge = float(m[1]), float(m[2])
    if breite <= 0:
        raise ValueError(f"Medium ohne Breite: {media_ready!r}")
    return Medium(breite, None if laenge == 0 else laenge, media_ready)


def mm_zu_px(mm: float) -> int:
    return round(mm / 25.4 * DPI)


def ersetze_platzhalter(zeile: str, heute: date | None = None) -> str:
    """{datum} -> heutiges Datum TT.MM.JJJJ (praktisch fuer Einmach- und Vorratsetiketten)."""
    return zeile.replace("{datum}", (heute or date.today()).strftime("%d.%m.%Y"))


def _schrift(groesse: int, pfad: str | None = None) -> ImageFont.FreeTypeFont:
    for p in ([pfad] if pfad else []) + SCHRIFTEN:
        if p and Path(p).is_file():
            return ImageFont.truetype(p, groesse)
    return ImageFont.load_default(size=groesse)


@dataclass(frozen=True)
class Layout:
    breite_px: int      # quer zur Laufrichtung = Rollenbreite
    laenge_px: int      # in Laufrichtung
    schriftgroesse: int
    laenge_mm: float
    qr_px: int = 0      # Kantenlaenge des QR-Codes, 0 = keiner
    quer: bool = False  # Text laeuft quer zur Rolle (Etikett kurz, Rollenbreite = Textbreite)


def layout(zeilen: list[str], medium: Medium, laenge_mm: float | None = None,
           qr: bool = False, schrift: str | None = None, groesse: str = "mittel") -> Layout:
    """Groesste Schrift, bei der alle Zeilen auf das Etikett passen.

    Gerendert wird quer (Text laeuft entlang der Rolle): die Rollenbreite ist die HOEHE des
    Textblocks, die Laenge ergibt sich bei Endlosrollen aus dem Text.
    """
    zeilen = [z for z in zeilen if z.strip()]
    if not zeilen:
        raise ValueError("Kein Text: mindestens eine nicht-leere Zeile angeben.")
    if len(zeilen) > MAX_ZEILEN:
        raise ValueError(f"Höchstens {MAX_ZEILEN} Zeilen, bekommen: {len(zeilen)}.")
    if groesse not in GROESSEN:
        raise ValueError(f"groesse muss eines von {', '.join(GROESSEN)} sein, nicht {groesse!r}.")
    if laenge_mm is not None and laenge_mm <= 0:
        raise ValueError("laenge_mm muss positiv sein.")
    if not medium.endlos:
        if laenge_mm is not None and abs(laenge_mm - medium.laenge_mm) > 0.5:
            raise ValueError(f"Eingelegt sind {medium.text()}; eine Länge von {laenge_mm:g} mm "
                             "ist damit nicht druckbar. laenge_mm weglassen.")
        laenge_mm = medium.laenge_mm

    hoehe = mm_zu_px(medium.breite_mm)
    nutz_h = hoehe - 2 * RAND_PX
    qr_min = min(mm_zu_px(15), nutz_h)  # unter 15 mm wird der Code mit dem Handy unzuverlaessig
    max_laenge = mm_zu_px(laenge_mm) if laenge_mm else None

    probe = Image.new("1", (1, 1))
    d = ImageDraw.Draw(probe)
    obergrenze = min(nutz_h, 220, GROESSEN[groesse])
    for groesse_px in range(obergrenze, 7, -1):
        f = _schrift(groesse_px, schrift)
        breiten = [d.textlength(z, font=f) for z in zeilen]
        block_h = groesse_px * len(zeilen) + groesse_px * ZEILENABSTAND * (len(zeilen) - 1)
        if block_h > nutz_h:
            continue
        qr_px = min(nutz_h, max(int(block_h), qr_min)) if qr else 0
        text_l = max(breiten)
        gesamt = int(text_l + qr_px + (RAND_PX if qr else 0) + 2 * RAND_PX)
        if max_laenge is not None and gesamt > max_laenge:
            continue
        laenge_px = max_laenge if max_laenge is not None else max(gesamt, hoehe)
        return Layout(hoehe, laenge_px, groesse_px, round(laenge_px / DPI * 25.4, 1), qr_px)
    raise ValueError("Text passt nicht aufs Etikett, auch nicht in kleinster Schrift. "
                     "Weniger Text oder (bei Endlosrolle) größere laenge_mm.")



def layout_quer(zeilen: list[str], medium: Medium, laenge_mm: float, qr: bool = False,
                schrift: str | None = None, groesse: str = "mittel") -> Layout:
    """Text quer zur Rolle: die Rollenbreite ist die Textbreite, laenge_mm die Hoehe.

    Fuer kurze Etiketten, die quer aufgeklebt werden (Schimmi 29.10.: 25 x 38 mm auf die Steckdose,
    die Flaeche ist nur 25 mm hoch und es soll nichts von Hand abgeschnitten werden). QR sitzt links.
    """
    zeilen = [z for z in zeilen if z.strip()]
    if not zeilen:
        raise ValueError("Kein Text: mindestens eine nicht-leere Zeile angeben.")
    if groesse not in GROESSEN:
        raise ValueError(f"groesse muss eines von {', '.join(GROESSEN)} sein, nicht {groesse!r}.")
    if not medium.endlos:
        raise ValueError(f"quer geht nur auf Endlosrollen; eingelegt sind {medium.text()}.")
    if not 10 <= laenge_mm <= 100:
        raise ValueError("Bei quer muss laenge_mm zwischen 10 und 100 mm liegen (das ist die Etikett-Höhe).")
    breite = mm_zu_px(medium.breite_mm)
    hoehe = mm_zu_px(laenge_mm)
    nutz_h = hoehe - 2 * RAND_PX
    qr_px = min(nutz_h, mm_zu_px(15)) if qr else 0
    nutz_b = breite - 2 * RAND_PX - (qr_px + RAND_PX if qr else 0)
    probe = ImageDraw.Draw(Image.new("1", (1, 1)))
    for g in range(min(nutz_h, 220, GROESSEN[groesse]), 7, -1):
        f = _schrift(g, schrift)
        block_h = g * len(zeilen) + g * ZEILENABSTAND * (len(zeilen) - 1)
        if block_h <= nutz_h and max(probe.textlength(z, font=f) for z in zeilen) <= nutz_b:
            return Layout(breite, hoehe, g, float(laenge_mm), qr_px, True)
    raise ValueError("Text passt quer nicht aufs Etikett. Weniger Text, ohne QR oder größere laenge_mm.")

def rendern(zeilen: list[str], medium: Medium, ziel: Path, laenge_mm: float | None = None,
            qr_text: str | None = None, rahmen: bool = False,
            schrift: str | None = None, groesse: str = "mittel", quer: bool = False) -> Layout:
    """Etikett als 1-Bit-PNG: ziel quer zum Ansehen, druckdatei(ziel) hochkant (Breite = Rolle) fuer CUPS."""
    zeilen = [ersetze_platzhalter(z) for z in zeilen if z.strip()]
    if quer:
        if laenge_mm is None:
            raise ValueError("quer braucht laenge_mm (Etikett-Höhe, z. B. 25).")
        return _rendern_quer(zeilen, medium, ziel, laenge_mm, qr_text, rahmen, schrift, groesse)
    lay = layout(zeilen, medium, laenge_mm, qr=bool(qr_text), schrift=schrift, groesse=groesse)
    f = _schrift(lay.schriftgroesse, schrift)
    quer = Image.new("1", (lay.laenge_px, lay.breite_px), 1)
    d = ImageDraw.Draw(quer)

    x0 = RAND_PX
    if qr_text:
        import qrcode
        seite = lay.qr_px
        q = qrcode.make(qr_text, border=1).convert("1").resize((seite, seite), Image.NEAREST)
        quer.paste(q, (RAND_PX, (lay.breite_px - seite) // 2))
        x0 = RAND_PX + seite + RAND_PX

    zeilen_h = lay.schriftgroesse * (1 + ZEILENABSTAND)
    block_h = lay.schriftgroesse * len(zeilen) + lay.schriftgroesse * ZEILENABSTAND * (len(zeilen) - 1)
    y = (lay.breite_px - block_h) / 2
    mitte_x = x0 + (lay.laenge_px - RAND_PX - x0) / 2
    for z in zeilen:
        d.text((mitte_x, y + lay.schriftgroesse / 2), z, font=f, fill=0, anchor="mm")
        y += zeilen_h
    if rahmen:
        d.rectangle((3, 3, lay.laenge_px - 4, lay.breite_px - 4), outline=0, width=4)

    ziel.parent.mkdir(parents=True, exist_ok=True)
    quer.save(ziel)
    quer.rotate(90, expand=True).save(druckdatei(ziel))
    return lay


def _rendern_quer(zeilen, medium, ziel, laenge_mm, qr_text, rahmen, schrift, groesse) -> Layout:
    lay = layout_quer(zeilen, medium, laenge_mm, qr=bool(qr_text), schrift=schrift, groesse=groesse)
    f = _schrift(lay.schriftgroesse, schrift)
    bild = Image.new("1", (lay.breite_px, lay.laenge_px), 1)  # Breite = Rolle, schon druckfertig
    d = ImageDraw.Draw(bild)
    x0 = RAND_PX
    if qr_text:
        import qrcode
        q = qrcode.make(qr_text, border=1).convert("1").resize((lay.qr_px, lay.qr_px), Image.NEAREST)
        bild.paste(q, (RAND_PX, (lay.laenge_px - lay.qr_px) // 2))
        x0 = RAND_PX + lay.qr_px + RAND_PX
    g = lay.schriftgroesse
    block_h = g * len(zeilen) + g * ZEILENABSTAND * (len(zeilen) - 1)
    y = (lay.laenge_px - block_h) / 2
    mitte_x = x0 + (lay.breite_px - RAND_PX - x0) / 2
    for z in zeilen:
        d.text((mitte_x, y + g / 2), z, font=f, fill=0, anchor="mm")
        y += g * (1 + ZEILENABSTAND)
    if rahmen:
        d.rectangle((3, 3, lay.breite_px - 4, lay.laenge_px - 4), outline=0, width=4)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    bild.save(ziel)
    bild.save(druckdatei(ziel))
    return lay


def druckdatei(vorschau: Path) -> Path:
    return vorschau.with_name(vorschau.stem + "-druck.png")


def cups_optionen_etikett(medium: Medium, lay: Layout) -> list[str]:
    """lp-Optionen fuer den Etikettendruck: Seitengroesse = Rolle, Schnitt nach dem Auftrag."""
    laenge = lay.laenge_mm if medium.endlos else medium.laenge_mm
    return ["-o", f"PageSize=Custom.{medium.breite_mm:g}x{laenge:g}mm",
            "-o", "fit-to-page", "-o", "CutMedia=EndOfJob"]


def cups_optionen_dokument(farbe: bool, duplex: bool, seiten: str | None, kopien: int) -> list[str]:
    if kopien < 1 or kopien > 50:
        raise ValueError("kopien muss zwischen 1 und 50 liegen.")
    opt = ["-n", str(kopien),
           "-o", "print-color-mode=" + ("color" if farbe else "monochrome"),
           "-o", "sides=" + ("two-sided-long-edge" if duplex else "one-sided")]
    if seiten:
        if not re.fullmatch(r"\d+(-\d+)?(,\d+(-\d+)?)*", seiten.replace(" ", "")):
            raise ValueError(f"Seitenbereich nicht lesbar: {seiten!r} (Beispiel: '1-3,5').")
        opt += ["-o", "page-ranges=" + seiten.replace(" ", "")]
    return opt


# ── Umfangsgrenze für Dokumentdruck ─────────────────────────────────────────
# Ohne Grenze könnte ein einzelner (z. B. per Prompt-Injection ausgelöster) Aufruf
# ein langes PDF × 50 drucken. Über der Grenze braucht es eine ausdrückliche Bestätigung.
MAX_SEITEN_OHNE_BESTAETIGUNG = 20


def seiten_im_bereich(seiten: str | None, gesamt: int) -> int:
    """Anzahl der Seiten, die ein Bereich wie '1-3,5' aus einem Dokument mit `gesamt` Seiten druckt."""
    if gesamt < 0:
        raise ValueError("Seitenzahl negativ.")
    if not seiten:
        return gesamt
    gewaehlt: set[int] = set()
    for teil in seiten.replace(" ", "").split(","):
        a, _, b = teil.partition("-")
        von, bis = int(a), int(b) if b else int(a)
        if von > bis:
            von, bis = bis, von
        gewaehlt.update(n for n in range(von, bis + 1) if 1 <= n <= gesamt)
    return len(gewaehlt)


def pruefe_umfang(seiten_gesamt: int, seiten: str | None, kopien: int, bestaetigt: bool,
                  grenze: int = MAX_SEITEN_OHNE_BESTAETIGUNG) -> int:
    """Gibt die Zahl der Druckseiten zurück; wirft ValueError, wenn sie die Grenze ohne Bestätigung übersteigt."""
    umfang = seiten_im_bereich(seiten, seiten_gesamt) * kopien
    if umfang > grenze and not bestaetigt:
        raise ValueError(
            f"Großer Druckauftrag: {umfang} Seiten ({seiten_im_bereich(seiten, seiten_gesamt)} Seiten × {kopien} "
            f"Kopien), Grenze ohne Bestätigung {grenze}. Erst den Nutzer fragen, dann mit bestaetigt=True erneut aufrufen.")
    return umfang
