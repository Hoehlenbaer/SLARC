import time
import json
import re
from llama_cpp import Llama

MODEL_PATH = "H:\SLARC_resources\models\Qwen3-4B-Instruct-2507-Q8_0.gguf"

llm = Llama(model_path=MODEL_PATH,n_ctx=4096,n_gpu_layers=-1,use_mlock=True,use_mmap=True,verbose=False)
#llm = Llama(model_path=model_path,n_ctx=1024,n_threads=2,n_batch=512,use_mlock=True,verbose=False)

prompt = r"""
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
  "stop_condition": "<string>",             // e.g. "no_unknown_cells", "object_found", "time_elapsed", "battery_threshold"
  "direction_bias": "<north|south|east|west|none>",
  "avoid_regions": ["<string>"],            // list of region descriptors to avoid, can be empty e.g. "right_corridor", "noisy_area", "narrow_passages"
  "search_strategy": "<flood_fill|directional_sweep|spiral|wall_following|frontier_only>",
  "exploration_mode": "<normal|careful|aggressive>",
  "max_distance": <number or null>,         // maximum allowed distance from home or current position; null if no limit; near=5, far=10
  "time_limit_seconds": <number or null>,   // time limit in seconds; null if no limit
  "battery_threshold": <number or null>,    // battery percentage at which to stop and return home; null if not used
  "return_home_on_stop": <boolean>,         // whether the robot should return to home when stop_condition is met
  "notes": "<string>"                       // short human-readable explanation of the policy
}


Rules:
- You MUST output ONLY a single JSON object matching the schema above.
- Do NOT include any extra text, comments, or explanations outside the JSON.
- If a field is not relevant, set it to null (for numbers) or [] (for lists) or a sensible default string.

Now process this exploration intention:

"Go east and a make quick exploration but avoid stairs, then return home"
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
        presence_penalty = 1.0,
        stop=["\n\n"]
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


# -----------------------------
# Run the test
# -----------------------------
policy = run_with_benchmark(prompt)

print("\nParsed policy object:")
print(json.dumps(policy, indent=2))
