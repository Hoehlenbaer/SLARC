"""
Exploration Manager V4 — Test Suite
Imports core logic from exploration_manager_V4.py.
Each test case is a single-sentence intention with expected fields
that MUST be present in the parsed policy, used for automated
pass/fail evaluation alongside the semantic validator.
"""

import json
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------
# Import V4 engine (model loads once here)
# ---------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from exploration_manager_V4 import (
    run_with_benchmark,
    validate_policy,
    resolve_pronouns,
    split_into_sentences,
)

# ---------------------------------------------------------------
# Test case definition
# expected: dict of fields that must appear with exactly these values.
#           Use ... (Ellipsis) to assert a field exists with any value.
# ---------------------------------------------------------------
TEST_CASES = [

    # --- Pure exploration ---
    {
        "id":       "EXP-01",
        "group":    "Exploration",
        "intention":"Explore the area to the north until all unknown cells are mapped.",
        "expected": {"direction_bias": "north", "stop_conditions": ["no_unknown_cells"]},
    },
    {
        "id":       "EXP-02",
        "group":    "Exploration",
        "intention":"Aggressively sweep the eastern region, no distance limit.",
        "expected": {"direction_bias": "east", "exploration_mode": "aggressive"},
    },
    {
        "id":       "EXP-03",
        "group":    "Exploration",
        "intention":"Do a wall-following sweep in the north-west, stay within 15 meters.",
        "expected": {"direction_bias": "north-west", "search_strategy": "wall_following",
                     "max_distance": 15},
    },
    {
        "id":       "EXP-04",
        "group":    "Exploration",
        "intention":"Perform a spiral search of the south-west quadrant.",
        "expected": {"direction_bias": "south-west", "search_strategy": "spiral"},
    },
    {
        "id":       "EXP-05",
        "group":    "Exploration",
        "intention":"Carefully explore the nearby area, staying within 5 meters of home.",
        "expected": {"exploration_mode": "careful", "max_distance": 5},
    },

    # --- Object search & interaction ---
    {
        "id":       "OBJ-01",
        "group":    "Object",
        "intention":"Search to the west for a fire extinguisher and mark its location.",
        "expected": {"object_name": "fire extinguisher", "object_interaction": "mark_location",
                     "direction_bias": "west"},
    },
    {
        "id":       "OBJ-02",
        "group":    "Object",
        "intention":"Head south to find the charging dock and grab the charging dock.",
        "expected": {"object_name": "charging dock", "object_interaction": "grab",
                     "direction_bias": "south"},
    },
    {
        "id":       "OBJ-03",
        "group":    "Object",
        "intention":"Locate the dog and follow it carefully.",
        "expected": {"object_name": "dog", "object_interaction": "follow",
                     "exploration_mode": "careful"},
    },
    {
        "id":       "OBJ-04",
        "group":    "Object",
        "intention":"Find the package in the north-east and inspect it.",
        "expected": {"object_name": "package", "object_interaction": "inspect",
                     "direction_bias": "north-east"},
    },
    {
        "id":       "OBJ-05",
        "group":    "Object",
        "intention":"Avoid the dog at all costs.",
        "expected": {"object_name": "dog", "object_interaction": "avoid"},
    },
    {
        "id":       "OBJ-06",
        "group":    "Object",
        "intention":"Locate the person and observe them from a safe distance.",
        "expected": {"object_name": "person", "object_interaction": "observe"},
    },
    {
        "id":       "OBJ-07",
        "group":    "Object",
        "intention":"Greet the person at last_known_position.",
        "expected": {"location_name": "last_known_position", "object_interaction": "greet"},
    },

    # --- Stop conditions ---
    {
        "id":       "STOP-01",
        "group":    "Stop conditions",
        "intention":"Explore until the battery drops below 20%, then stop.",
        "expected": {"stop_conditions": ["battery_threshold"], "battery_threshold": 20},
    },
    {
        "id":       "STOP-02",
        "group":    "Stop conditions",
        "intention":"Search for 5 minutes, then stop and return home.",
        "expected": {"stop_conditions": ["time_elapsed"], "time_limit_seconds": 300,
                     "return_home_on_stop": True},
    },
    {
        "id":       "STOP-03",
        "group":    "Stop conditions",
        "intention":"Explore until you find the cat, then stop.",
        "expected": {"stop_conditions": ["object_found"], "object_name": "cat"},
    },
    {
        "id":       "STOP-04",
        "group":    "Stop conditions",
        "intention":"Map the area completely and return home when done.",
        "expected": {"stop_conditions": ["no_unknown_cells"], "return_home_on_stop": True},
    },
    {
        "id":       "STOP-05",
        "group":    "Stop conditions",
        "intention":"Locate the ball within 2 minutes or until found, then return home.",
        "expected": {"object_name": "ball", "return_home_on_stop": True},
    },

    # --- Named locations ---
    {
        "id":       "LOC-01",
        "group":    "Named locations",
        "intention":"Navigate to the location called charging_station and wait there.",
        "expected": {"location_name": "charging_station"},
    },
    {
        "id":       "LOC-02",
        "group":    "Named locations",
        "intention":"The last seen position of the robot is called robot:last_pos -> navigate there and perform a flood fill search.",
        "expected": {"location_name": "robot:last_pos", "search_strategy": "flood_fill"},
    },
    {
        "id":       "LOC-03",
        "group":    "Named locations",
        "intention":"Move to the area labeled danger_zone and avoid it.",
        "expected": {"location_name": ..., "avoid_regions": ...},
    },

    # --- Avoid regions ---
    {
        "id":       "AVD-01",
        "group":    "Avoid regions",
        "intention":"Explore freely but avoid the narrow_passage and the dark_corridor.",
        "expected": {"avoid_regions": ...},   # any non-empty list
    },

    # --- Return home ---
    {
        "id":       "RET-01",
        "group":    "Return home",
        "intention":"Return home immediately.",
        "expected": {"return_home_on_stop": True},
    },
    {
        "id":       "RET-02",
        "group":    "Return home",
        "intention":"Explore for 30 minutes and return home afterwards.",
        "expected": {"time_limit_seconds": 1800, "return_home_on_stop": True},
    },


    # --- Exploration (continued) ---
    {
        "id":       "EXP-06",
        "group":    "Exploration",
        "intention":"Perform a flood fill search of the entire reachable area.",
        "expected": {"search_strategy": "flood_fill"},
    },
    {
        "id":       "EXP-07",
        "group":    "Exploration",
        "intention":"Sweep southward for 3 minutes then stop.",
        "expected": {"direction_bias": "south", "time_limit_seconds": 180},
        "note": "stop_conditions derived implicitly by normalize_policy",
    },
    {
        "id":       "EXP-08",
        "group":    "Exploration",
        "intention":"Aggressively explore far to the north, up to 20 meters, and return home when done.",
        "expected": {"direction_bias": "north", "exploration_mode": "aggressive",
                     "max_distance": 20, "return_home_on_stop": True},
    },
    {
        "id":       "EXP-09",
        "group":    "Exploration",
        "intention":"Carefully explore nearby using frontier search, avoid the staircase region.",
        "expected": {"exploration_mode": "careful", "search_strategy": "frontier_only",
                     "avoid_regions": ...},
    },
    {
        "id":       "EXP-10",
        "group":    "Exploration",
        "intention":"Map westward using a directional sweep and stop when the battery hits 25%.",
        "expected": {"direction_bias": "west", "search_strategy": "directional_sweep",
                     "stop_conditions": ["battery_threshold"], "battery_threshold": 25},
    },

    # --- Object (continued) ---
    {
        "id":       "OBJ-08",
        "group":    "Object",
        "intention":"Head north-east to find the toolbox and mark its location.",
        "expected": {"direction_bias": "north-east", "object_name": "toolbox",
                     "object_interaction": "mark_location"},
    },
    {
        "id":       "OBJ-09",
        "group":    "Object",
        "intention":"Locate the suspicious package and carefully inspect it.",
        "expected": {"object_name": "suspicious package", "object_interaction": "inspect",
                     "exploration_mode": "careful"},
    },
    {
        "id":       "OBJ-10",
        "group":    "Object",
        "intention":"Follow the child for 5 minutes then return home.",
        "expected": {"object_name": "child", "object_interaction": "follow",
                     "time_limit_seconds": 300, "return_home_on_stop": True},
    },
    {
        "id":       "OBJ-11",
        "group":    "Object",
        "intention":"Head west to find the water bottle within 10 meters and grab the water bottle.",
        "expected": {"direction_bias": "west", "object_name": "water bottle",
                     "object_interaction": "grab", "max_distance": 10},
    },
    {
        "id":       "OBJ-12",
        "group":    "Object",
        "intention":"Avoid the broken glass on the floor.",
        "expected": {"object_name": "broken glass", "object_interaction": "avoid"},
    },

    # --- Stop conditions (continued) ---
    {
        "id":       "STOP-06",
        "group":    "Stop conditions",
        "intention":"Explore northward until all cells are mapped or the battery drops below 15%.",
        "expected": {"direction_bias": "north",
                     "stop_conditions": ["no_unknown_cells", "battery_threshold"],
                     "battery_threshold": 15},
    },
    {
        "id":       "STOP-07",
        "group":    "Stop conditions",
        "intention":"Explore until the battery drops below 30% and return home immediately.",
        "expected": {"stop_conditions": ["battery_threshold"], "battery_threshold": 30,
                     "return_home_on_stop": True},
    },
    {
        "id":       "STOP-08",
        "group":    "Stop conditions",
        "intention":"Sweep eastward for exactly 10 minutes without returning home.",
        "expected": {"direction_bias": "east", "time_limit_seconds": 600,
                     "return_home_on_stop": False},
        "note": "stop_conditions derived implicitly by normalize_policy",
    },

    # --- Named locations (continued) ---
    {
        "id":       "LOC-04",
        "group":    "Named locations",
        "intention":"Navigate northward to the area called north_garden until all unknown cells are mapped.",
        "expected": {"direction_bias": "north", "location_name": "north_garden",
                     "stop_conditions": ["no_unknown_cells"]},
    },
    {
        "id":       "LOC-05",
        "group":    "Named locations",
        "intention":"Move to storage_room and perform a spiral search inside.",
        "expected": {"location_name": "storage_room", "search_strategy": "spiral"},
    },
    {
        "id":       "LOC-06",
        "group":    "Named locations",
        "intention":"Inspect the object at anomaly_pos.",
        "expected": {"location_name": "anomaly_pos", "object_interaction": "inspect"},
    },

    # --- Avoid regions (continued) ---
    {
        "id":       "AVD-02",
        "group":    "Avoid regions",
        "intention":"Head east but avoid the construction_zone.",
        "expected": {"direction_bias": "east", "avoid_regions": ...},
    },
    {
        "id":       "AVD-03",
        "group":    "Avoid regions",
        "intention":"Carefully sweep southward, avoiding the wet_floor and the loading_dock.",
        "expected": {"direction_bias": "south", "exploration_mode": "careful",
                     "avoid_regions": ...},
    },

    # --- Return home (continued) ---
    {
        "id":       "RET-03",
        "group":    "Return home",
        "intention":"Find the docking unit and grab the docking unit, then return home.",
        "expected": {"object_name": "docking unit", "object_interaction": "grab",
                     "return_home_on_stop": True},
    },
    {
        "id":       "RET-04",
        "group":    "Return home",
        "intention":"Explore until the battery is below 10% and return home.",
        "expected": {"stop_conditions": ["battery_threshold"], "battery_threshold": 10,
                     "return_home_on_stop": True},
    },

    # --- Complex (continued) ---
    {
        "id":       "CMX-04",
        "group":    "Complex",
        "intention":"Head north-west, carefully follow the wall, avoid the server_room, stop after 15 minutes.",
        "expected": {"direction_bias": "north-west", "exploration_mode": "careful",
                     "search_strategy": "wall_following", "avoid_regions": ...,
                     "stop_conditions": ["time_elapsed"], "time_limit_seconds": 900},
    },
    {
        "id":       "CMX-05",
        "group":    "Complex",
        "intention":"Aggressively sweep east up to 20 meters until all unknown cells are mapped or the battery drops below 20%, then return home.",
        "expected": {"direction_bias": "east", "exploration_mode": "aggressive",
                     "max_distance": 20, "battery_threshold": 20,
                     "return_home_on_stop": True},
    },
    {
        "id":       "CMX-06",
        "group":    "Complex",
        "intention":"Navigate to depot:location, grab the spare_part there, and return home within 8 minutes.",
        "expected": {"location_name": "depot:location", "object_name": "spare_part",
                     "object_interaction": "grab", "return_home_on_stop": True,
                     "time_limit_seconds": 480},
    },
    {
        "id":       "CMX-07",
        "group":    "Complex",
        "intention":"Perform a careful spiral search southward within 5 meters, stopping when all unknown cells are found.",
        "expected": {"direction_bias": "south", "exploration_mode": "careful",
                     "search_strategy": "spiral", "max_distance": 5,
                     "stop_conditions": ["no_unknown_cells"]},
    },

    # --- Combined / complex ---
    {
        "id":       "CMX-01",
        "group":    "Complex",
        "intention":"Carefully search the south for a person, follow them, and return home when the battery drops below 30%.",
        "expected": {"direction_bias": "south", "object_name": "person",
                     "object_interaction": "follow", "battery_threshold": 30,
                     "return_home_on_stop": True},
    },
    {
        "id":       "CMX-02",
        "group":    "Complex",
        "intention":"Aggressively map the north-east up to 20 meters, stop when all cells are known.",
        "expected": {"direction_bias": "north-east", "exploration_mode": "aggressive",
                     "max_distance": 20, "stop_conditions": ["no_unknown_cells"]},
    },
    {
        "id":       "CMX-03",
        "group":    "Complex",
        "intention":"Find the keys near the entrance, grab them, and return home.",
        "expected": {"object_name": "keys", "object_interaction": "grab",
                     "return_home_on_stop": True},
    },
]

