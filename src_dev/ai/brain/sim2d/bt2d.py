# brain/sim2d/bt2d.py
# Version 0.1 (11.11.2026) – Behavior-Tree-Blätter auf Karte und Blackboard.
#
# Gleiche Teilbäume wie brain/sim/bt.py, aber die Blätter navigieren mit A* auf der
# eigenen Karte (nav/layers.py) und sehen nur, was im Blackboard steht. Die Bewegung
# selbst führt der simulierte Körper aus (world2d); auf dem Roboter ersetzt die
# ESP32-Brücke nur Ctx.step() und Ctx.drive().

from __future__ import annotations

import math
from typing import Callable, Optional

import py_trees
from py_trees.common import Status

from ..datatypes import Option
from ..nav.layers import MapLayers
from ..nav.tracker import ObjectTracker
from ..perception_classes import normalize_item, typical_rooms
from ..sim.world import LYING_W
from .world2d import BASE_W, SPEED_M_S, World2D

DT = 0.5
REPLAN_S = 8.0
ARRIVE_M = 0.35


class Ctx:
    """Gemeinsamer Zustand der Blätter: Körper, Blackboard, Kartenebenen, Tracker."""

    def __init__(self, world: World2D, log: Callable[[str], None]):
        self.world = world
        self.bb = world.bb
        self.layers = MapLayers(world.bb)
        self.tracker = ObjectTracker()
        self.log = log
        self.found: Optional[str] = None
        self.node = ""
        self.prev_point = (world.bb.home.x, world.bb.home.y)

    def step(self, power_w: float = BASE_W, sense: bool = True) -> None:
        """Ein Zeitschritt: Körper bewegen, Sinne, Blackboard, Tracker, Kartenebenen."""
        w, bb = self.world, self.bb
        w.step(DT, power_w)
        w.sync()
        for kind, tid in self.tracker.update(bb.objects, bb.detections, bb.t, w.expect_visible, bb.area_at):
            o = bb.objects[tid]
            text = {"neu": f"neu: {o.cls} ({tid}, {o.area})", "fehlt": f"fehlt: {o.cls} ({tid}, {o.area})",
                    "verschoben": f"verschoben: {o.cls} ({tid}, jetzt {o.area})",
                    "wieder_da": f"wieder da: {o.cls} ({tid}, war verdeckt)"}[kind]
            bb.event(kind, text)
            self.log(f"   {text}")
        self.layers.refresh()


class Leaf(py_trees.behaviour.Behaviour):
    def __init__(self, name: str, ctx: Ctx):
        super().__init__(name)
        self.ctx = ctx

    def tick(self):
        self.ctx.node = self.name
        yield from super().tick()


class Wait(Leaf):
    def __init__(self, name: str, ctx: Ctx, seconds: float, lying: bool = False):
        super().__init__(name, ctx)
        self.seconds, self.lying = seconds, lying

    def initialise(self):
        self.left = self.seconds
        self.ctx.world.stop()

    def update(self):
        self.ctx.step(LYING_W if self.lying else BASE_W)
        self.left -= DT
        return Status.SUCCESS if self.left <= 0 else Status.RUNNING


class NavigateTo(Leaf):
    """Mit A* auf der eigenen Karte zu einem Ziel: Bereich, Grenze, Objekt, Person, "home"."""

    def __init__(self, ctx: Ctx, target: Optional[str] = None, target_fn: Optional[Callable[[], Optional[str]]] = None,
                 approach_m: float = 0.0, label: str = ""):
        super().__init__(f"Gehe zu {label or target or '…'}", ctx)
        self.target, self.target_fn, self.approach_m = target, target_fn, approach_m

    def _goal(self):
        tgt = self.target or (self.target_fn() if self.target_fn else None)
        p = self.ctx.layers.target_point(tgt) if tgt else None
        if p and self.approach_m > 0:                 # vor dem Ding stehen bleiben, nicht darauf
            bb = self.ctx.bb
            dx, dy = bb.pose.x - p[0], bb.pose.y - p[1]
            d = math.hypot(dx, dy)
            if d > self.approach_m:
                p = (p[0] + dx / d * self.approach_m, p[1] + dy / d * self.approach_m)
            else:
                p = (bb.pose.x, bb.pose.y)
        return tgt, p

    def _plan(self) -> bool:
        tgt, p = self._goal()
        nav = self.ctx.bb.nav
        if p is None:
            nav.status = "kein_ziel"
            return False
        pts = self.ctx.layers.plan(*p)
        nav.goal, nav.goal_label = p, str(tgt)
        if pts is None:
            nav.status, nav.path = "kein_weg", []
            return False
        nav.path, nav.status = pts, "unterwegs"
        self.ctx.world.set_path(pts)
        self.goal = p
        return True

    def initialise(self):
        self.ctx.layers.refresh(force=True)
        self.ok = self._plan()
        self.t_plan = self.ctx.bb.t
        bb = self.ctx.bb
        dist = self.ctx.layers.path_length(bb.nav.path) if self.ok else 0.0
        self.deadline = bb.t + 3.0 * dist / SPEED_M_S + 60.0
        if self.ok and not self.target:
            self.name = f"Gehe zu {bb.nav.goal_label}"

    def update(self):
        if not self.ok:
            return Status.FAILURE
        ctx, bb, w = self.ctx, self.ctx.bb, self.ctx.world
        ctx.step()
        if math.hypot(bb.pose.x - self.goal[0], bb.pose.y - self.goal[1]) < ARRIVE_M:
            w.stop()
            bb.nav.status, bb.nav.path = "angekommen", []
            return Status.SUCCESS
        if bb.t > self.deadline:
            w.stop()
            bb.nav.status = "zeit_um"
            return Status.FAILURE
        if w.blocked or not w.moving() or bb.t - self.t_plan > REPLAN_S:
            bb.nav.replans += 1
            self.t_plan = bb.t
            ctx.layers.refresh(force=True)
            if not self._plan():
                w.stop()
                return Status.FAILURE
        return Status.RUNNING

    def terminate(self, new_status):
        if new_status == Status.INVALID:
            self.ctx.world.stop()


