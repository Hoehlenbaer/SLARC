# brain/sim2d/world2d.py
# Version 0.2 (11.11.2026) – 2D-Welt: Wahrheit, Körper, Kamera.  # SIM ONLY
# V0.2: nachgebildetes VLM für „Was ist das?“ (vlm_what) mit der gemessenen Trefferquote
#       (PC 08.11.2026: Haushalt ~0,76–0,78 mit Rahmen); face() dreht zu einem Punkt.
#
# Ersetzt für die Simulation: Fortbewegung (ESP32), Stereo-Tiefe, Detektion (Hailo) und
# Lokalisierung (SLAM). Schreibt nur ins Blackboard; das Brain liest nur dort.
#   - Körper: dreht auf der Stelle, geht dann geradeaus zum nächsten Wegpunkt.
#   - Kamera: Sichtkegel KAMERA_FOV, Reichweite KAMERA_RANGE_M; Tiefenstrahlen für die
#     Karte, Detektionen für sichtbare Dinge (Verdeckung durch Wände und Möbel).
#   - Lokalisierung: wahre Pose (Annahme: SLAM genau genug; Rauschen später).
#   - Raumnamen: Zellen bekommen beim ersten Freisehen den wahren Raumnamen. Auf dem
#     Roboter kommen Namen aus Ankern (perception_classes.ROOM_ANCHORS) oder vom Menschen.
# Zahlen sind Annahmen.

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..blackboard import Blackboard, Detection, PersonTrack, Pose
from ..needs import BATTERY_WH
from ..nav.gridmap import GridMap
from ..sim.world import BASE_W, LYING_W, WALK_WH_PER_M, ChatEvent, soc_to_voltage
from .floorplan import SIZE, TRUTH_RES, Plan, default_plan, rasterize

SPEED_M_S = 0.12                 # wie brain/sim/world.py
TURN_RAD_S = math.radians(30)
KAMERA_FOV = math.radians(80)
KAMERA_RANGE_M = 4.0
RAY_STEP_DEG = 2.0
P_MISS = 0.15                    # Detektion verpasst ein sichtbares Ding
PERSON_SPEED = 0.8
MAP_RES = 0.1
VLM_P_OK = 0.75                  # „Was ist das?“ richtig (gemessen, Haushalt mit Rahmen)
VLM_P_NOTHING = 0.8              # Fehlalarm als „nichts“ erkannt (Annahme)
VLM_WRONG = ["socke", "kabel", "spielzeug", "karton", "tüte", "schuh", "dose", "decke", "kissen", "flasche"]


@dataclass
class SimPerson:
    pid: str
    name: str                                    # nur für Chat und Ausgabe
    schedule: list                               # [(t_von_s, t_bis_s, raum)]
    x: float = -10.0
    y: float = -10.0
    room: Optional[str] = None
    path: Optional[list] = None


