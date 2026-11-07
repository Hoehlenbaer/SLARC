# brain/sim/world.py
# Version 0.1 (07.11.2026) – Abstrakte Wohnung für Tagesläufe des Brain.
#
# Keine Physik: Räume als Graph mit Weglängen, Laufen kostet Zeit und Akku,
# Objekte und Personen liegen in Räumen. SLARC sieht nur, was in seinem Raum
# ist, und nur Klassen der Detektion V5.0 (perception_classes.py). Personen
# erscheinen ohne Namen ("person"), weil die Perzeption sie nicht unterscheidet.
# Alle Zahlen sind Annahmen.

from __future__ import annotations

import heapq
import random
from dataclasses import dataclass, field
from typing import Optional

from ..datatypes import ObjectSeen, Observation, Person, Request
from ..needs import BATTERY_WH, CELLS, SOC_CURVE

SPEED_M_S = 0.12          # Gehgeschwindigkeit in der Wohnung (Annahme)
BASE_W = 15.0             # Grundlast: Pi, ESP32, Servos halten (Annahme)
WALK_WH_PER_M = 0.2       # Mehrverbrauch beim Gehen (wie needs.WH_PER_M)


@dataclass
class Room:
    name: str
    light: float = 0.9
    anchors: tuple = ()   # feste Dinge, an denen man den Raum erkennt


@dataclass
class SimObject:
    oid: str
    cls: str
    room: str
    dist_m: float = 1.5
    movable: bool = False


@dataclass
class SimPerson:
    pid: str
    name: str                                        # nur für Chat und Ausgabe, SLARC sieht ihn nicht
    schedule: list = field(default_factory=list)     # [(t_von_s, t_bis_s, raum)]

    def room_at(self, t: float) -> Optional[str]:
        for a, b, r in self.schedule:
            if a <= t < b:
                return r
        return None


@dataclass
class ChatEvent:
    t: float
    sender: str
    text: str


def soc_to_voltage(soc: float) -> float:
    """Umkehrung von needs.SOC_CURVE: Ladezustand -> Spannung unter Last."""
    pts = SOC_CURVE
    if soc <= pts[0][1]:
        return pts[0][0] * CELLS
    for (v0, s0), (v1, s1) in zip(pts, pts[1:]):
        if soc <= s1:
            return (v0 + (v1 - v0) * (soc - s0) / (s1 - s0)) * CELLS
    return pts[-1][0] * CELLS


class World:
    def __init__(self, rooms: list[Room], edges: list[tuple], home: str,
                 objects: list[SimObject], persons: list[SimPerson], chat: list[ChatEvent],
                 soc0: float = 0.9, seed: int = 1):
        self.rooms = {r.name: r for r in rooms}
        self.adj: dict[str, dict[str, float]] = {r.name: {} for r in rooms}
        for a, b, d in edges:
            self.adj[a][b] = d
            self.adj[b][a] = d
        self.home = home
        self.objects = {o.oid: o for o in objects}
        self.persons = {p.pid: p for p in persons}
        self.chat = sorted(chat, key=lambda e: e.t)
        self.rng = random.Random(seed)
        self.t = 0.0
        self.room = home
        self.prev_room = home
        self.explored = {home}
        self.energy_wh = soc0 * BATTERY_WH
        self.walked_m = 0.0
        self.path: list[str] = []     # Räume, die noch zu gehen sind
        self.leg_left_m = 0.0
        self.messages: list[tuple] = []   # (t, text) – was SLARC den Menschen meldet

    # ---------------------------------------------------------------- Zeit und Akku
    def advance(self, dt: float, walking_m: float = 0.0) -> None:
        self.t += dt
        self.energy_wh -= BASE_W * dt / 3600.0 + WALK_WH_PER_M * walking_m
        self.walked_m += walking_m
        self._move_things(dt)

    def soc(self) -> float:
        return max(0.0, self.energy_wh / BATTERY_WH)

    def battery_v(self) -> float:
        return soc_to_voltage(self.soc())

    def _move_things(self, dt: float) -> None:
        # Bewegliche Dinge (Katze) wechseln ab und zu den Raum (im Mittel alle 15 min)
        for o in self.objects.values():
            if o.movable and self.rng.random() < dt / 900.0:
                o.room = self.rng.choice(list(self.adj[o.room].keys()))

    # ---------------------------------------------------------------- Wege
    def route(self, start: str, goal: str) -> Optional[tuple[list[str], float]]:
        dist = {start: 0.0}
        prev: dict[str, str] = {}
        q = [(0.0, start)]
        while q:
            d, u = heapq.heappop(q)
            if u == goal:
                break
            if d > dist[u]:
                continue
            for v, w in self.adj[u].items():
                nd = d + w
                if nd < dist.get(v, 1e18):
                    dist[v], prev[v] = nd, u
                    heapq.heappush(q, (nd, v))
        if goal not in dist:
            return None
        path, n = [], goal
        while n != start:
            path.append(n)
            n = prev[n]
        return list(reversed(path)), dist[goal]

    def start_walk(self, goal: str) -> bool:
        if goal == self.room:
            self.path, self.leg_left_m = [], 0.0
            return True
        r = self.route(self.room, goal)
        if r is None:
            return False
        self.path = r[0]
        self.leg_left_m = self.adj[self.room][self.path[0]]
        return True

    def walk(self, dt: float) -> bool:
        """Ein Zeitschritt Gehen. True, wenn das Ziel erreicht ist."""
        if not self.path:
            self.advance(dt)
            return True
        step = min(SPEED_M_S * dt, self.leg_left_m)
        self.leg_left_m -= step
        self.advance(dt, step)
        if self.leg_left_m <= 1e-6:
            self.prev_room, self.room = self.room, self.path.pop(0)
            if self.path:
                self.leg_left_m = self.adj[self.room][self.path[0]]
        return not self.path

    def moving(self) -> bool:
        return bool(self.path)

    # ---------------------------------------------------------------- Wahrnehmung
    def visible_objects(self) -> list[SimObject]:
        if self.moving():
            return []
        return [o for o in self.objects.values() if o.room == self.room]

    def persons_here(self) -> list[SimPerson]:
        return [p for p in self.persons.values() if p.room_at(self.t) == self.room]

    def find_person(self, pid: str) -> Optional[str]:
        p = self.persons.get(pid)
        return p.room_at(self.t) if p else None

    def frontier(self) -> list[str]:
        f = []
        for r in self.explored:
            for n in self.adj[r]:
                if n not in self.explored and n not in f:
                    f.append(n)
        return f

    def observe(self, requests: list[Request], chat_new: bool, tapped: bool,
                last_result: Optional[tuple]) -> Observation:
        room = self.rooms[self.room]
        home = self.route(self.room, self.home)
        return Observation(
            t=self.t,
            battery_v=self.battery_v(),
            home_dist_m=0.0 if self.room == self.home else (home[1] if home else None),
            at_home=self.room == self.home and not self.moving(),
            place=self.room,
            frontier=self.frontier(),
            known_places=sorted(self.explored),
            unknown_frac=1.0 - len(self.explored) / len(self.rooms),
            objects=[ObjectSeen(o.oid, o.cls, o.room, o.dist_m) for o in self.visible_objects()],
            persons=[Person(p.pid, None, 1.5) for p in self.persons_here()] if not self.moving() else [],
            requests=list(requests),
            chat_new=chat_new,
            light=room.light,
            floor_known=self.room in self.explored,
            tapped=tapped,
            last_result=last_result,
        )


