# brain/sim2d/floorplan.py
# Version 0.1 (11.11.2026) – Grundriss der Beispielwohnung (Wahrheit, SIM ONLY).
#
# Dieselben sieben Räume wie brain/sim/world.default_flat, jetzt mit Maßen, Wänden,
# Türen (0,9 m), Möbeln (Hindernisse und zugleich erkennbare Objekte) und kleinen
# Dingen am Boden. Alle Klassen aus perception_classes. Maße in m, Ursprung unten links.

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

TRUTH_RES = 0.05
WALL_T = 0.1
SIZE = (12.0, 9.0)


@dataclass
class RoomDef:
    name: str
    rect: tuple            # (x0, y0, x1, y1)
    light: float
    spot: tuple            # wo sich Menschen dort meist aufhalten


@dataclass
class Thing:
    oid: str
    cls: str
    x: float
    y: float
    rect: tuple | None = None      # Möbel: Grundfläche (Hindernis); kleine Dinge: None
    movable: bool = False


@dataclass
class Plan:
    rooms: list[RoomDef]
    walls: list[tuple]             # Linien (x0, y0, x1, y1), achsparallel
    doors: list[tuple]             # Lücken (x0, y0, x1, y1)
    things: list[Thing]
    home: tuple = (1.0, 4.75, 0.0)
    extra: dict = field(default_factory=dict)


def default_plan() -> Plan:
    rooms = [
        RoomDef("wohnzimmer", (0, 0, 6, 4), 0.9, (1.6, 1.8)),
        RoomDef("küche", (6, 0, 10, 4), 0.9, (8.0, 3.0)),
        RoomDef("abstellraum", (10, 0, 12, 4), 0.3, (10.8, 2.0)),
        RoomDef("flur", (0, 4, 12, 5.5), 0.8, (6.0, 4.75)),
        RoomDef("schlafzimmer", (0, 5.5, 4.5, 9), 0.5, (3.2, 7.5)),
        RoomDef("kinderzimmer", (4.5, 5.5, 8.5, 9), 0.8, (5.8, 7.8)),
        RoomDef("bad", (8.5, 5.5, 12, 9), 0.6, (10.2, 7.2)),
    ]
    W, H = SIZE
    walls = [(0, 0, W, 0), (0, H, W, H), (0, 0, 0, H), (W, 0, W, H),
             (0, 4, W, 4), (0, 5.5, W, 5.5),
             (6, 0, 6, 4), (10, 0, 10, 4), (4.5, 5.5, 4.5, H), (8.5, 5.5, 8.5, H)]
    doors = [(2.0, 4, 2.9, 4), (7.0, 4, 7.9, 4),            # Flur – Wohnzimmer, Flur – Küche
             (6, 1.5, 6, 2.4), (10, 2.5, 10, 3.4),          # Wohnzimmer – Küche, Küche – Abstellraum
             (3.0, 5.5, 3.9, 5.5), (5.5, 5.5, 6.4, 5.5), (9.0, 5.5, 9.9, 5.5)]   # Schlaf-, Kinderzimmer, Bad
    F = [  # Möbel: (oid, cls, rect)
        ("sofa1", "sofa", (0.3, 0.3, 2.5, 1.2)), ("tv1", "fernseher", (2.8, 0.15, 4.2, 0.5)),
        ("pflanze1", "topfpflanze", (5.4, 3.4, 5.85, 3.85)),
        ("ofen1", "ofen", (6.15, 0.15, 6.8, 0.7)), ("kue1", "kühlschrank", (9.25, 0.15, 9.85, 0.8)),
        ("tisch1", "esstisch", (7.3, 1.2, 8.5, 2.3)), ("stuhl1", "stuhl", (6.85, 1.55, 7.2, 1.9)),
        ("koffer1", "koffer", (11.2, 0.3, 11.8, 0.8)),
        ("bett1", "bett", (0.2, 6.8, 2.2, 8.85)), ("bett2", "bett", (6.9, 7.3, 8.35, 8.85)),
        ("wb1", "waschbecken", (8.7, 8.4, 9.4, 8.85)), ("wc1", "toilette", (11.3, 8.2, 11.85, 8.85)),
    ]
    I = [  # kleine Dinge am Boden: (oid, cls, x, y, beweglich)
        ("fb1", "fernbedienung", 3.3, 6.5, False),     # liegt nicht da, wo man sie erwartet
        ("tasse1", "tasse", 8.9, 2.9, False), ("handy1", "handy", 9.3, 3.3, False),
        ("fl1", "flasche", 10.5, 0.5, False), ("unb1", "unbekannt", 11.4, 3.3, False),
        ("teddy1", "teddy", 5.2, 6.3, False), ("ruck1", "rucksack", 1.3, 4.45, False),
        ("katze1", "katze", 3.6, 2.4, True),
    ]
    things = [Thing(o, c, (r[0] + r[2]) / 2, (r[1] + r[3]) / 2, r) for o, c, r in F]
    things += [Thing(o, c, x, y, None, mv) for o, c, x, y, mv in I]
    return Plan(rooms, walls, doors, things)


def rasterize(plan: Plan, res: float = TRUTH_RES, margin: float = 0.5):
    """Wahrheitsraster (True = belegt) und Raumraster (Index in plan.rooms, -1 = draußen).
    Ursprung (-margin, -margin)."""
    W, H = SIZE
    w = int(round((W + 2 * margin) / res))
    h = int(round((H + 2 * margin) / res))
    occ = np.zeros((h, w), bool)
    room = np.full((h, w), -1, np.int16)

    def cells(x0, y0, x1, y1):
        i0, i1 = int((min(y0, y1) + margin) / res), int((max(y0, y1) + margin) / res)
        j0, j1 = int((min(x0, x1) + margin) / res), int((max(x0, x1) + margin) / res)
        return slice(max(0, i0), min(h, i1 + 1)), slice(max(0, j0), min(w, j1 + 1))

    for k, r in enumerate(plan.rooms):
        room[cells(*r.rect)] = k
    t = WALL_T / 2
    for x0, y0, x1, y1 in plan.walls:
        occ[cells(x0 - t, y0 - t, x1 + t, y1 + t)] = True
    for x0, y0, x1, y1 in plan.doors:
        si, sj = cells(x0 - t - 0.01, y0 - t - 0.01, x1 + t + 0.01, y1 + t + 0.01)
        if x0 == x1:                                   # Tür in senkrechter Wand
            si = slice(si.start + 1, si.stop - 1)
        else:
            sj = slice(sj.start + 1, sj.stop - 1)
        occ[si, sj] = False
    for th in plan.things:
        if th.rect:
            occ[cells(*th.rect)] = True
    return occ, room, (-margin, -margin)
