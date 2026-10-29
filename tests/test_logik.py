from datetime import date
from pathlib import Path

import pytest
from PIL import Image

from drucker_mcp import logik

ENDLOS = logik.medium_aus_ipp("roll_current_38x0mm")          # am Brother QL-820NWB gelesen
GESTANZT = logik.medium_aus_ipp("om_brother-label-38x90mm_38x90mm")


def test_endlosrolle_erkannt():
    assert ENDLOS.breite_mm == 38 and ENDLOS.endlos and ENDLOS.laenge_mm is None


def test_vorgestanzt_erkannt():
    assert GESTANZT.breite_mm == 38 and GESTANZT.laenge_mm == 90 and not GESTANZT.endlos


@pytest.mark.parametrize("roh", ["", "roll_current", "a4", "roll_current_0x0mm"])
def test_unbekanntes_medium_wird_abgelehnt(roh):
    # Negativkontrolle: ein unlesbares Medium darf nicht still als "irgendwas" durchgehen
    with pytest.raises(ValueError):
        logik.medium_aus_ipp(roh)


def test_endlos_laenge_waechst_mit_text():
    kurz = logik.layout(["Salz"], ENDLOS)
    lang = logik.layout(["Salz-Dillgurken aus dem Keller"], ENDLOS)
    assert lang.laenge_px > kurz.laenge_px
    assert kurz.breite_px == logik.mm_zu_px(38)


def test_endlos_nie_kuerzer_als_breit():
    assert logik.layout(["A"], ENDLOS).laenge_px >= logik.mm_zu_px(38)


def test_gestanzt_hat_feste_laenge():
    lay = logik.layout(["Kurz"], GESTANZT)
    assert lay.laenge_px == logik.mm_zu_px(90)


def test_gestanzt_falsche_laenge_wird_abgelehnt():
    # Negativkontrolle: Auftrag passt nicht zur eingelegten Rolle -> kein Druck
    with pytest.raises(ValueError, match="vorgestanzt"):
        logik.layout(["Kurz"], GESTANZT, laenge_mm=50)


def test_zu_viel_text_fuer_feste_laenge_wird_abgelehnt():
    with pytest.raises(ValueError, match="passt nicht"):
        logik.layout(["X" * 400], GESTANZT)


def test_leerer_text_wird_abgelehnt():
    with pytest.raises(ValueError):
        logik.layout(["", "  "], ENDLOS)


def test_mehr_zeilen_kleinere_schrift():
    eine = logik.layout(["Zeile"], ENDLOS).schriftgroesse
    vier = logik.layout(["Zeile"] * 4, ENDLOS).schriftgroesse
    assert vier < eine


def test_rendern_hochkant_in_rollenbreite(tmp_path: Path):
    ziel = tmp_path / "e.png"
    lay = logik.rendern(["TEST", "schimmilab"], ENDLOS, ziel, rahmen=True)
    with Image.open(logik.druckdatei(ziel)) as img:
        assert img.size == (lay.breite_px, lay.laenge_px)   # Druckdatei: Breite = Rolle
        assert img.mode == "1"
        assert img.getextrema() == (0, 255)                  # es ist auch etwas schwarz
    with Image.open(ziel) as img:
        assert img.size == (lay.laenge_px, lay.breite_px)   # Vorschau quer, lesbar


def test_rendern_mit_qr_braucht_mehr_laenge(tmp_path: Path):
    ohne = logik.rendern(["Keller"], ENDLOS, tmp_path / "a.png")
    mit = logik.rendern(["Keller"], ENDLOS, tmp_path / "b.png", qr_text="https://schimmilab.de")
    assert mit.laenge_px > ohne.laenge_px


def test_datum_platzhalter():
    assert logik.ersetze_platzhalter("ab {datum}", date(2026, 10, 29)) == "ab 29.10.2026"


def test_cups_optionen_endlos_und_gestanzt():
    lay = logik.layout(["Test"], ENDLOS)
    opt = logik.cups_optionen_etikett(ENDLOS, lay)
    assert f"PageSize=Custom.38x{lay.laenge_mm:g}mm" in opt and "CutMedia=EndOfJob" in opt
    opt2 = logik.cups_optionen_etikett(GESTANZT, logik.layout(["Test"], GESTANZT))
    assert "PageSize=Custom.38x90mm" in opt2


def test_dokument_optionen():
    opt = logik.cups_optionen_dokument(farbe=False, duplex=True, seiten="1-3, 5", kopien=2)
    assert "print-color-mode=monochrome" in opt and "sides=two-sided-long-edge" in opt
    assert "page-ranges=1-3,5" in opt and opt[:2] == ["-n", "2"]


@pytest.mark.parametrize("seiten", ["eins", "1--3", "1;3"])
def test_dokument_seitenbereich_unsinn_abgelehnt(seiten):
    with pytest.raises(ValueError):
        logik.cups_optionen_dokument(True, False, seiten, 1)
