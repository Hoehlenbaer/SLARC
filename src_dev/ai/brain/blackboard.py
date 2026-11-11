# brain/blackboard.py
# Version 0.2 (11.11.2026) – Blackboard: gemeinsamer Weltzustand auf dem Pi.  # PORTABLE
# V0.2 (BB 0.2): „Was ist das?“ – Detection.quelle, TrackedObject.ident/answers/name_source;
#       benannte Dinge erscheinen fürs Brain unter ihrem Namen, verworfene gar nicht.
#
# Schreiber und Leser (Konzept: Documentation/Brain_Konzept.md, Abschnitt 18):
#   SLAM / Lokalisierung  -> pose, map, home
#   Perzeption (Hailo)    -> detections (je Bild, Weltkoordinaten), persons
#   Tracker (nav/tracker) -> objects (dauerhafte Kennung, Zustand da/fehlt, verschoben)
#   Kartenebenen (nav/frontier) -> frontiers, areas
#   Navigation (A*)       -> nav (Ziel, Pfad, Status, Weg nach Hause)
#   ESP32-Brücke          -> robot (Akku, Modus), Sicherheitsflags
#   Brain (Arbiter, BT)   -> robot.behavior/node/mood/needs; liest alles andere
# Das Brain sieht die Welt nur über to_observation(). In der Simulation schreibt
# brain/sim2d die Felder, auf dem Roboter die jeweiligen Prozesse.
#
# Einheiten SI (m, s, rad, V), Weltkoordinaten x rechts, y oben, theta gegen den
# Uhrzeigersinn ab x. to_dict() liefert JSON-fähige Daten (Aufzeichnung, IPC, Viewer).

from __future__ import annotations

import math
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Optional

from .datatypes import ObjectSeen, Observation, Person, Request
from .nav.gridmap import FREE, GridMap

BB_VERSION = "0.2"
OBJECT_RECENT_S = 8.0       # so lange gilt ein Objekt als „im Blick“ für das Brain
PERSON_RECENT_S = 3.0
AT_HOME_M = 0.4
FRONTIER_UNKNOWN_M = 8.0    # Grenzlänge, ab der unknown_frac = 1 (Neugier)
MIN_AREA_CELLS = 30         # Bereich gilt als bekannt ab ~0,3 m²


@dataclass
class Pose:
    x: float
    y: float
    theta: float
    t: float = 0.0


@dataclass
class Detection:
    """Eine Erkennung der Perzeption in einem Bild, schon in Weltkoordinaten."""
    cls: str               # Klasse aus perception_classes (deutsch), auch "unbekannt"
    x: float
    y: float
    conf: float
    t: float
    box: Optional[tuple] = None      # Bildbox (x, y, w, h) für „Was ist das?“; in der Sim None
    quelle: str = "yolo"             # yolo | geometrie (etwas ragt aus dem Boden, Klasse unbekannt)


@dataclass
class TrackedObject:
    track_id: str          # dauerhafte Kennung, z. B. "katze-7"
    cls: str
    x: float
    y: float
    conf: float
    first_seen: float
    last_seen: float
    n_seen: int
    state: str = "da"      # "da" | "fehlt"
    moved: bool = False    # an anderer Stelle wiedergefunden
    area: Optional[str] = None
    misses: int = 0
    name_vlm: Optional[str] = None   # „Was ist das?“: Name (Vermutung des VLM oder Antwort des Menschen)
    name_sure: bool = False          # durch zweiten Blick oder den Menschen bestätigt
    name_source: str = ""            # vlm | mensch
    ident: str = ""                  # nur "unbekannt": offen | vermutet | unklar | sicher | nichts
    answers: list = field(default_factory=list)   # Antworten des VLM in der Reihenfolge der Blicke

    @property
    def label(self) -> str:
        """Name fürs Brain: bestätigter Name, sonst die Klasse der Detektion."""
        return self.name_vlm if self.name_sure and self.name_vlm else self.cls


@dataclass
class PersonTrack:
    track_id: str          # in der Simulation die wahre Kennung (SIM ONLY), auf dem Roboter Tracking
    x: float
    y: float
    last_seen: float
    name: Optional[str] = None       # Perzeption unterscheidet Personen nicht


@dataclass
class Frontier:
    fid: str               # lesbarer Name, z. B. "flur ost"
    x: float               # Zielpunkt (Grenzzelle nahe dem Schwerpunkt)
    y: float
    size: int              # Zellen
    area: str
    reachable: bool = True


@dataclass
class Area:
    name: str
    x: float               # Mittelpunkt der freien Fläche
    y: float
    cells: int


@dataclass
class NavState:
    goal: Optional[tuple] = None     # (x, y)
    goal_label: str = ""
    path: list = field(default_factory=list)   # [(x, y), …] Wegpunkte
    status: str = "frei"             # frei | unterwegs | angekommen | kein_weg | blockiert
    replans: int = 0
    home_dist_m: Optional[float] = None


