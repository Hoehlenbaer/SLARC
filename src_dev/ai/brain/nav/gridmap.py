# brain/nav/gridmap.py
# Version 0.1 (11.11.2026) – Belegungskarte (2D) für Navigation und Brain.  # PORTABLE
#
# Raster mit Log-Odds je Zelle (ROS-Konvention nach außen: -1 unbekannt, 0…100 belegt in %).
# Tiefenstrahlen (Stereo auf dem Roboter, Raycast in der Simulation) tragen frei/belegt ein.
# Zusätzlich je freier Zelle eine Bereichskennung (Raum), damit das Brain mit Namen
# arbeiten kann („küche“). Woher die Namen kommen, ist nicht Sache der Karte: in der
# Simulation aus der Wahrheit, auf dem Roboter aus Ankern bzw. vom Menschen benannt.
#
# Koordinaten: Welt in m, x nach rechts, y nach oben; Zelle (i, j) = (Zeile, Spalte),
# Zeile i wächst mit y. Nur numpy, kein scipy (auf dem Pi nicht vorausgesetzt).

from __future__ import annotations

import math
from typing import Optional

import numpy as np

# Zustände für Planer und Anzeige
UNKNOWN, FREE, OCC = 0, 1, 2

L_FREE = -0.4        # Log-Odds je „Strahl ging hindurch“
L_OCC = 0.9          # Log-Odds je „Strahl endete hier“
L_MIN, L_MAX = -4.0, 4.0
T_FREE = -0.35       # darunter frei
T_OCC = 0.6          # darüber belegt


class GridMap:
    def __init__(self, width_m: float, height_m: float, res: float = 0.1,
                 origin: tuple[float, float] = (0.0, 0.0)):
        self.res = res
        self.ox, self.oy = origin
        self.w = int(math.ceil(width_m / res))
        self.h = int(math.ceil(height_m / res))
        self.lo = np.zeros((self.h, self.w), np.float32)
        self.area = np.full((self.h, self.w), -1, np.int16)
        self.area_names: list[str] = []
        self.version = 0                       # zählt Änderungen (für Caches)

    # ---------------------------------------------------------------- Koordinaten
    def to_cell(self, x: float, y: float) -> tuple[int, int]:
        return int((y - self.oy) / self.res), int((x - self.ox) / self.res)

    def to_world(self, i: int, j: int) -> tuple[float, float]:
        return self.ox + (j + 0.5) * self.res, self.oy + (i + 0.5) * self.res

    def inside(self, i: int, j: int) -> bool:
        return 0 <= i < self.h and 0 <= j < self.w

    # ---------------------------------------------------------------- Zustände
    def states(self) -> np.ndarray:
        s = np.full(self.lo.shape, UNKNOWN, np.int8)
        s[self.lo < T_FREE] = FREE
        s[self.lo > T_OCC] = OCC
        return s

    def occupancy(self) -> np.ndarray:
        """ROS-Konvention: -1 unbekannt, sonst Belegungswahrscheinlichkeit 0…100."""
        p = np.round(100.0 / (1.0 + np.exp(-self.lo))).astype(np.int8)
        p[self.states() == UNKNOWN] = -1
        return p

    def state_at(self, x: float, y: float) -> int:
        i, j = self.to_cell(x, y)
        if not self.inside(i, j):
            return UNKNOWN
        v = self.lo[i, j]
        return FREE if v < T_FREE else OCC if v > T_OCC else UNKNOWN

    # ---------------------------------------------------------------- Eintragen
    def integrate_scan(self, x: float, y: float, theta: float, angles: np.ndarray,
                       ranges: np.ndarray, hit: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Strahlen ab (x, y) in Richtung theta+angles mit Länge ranges eintragen.
        hit[k]: Strahl k endete an einem Hindernis (sonst maximale Reichweite).
        Gibt die Zellen zurück, die in diesem Scan frei gesehen wurden (Zeilen, Spalten)."""
        step = self.res * 0.5
        n = int(np.max(ranges) / step) + 1 if len(ranges) else 0
        d = np.arange(n, dtype=np.float32) * step                       # (n,)
        a = theta + angles.astype(np.float32)                           # (k,)
        mask = d[None, :] < (ranges[:, None] - self.res * 0.5)          # frei bis kurz vor dem Ende
        px = x + d[None, :] * np.cos(a)[:, None]
        py = y + d[None, :] * np.sin(a)[:, None]
        fi = ((py - self.oy) / self.res).astype(np.int32)[mask]
        fj = ((px - self.ox) / self.res).astype(np.int32)[mask]
        ok = (fi >= 0) & (fi < self.h) & (fj >= 0) & (fj < self.w)
        free_idx = np.unique(fi[ok] * self.w + fj[ok])
        hx = x + ranges[hit] * np.cos(a[hit])
        hy = y + ranges[hit] * np.sin(a[hit])
        oi = ((hy - self.oy) / self.res).astype(np.int32)
        oj = ((hx - self.ox) / self.res).astype(np.int32)
        ok = (oi >= 0) & (oi < self.h) & (oj >= 0) & (oj < self.w)
        occ_idx = np.unique(oi[ok] * self.w + oj[ok])
        free_idx = np.setdiff1d(free_idx, occ_idx, assume_unique=True)
        flat = self.lo.reshape(-1)
        flat[free_idx] = np.clip(flat[free_idx] + L_FREE, L_MIN, L_MAX)
        flat[occ_idx] = np.clip(flat[occ_idx] + L_OCC, L_MIN, L_MAX)
        self.version += 1
        return free_idx // self.w, free_idx % self.w

    # ---------------------------------------------------------------- Bereiche (Räume)
    def area_id(self, name: str) -> int:
        if name not in self.area_names:
            self.area_names.append(name)
        return self.area_names.index(name)

    def label(self, rows: np.ndarray, cols: np.ndarray, ids: np.ndarray) -> None:
        """Bereichskennung für Zellen setzen (nur wo noch keine ist)."""
        cur = self.area[rows, cols]
        m = (cur < 0) & (ids >= 0)
        self.area[rows[m], cols[m]] = ids[m]

    def area_at(self, x: float, y: float) -> Optional[str]:
        i, j = self.to_cell(x, y)
        if not self.inside(i, j):
            return None
        k = int(self.area[i, j])
        if k < 0:                                   # Zelle ohne Kennung: nächste mit Kennung (3×3, 5×5)
            for r in (1, 2):
                win = self.area[max(0, i - r):i + r + 1, max(0, j - r):j + r + 1]
                vals = win[win >= 0]
                if vals.size:
                    k = int(np.bincount(vals).argmax())
                    break
        return self.area_names[k] if k >= 0 else None

    # ---------------------------------------------------------------- Sichtlinie
    def line_clear(self, x0: float, y0: float, x1: float, y1: float, skip_end_m: float = 0.3) -> bool:
        """Keine belegte Zelle zwischen den Punkten (die letzten skip_end_m zählen nicht:
        das Ziel selbst darf an einer Wand stehen)."""
        dist = math.hypot(x1 - x0, y1 - y0) - skip_end_m
        if dist <= 0:
            return True
        n = int(dist / (self.res * 0.5)) + 1
        t = np.linspace(0.0, dist, n) / (dist + skip_end_m)
        px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        i = ((py - self.oy) / self.res).astype(np.int32)
        j = ((px - self.ox) / self.res).astype(np.int32)
        ok = (i >= 0) & (i < self.h) & (j >= 0) & (j < self.w)
        return not bool(np.any(self.lo[i[ok], j[ok]] > T_OCC))
