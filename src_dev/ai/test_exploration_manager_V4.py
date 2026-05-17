import time
import json
import re
from llama_cpp import Llama

# ---------------------------------------------------------------
# Config
# ---------------------------------------------------------------
MODEL_PATH = "H:/SLARC_resources/models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"

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
    policy = json.loads(match.group(0))

    u = response["usage"]
    print("\n=== Benchmark Results ===")
    print(f"Latency:    {latency:.3f} s")
    print(f"Tokens in:  {u['prompt_tokens']}")
    print(f"Tokens out: {u['completion_tokens']}")
    print(f"Throughput: {u['total_tokens'] / latency:.1f} t/s")

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

    # Semantic consistency
    if "object_found" in stop and not policy.get("object_name"):
        warnings.append("stop_condition 'object_found' but object_name is missing")
    if "battery_threshold" in stop and policy.get("battery_threshold") is None:
        warnings.append("stop_condition 'battery_threshold' but battery_threshold is missing")
    if "time_elapsed" in stop and policy.get("time_limit_seconds") is None:
        warnings.append("stop_condition 'time_elapsed' but time_limit_seconds is missing")
    if policy.get("object_interaction") in ("follow", "grab", "greet", "inspect"):
        if not policy.get("object_name"):
            warnings.append(f"object_interaction '{policy['object_interaction']}' but object_name is missing")

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
        "After following the cat for 10 minutes, return home."
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
