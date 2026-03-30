"""
PS2 game serial (disc ID) parsing and normalisation.

PS2 serials follow the pattern:  <region_prefix>-<5 digit number>
Examples:
  SLUS-21548   → USA
  SLES-55505   → Europe
  SLPS-25790   → Japan
  SCUS-97330   → USA (Sony 1st party)
  SCES-55474   → Europe (Sony 1st party)

PCSX2 may emit them with underscores or dots:
  SLUS_211.48  →  SLUS-21148
  SLPS_250.99  →  SLPS-25099
"""
from __future__ import annotations

import re

_SERIAL_CLEAN_RE = re.compile(
    r"^(?P<prefix>[A-Z]{2,4})[_\-]?(?P<digits>\d{3})[\._]?(?P<suffix>\d{2})$",
    re.IGNORECASE,
)

_REGION_MAP: dict[str, str] = {
    "SLUS": "USA",
    "SCUS": "USA",
    "SLPS": "Japan",
    "SCPS": "Japan",
    "SLPM": "Japan",
    "SLES": "Europe",
    "SCES": "Europe",
    "SLED": "Europe",
    "SLKA": "Korea",
    "SLAJ": "Japan",  # Asia
}


def normalise_serial(raw: str) -> str | None:
    """
    Normalise a PS2 serial into canonical form (e.g. SLUS-21548).
    Returns None if the string doesn't look like a PS2 serial.
    """
    raw = raw.strip().upper()
    m = _SERIAL_CLEAN_RE.match(raw)
    if not m:
        # Try the already-canonical format first (SLUS-21548)
        if re.match(r"^[A-Z]{2,4}-\d{5}$", raw):
            return raw
        return None
    prefix = m.group("prefix")
    digits = m.group("digits")
    suffix = m.group("suffix")
    return f"{prefix}-{digits}{suffix}"


def get_region(serial: str) -> str:
    """Return the region string for a normalised serial (e.g. 'USA')."""
    prefix = serial.split("-")[0].upper()
    return _REGION_MAP.get(prefix, "Unknown")


def serial_to_image_key(serial: str) -> str:
    """
    Convert a serial to a safe lowercase key suitable for Discord asset names
    or image filenames.  SLUS-21548 → slus_21548
    """
    return serial.lower().replace("-", "_")
