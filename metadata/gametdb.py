"""
GameTDB offline XML fallback parser.

GameTDB provides a PS2 game database as XML.
Download: https://www.gametdb.com/PS2db.txt (tab-separated, easily parseable)
Or:       https://www.gametdb.com/PS2db.xml (full XML)

This module handles both formats. It's purely offline — no network calls.
Run once, or update it occasionally using the supplied utility.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from utils.logger import logger


@dataclass
class GameTDBEntry:
    serial: str
    title: str
    region: str | None


class GameTDBParser:
    """Parse a GameTDB PS2 database file into a serial → GameTDBEntry map."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._db: dict[str, GameTDBEntry] = {}
        self._loaded = False

    def load(self) -> bool:
        """Load the database from disk. Returns True on success."""
        if self._loaded:
            return True
        if not self._path or not self._path.exists():
            logger.debug("GameTDB: no database file configured/found")
            return False

        suffix = self._path.suffix.lower()
        try:
            if suffix in (".txt", ".tsv", ".csv"):
                self._load_tsv(self._path)
            elif suffix == ".xml":
                self._load_xml(self._path)
            else:
                # Try TSV first
                self._load_tsv(self._path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GameTDB: failed to load {}: {}", self._path, exc)
            return False

        logger.info("GameTDB: loaded {} entries from {}", len(self._db), self._path)
        self._loaded = True
        return True

    def _load_tsv(self, path: Path) -> None:
        """Load GameTDB's tab-separated format: ID\tTitle\tRegion\t..."""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                if len(row) < 2:
                    continue
                serial = row[0].strip().upper()
                title = row[1].strip()
                region = row[2].strip() if len(row) > 2 else None
                if serial and title:
                    self._db[serial] = GameTDBEntry(serial=serial, title=title, region=region)

    def _load_xml(self, path: Path) -> None:
        """Load full GameTDB XML format."""
        import xml.etree.ElementTree as ET
        tree = ET.parse(path)
        root = tree.getroot()
        for game in root.findall("game"):
            id_elem = game.find("id")
            locale_elem = game.find("locale[@lang='EN']")
            if locale_elem is None:
                locale_elem = game.find("locale")
            title_elem = locale_elem.find("title") if locale_elem is not None else None

            if id_elem is None or title_elem is None:
                continue
            serial = id_elem.text.strip().upper() if id_elem.text else ""
            title = title_elem.text.strip() if title_elem.text else ""
            region = game.get("region")
            if serial and title:
                self._db[serial] = GameTDBEntry(serial=serial, title=title, region=region)

    def lookup(self, serial: str) -> GameTDBEntry | None:
        """Return a GameTDB entry by serial, or None if not found."""
        if not self._loaded:
            self.load()
        return self._db.get(serial.upper())
