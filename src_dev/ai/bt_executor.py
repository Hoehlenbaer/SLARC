"""
bt_executor.py — SLARC Behavior Tree Executor
"""

import time
import threading
import py_trees
from dataclasses import dataclass
from typing import Optional

@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

@dataclass
class TrackedObject:
    class_name: str
    world_pos:  Vec3
    confidence: float
    last_seen:  float
    track_id:   int

class MockBlackboard:
    def __init__(self):
        self._lock       = threading.RLock()
        self._frontiers  = 50
        self._objects    = {}
        self._battery    = 100.0
        self._at_goal    = False
        self._charging   = False
        self._tick_count = 0

    def sim_tick(self, dt: float = 0.1,
                 drain_per_sec: float = 5.0,
                 charge_per_sec: float = 30.0):
        """
        Time-proportional simulation.
        dt             : real seconds per tick (= 1/hz)
        drain_per_sec  : battery % lost per real second when driving
        charge_per_sec : battery % gained per real second when docked
        Default at 10 Hz: ~5%/s drain  → 100% in 20s
                          ~30%/s charge → 0→90% in 3s
        """
        with self._lock:
            self._tick_count += 1
            if self._charging:
                self._battery = min(100.0, self._battery + charge_per_sec * dt)
            else:
                self._battery = max(0.0,   self._battery - drain_per_sec  * dt)

    def set_charging(self, v: bool):
        """Enable/disable charging simulation (call when docked at home)."""
        with self._lock:
            self._charging = v

    def set_frontiers(self, n: int):
        with self._lock:
            self._frontiers = max(0, n)

    def set_battery(self, pct: float):
        with self._lock:
            self._battery = float(pct)

    def set_object(self, name, x, y, confidence=0.9):
        with self._lock:
            self._objects[name] = TrackedObject(name, Vec3(x,y,0), confidence, time.time(), hash(name))

    def remove_object(self, name):
        with self._lock:
            self._objects.pop(name, None)

    def set_at_goal(self, v):
        with self._lock:
            self._at_goal = v

    def get_frontiers(self):
        with self._lock:
            return list(range(self._frontiers))

    def find(self, name):
        with self._lock:
            return self._objects.get(name)

    def get_position(self, name):
        with self._lock:
            obj = self._objects.get(name)
            return obj.world_pos if obj else None

    def is_visible(self, name):
        with self._lock:
            return name in self._objects

    def battery_percent(self):
        with self._lock:
            return self._battery

    def at_home(self):
        with self._lock:
            return self._at_goal

    def reached_goal(self):
        with self._lock:
            return self._at_goal

    def tick_count(self):
        with self._lock:
            return self._tick_count

blackboard = MockBlackboard()

def set_blackboard(bb):
    global blackboard
    blackboard = bb


# ================================================================
# Mission Progress Tracker
# Persists stage completion OUTSIDE py_trees memory.
# When ReactiveGuard preempts the Mission Sequence, py_trees calls
# terminate(INVALID) on it — clearing memory=True state and causing
# a full restart. MissionProgress survives this reset, allowing
# StageWrapper to skip already-completed stages in O(1).
# ================================================================

class MissionProgress:
    def __init__(self, n_stages: int):
        self._completed = [False] * n_stages
        self._lock       = threading.Lock()

    def mark_done(self, idx: int):
        with self._lock:
            self._completed[idx] = True
            print(f"  [Progress] Stage {idx} complete "
                  f"({sum(self._completed)}/{len(self._completed)} done)")

    def is_done(self, idx: int) -> bool:
        with self._lock:
            return self._completed[idx]

    def reset(self):
        with self._lock:
            self._completed = [False] * len(self._completed)

    def summary(self) -> str:
        with self._lock:
            return " ".join("✓" if d else "░" for d in self._completed)


# Global progress tracker — set by build_root()
mission_progress: Optional[MissionProgress] = None


