"""Minimaler IPP-Client: nur Get-Printer-Attributes, um die eingelegte Rolle zu lesen.

CUPS selbst liefert media-ready fuer eine dnssd-Queue nicht (am 29.10.2026 geprueft), und die
Raster-Statusabfrage des Brother ueber Port 9100 bleibt im Netz stumm. Also direkt per IPP an
den Drucker. Bewusst ohne ipptool, damit es auch ohne CUPS-Werkzeuge laeuft.
"""
from __future__ import annotations

import struct
import time
import urllib.error
import urllib.request
from urllib.parse import unquote, urlparse

TAG_OP, TAG_ENDE = 0x01, 0x03
TAG_INTEGER, TAG_BOOL, TAG_ENUM = 0x21, 0x22, 0x23
TAG_COLL_BEGIN, TAG_COLL_END, TAG_MEMBER = 0x34, 0x37, 0x4A
TAG_KEYWORD, TAG_URI, TAG_CHARSET, TAG_LANG = 0x44, 0x45, 0x47, 0x48


def _attr(tag: int, name: str, wert: bytes) -> bytes:
    n = name.encode()
    return struct.pack(">BH", tag, len(n)) + n + struct.pack(">H", len(wert)) + wert


def anfrage(uri: str, attribute: list[str], request_id: int = 1) -> bytes:
    body = struct.pack(">BBHI", 2, 0, 0x000B, request_id) + bytes([TAG_OP])
    body += _attr(TAG_CHARSET, "attributes-charset", b"utf-8")
    body += _attr(TAG_LANG, "attributes-natural-language", b"en")
    body += _attr(TAG_URI, "printer-uri", uri.encode())
    for i, a in enumerate(attribute):
        body += _attr(TAG_KEYWORD, "requested-attributes" if i == 0 else "", a.encode())
    return body + bytes([TAG_ENDE])


def parse_antwort(daten: bytes) -> tuple[int, dict[str, list]]:
    """-> (status_code, {name: [werte]}). Collections werden uebersprungen."""
    if len(daten) < 9:
        raise ValueError("IPP-Antwort zu kurz")
    _, _, status, _ = struct.unpack(">BBHI", daten[:8])
    pos, name, tiefe, attrs = 8, "", 0, {}
    while pos < len(daten):
        tag = daten[pos]
        pos += 1
        if tag == TAG_ENDE:
            break
        if tag < 0x10:  # Gruppen-Begrenzer
            continue
        (nlen,) = struct.unpack(">H", daten[pos:pos + 2]); pos += 2
        n = daten[pos:pos + nlen].decode(errors="replace"); pos += nlen
        (vlen,) = struct.unpack(">H", daten[pos:pos + 2]); pos += 2
        roh = daten[pos:pos + vlen]; pos += vlen
        if tag == TAG_COLL_BEGIN:
            tiefe += 1
            if n:
                name = n
            continue
        if tag == TAG_COLL_END:
            tiefe -= 1
            continue
        if tiefe > 0 or tag == TAG_MEMBER:
            continue
        if n:
            name = n
        if tag in (TAG_INTEGER, TAG_ENUM) and vlen == 4:
            wert = struct.unpack(">i", roh)[0]
        elif tag == TAG_BOOL and vlen == 1:
            wert = bool(roh[0])
        else:
            wert = roh.decode(errors="replace")
        attrs.setdefault(name, []).append(wert)
    return status, attrs


def drucker_attribute(uri: str, attribute: list[str], timeout: float = 8.0) -> dict[str, list]:
    """Get-Printer-Attributes an ipp(s)://host[:port]/pfad."""
    u = urlparse(uri)
    if u.scheme not in ("ipp", "ipps"):
        raise ValueError(f"Keine IPP-Adresse: {uri!r}")
    http = ("https" if u.scheme == "ipps" else "http") + f"://{u.hostname}:{u.port or 631}{u.path or '/'}"
    req = urllib.request.Request(http, data=anfrage(uri, attribute),
                                 headers={"Content-Type": "application/ipp"})
    for versuch in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status, attrs = parse_antwort(r.read())
            break
        except urllib.error.HTTPError as e:
            # Brother QL antwortet bei mehreren Abfragen kurz hintereinander mit 503 (29.10. belegt)
            if e.code == 503 and versuch < 2:
                time.sleep(1.0 + versuch)
                continue
            raise RuntimeError(f"Drucker unter {u.hostname} antwortet mit HTTP {e.code} ({e.reason}).") from e
        except OSError as e:  # URLError, Timeout, Verbindung abgelehnt
            raise RuntimeError(f"Drucker unter {u.hostname} nicht erreichbar ({getattr(e, 'reason', e)}). "
                               "Ist er eingeschaltet und im Netz?") from e
    if status >= 0x0100:
        raise RuntimeError(f"Drucker meldet IPP-Status 0x{status:04x} für {uri}")
    return attrs


def dnssd_dienstname(device_uri: str) -> str | None:
    """'dnssd://Brother%20QL-820NWB._ipp._tcp.local./?uuid=..' -> 'Brother QL-820NWB._ipp._tcp.local.'"""
    u = urlparse(device_uri)
    if u.scheme != "dnssd":
        return None
    return unquote(u.netloc)


def dnssd_aufloesen(dienst: str, timeout_ms: int = 4000) -> str:
    """Bonjour-Dienstname -> ipp://host:port/rp"""
    from zeroconf import ServiceInfo, Zeroconf

    typ = dienst.split(".", 1)[1] if "._ipp" in dienst else "_ipp._tcp.local."
    typ = typ[typ.index("_"):]
    z = Zeroconf()
    try:
        info = ServiceInfo(typ, dienst)
        if not info.request(z, timeout_ms):
            raise RuntimeError(f"Drucker {dienst!r} antwortet nicht per Bonjour (aus oder nicht im Netz?)")
        rp = (info.properties or {}).get(b"rp", b"ipp/print").decode()
        adressen = info.parsed_addresses()
        host = next((a for a in adressen if ":" not in a), None) or (info.server or "").rstrip(".")
        schema = "ipps" if "_ipps" in typ else "ipp"
        return f"{schema}://{host}:{info.port}/{rp}"
    finally:
        z.close()
