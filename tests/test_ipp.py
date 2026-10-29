import struct

import pytest

from drucker_mcp import ipp


def _antwort(status: int, attrs: bytes) -> bytes:
    return struct.pack(">BBHI", 2, 0, status, 1) + bytes([0x04]) + attrs + bytes([0x03])


def _a(tag: int, name: str, wert: bytes) -> bytes:
    return ipp._attr(tag, name, wert)


def test_anfrage_hat_operation_und_uri():
    a = ipp.anfrage("ipp://drucker:631/ipp/print", ["media-ready"])
    assert a[:4] == bytes([2, 0, 0x00, 0x0B])
    assert b"ipp://drucker:631/ipp/print" in a and b"media-ready" in a and a.endswith(b"\x03")


def test_media_ready_wird_gelesen_collection_uebersprungen():
    daten = _antwort(0, (
        _a(ipp.TAG_KEYWORD, "media-ready", b"roll_current_38x0mm")
        # media-col-ready ist eine Collection; ihre Mitglieder duerfen media-ready NICHT ueberschreiben
        + _a(ipp.TAG_COLL_BEGIN, "media-col-ready", b"")
        + _a(ipp.TAG_MEMBER, "", b"media-type")
        + _a(ipp.TAG_KEYWORD, "", b"roll")
        + _a(ipp.TAG_COLL_END, "", b"")
        + _a(ipp.TAG_INTEGER, "marker-levels", struct.pack(">i", 100))
    ))
    status, attrs = ipp.parse_antwort(daten)
    assert status == 0
    assert attrs["media-ready"] == ["roll_current_38x0mm"]
    assert attrs["marker-levels"] == [100]
    assert "media-col-ready" not in attrs


def test_mehrwertiges_attribut():
    daten = _antwort(0, _a(ipp.TAG_KEYWORD, "media-ready", b"a_1x2mm") + _a(ipp.TAG_KEYWORD, "", b"b_3x4mm"))
    assert ipp.parse_antwort(daten)[1]["media-ready"] == ["a_1x2mm", "b_3x4mm"]


def test_zu_kurze_antwort_wird_abgelehnt():
    with pytest.raises(ValueError):
        ipp.parse_antwort(b"\x02\x00")


def test_keine_ipp_adresse_abgelehnt():
    with pytest.raises(ValueError):
        ipp.drucker_attribute("http://drucker/", ["media-ready"])


def test_dnssd_dienstname():
    uri = "dnssd://Brother%20QL-820NWB._ipp._tcp.local./?uuid=e3248000-80ce-11db-8000-0080775e6c12"
    assert ipp.dnssd_dienstname(uri) == "Brother QL-820NWB._ipp._tcp.local."
    assert ipp.dnssd_dienstname("ipp://host/ipp/print") is None