# ================================================================
# Stage Progress Nodes
# Uses standard py_trees composites only — no direct child.update()
# calls that bypass py_trees internal tick state management.
#
# Per-stage structure in the Mission Sequence:
#
#   Selector(memory=False)          "Stage N"
#     StageAlreadyDone(N)           → SUCCESS if done (1-tick skip)
#     Sequence(memory=True)         "Run[N]"
#       <stage content>             → actual policy subtree
#       MarkStageDone(N)            → marks done, returns SUCCESS
# ================================================================

class StageAlreadyDone(py_trees.behaviour.Behaviour):
    """Returns SUCCESS immediately if stage N was already completed."""
    def __init__(self, idx: int):
        super().__init__(f"Done?[{idx}]")
        self.idx = idx

    def update(self):
        return (py_trees.common.Status.SUCCESS
                if (mission_progress and mission_progress.is_done(self.idx))
                else py_trees.common.Status.FAILURE)


class MarkStageDone(py_trees.behaviour.Behaviour):
    """Called when stage content succeeds — marks stage as permanently done."""
    def __init__(self, idx: int):
        super().__init__(f"Mark[{idx}]")
        self.idx = idx

    def update(self):
        if mission_progress:
            mission_progress.mark_done(self.idx)
        return py_trees.common.Status.SUCCESS


class BatteryAbove(py_trees.behaviour.Behaviour):
    def __init__(self, threshold):
        super().__init__(f"Batt>{threshold:.0f}%")
        self.threshold = threshold
    def update(self):
        return (py_trees.common.Status.SUCCESS
                if blackboard.battery_percent() > self.threshold
                else py_trees.common.Status.FAILURE)

class ObjectVisible(py_trees.behaviour.Behaviour):
    def __init__(self, object_name):
        super().__init__(f"Visible({object_name})")
        self.object_name = object_name
    def update(self):
        return (py_trees.common.Status.SUCCESS
                if blackboard.is_visible(self.object_name)
                else py_trees.common.Status.FAILURE)

class TimeElapsed(py_trees.behaviour.Behaviour):
    def __init__(self, seconds):
        super().__init__(f"Time>{seconds:.0f}s")
        self.seconds  = seconds
        self._started = None
    def initialise(self):
        if self._started is None:
            self._started = time.perf_counter()
    def update(self):
        if self._started is None:
            return py_trees.common.Status.FAILURE
        return (py_trees.common.Status.SUCCESS
                if (time.perf_counter() - self._started) >= self.seconds
                else py_trees.common.Status.FAILURE)
    def terminate(self, new_status):
        if new_status == py_trees.common.Status.INVALID:
            self._started = None

class ChargingNode(py_trees.behaviour.Behaviour):
    """
    Waits at home until battery reaches target_pct.
    Enables charging simulation in MockBlackboard on entry,
    disables it on exit so battery drain resumes during mission.
    """

    def __init__(self, target_pct: float):
        super().__init__(f"Charge>{target_pct:.0f}%")
        self.target_pct = target_pct

    def initialise(self):
        blackboard.set_charging(True)
        print(f"      [ChargingNode] docked, charging to {self.target_pct:.0f}%...")

    def update(self):
        current = blackboard.battery_percent()
        if current >= self.target_pct:
            print(f"      [ChargingNode] charged to {current:.0f}% OK")
            return py_trees.common.Status.SUCCESS
        print(f"      [ChargingNode] charging... {current:.0f}%/{self.target_pct:.0f}%")
        return py_trees.common.Status.RUNNING

    def terminate(self, new_status):
        blackboard.set_charging(False)   # resume normal drain after undocking


class GoToRegion(py_trees.behaviour.Behaviour):
    def __init__(self, region, max_distance=None):
        super().__init__(f"GoTo({region})")
        self.region       = region
        self.max_distance = max_distance
        self._ticks       = 0
    def initialise(self):
        self._ticks = 0
        blackboard.set_at_goal(False)
        dist = f", max {self.max_distance}m" if self.max_distance else ""
        print(f"      [GoToRegion] -> '{self.region}'{dist}")
    def update(self):
        self._ticks += 1
        if self._ticks >= 3:
            blackboard.set_at_goal(True)
            print(f"      [GoToRegion] arrived at '{self.region}' OK")
            return py_trees.common.Status.SUCCESS
        return py_trees.common.Status.RUNNING

