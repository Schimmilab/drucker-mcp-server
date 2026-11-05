"""Umfangsgrenze für den Dokumentdruck: große Aufträge nur mit ausdrücklicher Bestätigung."""
import pytest
from PIL import Image

from drucker_mcp import logik, server


# ── Logik ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bereich, gesamt, erwartet", [
    (None, 12, 12),
    ("1-3,5", 12, 4),
    ("3-1", 12, 3),          # vertauscht
    ("1-3,2-4", 12, 4),      # Überlappung zählt einmal
    ("10-99", 12, 3),        # über das Ende hinaus
])
def test_seiten_im_bereich(bereich, gesamt, erwartet):
    assert logik.seiten_im_bereich(bereich, gesamt) == erwartet


def test_muss_rot_grosser_auftrag_ohne_bestaetigung():
    with pytest.raises(ValueError, match="bestaetigt=True"):
        logik.pruefe_umfang(300, None, 50, bestaetigt=False)


def test_grenze_genau_erlaubt_und_eins_darueber_nicht():
    assert logik.pruefe_umfang(10, None, 2, bestaetigt=False) == 20
    with pytest.raises(ValueError):
        logik.pruefe_umfang(21, None, 1, bestaetigt=False)


def test_bestaetigt_laesst_grossen_auftrag_durch():
    assert logik.pruefe_umfang(300, None, 50, bestaetigt=True) == 15000


def test_seitenbereich_entschaerft_langes_dokument():
    # 300-Seiten-PDF, aber nur Seite 1-5 × 2 = 10 → ohne Bestätigung ok
    assert logik.pruefe_umfang(300, "1-5", 2, bestaetigt=False) == 10


# ── Server-Pfad: blockiert, BEVOR an CUPS geht ─────────────────────────────

def _pdf(pfad, seiten):
    bilder = [Image.new("RGB", (60, 80), "white") for _ in range(seiten)]
    bilder[0].save(pfad, "PDF", save_all=True, append_images=bilder[1:])
    return pfad


@pytest.fixture
def cups_attrappe(monkeypatch):
    aufrufe = []
    monkeypatch.setattr(server.cups, "drucken", lambda *a, **k: aufrufe.append(a) or "Job-1")
    return aufrufe


def test_server_blockiert_langes_pdf_ohne_bestaetigung(tmp_path, cups_attrappe):
    pdf = _pdf(tmp_path / "lang.pdf", 25)
    with pytest.raises(ValueError, match="25 Seiten"):
        server.datei_drucken(str(pdf))
    assert cups_attrappe == [], "Auftrag ging trotz Grenze an CUPS"


def test_server_druckt_kurzes_pdf_und_meldet_umfang(tmp_path, cups_attrappe):
    pdf = _pdf(tmp_path / "kurz.pdf", 3)
    antwort = server.datei_drucken(str(pdf), kopien=2)
    assert len(cups_attrappe) == 1 and "6 Seiten" in antwort


def test_server_druckt_langes_pdf_mit_bestaetigung(tmp_path, cups_attrappe):
    pdf = _pdf(tmp_path / "lang.pdf", 25)
    server.datei_drucken(str(pdf), bestaetigt=True)
    assert len(cups_attrappe) == 1
