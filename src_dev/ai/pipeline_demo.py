"""
pipeline_demo.py — SLARC End-to-End Pipeline Demo
==================================================
Intention → ExplorationManager → Policies → BehaviorTree → Simulated Execution

Runs entirely without hardware. The MockBlackboard is advanced by a
scripted simulation hook that mirrors the original test scenario:

  Phase 1: Move south-east, explore until all cells mapped
  Phase 2: Move west, search for cat, follow cat
  Phase 3: Battery drops below 50% → greet cat → return home
  Phase 4: Navigate to cat_location, spiral search, follow cat
  Phase 5: Follow cat for 10 minutes → return home

Dependencies:
  pip install py_trees
  exploration_manager_V4.py and bt_executor.py in same directory.
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from exploration_manager_V4 import (
    llm, PROMPT_TEMPLATE,
    split_into_sentences, resolve_pronouns,
    run_with_benchmark, normalize_policy, validate_policy,
)
import bt_executor as bt
from bt_executor import (
    MockBlackboard, set_blackboard,
    build_root, BTExecutor,
)

# ================================================================
# Step 1 — Run EM to produce policies
# ================================================================

def run_exploration_manager(intention: str) -> list[dict]:
    print("=" * 70)
    print("STEP 1 — Exploration Manager: Intention → Policies")
    print("=" * 70)
    print(f"Intention: {intention[:120]}\n")

    policies    = []
    prev_policy = None

    for sentence in split_into_sentences(intention):
        sentence = resolve_pronouns(sentence, prev_policy)
        print(f"  → {sentence[:80]}{'...' if len(sentence)>80 else ''}")
        policy   = run_with_benchmark(sentence)
        policy   = normalize_policy(policy)
        warnings = validate_policy(policy)

        if warnings:
            for w in warnings:
                print(f"    ⚠ {w}")

        policies.append(policy)
        prev_policy = policy

    print(f"\n  {len(policies)} policies generated.\n")
    return policies


# ================================================================
# Step 2 — Build BT from policies
# ================================================================

def build_behavior_tree(policies: list[dict]) -> bt.py_trees.behaviour.Behaviour:
    print("=" * 70)
    print("STEP 2 — BT Builder: Policies → Behavior Tree")
    print("=" * 70)

    root = build_root(policies)

    print(bt.py_trees.display.ascii_tree(root))
    return root


# ================================================================
# Step 3 — Simulated execution
# Scripted MockBlackboard transitions mirror the test scenario.
# ================================================================

def make_sim_hook(bb):
    """
    Time-based simulation hook — receives (tick, elapsed_seconds).
    Battery drain is handled automatically by sim_tick(dt=period).
    At 10 Hz with drain_per_sec=5%: 90% -> 50% in ~8 real seconds.
    """
    def hook(tick, elapsed):
        # Phase 1: clear frontiers over first 2 real seconds
        if elapsed < 2.0:
            bb.set_frontiers(max(0, int(50 * (1.0 - elapsed / 2.0))))
            if tick == 2:
                print("  [SIM] clearing frontiers...")

        # Phase 2: cat appears after robot reaches west (~3s)
        if tick == 30 and not bb.is_visible("cat"):
            print("  [SIM] cat spotted in west!")
            bb.set_object("cat", -8.0, 2.0, confidence=0.92)

        # After charging, cat reappears at cat_location (~tick 120 = ~12s)
        if tick == 120 and not bb.is_visible("cat"):
            print("  [SIM] cat reappears at cat_location")
            bb.set_object("cat", -6.0, 3.0, confidence=0.85)

    return hook

def run_simulation(root, bb: MockBlackboard):
    print("=" * 70)
    print("STEP 3 — Simulated Execution")
    print("=" * 70)
    print("  Battery drain: 0.5%/tick  |  Tick rate: 10 Hz (simulated)\n")

    set_blackboard(bb)
    executor = BTExecutor(root, hz=10.0, timeout_seconds=45.0)
    executor.run(sim_hook=make_sim_hook(bb))


# ================================================================
# Main
# ================================================================

if __name__ == "__main__":

    # Original test intention (split into 5 sentences by EM)
    # Demo uses short real-time durations so TimeElapsed fires in seconds.
    # At 10 Hz with time.sleep(0.1), 1 real second = 10 ticks.
    INTENTION = (
        "There are unknown regions in the south, which are far away, and in the near south-east "
        "-> Move to south-east with a maximum distance of 10m, then stay in the region. "
        "There're no more unknown cells in the south-east, but in the west "
        "-> Move there, search for the cat, then follow the cat until battery drops below 70%. "
        "When your battery is below 30%, greet the cat and return home. "
        "The cat_location is the cat's last known position -> navigate there, "
        "perform a spiral search to find the cat, follow the cat for 3 seconds, "
        "then return home."
    )

    # -- EM --
    policies = run_exploration_manager(INTENTION)

    print("Policies:")
    for i, p in enumerate(policies):
        print(f"  [{i+1}] {json.dumps(p)}")
    print()

    # -- BT --
    bb   = MockBlackboard()
    bb.set_frontiers(50)
    bb.set_battery(100.0)
    set_blackboard(bb)

    root = build_behavior_tree(policies)

    # -- Simulation --
    run_simulation(root, bb)