class FrontierExplore(py_trees.behaviour.Behaviour):
    def __init__(self, strategy="frontier_only", mode="normal"):
        super().__init__(f"Explore({strategy})")
        self.strategy = strategy
        self.mode     = mode
    def update(self):
        frontiers = blackboard.get_frontiers()
        if not frontiers:
            print(f"      [FrontierExplore] all cells mapped OK")
            return py_trees.common.Status.SUCCESS
        blackboard.set_frontiers(max(0, len(frontiers) - 5))
        print(f"      [FrontierExplore] {len(frontiers)} frontiers remaining")
        return py_trees.common.Status.RUNNING

class SearchForObject(py_trees.behaviour.Behaviour):
    """Self-terminates with SUCCESS when object found. No external guard needed."""
    def __init__(self, object_name, strategy=None):
        super().__init__(f"Search({object_name})")
        self.object_name = object_name
        self.strategy    = strategy
        self._ticks      = 0
    def initialise(self):
        self._ticks = 0
    def update(self):
        if blackboard.is_visible(self.object_name):
            print(f"      [SearchForObject] found '{self.object_name}' OK")
            return py_trees.common.Status.SUCCESS
        self._ticks += 1
        print(f"      [SearchForObject] seeking '{self.object_name}' ({self.strategy or 'frontier'}), tick {self._ticks}")
        return py_trees.common.Status.RUNNING

class FollowObject(py_trees.behaviour.Behaviour):
    def __init__(self, object_name, mode="normal"):
        super().__init__(f"Follow({object_name})")
        self.object_name = object_name
        self.mode        = mode
    def update(self):
        pos = blackboard.get_position(self.object_name)
        if pos is None:
            print(f"      [FollowObject] lost '{self.object_name}' -> FAILURE")
            return py_trees.common.Status.FAILURE
        batt = blackboard.battery_percent()
        print(f"      [FollowObject] '{self.object_name}' @ ({pos.x:.1f},{pos.y:.1f}), batt={batt:.0f}%")
        return py_trees.common.Status.RUNNING

class InteractWithObject(py_trees.behaviour.Behaviour):
    """Single-shot: runs once then SUCCESS."""
    def __init__(self, object_name, interaction):
        super().__init__(f"{interaction.capitalize()}({object_name})")
        self.object_name = object_name
        self.interaction = interaction
        self._done       = False
    def initialise(self):
        self._done = False
    def update(self):
        if not self._done:
            print(f"      [Interact] {self.interaction} '{self.object_name}' OK")
            self._done = True
            return py_trees.common.Status.RUNNING
        return py_trees.common.Status.SUCCESS

class ReturnHome(py_trees.behaviour.Behaviour):
    def __init__(self):
        super().__init__("ReturnHome")
        self._ticks = 0
    def initialise(self):
        self._ticks = 0
        blackboard.set_at_goal(False)
    def update(self):
        self._ticks += 1
        if self._ticks >= 3:
            blackboard.set_at_goal(True)
            print(f"      [ReturnHome] arrived home OK")
            return py_trees.common.Status.SUCCESS
        print(f"      [ReturnHome] heading home...")
        return py_trees.common.Status.RUNNING


