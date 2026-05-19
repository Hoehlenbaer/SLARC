import time
import json
import re
import os
from llama_cpp import Llama

# ---------------------------------------------------------------
# Config
# ---------------------------------------------------------------
#MODEL_PATH = "H:/SLARC_resources/models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
#MODEL_PATH = "/home/admin/.models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"


def find_model_path(model_name):
    """
    Searches for a model file in a predefined list of directories.

    Args:
        model_name (str): The name of the model file to find.

    Returns:
        str: The full path to the model file if found, otherwise None.
    """
    # 1. Check in the same folder as the script
    # os.path.abspath(__file__) gives the absolute path of the script
    # os.path.dirname gets the directory of the script
    script_directory = os.path.dirname(os.path.abspath(__file__))
    
    # Potential paths for the model file
    # The list is ordered by search priority.
    search_paths = [
        # Priority 1: Same folder as the script
        script_directory,
        # Priority 2: Specified Windows path
        "H:/SLARC_resources/models/",
        # Priority 3: Specified Linux path
        "/home/admin/.models/"
    ]

    print(f"Searching for model: {model_name}")
    print("-" * 30)

    for path in search_paths:
        # os.path.join creates a valid path for the current OS
        potential_path = os.path.join(path, model_name)
        print(f"Checking: {potential_path}")
        
        # os.path.exists checks if a file or directory exists
        if os.path.exists(potential_path):
            print("\nModel found!")
            return potential_path

    print("\nModel not found in any of the specified locations.")
    return None

MODEL_FILENAME = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
MODEL_PATH = find_model_path(MODEL_FILENAME)

llm = Llama(
    model_path   = MODEL_PATH,
    n_ctx        = 4096,
    n_gpu_layers = -1,
    use_mlock    = True,
    use_mmap     = True,
    verbose      = False,
)

# ---------------------------------------------------------------
# Prompt template — V4
# Sweet spot between V1 (605 tokens, full engine description) and
# V3 (237 tokens, too terse: model omits explicitly stated fields,
# outputs max_distance as string "near" instead of number).
# Full field list with types gives the model enough context; omitting
# the engine description saves ~350 tokens vs V1.
# KV-Cache hits from Call 2 onward on the invariant prefix.
# ---------------------------------------------------------------
PROMPT_TEMPLATE = (
    "You are a robot exploration policy planner.\n"
    "Translate the intention into a JSON policy. Output ONLY the JSON.\n"
    "Include only fields relevant to the intention.\n"
    "\n"
    "Fields and valid values:\n"
    '- stop_conditions   : list of "no_unknown_cells"|"object_found"|"time_elapsed"|"battery_threshold"\n'
    '- direction_bias    : "north"|"south"|"east"|"west"|"north-east"|"north-west"|"south-east"|"south-west"|"location"|"none"\n'
    '- object_name       : string — name of object to find or interact with\n'
    '- location_name     : string — named location reference (e.g. "cat:location")\n'
    '- object_interaction: "grab"|"greet"|"inspect"|"mark_location"|"avoid"|"follow"|"observe"\n'
    '- avoid_regions     : list of region name strings\n'
    '- search_strategy   : "flood_fill"|"directional_sweep"|"spiral"|"wall_following"|"frontier_only"\n'
    '- exploration_mode  : "normal"|"careful"|"aggressive"\n'
    "- max_distance      : number in meters or null  (near=5, far=20, null=unlimited)\n"
    "- time_limit_seconds: number in seconds or null\n"
    "- battery_threshold : battery percent as number 0-100 or null\n"
    "- return_home_on_stop: true or false\n"
    "- charge_to         : battery % to reach before resuming mission, or null\n"
    "- notes             : one concise sentence\n"
    "\n"
    'Intention: "{{INTENTION}}"'
)

# ---------------------------------------------------------------
# Sentence splitter
# ---------------------------------------------------------------
def split_into_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]

# ---------------------------------------------------------------
# Pronoun resolution
# Replaces pronouns referring to the previous policy's object_name
# before the sentence reaches the LLM. Prevents missing object_name
# in policies where the intention uses "it", "her", etc. anaphorically.
# E.g. "follow it" → "follow the cat" when prev object_name = "cat".
# ---------------------------------------------------------------
_PRONOUNS = re.compile(r'\b(it|her|him|them|they)\b', re.IGNORECASE)

def resolve_pronouns(sentence: str, prev_policy: dict | None) -> str:
    if prev_policy is None:
        return sentence
    obj = prev_policy.get("object_name")
    if obj and _PRONOUNS.search(sentence):
        resolved = _PRONOUNS.sub(f'the {obj}', sentence)
        print(f"  [pronoun resolved] → {resolved}")
        return resolved
    return sentence

