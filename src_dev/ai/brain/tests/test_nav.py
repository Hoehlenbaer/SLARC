# brain/tests/test_nav.py
# Version 0.1 (11.11.2026) – Karte, A*, Grenzen, Tracker, Blackboard (ohne Simulation).

import json
import math

import numpy as np

from brain.blackboard import Blackboard, Detection, Pose
from brain.nav.astar import a_star, build_costmap, dijkstra, simplify
from brain.nav.frontier import find_frontiers
from brain.nav.gridmap import FREE, OCC, UNKNOWN, GridMap
from brain.nav.tracker import MOVED_M, ObjectTracker


def scan_room(m: GridMap, x: float, y: float, door=(1.5, 2.4)):
    """Rundumscan in einem 6×4-m-Raum mit Trennwand bei x=3 und Tür (y in door)."""
    ang = np.radians(np.arange(-180, 180, 2.0)).astype(np.float32)
    rs, hs = [], []
    for a in ang:
        for d in np.arange(0, 4.0, 0.02):
            px, py = x + d * math.cos(a), y + d * math.sin(a)
            if px <= 0.05 or px >= 5.95 or py <= 0.05 or py >= 3.95 or (2.95 <= px <= 3.05 and not door[0] <= py <= door[1]):
                rs.append(d), hs.append(True)
                break
        else:
            rs.append(4.0), hs.append(False)
    m.integrate_scan(x, y, 0.0, ang, np.array(rs, np.float32), np.array(hs))


def test_gridmap_scan_and_states():
    m = GridMap(6, 4, 0.1)
    assert (m.states() == UNKNOWN).all()
    scan_room(m, 1.0, 2.0)
    assert m.state_at(1.5, 2.0) == FREE and m.state_at(2.96, 0.8) == OCC   # Vorderkante der Wand
    occ = m.occupancy()
    assert occ.min() == -1 and occ.max() > 60
    assert m.line_clear(1.0, 2.0, 2.0, 2.0) and not m.line_clear(1.0, 1.0, 5.0, 1.0)


def test_astar_through_door_and_dijkstra():
    m = GridMap(6, 4, 0.1)
    for x in (1.0, 2.5, 4.5):
        scan_room(m, x, 2.0)
    cost = build_costmap(m.states(), m.res)
    s, g = m.to_cell(1.0, 1.0), m.to_cell(5.0, 3.0)
    path = a_star(cost, s, g)
    assert path and path[0] == s and path[-1] == g
    door = [m.to_world(*c) for c in path if abs(m.to_world(*c)[0] - 3.0) < 0.06]
    assert door and all(1.5 <= y <= 2.4 for _, y in door)            # durch die Tür
    assert len(simplify(path, cost)) < len(path)
    d = dijkstra(cost, s)
    assert np.isfinite(d[g]) and d[g] * m.res > math.hypot(4, 2)
    assert np.isinf(cost[m.to_cell(3.0, 0.8)])                        # Wand gesperrt


def test_frontiers_named_by_area():
    m = GridMap(6, 4, 0.1)
    scan_room(m, 1.0, 2.0)
    rows, cols = np.nonzero(m.states() == FREE)
    m.label(rows, cols, np.full(rows.shape, m.area_id("wohnzimmer"), np.int16))
    fr = find_frontiers(m)
    assert fr and all(f["area"] == "wohnzimmer" for f in fr)
    assert any(f["fid"].startswith("wohnzimmer ost") for f in fr)     # Tür nach Osten


def test_tracker_new_missing_back_moved():
    tracks, tr = {}, ObjectTracker()
    vis = lambda x, y: True
    area = lambda x, y: "küche" if x < 5 else "flur"
    ev = tr.update(tracks, [Detection("tasse", 1.0, 1.0, 0.9, 0.0)], 0.0, vis, area)
    assert ev == [("neu", "tasse-1")]
    tr.update(tracks, [Detection("tasse", 1.1, 1.0, 0.9, 0.5)], 0.5, vis, area)
    assert len(tracks) == 1 and tracks["tasse-1"].n_seen == 2
    for k in range(4):
        ev = tr.update(tracks, [], 1.0 + k, vis, area)
    assert ev == [("fehlt", "tasse-1")] and tracks["tasse-1"].state == "fehlt"
    ev = tr.update(tracks, [Detection("tasse", 1.2, 1.0, 0.9, 6.0)], 6.0, vis, area)
    assert ev == [("wieder_da", "tasse-1")] and not tracks["tasse-1"].moved
    for k in range(4):
        tr.update(tracks, [], 7.0 + k, vis, area)
    ev = tr.update(tracks, [Detection("tasse", 1.2 + MOVED_M + 5, 1.0, 0.9, 12.0)], 12.0, vis, area)
    assert ev == [("verschoben", "tasse-1")] and tracks["tasse-1"].moved and tracks["tasse-1"].area == "flur"
    tr.update(tracks, [], 13.0, lambda x, y: False, area)              # nicht im Blick: kein Fehlen
    assert tracks["tasse-1"].misses == 0


def test_blackboard_observation_and_json():
    m = GridMap(6, 4, 0.1)
    scan_room(m, 1.0, 2.0)
    rows, cols = np.nonzero(m.states() == FREE)
    m.label(rows, cols, np.full(rows.shape, m.area_id("wohnzimmer"), np.int16))
    bb = Blackboard(m, Pose(1.0, 2.0, 0.0))
    bb.t = 10.0
    ObjectTracker().update(bb.objects, [Detection("handy", 2.0, 2.0, 0.9, 10.0)], 10.0, lambda x, y: True, bb.area_at)
    obs = bb.to_observation([], False, False, None)
    assert obs.place == "wohnzimmer" and obs.at_home and obs.floor_known
    assert obs.objects and obs.objects[0].cls == "handy" and abs(obs.objects[0].dist_m - 1.0) < 1e-6
    bb.t = 30.0
    assert not bb.to_observation([], False, False, None).objects          # nicht mehr „im Blick“
    d = json.loads(json.dumps(bb.to_dict()))
    assert d["version"] == "0.1" and d["map"]["areas"] == ["wohnzimmer"] and d["objects"][0]["track_id"] == "handy-1"