# ---------------------------------------------------------------
# Field assertion helper
# Handles nested list equality and Ellipsis wildcard.
# ---------------------------------------------------------------
def check_expected(policy: dict, expected: dict) -> list[str]:
    failures = []
    for field, exp_val in expected.items():
        if field not in policy:
            failures.append(f"missing field '{field}'")
            continue
        actual = policy[field]
        if exp_val is ...:
            # Just assert field exists and is truthy (non-empty)
            if not actual:
                failures.append(f"'{field}' is empty/falsy, expected a value")
        elif isinstance(exp_val, list) and isinstance(actual, list):
            if set(exp_val) != set(actual):
                failures.append(f"'{field}': expected {exp_val}, got {actual}")
        else:
            if actual != exp_val:
                failures.append(f"'{field}': expected {repr(exp_val)}, got {repr(actual)}")
    return failures

# ---------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------
def run_test_suite():
    results   = []
    t_total   = time.perf_counter()

    print("=" * 70)
    print("SLARC Exploration Manager V4 — Test Suite")
    print("=" * 70)

    # prev_policy is intentionally NOT carried across test cases —
    # pronoun resolution is for sequential mission sentences only.
    # Each test case is independent; reset before every case.

    for tc in TEST_CASES:
        tid         = tc["id"]
        group       = tc["group"]
        prev_policy = tc.get("prev_policy_override", None)
        sentence    = resolve_pronouns(tc["intention"], prev_policy)

        print(f"\n[{tid}] {group}: {sentence[:72]}{'...' if len(sentence) > 72 else ''}")

        try:
            policy   = run_with_benchmark(sentence)
            val_warn = validate_policy(policy)
            exp_fail = check_expected(policy, tc["expected"])
            passed   = len(val_warn) == 0 and len(exp_fail) == 0

            results.append({
                "id":      tid,
                "group":   group,
                "passed":  passed,
                "val":     val_warn,
                "exp":     exp_fail,
                "policy":  policy,
            })

            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {status}")
            if val_warn:
                for w in val_warn:
                    print(f"    ⚠ validator: {w}")
            if exp_fail:
                for f in exp_fail:
                    print(f"    ✗ expected:  {f}")

        except Exception as e:
            results.append({"id": tid, "group": group, "passed": False,
                             "val": [], "exp": [str(e)], "policy": {}})
            print(f"  ✗ EXCEPTION: {e}")

        # (prev_policy not propagated between independent test cases)

    # ---------------------------------------------------------------
    # Summary table
    # ---------------------------------------------------------------
    elapsed = time.perf_counter() - t_total
    passed  = [r for r in results if r["passed"]]
    failed  = [r for r in results if not r["passed"]]

    print("\n" + "=" * 70)
    print(f"RESULTS: {len(passed)}/{len(results)} passed  "
          f"({len(failed)} failed)  —  {elapsed:.1f}s total")
    print("=" * 70)

    # Group summary
    groups = {}
    for r in results:
        groups.setdefault(r["group"], []).append(r["passed"])
    print("\nBy group:")
    for grp, outcomes in groups.items():
        n   = len(outcomes)
        ok  = sum(outcomes)
        bar = "█" * ok + "░" * (n - ok)
        print(f"  {grp:<20} {bar}  {ok}/{n}")

    if failed:
        print("\nFailed cases:")
        for r in failed:
            print(f"  [{r['id']}]")
            for msg in r["val"] + r["exp"]:
                print(f"    - {msg}")
            if r["policy"]:
                print(f"    policy: {json.dumps(r['policy'])}")

    print()
    return results