# ---------------------------------------------------------------
# Inference + benchmark
# ---------------------------------------------------------------
def run_with_benchmark(intention: str) -> dict:
    prompt = PROMPT_TEMPLATE.replace("{{INTENTION}}", intention)

    print("Running benchmark...")
    t0 = time.perf_counter()

    response = llm(
        prompt,
        max_tokens       = 256,
        temperature      = 0.2,
        top_p            = 0.9,
        top_k            = 40,
        presence_penalty = 0.0,
    )

    latency = time.perf_counter() - t0
    raw     = response["choices"][0]["text"].strip()

    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in model output:\n{raw}")
    policy   = normalize_policy(json.loads(match.group(0)))
    warnings = validate_policy(policy)
    if warnings:
        for w in warnings:
            print(f"  [POLICY WARNING] {w}")

    u = response["usage"]
    print("\n=== Benchmark Results ===")
    print(f"Latency:    {latency:.3f} s")
    print(f"Tokens in:  {u['prompt_tokens']}")
    print(f"Tokens out: {u['completion_tokens']}")
    print(f"Throughput: {u['total_tokens'] / latency:.1f} t/s")

    return policy

# ---------------------------------------------------------------
# Policy normalizer
# The model consistently sets time_limit_seconds / battery_threshold
# without adding the corresponding stop_condition enum — a systematic
# omission. Rather than forcing ever-more-explicit prompt wording,
# derive implicitly at parse time. Called before validate_policy so
# the validator sees a fully consistent policy.
# ---------------------------------------------------------------
def normalize_policy(policy: dict) -> dict:
    stop    = set(policy.get("stop_conditions", []))
    changed = False
    if policy.get("time_limit_seconds") is not None and "time_elapsed" not in stop:
        stop.add("time_elapsed")
        changed = True
    if policy.get("battery_threshold") is not None and "battery_threshold" not in stop:
        stop.add("battery_threshold")
        changed = True
    if changed:
        policy["stop_conditions"] = sorted(stop)   # sorted for deterministic output

    # charge_to heuristic: when returning home because of low battery,
    # default to charging to 90% before resuming the mission.
    # Only applies when battery_threshold triggered the return — not time/object returns.
    if (policy.get("return_home_on_stop") and
            policy.get("battery_threshold") is not None and
            "charge_to" not in policy):
        policy["charge_to"] = 90

    return policy

# ---------------------------------------------------------------
# Semantic validator
# Grammar enforces syntax; this catches semantic inconsistencies
# that are impossible to express in GBNF without combinatorial
# explosion (e.g. conditional field dependencies).
# ---------------------------------------------------------------
VALID_STOP_CONDITIONS  = {"no_unknown_cells", "object_found", "time_elapsed", "battery_threshold"}
VALID_DIRECTION_BIAS   = {"north", "south", "east", "west", "north-east", "north-west",
                          "south-east", "south-west", "location", "none"}
VALID_INTERACTIONS     = {"grab", "greet", "inspect", "mark_location", "avoid", "follow", "observe"}
VALID_STRATEGIES       = {"flood_fill", "directional_sweep", "spiral", "wall_following", "frontier_only"}
VALID_MODES            = {"normal", "careful", "aggressive"}

