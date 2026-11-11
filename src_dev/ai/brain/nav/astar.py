# brain/nav/astar.py
# Version 0.1 (11.11.2026) – Kostenkarte und A* auf der Belegungskarte.  # PORTABLE
#
# Nach src_dev/motion_control/Pathfinder_V4.py (Marco): Kostenkarte mit Strafe für
# Wandnähe, 8er-Nachbarschaft, euklidische Heuristik. Ohne matplotlib und scipy, damit
# es headless und auf dem Pi läuft; Höhe/Steigung (V4) entfällt in der Wohnung.
# Unterschiede zu V4:
#   - Kosten je Schritt = Schrittlänge × Zellkosten (V4: Schritt + Zellkosten).
#   - Harte Sperre um Hindernisse = Roboterradius (Aufblasen), weiche Strafe bis MIN_CLEARANCE_M.
#   - Unbekannte Zellen sind begehbar, aber teurer (optimistisch planen, unterwegs neu planen).

from __future__ import annotations

import heapq
import math
from typing import Optional

import numpy as np

from .gridmap import FREE, OCC, UNKNOWN

ROBOT_RADIUS_M = 0.25       # halbe Spannweite mit Beinen (Annahme, nachmessen)
MIN_CLEARANCE_M = 0.5       # bis hierher kostet Wandnähe extra
W_CLEARANCE = 20.0          # Strafe direkt an der Sperrgrenze (V4: 160 bei Schritt 1, hier je m)
UNKNOWN_COST = 4.0          # Zusatzkosten je unbekannter Zelle

NEIGHBORS = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
             (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)), (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2))]


def obstacle_distance(occ: np.ndarray, max_cells: int) -> np.ndarray:
    """Abstand jeder Zelle zum nächsten Hindernis in Zellen (Schachbrett-Metrik),
    höchstens max_cells. Wellenfront durch wiederholtes Ausdehnen (ohne scipy)."""
    dist = np.full(occ.shape, max_cells, np.int16)
    front = occ.copy()
    seen = occ.copy()
    dist[occ] = 0
    for d in range(1, max_cells):
        grow = np.zeros_like(front)
        grow[1:, :] |= front[:-1, :]
        grow[:-1, :] |= front[1:, :]
        grow[:, 1:] |= front[:, :-1]
        grow[:, :-1] |= front[:, 1:]
        grow[1:, 1:] |= front[:-1, :-1]
        grow[1:, :-1] |= front[:-1, 1:]
        grow[:-1, 1:] |= front[1:, :-1]
        grow[:-1, :-1] |= front[1:, 1:]
        grow &= ~seen
        if not grow.any():
            break
        dist[grow] = d
        seen |= grow
        front = grow
    return dist


def build_costmap(states: np.ndarray, res: float) -> np.ndarray:
    """Zellkosten ≥ 1, np.inf = gesperrt (Hindernis oder näher als Roboterradius)."""
    occ = states == OCC
    max_cells = int(math.ceil(MIN_CLEARANCE_M / res)) + 1
    d_m = obstacle_distance(occ, max_cells).astype(np.float32) * res
    cost = np.ones(states.shape, np.float32)
    near = d_m < MIN_CLEARANCE_M
    cost[near] += W_CLEARANCE * (MIN_CLEARANCE_M - d_m[near]) / MIN_CLEARANCE_M
    cost[states == UNKNOWN] += UNKNOWN_COST
    cost[d_m < ROBOT_RADIUS_M] = np.inf
    return cost


def nearest_passable(cost: np.ndarray, cell: tuple[int, int], max_r: int = 10) -> Optional[tuple[int, int]]:
    """Nächste begehbare Zelle um cell (Ziel in der Wand oder im Möbel)."""
    i0, j0 = cell
    h, w = cost.shape
    best, bd = None, 1e9
    for r in range(0, max_r + 1):
        for i in range(i0 - r, i0 + r + 1):
            for j in (j0 - r, j0 + r) if abs(i - i0) != r else range(j0 - r, j0 + r + 1):
                if 0 <= i < h and 0 <= j < w and np.isfinite(cost[i, j]):
                    d = (i - i0) ** 2 + (j - j0) ** 2
                    if d < bd:
                        best, bd = (i, j), d
        if best is not None:
            return best
    return None


