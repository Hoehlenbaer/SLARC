# brain/sim/bt.py
# Version 0.1 (07.11.2026) – Behavior-Tree-Schicht: ein fester Teilbaum je Verhalten.
#
# Der Arbiter wählt das Verhalten (Option), build_tree() baut den passenden
# Teilbaum aus py_trees-Knoten, der Runner tickt ihn, bis SUCCESS oder FAILURE.
# Das Ergebnis geht als last_result zurück an den Arbiter. Das LLM baut nie Bäume.
#
# Die Blätter sprechen hier mit der simulierten Welt (world.py). Auf dem Roboter
# sprechen dieselben Teilbäume über das Protokoll mit dem ESP32 bzw. mit SLAM
# und Perzeption; dafür werden nur die Blätter ausgetauscht.

from __future__ import annotations

from typing import Callable, Optional

import py_trees
from py_trees.common import Status

from ..datatypes import Option
from ..perception_classes import ROOM_ANCHORS, normalize_item, typical_rooms
from .world import World

DT = 0.5            # Tick der Bäume in der Simulation, s


class Ctx:
    """Gemeinsamer Zustand für die Blätter eines Baums (eine Art Blackboard)."""

    def __init__(self, world: World, log: Callable[[str], None]):
        self.world = world
        self.log = log
        self.found: Optional[str] = None      # oid des gefundenen Objekts
        self.report_text: Optional[str] = None


class Leaf(py_trees.behaviour.Behaviour):
    def __init__(self, name: str, ctx: Ctx):
        super().__init__(name)
        self.ctx = ctx


class Wait(Leaf):
    """Etwas tun, das nur Zeit kostet (Geste, Pause, Nachricht senden)."""

    def __init__(self, name: str, ctx: Ctx, seconds: float):
        super().__init__(name, ctx)
        self.seconds = seconds

    def initialise(self):
        self.left = self.seconds

    def update(self):
        self.ctx.world.advance(DT)
        self.left -= DT
        return Status.SUCCESS if self.left <= 0 else Status.RUNNING


class GoTo(Leaf):
    def __init__(self, ctx: Ctx, room: Optional[str] = None, room_fn: Optional[Callable[[], Optional[str]]] = None):
        super().__init__(f"Gehe nach {room}" if room else "Gehe hin", ctx)
        self.room, self.room_fn = room, room_fn

    def initialise(self):
        goal = self.room or (self.room_fn() if self.room_fn else None)
        self.ok = goal is not None and self.ctx.world.start_walk(goal)
        if goal and not self.room:
            self.name = f"Gehe nach {goal}"

    def update(self):
        if not self.ok:
            return Status.FAILURE
        return Status.SUCCESS if self.ctx.world.walk(DT) else Status.RUNNING


class LookAround(Wait):
    """Umsehen: Raum gilt danach als erkundet. Erkennt den Raum an seinen Ankern."""

    def __init__(self, ctx: Ctx, seconds: float = 6.0):
        super().__init__("Umsehen", ctx, seconds)

    def update(self):
        s = super().update()
        if s == Status.SUCCESS:
            w = self.ctx.world
            if w.room not in w.explored:
                w.explored.add(w.room)
                anchors = sorted({o.cls for o in w.visible_objects() if o.cls in ROOM_ANCHORS})
                guess = {ROOM_ANCHORS[a] for a in anchors}
                hint = f", Anker {', '.join(anchors)} -> {'/'.join(sorted(guess))}" if anchors else ", keine Anker"
                self.ctx.log(f"   erkundet: {w.room}{hint}")
        return s


class Visible(Leaf):
    """Bedingung: Ist ein Ding dieser Klasse im Raum zu sehen?"""

    def __init__(self, ctx: Ctx, cls: str):
        super().__init__(f"Sehe ich {cls}?", ctx)
        self.cls = cls

    def update(self):
        for o in self.ctx.world.visible_objects():
            if o.cls == self.cls:
                self.ctx.found = o.oid
                return Status.SUCCESS
        return Status.FAILURE


class ObjectHere(Leaf):
    def __init__(self, ctx: Ctx, oid: str):
        super().__init__(f"{oid} noch da?", ctx)
        self.oid = oid

    def update(self):
        o = self.ctx.world.objects.get(self.oid)
        return Status.SUCCESS if o and o.room == self.ctx.world.room else Status.FAILURE


class Report(Leaf):
    """Meldung an die Menschen (Web-Chat/Handy)."""

    def __init__(self, ctx: Ctx, oid: Optional[str] = None):
        super().__init__("Melden", ctx)
        self.oid = oid

    def update(self):
        w = self.ctx.world
        oid = self.oid or self.ctx.found
        o = w.objects.get(oid) if oid else None
        text = f"{o.cls.capitalize()} ist im Raum {o.room}." if o else "Ich habe nichts gefunden."
        w.messages.append((w.t, text))
        self.ctx.log(f"   >> Meldung: {text}")
        return Status.SUCCESS


class PersonHere(Leaf):
    def __init__(self, ctx: Ctx, pid: str):
        super().__init__("Person da?", ctx)
        self.pid = pid

    def update(self):
        return Status.SUCCESS if self.ctx.world.find_person(self.pid) == self.ctx.world.room else Status.FAILURE