# ---------------------------------------------------------------
# Natural language cases — convention violations
# These are phrased as a human would naturally speak, deliberately
# breaking the conventions discovered during test-suite development.
# No pass/fail: the runner reports what the model produces and which
# fields are missing, wrong-typed, or semantically inconsistent.
# ---------------------------------------------------------------
NATURAL_CASES = [
    {
        "id":    "NAT-01",
        "label": "Relative direction (no compass)",
        "intention": "Go a bit to the left and look around.",
        "note":  "Relative direction — model maps left→west, right→east assuming north heading. Undocumented feature.",
    },
    {
        "id":    "NAT-02",
        "label": "Informal object check",
        "intention": "Go check on the cat.",
        "note":  "'Check on' is not a valid object_interaction; expect 'inspect' or 'observe' or hallucination.",
    },
    {
        "id":    "NAT-03",
        "label": "Vague distance",
        "intention": "Explore around here for a bit, maybe 10 meters or so.",
        "note":  "'Or so' and 'a bit' add uncertainty — max_distance may be missing or approximate.",
    },
    {
        "id":    "NAT-04",
        "label": "Implicit pronoun without context",
        "intention": "Follow it carefully.",
        "note":  "Pure pronoun, no prev_policy — object_name will be missing.",
    },
    {
        "id":    "NAT-05",
        "label": "Vague object class",
        "intention": "Find something interesting to the east.",
        "note":  "'Something interesting' is not a concrete object_name — expect hallucinated or null.",
    },
    {
        "id":    "NAT-06",
        "label": "Negation instead of avoid",
        "intention": "Don't go near the couch.",
        "note":  "Negation pattern — model should use object_interaction=avoid or avoid_regions, but may not.",
    },
    {
        "id":    "NAT-07",
        "label": "Informal temporal ('for a while')",
        "intention": "Explore for a while and then come back.",
        "note":  "'A while' has no numeric value — time_limit_seconds likely null or hallucinated.",
    },
    {
        "id":    "NAT-08",
        "label": "Directional idiom ('over there')",
        "intention": "Go check what's over there behind the door.",
        "note":  "'Over there' and 'behind the door' are relative, not compass/named — direction_bias and location_name will be guessed.",
    },
    {
        "id":    "NAT-09",
        "label": "First-person ownership",
        "intention": "I want you to find my keys and bring them back.",
        "note":  "'My keys' and 'bring them back' — expect object_name=keys but object_interaction may not include 'grab' + return.",
    },
    {
        "id":    "NAT-10",
        "label": "Compound multi-policy as single sentence",
        "intention": "Search north until you find the cat, follow the cat, and when the battery is low return home.",
        "note":  "Three policies collapsed into one sentence — EM gets one policy, BT would need three.",
    },
]

