# brain/nav/frontier.py
# Version 0.1 (11.11.2026) – Grenzen zum Unbekannten und Bereiche aus der Karte.  # PORTABLE
#
# Grenze (Frontier) = freie Zelle mit unbekanntem Nachbarn. Zusammenhängende Grenzzellen
# bilden eine Grenze; zu kleine (Rauschen, Ecken) fallen weg. Jede Grenze bekommt einen
# lesbaren Namen aus Bereich und Himmelsrichtung („flur ost“), weil das Brain mit Namen
# arbeitet (Option „Unbekanntes erkunden: flur ost“).

from __future__ import annotations

from collections import Counter, deque

import numpy as np

from .gridmap import FREE, UNKNOWN, GridMap

MIN_FRONTIER_CELLS = 6        # ~0,6 m Grenzlänge bei 10 cm Raster


def frontier_cells(states: np.ndarray) -> np.ndarray:
    free = states == FREE
    unk = states == UNKNOWN
    nb = np.zeros_like(unk)
    nb[1:, :] |= unk[:-1, :]
    nb[:-1, :] |= unk[1:, :]
    nb[:, 1:] |= unk[:, :-1]
    nb[:, :-1] |= unk[:, 1:]
    return free & nb


def clusters(mask: np.ndarray, min_cells: int = MIN_FRONTIER_CELLS) -> list[list[tuple[int, int]]]:
    """Zusammenhängende Zellen (8er-Nachbarschaft), größte zuerst."""
    h, w = mask.shape
    seen = np.zeros_like(mask)
    out = []
    for i0, j0 in zip(*np.nonzero(mask)):
        if seen[i0, j0]:
            continue
        comp, q = [], deque([(i0, j0)])
        seen[i0, j0] = True
        while q:
            i, j = q.popleft()
            comp.append((int(i), int(j)))
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    a, b = i + di, j + dj
                    if 0 <= a < h and 0 <= b < w and mask[a, b] and not seen[a, b]:
                        seen[a, b] = True
                        q.append((a, b))
        if len(comp) >= min_cells:
            out.append(comp)
    out.sort(key=len, reverse=True)
    return out


def direction(dx: float, dy: float) -> str:
    if abs(dx) >= abs(dy):
        return "ost" if dx > 0 else "west"
    return "nord" if dy > 0 else "süd"


def area_centers(m: GridMap) -> dict[str, tuple[float, float, int]]:
    """Mittelpunkt (x, y) und Zellenzahl je benanntem Bereich (nur freie Zellen)."""
    st = m.states()
    out = {}
    for k, name in enumerate(m.area_names):
        ii, jj = np.nonzero((m.area == k) & (st == FREE))
        if ii.size:
            x, y = m.to_world(float(ii.mean()), float(jj.mean()))
            out[name] = (x - m.res * 0.5, y - m.res * 0.5, int(ii.size))
    return out


def anchor_point(m: GridMap, name: str, cost: np.ndarray) -> tuple[float, float] | None:
    """Begehbarer Punkt in einem Bereich, möglichst nah an dessen Mitte (Ziel für „Gehe in die Küche“)."""
    if name not in m.area_names:
        return None
    k = m.area_names.index(name)
    ii, jj = np.nonzero((m.area == k) & np.isfinite(cost) & (m.states() == FREE))
    if not ii.size:
        return None
    ci, cj = ii.mean(), jj.mean()
    n = int(np.argmin((ii - ci) ** 2 + (jj - cj) ** 2))
    return m.to_world(int(ii[n]), int(jj[n]))


def find_frontiers(m: GridMap, states: np.ndarray | None = None) -> list[dict]:
    """Grenzen mit Name, Mittelpunkt, Zielzelle (die Grenzzelle nächst dem Schwerpunkt) und Größe."""
    st = m.states() if states is None else states
    centers = area_centers(m)
    out, names = [], Counter()
    for comp in clusters(frontier_cells(st)):
        ii = np.array([c[0] for c in comp])
        jj = np.array([c[1] for c in comp])
        ci, cj = ii.mean(), jj.mean()
        k = int(np.argmin((ii - ci) ** 2 + (jj - cj) ** 2))
        gx, gy = m.to_world(int(ii[k]), int(jj[k]))
        labels = [int(m.area[i, j]) for i, j in comp if m.area[i, j] >= 0]
        area = m.area_names[Counter(labels).most_common(1)[0][0]] if labels else "unbenannt"
        c = centers.get(area)
        name = f"{area} {direction(gx - c[0], gy - c[1])}" if c else area
        names[name] += 1
        if names[name] > 1:
            name = f"{name} {names[name]}"
        out.append({"fid": name, "x": gx, "y": gy, "size": len(comp), "area": area})
    return out