class FollowPerson(Leaf):
    """Einer Person für eine Weile folgen (in der Simulation: ihrem Raum)."""

    def __init__(self, ctx: Ctx, pid: str, seconds: float = 90.0):
        super().__init__("Folgen", ctx)
        self.pid, self.seconds = pid, seconds

    def initialise(self):
        self.left = self.seconds

    def update(self):
        w = self.ctx.world
        room = w.find_person(self.pid)
        if room is None:
            return Status.FAILURE            # aus den Augen verloren
        if room != w.room and not w.moving():
            w.start_walk(room)
        w.walk(DT) if w.moving() else w.advance(DT)
        self.left -= DT
        return Status.SUCCESS if self.left <= 0 else Status.RUNNING


class Push(Leaf):
    def __init__(self, ctx: Ctx, rng, p_ok: float = 0.8):
        super().__init__("Herausschieben", ctx)
        self.rng, self.p_ok = rng, p_ok

    def initialise(self):
        self.left = 8.0

    def update(self):
        self.ctx.world.advance(DT)
        self.left -= DT
        if self.left > 0:
            return Status.RUNNING
        return Status.SUCCESS if self.rng.random() < self.p_ok else Status.FAILURE


class LieDown(Leaf):
    """Ausruhen: läuft, bis der Arbiter etwas anderes startet."""

    def __init__(self, ctx: Ctx):
        super().__init__("Hinlegen", ctx)

    def update(self):
        self.ctx.world.advance(DT)
        return Status.RUNNING


def _seq(name, *children):
    s = py_trees.composites.Sequence(name, memory=True)
    s.add_children(list(children))
    return s


def _sel(name, *children):
    s = py_trees.composites.Selector(name, memory=True)
    s.add_children(list(children))
    return s


def search_plan(world: World, item: str, places_fn=None, last_seen: Optional[dict] = None) -> list[str]:
    """Reihenfolge der Räume: zuerst wo es zuletzt gesehen wurde (Gedächtnis), dann LLM
    (search_places) oder typische Räume, dann der Rest nach Entfernung."""
    first = []
    if last_seen and item in last_seen:
        first.append(last_seen[item][0])
    first += list(places_fn(item, list(world.rooms))) if places_fn else list(typical_rooms(item))
    first = list(dict.fromkeys(first))
    rest = sorted(world.rooms, key=lambda r: world.route(world.room, r)[1] if world.route(world.room, r) else 1e9)
    return [r for r in first if r in world.rooms] + [r for r in rest if r not in first]


def build_tree(opt: Option, ctx: Ctx, rng, places_fn=None, last_seen=None) -> py_trees.behaviour.Behaviour:
    w = ctx.world
    b, a = opt.behavior, opt.arg
    if b == "explore_frontier":
        return _seq(f"Erkunden: {a}", GoTo(ctx, a), LookAround(ctx))
    if b == "look_around":
        return _seq("Umsehen", LookAround(ctx, 5.0))
    if b == "wander":
        return _seq(f"Rundgang: {a}", GoTo(ctx, a), LookAround(ctx, 5.0))
    if b == "doze":
        return _seq("Dösen", Wait("Hinlegen, Augen halb zu", ctx, 300.0))
    if b in ("inspect_object", "approach_avoid"):
        room = w.objects[a].room if a in w.objects else w.room
        if b == "inspect_object":
            return _seq(f"Untersuchen: {a}", GoTo(ctx, room), ObjectHere(ctx, a),
                        Wait("Annähern", ctx, 4.0), Wait("Antasten", ctx, 2.0))
        return _seq(f"Vorsichtig: {a}", GoTo(ctx, room), ObjectHere(ctx, a), Wait("Annähern", ctx, 2.0),
                    Wait("Zurückweichen", ctx, 2.0), Wait("Wieder annähern", ctx, 3.0), Wait("Antasten", ctx, 2.0))
    if b == "search_item":
        cls = normalize_item(a) or a
        plan = search_plan(w, cls, places_fn, last_seen)
        tries = [_seq(f"in {r}?", GoTo(ctx, r), LookAround(ctx, 4.0), Visible(ctx, cls)) for r in plan]
        return _seq(f"Suchen: {cls}", _sel("Räume nacheinander", *tries), Report(ctx))
    if b == "report":
        return _seq("Melden", Wait("Nachricht senden", ctx, 1.0), Report(ctx, a))
    if b == "greet":
        return _seq("Begrüßen", GoTo(ctx, room_fn=lambda: w.find_person(a)), PersonHere(ctx, a),
                    Wait("Aufrichten, Bein heben", ctx, 3.0))
    if b == "follow":
        return _seq("Begleiten", GoTo(ctx, room_fn=lambda: w.find_person(a)), FollowPerson(ctx, a))
    if b == "push_out":
        cls = normalize_item(a) or a
        plan = search_plan(w, cls, places_fn, last_seen)
        tries = [_seq(f"in {r}?", GoTo(ctx, r), LookAround(ctx, 4.0), Visible(ctx, cls)) for r in plan]
        return _seq(f"Hervorschieben: {cls}", _sel("Räume nacheinander", *tries),
                    Wait("Tief gehen", ctx, 4.0), Push(ctx, rng), Report(ctx))
    if b == "return_home":
        return _seq("Heimweg", GoTo(ctx, w.home))
    if b == "rest":
        return _seq("Ausruhen", LieDown(ctx))
    if b == "retreat":
        return _seq("Rückzug", Wait("Ducken", ctx, 2.0), GoTo(ctx, w.prev_room))
    return _seq("Abwarten", Wait("Stehen, Gewicht verlagern", ctx, 10.0))