class LookAround(Leaf):
    """Einmal auf der Stelle drehen: Karte und Detektion rundum."""

    def __init__(self, ctx: Ctx, turns: float = 1.0):
        super().__init__("Umsehen", ctx)
        self.turns = turns

    def initialise(self):
        self.ctx.world.stop()
        self.ctx.world.spin(2 * math.pi * self.turns)

    def update(self):
        self.ctx.step()
        return Status.RUNNING if self.ctx.world.moving() else Status.SUCCESS


class Visible(Leaf):
    def __init__(self, ctx: Ctx, cls: str):
        super().__init__(f"Sehe ich {cls}?", ctx)
        self.cls = cls

    def update(self):
        bb = self.ctx.bb
        hits = [o for o in bb.recent_objects() if o.cls == self.cls]
        if hits:
            self.ctx.found = min(hits, key=lambda o: bb.dist(o.x, o.y)).track_id
            return Status.SUCCESS
        return Status.FAILURE


class ObjectHere(Leaf):
    def __init__(self, ctx: Ctx, tid: str):
        super().__init__(f"{tid} noch da?", ctx)
        self.tid = tid

    def update(self):
        bb = self.ctx.bb
        o = bb.objects.get(self.tid)
        return Status.SUCCESS if o and o.state == "da" and bb.t - o.last_seen < 6.0 else Status.FAILURE


class Report(Leaf):
    def __init__(self, ctx: Ctx, tid: Optional[str] = None):
        super().__init__("Melden", ctx)
        self.tid = tid

    def update(self):
        bb, w = self.ctx.bb, self.ctx.world
        tid = self.tid or self.ctx.found
        o = bb.objects.get(tid) if tid else None
        text = f"{o.cls.capitalize()} ist im Raum {o.area}." if o else "Ich habe nichts gefunden."
        w.messages.append((bb.t, text))
        bb.event("meldung", text)
        self.ctx.log(f"   >> Meldung: {text}")
        return Status.SUCCESS


class PersonHere(Leaf):
    def __init__(self, ctx: Ctx, pid: str):
        super().__init__("Person da?", ctx)
        self.pid = pid

    def update(self):
        bb = self.ctx.bb
        p = bb.persons.get(self.pid)
        ok = p is not None and bb.t - p.last_seen < 4.0 and bb.dist(p.x, p.y) < 2.5
        return Status.SUCCESS if ok else Status.FAILURE


class FollowPerson(Leaf):
    def __init__(self, ctx: Ctx, pid: str, seconds: float = 90.0):
        super().__init__("Folgen", ctx)
        self.pid, self.seconds = pid, seconds

    def initialise(self):
        self.left = self.seconds
        self.t_plan = -1e9

    def update(self):
        ctx, bb = self.ctx, self.ctx.bb
        p = bb.persons.get(self.pid)
        if p is None or bb.t - p.last_seen > 20.0:
            ctx.world.stop()
            return Status.FAILURE                    # aus den Augen verloren
        if bb.t - self.t_plan > 3.0:
            self.t_plan = bb.t
            if bb.dist(p.x, p.y) > 1.2:
                d = bb.dist(p.x, p.y)
                gx, gy = p.x + (bb.pose.x - p.x) / d * 1.0, p.y + (bb.pose.y - p.y) / d * 1.0
                pts = ctx.layers.plan(gx, gy)
                if pts:
                    ctx.world.set_path(pts)
                    bb.nav.path, bb.nav.goal, bb.nav.goal_label, bb.nav.status = pts, (gx, gy), self.pid, "unterwegs"
            else:
                ctx.world.stop()
                ctx.world.th = math.atan2(p.y - bb.pose.y, p.x - bb.pose.x)   # zur Person drehen
        ctx.step()
        self.left -= DT
        return Status.SUCCESS if self.left <= 0 else Status.RUNNING