def a_star(cost: np.ndarray, start: tuple[int, int], goal: tuple[int, int],
           max_expand: int = 400_000) -> Optional[list[tuple[int, int]]]:
    """Kürzester Weg (Kosten) von start nach goal, Liste von Zellen inkl. beider Enden."""
    h, w = cost.shape
    if not (0 <= goal[0] < h and 0 <= goal[1] < w) or not np.isfinite(cost[goal]):
        return None
    flat = cost.reshape(-1)
    s, g = start[0] * w + start[1], goal[0] * w + goal[1]
    gi, gj = goal
    g_score = {s: 0.0}
    came: dict[int, int] = {}
    openq = [(0.0, s)]
    closed = set()
    n = 0
    while openq and n < max_expand:
        _, u = heapq.heappop(openq)
        if u == g:
            path = [u]
            while u in came:
                u = came[u]
                path.append(u)
            return [(p // w, p % w) for p in reversed(path)]
        if u in closed:
            continue
        closed.add(u)
        n += 1
        ui, uj = divmod(u, w)
        gu = g_score[u]
        for di, dj, step in NEIGHBORS:
            vi, vj = ui + di, uj + dj
            if not (0 <= vi < h and 0 <= vj < w):
                continue
            v = vi * w + vj
            c = flat[v]
            if not math.isfinite(c) or v in closed:
                continue
            ng = gu + step * c
            if ng < g_score.get(v, math.inf):
                g_score[v] = ng
                came[v] = u
                heapq.heappush(openq, (ng + math.hypot(gi - vi, gj - vj), v))
    return None


def dijkstra(cost: np.ndarray, start: tuple[int, int], max_dist_cells: float = math.inf) -> np.ndarray:
    """Weglänge (in Zellen, ohne Kostenaufschläge) von start zu allen erreichbaren Zellen.
    Für „Weg nach Hause“ und Erreichbarkeit von Grenzen; inf = unerreichbar."""
    h, w = cost.shape
    passable = np.isfinite(cost).reshape(-1)
    dist = np.full(h * w, np.inf)
    s = start[0] * w + start[1]
    if not passable[s]:
        return dist.reshape(h, w)
    dist[s] = 0.0
    q = [(0.0, s)]
    while q:
        d, u = heapq.heappop(q)
        if d > dist[u] or d > max_dist_cells:
            continue
        ui, uj = divmod(u, w)
        for di, dj, step in NEIGHBORS:
            vi, vj = ui + di, uj + dj
            if 0 <= vi < h and 0 <= vj < w:
                v = vi * w + vj
                nd = d + step
                if passable[v] and nd < dist[v]:
                    dist[v] = nd
                    heapq.heappush(q, (nd, v))
    return dist.reshape(h, w)


def simplify(path: list[tuple[int, int]], cost: np.ndarray, max_cost: float = 3.0) -> list[tuple[int, int]]:
    """Wegpunkte ausdünnen: gerade Stücke zusammenfassen, solange die Verbindungslinie
    nur über günstige Zellen (Kosten ≤ max_cost, also nicht dicht an der Wand) führt."""
    if len(path) <= 2:
        return list(path)

    def clear(a, b) -> bool:
        n = max(abs(b[0] - a[0]), abs(b[1] - a[1])) * 2 + 1
        for k in range(n + 1):
            t = k / n
            i = int(round(a[0] + (b[0] - a[0]) * t))
            j = int(round(a[1] + (b[1] - a[1]) * t))
            if not cost[i, j] <= max_cost:
                return False
        return True

    out = [path[0]]
    k = 0
    while k < len(path) - 1:
        nxt = k + 1
        for m in range(len(path) - 1, k + 1, -1):
            if clear(path[k], path[m]):
                nxt = m
                break
        out.append(path[nxt])
        k = nxt
    return out


def path_length_m(path: list[tuple[int, int]], res: float) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:])) * res