def validate_policy(policy: dict) -> list[str]:
    warnings = []
    stop = set(policy.get("stop_conditions", []))

    # Type validation (V3 regression: max_distance output as string "near" instead of number)
    if "max_distance" in policy and policy["max_distance"] is not None:
        if not isinstance(policy["max_distance"], (int, float)):
            warnings.append(f"max_distance must be a number, got: {repr(policy['max_distance'])}")
    if "time_limit_seconds" in policy and policy["time_limit_seconds"] is not None:
        if not isinstance(policy["time_limit_seconds"], (int, float)):
            warnings.append(f"time_limit_seconds must be a number, got: {repr(policy['time_limit_seconds'])}")
    if "battery_threshold" in policy and policy["battery_threshold"] is not None:
        if not isinstance(policy["battery_threshold"], (int, float)):
            warnings.append(f"battery_threshold must be a number, got: {repr(policy['battery_threshold'])}")
    if "charge_to" in policy and policy["charge_to"] is not None:
        if not isinstance(policy["charge_to"], (int, float)):
            warnings.append(f"charge_to must be a number, got: {repr(policy['charge_to'])}")
        elif not (0 <= policy["charge_to"] <= 100):
            warnings.append(f"charge_to out of range [0,100]: {policy['charge_to']}")
        if not policy.get("return_home_on_stop"):
            warnings.append("charge_to set but return_home_on_stop is false")

    # Enum validation (catches hallucinated values without grammar)
    for sc in stop:
        if sc not in VALID_STOP_CONDITIONS:
            warnings.append(f"Unknown stop_condition: '{sc}'")
    if "direction_bias" in policy and policy["direction_bias"] not in VALID_DIRECTION_BIAS:
        warnings.append(f"Unknown direction_bias: '{policy['direction_bias']}'")
    if "object_interaction" in policy and policy["object_interaction"] not in VALID_INTERACTIONS:
        warnings.append(f"Unknown object_interaction: '{policy['object_interaction']}'")
    if "search_strategy" in policy and policy["search_strategy"] not in VALID_STRATEGIES:
        warnings.append(f"Unknown search_strategy: '{policy['search_strategy']}'")
    if "exploration_mode" in policy and policy["exploration_mode"] not in VALID_MODES:
        warnings.append(f"Unknown exploration_mode: '{policy['exploration_mode']}'")

    # Semantic consistency — field dependencies
    if "object_found" in stop and not policy.get("object_name"):
        warnings.append("stop_condition 'object_found' but object_name is missing")
    if "battery_threshold" in stop and policy.get("battery_threshold") is None:
        warnings.append("stop_condition 'battery_threshold' but battery_threshold is missing")
    if "time_elapsed" in stop and policy.get("time_limit_seconds") is None:
        warnings.append("stop_condition 'time_elapsed' but time_limit_seconds is missing")
    if policy.get("object_interaction") in ("follow", "grab", "greet", "inspect"):
        if not policy.get("object_name"):
            warnings.append(
                f"object_interaction '{policy['object_interaction']}' but object_name is missing")

    # Semantic consistency — termination reachability for continuous interactions
    #
    # follow/observe run indefinitely until a stop condition fires.
    # Valid terminators:  time_elapsed, battery_threshold
    # Invalid terminators: no_unknown_cells (exploration concept, not a follow terminator)
    # No terminator at all: robot follows forever — only safe with an external ReactiveGuard
    interact = policy.get("object_interaction")
    if interact in ("follow", "observe"):
        has_time         = ("time_elapsed"      in stop and
                            policy.get("time_limit_seconds") is not None)
        has_battery      = ("battery_threshold" in stop and
                            policy.get("battery_threshold") is not None)
        # object_found is a valid terminator for follow/observe:
        # the Stage's Search phase triggers SUCCESS before the interaction
        # phase runs long enough to cause an indefinite-execution problem.
        has_object_found = ("object_found" in stop and
                            bool(policy.get("object_name")))
        bad_stops        = stop & {"no_unknown_cells"}  # exploration-only concept

        if bad_stops and not (has_time or has_battery or has_object_found):
            warnings.append(
                f"object_interaction '{interact}' uses exploration stop_condition "
                f"{sorted(bad_stops)} — these never fire during follow/observe. "
                f"Add time_limit_seconds, battery_threshold, or object_found.")

        if not has_time and not has_battery and not has_object_found:
            warnings.append(
                f"object_interaction '{interact}' has no time, battery, or "
                f"object_found termination — robot will run indefinitely until "
                f"an external ReactiveGuard fires. "
                f"Consider adding time_limit_seconds or battery_threshold.")

    return warnings

# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------
if __name__ == "__main__":
    intention = (
        "There are unknown regions in the south, which are far away, and in the near south-east "
        "-> Move to south-east with a maximum distance of 10m, then stay in the region. "
        "There're no more unknown cells in the south-east, but in the west "
        "-> Move there and carefully search and find the cat, then follow her. "
        "When your battery is below 50%, greet the cat and return home. "
        "The cat's last location is called cat:location -> move there, perform a spiral search "
        "to find it again and continue to follow it. "
        "After following for 10 minutes, return home."
    )

    policies    = []
    prev_policy = None

    for sentence in split_into_sentences(intention):
        sentence = resolve_pronouns(sentence, prev_policy)
        print(f"\n--- Intention: {sentence[:80]}{'...' if len(sentence) > 80 else ''}")
        policy   = run_with_benchmark(sentence)
        warnings = validate_policy(policy)

        print("\nParsed policy:")
        print(json.dumps(policy, indent=2))

        if warnings:
            print("\n⚠ Validation warnings:")
            for w in warnings:
                print(f"  - {w}")

        policies.append(policy)
        prev_policy = policy

    print("\n\n=== Merged Policies ===")
    print(json.dumps(policies, indent=2))