def make_stop_guard(child, stop_conditions, policy):
    """
    Runs child until stop condition triggers, then returns SUCCESS.
    Uses Selector pattern — SUCCESS on trigger, not FAILURE.

      Selector(memory=False)
        Sequence(memory=False)
          [continue-while checks]   <- FAIL when stop fires
          child                     <- RUNNING normally
        Success("StopConditionMet") <- triggers when above fails
    """
    checks = []
    for sc in stop_conditions:
        if sc == "battery_threshold" and policy.get("battery_threshold") is not None:
            checks.append(BatteryAbove(policy["battery_threshold"]))
        elif sc == "time_elapsed" and policy.get("time_limit_seconds") is not None:
            checks.append(
                py_trees.decorators.Inverter(
                    child=TimeElapsed(policy["time_limit_seconds"]),
                    name="!TimeUp",
                )
            )
    if not checks:
        return child

    outer = py_trees.composites.Selector(name=f"Until({child.name})", memory=False)
    inner = py_trees.composites.Sequence(name=f"While({child.name})", memory=False)
    for c in checks:
        inner.add_child(c)
    inner.add_child(child)
    outer.add_children([inner, py_trees.behaviours.Success(name="StopConditionMet")])
    return outer


def _is_reactive(policy):
    """
    Reactive = battery-triggered, no navigation/search intent.
    Routes to Root Selector as preemption guard, not Mission stage.
    """
    stop     = set(policy.get("stop_conditions", []))
    has_batt = "battery_threshold" in stop and policy.get("battery_threshold") is not None
    has_nav  = policy.get("direction_bias") not in (None, "none") or bool(policy.get("location_name"))
    has_exp  = bool(policy.get("search_strategy"))
    return has_batt and not has_nav and not has_exp


def _build_reactive_guard(policy):
    batt = policy.get("battery_threshold")
    if batt is None:
        return None
    seq = py_trees.composites.Sequence(name=f"ReactiveGuard(<{batt:.0f}%)", memory=True)
    seq.add_child(
        py_trees.decorators.Inverter(
            name=f"Batt<{batt:.0f}%",
            child=BatteryAbove(batt),
        )
    )
    obj = policy.get("object_name")
    act = policy.get("object_interaction")
    if obj and act in ("greet", "grab", "inspect", "observe", "mark_location"):
        seq.add_child(InteractWithObject(obj, act))
    if policy.get("return_home_on_stop"):
        seq.add_child(ReturnHome())
    if policy.get("charge_to") is not None:
        seq.add_child(ChargingNode(policy["charge_to"]))
    # After all actions complete, force FAILURE so the Root Selector
    # falls through to Mission — allowing it to resume from last stage.
    # Without this, a successful ReactiveGuard would terminate the mission.
    seq.add_child(py_trees.behaviours.Failure(name="ResumeMission"))
    return seq


def build_tree_from_policy(policy):
    stop     = set(policy.get("stop_conditions", []))
    obj_name = policy.get("object_name")
    interact = policy.get("object_interaction")
    strategy = policy.get("search_strategy")
    mode     = policy.get("exploration_mode", "normal")

    label = (policy.get("notes") or "policy")[:40]
    stage = py_trees.composites.Sequence(name=f"Stage[{label}]", memory=True)

    # 1. Navigation
    direction = policy.get("direction_bias")
    if direction and direction not in ("none", None):
        stage.add_child(GoToRegion(direction, policy.get("max_distance")))
    location = policy.get("location_name")
    if location:
        stage.add_child(GoToRegion(location, policy.get("max_distance")))

    # 2. Pure exploration
    if "no_unknown_cells" in stop and not obj_name:
        stage.add_child(FrontierExplore(strategy or "frontier_only", mode))
        stop.discard("no_unknown_cells")

    # 3. Search phase — SearchForObject self-terminates, no guard needed
    needs_search = (
        obj_name and
        interact not in ("avoid", "observe", "mark_location") and
        ("object_found" in stop or location is None)
    )
    if needs_search:
        stage.add_child(SearchForObject(obj_name, strategy))
        stop.discard("object_found")   # consumed here, not propagated

    # 4. Interaction phase — apply remaining stop guards (battery, time)
    guard_cond = stop - {"no_unknown_cells", "object_found"}

    if interact == "avoid":
        pass
    elif interact in ("observe", "mark_location"):
        node = InteractWithObject(obj_name or "target", interact)
        stage.add_child(make_stop_guard(node, guard_cond, policy))
    elif interact == "follow":
        node = FollowObject(obj_name or "target", mode)
        stage.add_child(make_stop_guard(node, guard_cond, policy))
    elif interact in ("grab", "greet", "inspect"):
        stage.add_child(InteractWithObject(obj_name or "target", interact))

    # 5. Return home + optional charging
    if policy.get("return_home_on_stop"):
        stage.add_child(ReturnHome())
    if policy.get("charge_to") is not None:
        stage.add_child(ChargingNode(policy["charge_to"]))

    return stage