class World2D:
    def __init__(self, plan: Optional[Plan] = None, soc0: float = 0.9, seed: int = 1,
                 persons: Optional[list[SimPerson]] = None, chat: Optional[list[ChatEvent]] = None):
        self.plan = plan or default_plan()
        self.rng = random.Random(seed)
        self.occ, self.room_grid, self.origin = rasterize(self.plan)
        self.rooms = {r.name: r for r in self.plan.rooms}
        self.things = {t.oid: t for t in self.plan.things}
        self.persons = {p.pid: p for p in (persons or [])}
        self.chat = sorted(chat or [], key=lambda e: e.t)
        hx, hy, hth = self.plan.home
        self.x, self.y, self.th = hx, hy, hth
        self.t = 0.0
        self.energy_wh = soc0 * BATTERY_WH
        self.walked_m = 0.0
        self.mode = "stehen"
        self.waypoints: list[tuple[float, float]] = []
        self.spin_left = 0.0                      # Restwinkel beim Umsehen
        self.face_to: Optional[float] = None      # Zielrichtung beim Hindrehen
        self.blocked = False
        self.messages: list[tuple] = []
        W, H = SIZE
        gm = GridMap(W + 1.0, H + 1.0, MAP_RES, self.origin)
        self.bb = Blackboard(gm, Pose(hx, hy, hth, 0.0))
        self._ang = np.radians(np.arange(-KAMERA_FOV / 2 / math.radians(1), KAMERA_FOV / 2 / math.radians(1) + 0.01,
                                         RAY_STEP_DEG)).astype(np.float32)
        self._area_ids = [gm.area_id(r.name) for r in self.plan.rooms]
        self.sync()

    # ---------------------------------------------------------------- Wahrheit
    def truth_cell(self, x: float, y: float) -> tuple[int, int]:
        return int((y - self.origin[1]) / TRUTH_RES), int((x - self.origin[0]) / TRUTH_RES)

    def truth_blocked(self, x: float, y: float) -> bool:
        i, j = self.truth_cell(x, y)
        h, w = self.occ.shape
        return not (0 <= i < h and 0 <= j < w) or bool(self.occ[i, j])

    def room_of(self, x: float, y: float) -> Optional[str]:
        i, j = self.truth_cell(x, y)
        h, w = self.occ.shape
        k = int(self.room_grid[i, j]) if 0 <= i < h and 0 <= j < w else -1
        return self.plan.rooms[k].name if k >= 0 else None

    def truth_los(self, x0, y0, x1, y1, skip_end: float = 0.0) -> bool:
        d = math.hypot(x1 - x0, y1 - y0) - skip_end
        if d <= 0:
            return True
        n = int(d / (TRUTH_RES * 0.5)) + 1
        for k in range(1, n + 1):
            t = k / n * d / (d + skip_end)
            if self.truth_blocked(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t):
                return False
        return True

    # ---------------------------------------------------------------- Zeit und Akku
    def advance(self, dt: float, walking_m: float = 0.0, power_w: float = BASE_W) -> None:
        self.t += dt
        self.energy_wh -= power_w * dt / 3600.0 + WALK_WH_PER_M * walking_m
        self.walked_m += walking_m
        self._move_people(dt)
        self._move_cat(dt)

    def soc(self) -> float:
        return max(0.0, self.energy_wh / BATTERY_WH)

    # ---------------------------------------------------------------- Körper
    def set_path(self, pts: list[tuple[float, float]]) -> None:
        self.waypoints = list(pts[1:]) if len(pts) > 1 else list(pts)
        self.blocked = False

    def stop(self) -> None:
        self.waypoints = []
        self.spin_left = 0.0
        self.face_to = None
        if self.mode in ("laufen", "drehen"):
            self.mode = "stehen"                  # sonst gilt SLARC am Ziel noch eine Sekunde als laufend

    def spin(self, angle: float) -> None:
        self.spin_left = angle

    def face(self, x: float, y: float) -> None:
        self.waypoints = []
        self.face_to = math.atan2(y - self.y, x - self.x)

    def vlm_what(self, x: float, y: float) -> Optional[str]:
        """Nachgebildetes VLM: Antwort auf „Was ist das?“ zum Ausschnitt um (x, y). SIM ONLY."""
        cands = [t for t in self.things.values() if math.hypot(t.x - x, t.y - y) < 0.6]
        if not cands:
            return "nichts" if self.rng.random() < VLM_P_NOTHING else self.rng.choice(VLM_WRONG)
        t = min(cands, key=lambda t: math.hypot(t.x - x, t.y - y))
        truth = t.true_name or t.cls
        p = VLM_P_NOTHING if truth == "nichts" else VLM_P_OK
        if self.rng.random() < p:
            return truth
        return self.rng.choice([w for w in VLM_WRONG if w != truth])

    def step(self, dt: float, power_w: float = BASE_W) -> None:
        """Ein Zeitschritt Körper: drehen, gehen oder stehen; danach Sinne."""
        walked = 0.0
        if self.face_to is not None:
            err = (self.face_to - self.th + math.pi) % (2 * math.pi) - math.pi
            a = min(TURN_RAD_S * dt, abs(err))
            self.th += math.copysign(a, err)
            self.mode = "drehen"
            if abs(err) - a < math.radians(2):
                self.face_to = None
        elif self.spin_left > 0:
            a = min(TURN_RAD_S * dt, self.spin_left)
            self.th = (self.th + a) % (2 * math.pi)
            self.spin_left -= a
            self.mode = "drehen"
        elif self.waypoints:
            tx, ty = self.waypoints[0]
            want = math.atan2(ty - self.y, tx - self.x)
            err = (want - self.th + math.pi) % (2 * math.pi) - math.pi
            if abs(err) > math.radians(10):
                self.th += math.copysign(min(TURN_RAD_S * dt, abs(err)), err)
                self.mode = "drehen"
            else:
                self.th = want
                d = math.hypot(tx - self.x, ty - self.y)
                s = min(SPEED_M_S * dt, d)
                nx, ny = self.x + s * math.cos(want), self.y + s * math.sin(want)
                if self.truth_blocked(nx, ny):
                    self.blocked = True                # Karte war falsch: Hindernis im Weg
                    self.waypoints = []
                else:
                    self.x, self.y, walked = nx, ny, s
                    if d - s < 0.03:
                        self.waypoints.pop(0)
                self.mode = "laufen"
        else:
            self.mode = "liegen" if power_w == LYING_W else "stehen"
        self.advance(dt, walked, power_w)
        self.sense()

    def moving(self) -> bool:
        return bool(self.waypoints) or self.spin_left > 0 or self.face_to is not None

    # ---------------------------------------------------------------- Sinne -> Blackboard
    def sense(self) -> None:
        bb = self.bb
        # Tiefe (Stereo): Raycast gegen die Wahrheit
        a = self.th + self._ang
        d = np.arange(0.0, KAMERA_RANGE_M, TRUTH_RES * 0.5, dtype=np.float32)
        px = self.x + d[None, :] * np.cos(a)[:, None]
        py = self.y + d[None, :] * np.sin(a)[:, None]
        i = ((py - self.origin[1]) / TRUTH_RES).astype(np.int32)
        j = ((px - self.origin[0]) / TRUTH_RES).astype(np.int32)
        h, w = self.occ.shape
        out = (i < 0) | (i >= h) | (j < 0) | (j >= w)
        blk = out | self.occ[np.clip(i, 0, h - 1), np.clip(j, 0, w - 1)]
        hit = blk.any(axis=1)
        first = np.where(hit, blk.argmax(axis=1), len(d) - 1)
        ranges = d[first].astype(np.float32)
        ranges[~hit] = KAMERA_RANGE_M
        rows, cols = bb.map.integrate_scan(self.x, self.y, self.th, self._ang, ranges, hit)
        # Raumnamen für neu frei gesehene Zellen (SIM ONLY)
        if rows.size:
            wx, wy = bb.map.ox + (cols + 0.5) * bb.map.res, bb.map.oy + (rows + 0.5) * bb.map.res
            ti = ((wy - self.origin[1]) / TRUTH_RES).astype(np.int32).clip(0, h - 1)
            tj = ((wx - self.origin[0]) / TRUTH_RES).astype(np.int32).clip(0, w - 1)
            k = self.room_grid[ti, tj]
            ids = np.where(k >= 0, np.array(self._area_ids, np.int16)[np.clip(k, 0, None)], -1).astype(np.int16)
            bb.map.label(rows, cols, ids)
        # Detektion
        dets = []
        for th in self.things.values():
            if self._in_view(th.x, th.y):
                r = 0.0 if th.rect is None else 0.5 * min(th.rect[2] - th.rect[0], th.rect[3] - th.rect[1]) + 0.1
                if self.truth_los(self.x, self.y, th.x, th.y, skip_end=r + 0.05) and self.rng.random() > P_MISS:
                    dist = math.hypot(th.x - self.x, th.y - self.y)
                    s = 0.03 + 0.02 * dist
                    dets.append(Detection(th.cls, th.x + self.rng.gauss(0, s), th.y + self.rng.gauss(0, s),
                                          round(0.95 - 0.08 * dist, 2), self.t))
        bb.detections = dets
        for p in self.persons.values():
            if p.room and self._in_view(p.x, p.y) and self.truth_los(self.x, self.y, p.x, p.y, 0.2):
                bb.persons[p.pid] = PersonTrack(p.pid, p.x, p.y, self.t)    # wahre Kennung: SIM ONLY

    def _in_view(self, x: float, y: float) -> bool:
        dx, dy = x - self.x, y - self.y
        dist = math.hypot(dx, dy)
        if dist > KAMERA_RANGE_M or dist < 0.05:
            return dist < 0.05
        err = (math.atan2(dy, dx) - self.th + math.pi) % (2 * math.pi) - math.pi
        return abs(err) <= KAMERA_FOV / 2

    def expect_visible(self, x: float, y: float) -> bool:
        """Für den Tracker: Stelle liegt im Sichtkegel und frei nach eigener Karte (PORTABLE-Logik)."""
        return self._in_view(x, y) and self.bb.map.line_clear(self.x, self.y, x, y, 0.35)

    def sync(self) -> None:
        """Pose, Akku, Licht ins Blackboard (SLAM, ESP32-Brücke)."""
        bb = self.bb
        bb.t = self.t
        bb.pose = Pose(self.x, self.y, self.th, self.t)
        bb.robot.soc = self.soc()
        bb.robot.battery_v = soc_to_voltage(self.soc())
        bb.robot.mode = self.mode
        room = self.room_of(self.x, self.y)
        bb.robot.light = self.rooms[room].light if room else 1.0

    # ---------------------------------------------------------------- Menschen und Katze
    def _move_people(self, dt: float) -> None:
        for p in self.persons.values():
            want = next((r for a, b, r in p.schedule if a <= self.t < b), None)
            if want != p.room:
                if want is None:
                    p.room, p.x, p.y, p.path = None, -10.0, -10.0, None
                else:
                    tx, ty = self.rooms[want].spot
                    if p.room is None:                    # kommt nach Hause: an der Wohnungstür (Flur)
                        p.x, p.y = 0.4, 4.75
                    p.path = self._people_route(p.x, p.y, tx, ty)
                    p.room = want
            if p.path:
                tx, ty = p.path[0]
                d = math.hypot(tx - p.x, ty - p.y)
                s = min(PERSON_SPEED * dt, d)
                if d > 1e-6:
                    p.x += (tx - p.x) / d * s
                    p.y += (ty - p.y) / d * s
                if d - s < 0.02:
                    p.path.pop(0)

    def _people_route(self, x0, y0, x1, y1) -> list:
        """Menschen gehen über die Türmitten (grob, reicht für die Anzeige)."""
        r0, r1 = self.room_of(x0, y0), self.room_of(x1, y1)
        if r0 == r1 or r0 is None:
            return [(x1, y1)]
        pts = []
        for dx0, dy0, dx1, dy1 in self.plan.doors:
            cx, cy = (dx0 + dx1) / 2, (dy0 + dy1) / 2
            sides = {self.room_of(cx + 0.3, cy), self.room_of(cx - 0.3, cy),
                     self.room_of(cx, cy + 0.3), self.room_of(cx, cy - 0.3)}
            if r0 in sides and r1 in sides:
                return [(cx, cy), (x1, y1)]
            if r0 in sides and "flur" in sides:
                pts.append((cx, cy))
        for dx0, dy0, dx1, dy1 in self.plan.doors:
            cx, cy = (dx0 + dx1) / 2, (dy0 + dy1) / 2
            sides = {self.room_of(cx + 0.3, cy), self.room_of(cx - 0.3, cy),
                     self.room_of(cx, cy + 0.3), self.room_of(cx, cy - 0.3)}
            if r1 in sides and "flur" in sides:
                pts.append((cx, cy))
        return pts + [(x1, y1)]

    def _move_cat(self, dt: float) -> None:
        for th in self.things.values():
            if th.movable and self.rng.random() < dt / 900.0:          # im Mittel alle 15 min
                for _ in range(50):
                    r = self.rng.choice(self.plan.rooms)
                    x0, y0, x1, y1 = r.rect
                    x, y = self.rng.uniform(x0 + 0.4, x1 - 0.4), self.rng.uniform(y0 + 0.4, y1 - 0.4)
                    if not self.truth_blocked(x, y) and math.hypot(x - self.x, y - self.y) > 1.0:
                        th.x, th.y = x, y
                        break


def default_people() -> tuple[list[SimPerson], list[ChatEvent]]:
    """Wie brain/sim/world.default_flat: Marco und Laura, dazu das Chat-Drehbuch."""
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
        ChatEvent(1.95 * h, "Marco", "Wo ist meine Socke?"),         # erst nach „Was ist das?“ suchbar
    ]
    return persons, chat
