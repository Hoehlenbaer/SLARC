# brain/nav/layers.py
# Version 0.1 (11.11.2026) – Abgeleitete Kartenebenen fürs Blackboard.  # PORTABLE
#
# Aus der Belegungskarte: Kostenkarte (A*), Grenzen mit Erreichbarkeit, Bereiche,
# Weglänge nach Hause. Teuer (Dijkstra über die ganze Karte), deshalb nur alle
# REFRESH_S Sekunden bzw. wenn sich die Karte geändert hat. Auf dem Roboter läuft das
# im SLAM-/Navigationsprozess, in der Simulation in der Tagesschleife.

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from ..blackboard import Area, Blackboard, Frontier
from .astar import a_star, build_costmap, dijkstra, nearest_passable, path_length_m, simplify
from .frontier import anchor_point, area_centers, find_frontiers

REFRESH_S = 5.0


class MapLayers:
    def __init__(self, bb: Blackboard):
        self.bb = bb
        self.cost: Optional[np.ndarray] = None
        self._ver = -1
        self._t = -1e9

    def costmap(self) -> np.ndarray:
        m = self.bb.map
        if self.cost is None or m.version != self._ver:
            self.cost = build_costmap(m.states(), m.res)
            self._ver = m.version
        return self.cost

    def refresh(self, force: bool = False) -> None:
        bb = self.bb
        if not force and bb.t - self._t < REFRESH_S:
            return
        self._t = bb.t
        m = bb.map
        cost = self.costmap()
        st = m.states()
        start = nearest_passable(cost, m.to_cell(bb.pose.x, bb.pose.y), 6)
        reach = dijkstra(cost, start) if start else np.full(cost.shape, np.inf)
        bb.frontiers = []
        for f in find_frontiers(m, st):
            c = nearest_passable(cost, m.to_cell(f["x"], f["y"]), 6)
            ok = c is not None and np.isfinite(reach[c])
            bb.frontiers.append(Frontier(f["fid"], f["x"], f["y"], f["size"], f["area"], bool(ok)))
        bb.areas = {n: Area(n, x, y, c) for n, (x, y, c) in area_centers(m).items()}
        hc = nearest_passable(cost, m.to_cell(bb.home.x, bb.home.y), 6)
        if hc and start:
            d = reach[hc]
            bb.nav.home_dist_m = float(d * m.res) if np.isfinite(d) else None

    # ---------------------------------------------------------------- Ziele und Wege
    def target_point(self, target: str) -> Optional[tuple[float, float]]:
        """Ziel nach Name: Bereich, Grenze, Objekt-Track, Person, "home"."""
        bb = self.bb
        if target == "home":
            return bb.home.x, bb.home.y
        for f in bb.frontiers:
            if f.fid == target:
                return f.x, f.y
        if target in bb.objects:
            o = bb.objects[target]
            return o.x, o.y
        if target in bb.persons:
            p = bb.persons[target]
            return p.x, p.y
        if target in bb.map.area_names:
            return anchor_point(bb.map, target, self.costmap())
        return None

    def plan(self, x: float, y: float) -> Optional[list[tuple[float, float]]]:
        """Weg von der aktuellen Pose zu (x, y) als Wegpunkte in m; None = kein Weg."""
        bb, m = self.bb, self.bb.map
        cost = self.costmap()
        s = nearest_passable(cost, m.to_cell(bb.pose.x, bb.pose.y), 6)
        g = nearest_passable(cost, m.to_cell(x, y), 8)
        if s is None or g is None:
            return None
        cells = a_star(cost, s, g)
        if cells is None:
            return None
        cells = simplify(cells, cost)
        return [m.to_world(i, j) for i, j in cells]

    def path_length(self, pts: list[tuple[float, float]]) -> float:
        return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


__all__ = ["MapLayers", "path_length_m"]