# ---------------------------------------------------------------
# Natural language runner — descriptive, no pass/fail
# ---------------------------------------------------------------
def run_natural_suite():
    print()
    print("=" * 70)
    print("SLARC EM V4 — Natural Language Stress Test (Convention Violations)")
    print("=" * 70)
    print("  These cases test robustness against informal human phrasing.")
    print("  Output is descriptive only — no PASS/FAIL threshold.")
    print()

    nat_results = []

    for tc in NATURAL_CASES:
        tid   = tc["id"]
        label = tc["label"]
        intention = tc["intention"]

        print(f"[{tid}] {label}")
        print(f"  Intention : {intention}")
        print(f"  Expected issue: {tc['note']}")

        try:
            policy   = run_with_benchmark(intention)
            val_warn = validate_policy(policy)

            issues = []

            # Only flag absence of fields that are semantically implied
            # by the intention — not all optional fields that happen to be missing.
            # (Absence of irrelevant fields is correct EM behavior.)
            intention_lower = intention.lower()
            if any(w in intention_lower for w in ("follow", "grab", "greet", "inspect")):
                if not policy.get("object_name"):
                    issues.append("object_name missing for interaction verb")
            if any(w in intention_lower for w in ("minute", "second", "hour")):
                if policy.get("time_limit_seconds") is None:
                    issues.append("time_limit_seconds missing despite temporal phrasing")
            if any(w in intention_lower for w in ("battery", "%", "percent")):
                if policy.get("battery_threshold") is None:
                    issues.append("battery_threshold missing despite battery phrasing")
            if any(w in intention_lower for w in ("north","south","east","west","left","right")):
                if "direction_bias" not in policy:
                    issues.append("direction_bias missing despite directional phrasing")

            # Check for hallucinated enum values
            from exploration_manager_V4 import (
                VALID_DIRECTION_BIAS, VALID_INTERACTIONS,
                VALID_STRATEGIES, VALID_MODES, VALID_STOP_CONDITIONS,
                normalize_policy,
            )
            policy = normalize_policy(policy)   # apply same normalization as main pipeline
            if "direction_bias" in policy:
                db = policy["direction_bias"]
                if db not in VALID_DIRECTION_BIAS:
                    issues.append(f"hallucinated direction_bias: {repr(db)}")

            if "object_interaction" in policy:
                oi = policy["object_interaction"]
                if oi not in VALID_INTERACTIONS:
                    issues.append(f"hallucinated object_interaction: {repr(oi)}")

            # Numeric type checks
            for field in ("max_distance", "time_limit_seconds", "battery_threshold"):
                val = policy.get(field)
                if val is not None and not isinstance(val, (int, float)):
                    issues.append(f"wrong type for {field}: {repr(val)}")

            nat_results.append({
                "id":      tid,
                "label":   label,
                "policy":  policy,
                "val":     val_warn,
                "issues":  issues,
            })

            print(f"  Policy    : {json.dumps(policy)}")
            if val_warn:
                for w in val_warn:
                    print(f"  ⚠ validator : {w}")
            if issues:
                for i in issues:
                    print(f"  ✗ issue     : {i}")
            if not val_warn and not issues:
                print(f"  ✓ No issues detected (model handled it gracefully)")

        except Exception as e:
            nat_results.append({"id": tid, "label": label,
                                  "policy": {}, "val": [], "issues": [str(e)]})
            print(f"  ✗ EXCEPTION: {e}")

        print()

    # ---------------------------------------------------------------
    # Natural suite summary
    # ---------------------------------------------------------------
    print("=" * 70)
    print("Natural Language Suite — Issue Summary")
    print("=" * 70)
    any_issues = False
    for r in nat_results:
        all_issues = r["val"] + r["issues"]
        tag = "⚠" if all_issues else "✓"
        print(f"  {tag} [{r['id']}] {r['label']}")
        for msg in all_issues:
            print(f"      → {msg}")
        if all_issues:
            any_issues = True
    if not any_issues:
        print("  All natural cases handled without detected issues.")
    print()
    return nat_results

# ---------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------
if __name__ == "__main__":
    run_test_suite()
    run_natural_suite()