EMERGENCY_BATTERY = 10.0

def build_root(policies):
    """
    Root(Selector, memory=False)
      ReactiveGuard(<N%)    <- highest priority, preempts mission
      EmergencyGuard        <- hard floor
      Mission(Sequence)     <- sequential policies
    """
    root = py_trees.composites.Selector(name="Root", memory=False)

    sequential = []
    for policy in policies:
        if _is_reactive(policy):
            guard = _build_reactive_guard(policy)
            if guard:
                root.add_child(guard)
                print(f"  [BT] Reactive: {guard.name}")
        else:
            sequential.append(policy)

    emergency = py_trees.composites.Sequence(name="EmergencyGuard", memory=True)
    emergency.add_children([
        py_trees.decorators.Inverter(name="BattCritical", child=BatteryAbove(EMERGENCY_BATTERY)),
        ReturnHome(),
    ])
    root.add_child(emergency)

    # Mission — each stage wrapped with persistent completion tracking.
    # Selector(memory=False) per stage:
    #   StageAlreadyDone  → skip in 1 tick if completed before
    #   Sequence → stage content + MarkStageDone on completion
    global mission_progress
    mission_progress = MissionProgress(len(sequential))

    mission = py_trees.composites.Sequence(name="Mission", memory=True)
    for idx, policy in enumerate(sequential):
        stage_content = build_tree_from_policy(policy)

        run_seq = py_trees.composites.Sequence(
            name=f"Run[{idx}]", memory=True)
        run_seq.add_children([stage_content, MarkStageDone(idx)])

        wrapper = py_trees.composites.Selector(
            name=f"Stage{idx}", memory=False)
        wrapper.add_children([StageAlreadyDone(idx), run_seq])

        mission.add_child(wrapper)
    root.add_child(mission)

    return root


class BTExecutor:
    def __init__(self, root, hz: float = 10.0, timeout_seconds: float = 120.0):
        self.tree            = py_trees.trees.BehaviourTree(root)
        self.hz              = hz
        self.period          = 1.0 / hz
        self.timeout_seconds = timeout_seconds

    def run(self, sim_hook=None) -> Optional[bool]:
        self.tree.setup(timeout=5)
        t_start = time.perf_counter()
        tick    = 0

        while True:
            elapsed = time.perf_counter() - t_start
            if elapsed >= self.timeout_seconds:
                print(f"\n  WARN Timeout ({self.timeout_seconds:.0f}s) reached "
                      f"after {tick} ticks")
                return None

            tick += 1
            batt = blackboard.battery_percent()
            print(f"\n  -- Tick {tick:03d}  t={elapsed:.1f}s  "
                  f"battery={batt:.0f}%  frontiers={len(blackboard.get_frontiers())} --")

            if sim_hook:
                sim_hook(tick, elapsed)

            self.tree.tick()
            # Time-proportional drain: dt = actual period
            blackboard.sim_tick(dt=self.period)
            time.sleep(self.period)     # keep real-time pacing

            status = self.tree.root.status
            if status == py_trees.common.Status.SUCCESS:
                print(f"\n  OK Mission complete  t={time.perf_counter()-t_start:.1f}s")
                return True
            if status == py_trees.common.Status.FAILURE:
                print(f"\n  FAIL Mission failed  t={time.perf_counter()-t_start:.1f}s")
                return False

