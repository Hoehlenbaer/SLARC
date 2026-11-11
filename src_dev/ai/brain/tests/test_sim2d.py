# brain/tests/test_sim2d.py
# Version 0.1 (11.11.2026) – 2D-Simulation: Welt, Kartenaufbau, Tageslauf, Viewer.

import json
import math

import numpy as np
import pytest

pytest.importorskip("py_trees")

from brain.nav.gridmap import FREE  # noqa: E402
from brain.sim2d import day2d  # noqa: E402
from brain.sim2d.floorplan import default_plan, rasterize  # noqa: E402
from brain.sim2d.world2d import World2D, default_people  # noqa: E402


def test_floorplan_doors_open():
    plan = default_plan()
    occ, room, origin = rasterize(plan)
    for x0, y0, x1, y1 in plan.doors:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        i, j = int((cy - origin[1]) / 0.05), int((cx - origin[0]) / 0.05)
        assert not occ[i, j], (x0, y0)
    assert {r.name for r in plan.rooms} == {"wohnzimmer", "küche", "abstellraum", "flur", "schlafzimmer",
                                           "kinderzimmer", "bad"}


def test_world_spin_maps_and_labels():
    w = World2D()
    w.spin(2 * math.pi)
    while w.moving():
        w.step(0.5)
    st = w.bb.map.states()
    assert (st == FREE).sum() > 500
    assert w.bb.area_at(w.x, w.y) == "flur"
    assert w.bb.map.state_at(w.x, w.y) == FREE


def test_day_run_records_and_explores(tmp_path):
    data = day2d.run(hours=0.4, quiet=True)
    s = data["summary"]
    assert len(s["bereiche"]) >= 4 and s["karte_frei_m2"] > 40 and s["gelaufen_m"] > 10
    fr = data["frames"]
    assert len(fr) > 500 and fr[0]["t"] <= 2.0
    assert sum(len(f["map"]) for f in fr) > 3000
    assert any(o[1] == "sofa" for f in fr for o in f["obj"])
    assert any(l[1].startswith("->") for f in fr for l in f["log"])
    out = tmp_path / "v.html"
    day2d.write_html(data, str(out))
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>") and "/*__SIM_DATA__*/" not in html and '"frames":' in html
    day2d.write_html(data, str(tmp_path / "f.html"), standalone=False)
    assert (tmp_path / "f.html").read_text(encoding="utf-8").startswith("<title>")


def test_brain_sees_only_blackboard():
    """Die Beobachtung entsteht aus dem Blackboard: unbekannte Räume sind dem Brain unbekannt."""
    persons, chat = default_people()
    w = World2D(persons=persons, chat=chat)
    obs = w.bb.to_observation([], False, False, None)
    assert obs.known_places == [] and obs.objects == []
    w.spin(2 * math.pi)
    while w.moving():
        w.step(0.5)
        w.sync()
    from brain.nav.layers import MapLayers
    MapLayers(w.bb).refresh(force=True)
    obs = w.bb.to_observation([], False, False, None)
    assert "flur" in obs.known_places and "bad" not in obs.known_places and obs.frontier


def test_identify_option_only_for_open_unknowns():
    from brain.behaviors import build_options
    from brain.datatypes import ObjectSeen, Observation
    from brain.memory import Memory
    from brain.needs import NeedsModel
    from brain.safety import check
    mem = Memory()
    obs = Observation(t=100.0, battery_v=12.3, home_dist_m=2.0, at_home=False, place="flur",
                      objects=[ObjectSeen("unbekannt-1", "unbekannt", "flur", 1.5, True, False, "offen"),
                               ObjectSeen("unbekannt-2", "unbekannt", "flur", 1.5, True, False, "vermutet")])
    st, _ = NeedsModel(mem).update(obs)
    keys = [o.key for o in build_options(obs, st, mem, check(obs))]
    assert any(k.startswith("identify(unbekannt-1") for k in keys)
    assert not any("unbekannt-2" in k for k in keys)                       # schon gefragt
    assert not any(k.startswith(("inspect_object(unbekannt", "approach_avoid(unbekannt")) for k in keys)


def test_decide_name_cases():
    from brain.blackboard import TrackedObject
    from brain.sim2d.bt2d import Ctx, DecideName
    w = World2D()
    ctx = Ctx(w, lambda m: None)
    def track(tid, answers):
        o = TrackedObject(tid, "unbekannt", 1.0, 4.7, 0.9, 0, 0, 1, area="flur", answers=list(answers))
        w.bb.objects[tid] = o
        DecideName(ctx, tid).update()
        return o
    o = track("u1", ["dose", "dose"])
    assert o.name_sure and o.label == "dose" and o.ident == "sicher"
    o = track("u2", ["kabel", "socke"])
    assert not o.name_sure and o.ident == "unklar" and o.name_vlm == "socke" and ctx.questions == ["u2"]
    assert "Was ist das?" in w.messages[-1][1]
    o = track("u3", ["nichts", "nichts"])
    assert o.ident == "nichts" and o not in w.bb.recent_objects()
    o = track("u4", ["kabel"])
    assert o.ident == "vermutet" and "u4" in ctx.questions


def test_day_identifies_asks_and_finds_named_item():
    data = day2d.run(hours=3.0, quiet=True)
    logs = [l for f in data["frames"] for _, l in f["log"]]
    assert any("(zweimal gleich)" in l for l in logs)                     # zwei gleiche Blicke
    assert any("benennt" in l for l in logs)                              # Mensch antwortet
    assert any(m == "Die Socke ist im Schlafzimmer." for _, m in data["messages"])
    assert not any(l.startswith("-> inspect_object(unbekannt") for l in logs)   # Unbekanntes nie antasten