@dataclass
class RobotState:
    battery_v: float = 12.0
    soc: float = 1.0
    mode: str = "stehen"             # stehen | laufen | drehen | liegen | denken
    light: float = 1.0
    tilt_deg: float = 0.0
    behavior: str = ""               # laufendes Verhalten (Option.key)
    node: str = ""                   # laufendes BT-Blatt
    mood: str = "ruhig"
    needs: dict = field(default_factory=dict)    # Name -> 0…1
    levels: dict = field(default_factory=dict)   # Name -> Stufe 0…4


class Blackboard:
    def __init__(self, gridmap: GridMap, home: Pose):
        self.version = BB_VERSION
        self.t = 0.0
        self.pose = Pose(home.x, home.y, home.theta, 0.0)
        self.home = home
        self.map = gridmap
        self.detections: list[Detection] = []
        self.objects: dict[str, TrackedObject] = {}
        self.persons: dict[str, PersonTrack] = {}
        self.frontiers: list[Frontier] = []
        self.areas: dict[str, Area] = {}
        self.nav = NavState()
        self.robot = RobotState()
        self.events: deque = deque(maxlen=200)      # (t, art, text)

    # ---------------------------------------------------------------- Hilfen
    def area_at(self, x: float, y: float) -> Optional[str]:
        return self.map.area_at(x, y)

    def place(self) -> str:
        return self.area_at(self.pose.x, self.pose.y) or "unbenannt"

    def dist(self, x: float, y: float) -> float:
        return math.hypot(x - self.pose.x, y - self.pose.y)

    def at_home(self) -> bool:
        return self.dist(self.home.x, self.home.y) < AT_HOME_M and self.robot.mode != "laufen"

    def event(self, kind: str, text: str) -> None:
        self.events.append((self.t, kind, text))

    def recent_objects(self) -> list[TrackedObject]:
        return [o for o in self.objects.values()
                if o.state == "da" and o.ident != "nichts" and self.t - o.last_seen <= OBJECT_RECENT_S]

    def known_names(self) -> set:
        """Namen, die SLARC durch „Was ist das?“ sicher kennt (für Chat und Suche)."""
        return {o.name_vlm for o in self.objects.values() if o.name_sure and o.name_vlm}

    # ---------------------------------------------------------------- fürs Brain
    def to_observation(self, requests: list[Request], chat_new: bool, tapped: bool,
                       last_result: Optional[tuple]) -> Observation:
        fr = sorted((f for f in self.frontiers if f.reachable), key=lambda f: self.dist(f.x, f.y))
        flen = sum(f.size for f in self.frontiers) * self.map.res
        return Observation(
            t=self.t,
            battery_v=self.robot.battery_v,
            home_dist_m=0.0 if self.at_home() else self.nav.home_dist_m,
            at_home=self.at_home(),
            place=self.place(),
            frontier=[f.fid for f in fr],
            known_places=sorted(a.name for a in self.areas.values() if a.cells >= MIN_AREA_CELLS),
            unknown_frac=min(1.0, flen / FRONTIER_UNKNOWN_M),
            objects=[ObjectSeen(o.track_id, o.label, o.area or self.place(), self.dist(o.x, o.y), True, o.moved,
                                (o.ident or "offen") if o.label == "unbekannt" else "")
                     for o in self.recent_objects()],
            persons=[Person(p.track_id, p.name, self.dist(p.x, p.y))
                     for p in self.persons.values() if self.t - p.last_seen <= PERSON_RECENT_S],
            requests=list(requests),
            chat_new=chat_new,
            tilt_deg=self.robot.tilt_deg,
            light=self.robot.light,
            floor_known=self.map.state_at(self.pose.x, self.pose.y) == FREE,
            tapped=tapped,
            last_result=last_result,
        )

    # ---------------------------------------------------------------- Ausgabe
    def to_dict(self) -> dict:
        """JSON-fähiger Zustand ohne Kartenraster (das geht als Diff bzw. eigenes Feld)."""
        return {
            "version": self.version, "t": round(self.t, 2),
            "pose": _r(asdict(self.pose)), "home": _r(asdict(self.home)),
            "map": {"res": self.map.res, "origin": [self.map.ox, self.map.oy], "w": self.map.w, "h": self.map.h,
                    "areas": list(self.map.area_names)},
            "objects": [_r(asdict(o)) for o in self.objects.values()],
            "persons": [_r(asdict(p)) for p in self.persons.values()],
            "frontiers": [_r(asdict(f)) for f in self.frontiers],
            "areas": [_r(asdict(a)) for a in self.areas.values()],
            "nav": _r(asdict(self.nav)),
            "robot": _r(asdict(self.robot)),
        }


def _r(d):
    """Zahlen runden (kleinere Aufzeichnung)."""
    if isinstance(d, float):
        return round(d, 3)
    if isinstance(d, dict):
        return {k: _r(v) for k, v in d.items()}
    if isinstance(d, (list, tuple)):
        return [_r(v) for v in d]
    return d