def default_flat(seed: int = 1, soc0: float = 0.9) -> World:
    """Beispielwohnung: Flur als Ausgangspunkt, sieben Räume. Anker nur aus echten Klassen."""
    rooms = [
        Room("flur", 0.8),
        Room("wohnzimmer", 0.9, ("sofa", "fernseher")),
        Room("küche", 0.9, ("kühlschrank", "ofen")),
        Room("bad", 0.6, ("toilette", "waschbecken")),
        Room("schlafzimmer", 0.5, ("bett",)),
        Room("kinderzimmer", 0.8, ("bett",)),
        Room("abstellraum", 0.3),
    ]
    edges = [("flur", "wohnzimmer", 4.0), ("flur", "küche", 3.0), ("flur", "bad", 2.5),
             ("flur", "schlafzimmer", 5.0), ("flur", "kinderzimmer", 6.0),
             ("küche", "abstellraum", 2.0), ("wohnzimmer", "küche", 3.5)]
    objects = [
        SimObject("sofa1", "sofa", "wohnzimmer", 2.5), SimObject("tv1", "fernseher", "wohnzimmer", 3.0),
        SimObject("fb1", "fernbedienung", "schlafzimmer", 1.2),   # liegt nicht da, wo man sie erwartet
        SimObject("kue1", "kühlschrank", "küche", 2.0), SimObject("ofen1", "ofen", "küche", 2.2),
        SimObject("tasse1", "tasse", "küche", 1.0), SimObject("fl1", "flasche", "abstellraum", 1.0),
        SimObject("wc1", "toilette", "bad", 1.5), SimObject("wb1", "waschbecken", "bad", 1.2),
        SimObject("bett1", "bett", "schlafzimmer", 2.0), SimObject("bett2", "bett", "kinderzimmer", 2.0),
        SimObject("teddy1", "teddy", "kinderzimmer", 1.0), SimObject("ruck1", "rucksack", "flur", 1.0),
        SimObject("handy1", "handy", "küche", 1.3), SimObject("koffer1", "koffer", "abstellraum", 1.5),
        SimObject("unb1", "unbekannt", "abstellraum", 1.0),
        SimObject("katze1", "katze", "wohnzimmer", 2.0, movable=True),
    ]
    h = 3600.0
    persons = [
        SimPerson("p-marco", "Marco", [(0.6 * h, 1.4 * h, "wohnzimmer"), (1.4 * h, 1.6 * h, "küche"),
                                       (1.6 * h, 3.0 * h, "wohnzimmer")]),
        SimPerson("p-laura", "Laura", [(1.0 * h, 2.5 * h, "kinderzimmer")]),
    ]
    chat = [
        ChatEvent(0.75 * h, "Marco", "Wo ist die Fernbedienung?"),
        ChatEvent(1.1 * h, "Marco", "Such mal meinen Schlüssel."),
        ChatEvent(1.3 * h, "Marco", "Gut gemacht!"),
        ChatEvent(1.8 * h, "Marco", "Hast du heute was Spannendes erlebt?"),
        ChatEvent(2.2 * h, "Marco", "Komm mit, ich zeig dir was."),
    ]
    return World(rooms, edges, "flur", objects, persons, chat, soc0=soc0, seed=seed)
