# brain/tests/test_sim.py
# Version 0.1 (07.11.2026) – Rauchtest für den simulierten Tag (ohne LLM).

import sys

import pytest

pytest.importorskip("py_trees")

from brain.datatypes import Option  # noqa: E402
from brain.sim import day  # noqa: E402
from brain.sim.bt import Ctx, build_tree, search_plan  # noqa: E402
from brain.sim.world import default_flat, soc_to_voltage  # noqa: E402
from brain.needs import soc_from_voltage  # noqa: E402


def test_soc_voltage_roundtrip():
    for s in (0.05, 0.3, 0.6, 0.95):
        assert abs(soc_from_voltage(soc_to_voltage(s)) - s) < 1e-6


def test_search_starts_where_last_seen():
    w = default_flat()
    plan = search_plan(w, "fernbedienung", last_seen={"fernbedienung": ["schlafzimmer", 10.0]})
    assert plan[0] == "schlafzimmer" and len(plan) == len(w.rooms)


def test_search_tree_finds_object():
    w = default_flat()
    logs = []
    ctx = Ctx(w, logs.append)
    import random
    tree = build_tree(Option("search_item", "fernbedienung", "", 0.5, "search"), ctx, random.Random(0))
    tree.setup_with_descendants()
    for _ in range(5000):
        tree.tick_once()
        if tree.status.name in ("SUCCESS", "FAILURE"):
            break
    assert tree.status.name == "SUCCESS" and w.room == "schlafzimmer"
    assert any("Fernbedienung" in m for _, m in w.messages)


def test_day_runs(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["day", "--hours", "1.2", "--seed", "3"])
    day.main()
    out = capsys.readouterr().out
    assert "Ende nach" in out and "explore_frontier" in out
    assert "Schlüssel kann ich leider noch nicht erkennen" in out
