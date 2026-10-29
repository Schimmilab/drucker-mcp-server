"""CUPS-Anbindung ueber die Standardwerkzeuge lp/lpstat/cancel (macOS und Linux)."""
from __future__ import annotations

import os
import re
import subprocess

# lpstat gibt sonst je nach Systemsprache 'Drucker … ist inaktiv' statt 'printer … is idle' aus
_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C"}


def _lauf(args: list[str], timeout: float = 20) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=_ENV)
    except FileNotFoundError as e:
        raise RuntimeError(f"{args[0]} nicht gefunden – ist CUPS installiert?") from e
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:2])} fehlgeschlagen: {(r.stderr or r.stdout).strip()}")
    return r.stdout


def drucker() -> list[dict]:
    """[{name, status, standard}] aus lpstat."""
    standard = ""
    try:
        m = re.search(r":\s*(\S+)\s*$", _lauf(["lpstat", "-d"]).strip())
        standard = m[1] if m else ""
    except RuntimeError:
        pass
    aus = []
    for zeile in _lauf(["lpstat", "-p"]).splitlines():
        m = re.match(r"printer\s+(\S+)\s+(.*)", zeile)
        if m:
            aus.append({"name": m[1], "status": m[2].split(".")[0], "standard": m[1] == standard})
    return aus


def device_uri(queue: str) -> str:
    out = _lauf(["lpstat", "-v", queue])
    m = re.search(r":\s*(\S+://\S+)", out)
    if not m:
        raise RuntimeError(f"Keine Geräteadresse für {queue!r} in lpstat -v")
    return m[1]


def drucken(queue: str | None, datei: str, optionen: list[str], titel: str) -> str:
    """Ohne queue geht der Auftrag an den CUPS-Standarddrucker."""
    ziel = ["-d", queue] if queue else []
    out = _lauf(["lp", *ziel, "-t", titel, *optionen, datei])
    m = re.search(r"(\S+-\d+)", out)
    return m[1] if m else out.strip()


def auftraege(queue: str | None = None) -> list[str]:
    return [z for z in _lauf(["lpstat", "-o"] + ([queue] if queue else [])).splitlines() if z.strip()]


def abbrechen(auftrag: str) -> None:
    _lauf(["cancel", auftrag])
