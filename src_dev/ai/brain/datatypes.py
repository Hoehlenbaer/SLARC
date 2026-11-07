# brain/datatypes.py
# Version 0.1 (07.11.2026) – Datentypen für das bedürfnisgesteuerte Brain.
# Konzept: Documentation/Brain_Konzept.md
#
# Alle Einheiten SI (m, s, V, °C). Weltbezug (Orte, Weglänge zum
# Ausgangspunkt) kommt nur vom Pi (SLAM), nie vom ESP32.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ObjectSeen:
    """Ein von der Perzeption erkanntes Objekt."""
    oid: str                 # stabile ID aus dem Tracking/Gedächtnis
    cls: str                 # Klasse der Detektion, z. B. "tasche"
    place: str               # Bereich, z. B. "wohnzimmer"
    dist_m: float            # Abstand zum Körper
    reachable: bool = True   # Weg frei (Planer)
    moved: bool = False      # Lage weicht vom Gedächtnis ab


@dataclass
class Person:
    pid: str
    name: Optional[str]      # None = unbekannt
    dist_m: float
    facing: bool = False     # schaut SLARC an


@dataclass
class Request:
    """Bitte eines Menschen (Web-Chat, später Sprache)."""
    rid: str
    text: str                # Wortlaut für Prompt und Tagebuch
    service: str             # Dienst aus SERVICES (behaviors.py)
    arg: Optional[str]       # z. B. "schlüssel", Person-ID
    from_person: Optional[str]
    t_created: float


@dataclass
class Observation:
    """Momentaufnahme, die das Brain im 1-Hz-Takt bekommt."""
    t: float
    battery_v: float                      # Akkuspannung unter Last (INA219)
    home_dist_m: Optional[float]          # Weglänge zum Ausgangspunkt, None = unbekannt
    at_home: bool
    place: str
    frontier: list[str] = field(default_factory=list)   # Bereiche mit unerkundeter Grenze in der Nähe
    known_places: list[str] = field(default_factory=list)  # schon erkundete Bereiche (für Rundgänge)
    unknown_frac: float = 0.0                           # Anteil unbekannter Fläche im Umkreis, 0…1
    objects: list[ObjectSeen] = field(default_factory=list)
    persons: list[Person] = field(default_factory=list)
    requests: list[Request] = field(default_factory=list)
    chat_new: bool = False                # neue Nachricht seit dem letzten Takt
    # Sicherheit / Unbehagen
    tilt_deg: float = 0.0
    light: float = 1.0                    # 0 dunkel … 1 hell
    floor_known: bool = True
    slipped: bool = False                 # Rutschen in diesem Takt (ESP32)
    stair_edge_near: bool = False
    climb_allowed: bool = False
    servo_temp_max_c: float = 35.0
    lifted: bool = False                  # hochgehoben (ESP32: alle Füße ohne Kontakt)
    tapped: bool = False                  # Panzer angetippt (ESP32: IMU-Impuls im Stand)
    # Rückmeldung des Verhaltens-Layers
    last_result: Optional[tuple[str, str]] = None   # (verhalten, "ok"|"failed")


@dataclass
class Option:
    """Ein machbares Ziel im Menü für LLM bzw. Code-Auswahl."""
    behavior: str
    arg: Optional[str]
    label: str            # Text im Prompt, z. B. "inspect_object(tasche, wohnzimmer, 2 m)"
    utility: float        # Bewertung durch den Code
    service: Optional[str] = None   # für Lernen durch Lob

    @property
    def key(self) -> str:
        return f"{self.behavior}({self.arg})" if self.arg else self.behavior