class Push(Leaf):
    def __init__(self, ctx: Ctx, rng, p_ok: float = 0.8):
        super().__init__("Herausschieben", ctx)
        self.rng, self.p_ok = rng, p_ok

    def initialise(self):
        self.left = 8.0

    def update(self):
        self.ctx.step()
        self.left -= DT
        if self.left > 0:
            return Status.RUNNING
        return Status.SUCCESS if self.rng.random() < self.p_ok else Status.FAILURE


class LieDown(Leaf):
    def __init__(self, ctx: Ctx):
        super().__init__("Hinlegen", ctx)

    def update(self):
        self.ctx.step(LYING_W)
        return Status.RUNNING


def _seq(name, *children):
    s = py_trees.composites.Sequence(name, memory=True)
    s.add_children(list(children))
    return s


def _sel(name, *children):
    s = py_trees.composites.Selector(name, memory=True)
    s.add_children(list(children))
    return s


def search_plan(ctx: Ctx, item: str, places_fn=None, last_seen: Optional[dict] = None) -> list[str]:
    """Bekannte Bereiche: zuerst wo es zuletzt gesehen wurde, dann LLM bzw. typische Räume,
    dann der Rest nach Entfernung. Noch nicht kartierte Räume kann SLARC nicht ansteuern."""
    bb = ctx.bb
    known = [a for a in bb.areas.values() if a.cells >= 30]
    names = [a.name for a in known]
    first = [last_seen[item][0]] if last_seen and item in last_seen else []
    first += list(places_fn(item, names)) if places_fn else list(typical_rooms(item))
    first = [r for r in dict.fromkeys(first) if r in names]
    rest = sorted((a for a in known if a.name not in first), key=lambda a: bb.dist(a.x, a.y))
    return first + [a.name for a in rest]


def build_tree(opt: Option, ctx: Ctx, rng, places_fn=None, last_seen=None) -> py_trees.behaviour.Behaviour:
    bb = ctx.bb
    b, a = opt.behavior, opt.arg
    if b == "explore_frontier":
        return _seq(f"Erkunden: {a}", NavigateTo(ctx, a), LookAround(ctx))
    if b == "look_around":
        return _seq("Umsehen", LookAround(ctx))
    if b == "wander":
        return _seq(f"Rundgang: {a}", NavigateTo(ctx, a), LookAround(ctx))
    if b == "doze":
        return _seq("Dösen", Wait("Hinlegen, Augen halb zu", ctx, 300.0, lying=True))
    if b == "seek_company":
        return _seq(f"Gesellschaft suchen: {a}", NavigateTo(ctx, a), LookAround(ctx))
    if b in ("inspect_object", "approach_avoid"):
        if b == "inspect_object":
            return _seq(f"Untersuchen: {a}", NavigateTo(ctx, a, approach_m=0.6), ObjectHere(ctx, a),
                        Wait("Annähern", ctx, 4.0), Wait("Antasten", ctx, 2.0))
        return _seq(f"Vorsichtig: {a}", NavigateTo(ctx, a, approach_m=1.0), ObjectHere(ctx, a),
                    Wait("Annähern", ctx, 2.0), Wait("Zurückweichen", ctx, 2.0), Wait("Wieder annähern", ctx, 3.0),
                    Wait("Antasten", ctx, 2.0))
    if b in ("search_item", "push_out"):
        cls = normalize_item(a) or a
        plan = search_plan(ctx, cls, places_fn, last_seen)
        tries = [_seq(f"in {r}?", NavigateTo(ctx, r), LookAround(ctx), Visible(ctx, cls)) for r in plan]
        if not tries:
            tries = [_seq("hier?", LookAround(ctx), Visible(ctx, cls))]
        if b == "search_item":
            return _seq(f"Suchen: {cls}", _sel("Bereiche nacheinander", *tries), Report(ctx))
        return _seq(f"Hervorschieben: {cls}", _sel("Bereiche nacheinander", *tries),
                    NavigateTo(ctx, target_fn=lambda: ctx.found, approach_m=0.4, label=cls),
                    Wait("Tief gehen", ctx, 4.0), Push(ctx, rng), Report(ctx))
    if b == "report":
        return _seq("Melden", Wait("Nachricht senden", ctx, 1.0), Report(ctx, a))
    if b == "greet":
        return _seq("Begrüßen", NavigateTo(ctx, a, approach_m=1.0, label="Person"), PersonHere(ctx, a),
                    Wait("Aufrichten, Bein heben", ctx, 3.0))
    if b == "follow":
        return _seq("Begleiten", NavigateTo(ctx, a, approach_m=1.0, label="Person"), FollowPerson(ctx, a))
    if b == "return_home":
        return _seq("Heimweg", NavigateTo(ctx, "home"))
    if b == "rest":
        return _seq("Ausruhen", LieDown(ctx))
    if b == "retreat":
        return _seq("Rückzug", Wait("Ducken", ctx, 2.0), NavigateTo(ctx, "home"))
    return _seq("Abwarten", Wait("Stehen, Gewicht verlagern", ctx, 10.0))
