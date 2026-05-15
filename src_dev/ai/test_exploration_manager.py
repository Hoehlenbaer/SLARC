import time
import json
import re
from llama_cpp import Llama

#MODEL_PATH = "/home/admin/.models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
MODEL_PATH = "H:\SLARC_resources\models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf"

llm = Llama(model_path=MODEL_PATH,n_ctx=4096,n_gpu_layers=-1,use_mlock=True,use_mmap=True,verbose=False)
#llm = Llama(model_path=MODEL_PATH,n_ctx=4096,n_threads=2,n_batch=512,use_mlock=True,verbose=False)

PROMPT_TEMPLATE = r"""
You are the exploration policy planner for a hexapod robot.

Your job is NOT to choose exact coordinates.
Instead, you translate high-level exploration intentions into a structured JSON policy
that a deterministic exploration engine will execute.

The exploration engine:
- Works on a 2D grid map.
- Knows which cells are:
  - explored free space "."
  - walls/obstacles "#"
  - unknown "?"
  - special tiles like home "H" and robot "R".
- Can:
  - find frontier cells (unknown cells adjacent to explored free space),
  - compute distances,
  - cluster frontiers by size,
  - avoid regions by label or coordinate range,
  - stop when a stop condition is met.

Your task:
Given an exploration intention in natural language, output ONLY a JSON policy object.

JSON schema (keys and meaning):

{
  "stop_conditions": ["<string>"],                       //valid strings: "no_unknown_cells", "object_found", "time_elapsed", "battery_threshold"
  "direction_bias": "<north|south|east|west|north-east|north-west|south-east|south-west|location|none>",
  "object_name": "<string or null>",
  "location_name" "<string or null>",
  "object_interaction": "<grab|greet|inspect|mark_location|avoid|follow|observe>",
  "avoid_regions": ["<string>"],                        // list of region descriptors to avoid, can be empty e.g. "right_corridor", "noisy_area", "narrow_passages"
  "search_strategy": "<flood_fill|directional_sweep|spiral|wall_following|frontier_only|null>",
  "exploration_mode": "<normal|careful|aggressive>",
  "max_distance": <number or null>,                     // maximum allowed distance in meters [m] from home or current position; null if no limit; near=5m, far=20m
  "time_limit_seconds": <number or null>,               // time limit in seconds; null if no limit
  "battery_threshold": <number or null>,                // battery percentage at which to stop and return home; null if not used
  "return_home_on_stop": <boolean>,                     // whether the robot should return to home when stop_condition is met
  "notes": "<string>"                                   // short human-readable explanation of the policy
}


Rules:
- You MUST output ONLY a single JSON object matching the schema above.
- Do NOT include any extra text, comments, or explanations outside the JSON.
- If a field is not relevant, set it to null (for numbers) or [] (for lists) or a sensible default string.

Now process this exploration intention:

"{{INTENTION}}"
"""



# -----------------------------
# Benchmark wrapper
# -----------------------------
def run_with_benchmark(prompt):
    print("Running benchmark...")

    start_time = time.time()

    response = llm(
        prompt,
        max_tokens=256,
        temperature=0.7, 
        min_p = 0.00, 
        top_p = 0.80, 
        top_k = 20, 
        presence_penalty = 1.0
    )

    end_time = time.time()
    latency = end_time - start_time
    
    # Extract raw text
    raw_output = response["choices"][0]["text"].strip()

    # Extract JSON object
    match = re.search(r'\{.*\}', raw_output, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output")

    json_text = match.group(0)
    policy = json.loads(json_text)

    # Benchmark metrics
    tokens_in = response["usage"]["prompt_tokens"]
    tokens_out = response["usage"]["completion_tokens"]
    total_tokens = response["usage"]["total_tokens"]

    tokens_per_second = total_tokens / latency if latency > 0 else 0

    print("\n=== Benchmark Results ===")
    print(f"Latency: {latency:.3f} seconds")
    print(f"Tokens in: {tokens_in}")
    print(f"Tokens out: {tokens_out}")
    print(f"Total tokens: {total_tokens}")
    print(f"Throughput: {tokens_per_second:.1f} tokens/sec")

    return policy

def split_into_sentences(text):
    # Split on periods, exclamation marks, question marks
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    # Remove empty parts
    return [p.strip() for p in parts if p.strip()]



# -----------------------------
# Run the test
# -----------------------------

intention = """There are unknown regions in the south, which are far away, and in the near south-east -> Move to south-east with a mximum distance of 10m, then stay in the region.
            There're no more unknown cells in the south-east, but in the west -> Move there and carefully search and find the cat, then follow her.
            when your battery is below 50%, greet the cat and return home.
            The cat's last location is called cat:location -> move there, perform a spiral search to find it again and continue to follow it. 
            After following for 10 minutes, return home."""

policies = []

for sentence in split_into_sentences(intention):
    prompt = PROMPT_TEMPLATE.replace("{{INTENTION}}", sentence)
    policy = run_with_benchmark(prompt)    
    print("\nParsed policy object:")
    print(json.dumps(policy, indent=2))
    policies.append(policy)

print("Merged policies:")
print(policies)