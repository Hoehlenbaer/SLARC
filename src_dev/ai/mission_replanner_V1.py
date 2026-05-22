import time
import json
import re
import os
from llama_cpp import Llama

# ---------------------------------------------------------------
# Config & Model Loading
# ---------------------------------------------------------------
def find_model_path(model_name):
    script_directory = os.path.dirname(os.path.abspath(__file__))
    search_paths = [
        script_directory,
        "H:/SLARC_resources/models/",
        "/home/admin/.models/"
    ]

    print(f"Searching for model: {model_name}")
    print("-" * 30)

    for path in search_paths:
        potential_path = os.path.join(path, model_name)
        print(f"Checking: {potential_path}")
        if os.path.exists(potential_path):
            print("Model found!\n")
            return potential_path

    print("Model not found in any of the specified locations.\n")
    return None

MODEL_FILENAME = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
MODEL_PATH = find_model_path(MODEL_FILENAME)

if not MODEL_PATH:
    exit(1)

llm = Llama(
    model_path   = MODEL_PATH,
    n_ctx        = 4096,
    n_gpu_layers = -1,
    use_mlock    = True,
    use_mmap     = True,
    verbose      = False,
)

# ---------------------------------------------------------------
# Replanner Prompt Template
# ---------------------------------------------------------------
PROMPT_TEMPLATE = (
    "You are the High-Level Executive Replanner for an autonomous robot.\n"
    "Your job is to read the current blackboard state, evaluate the recent interruption, "
    "and output a new mission intention for the Exploration Manager.\n"
    "\n"
    "BLACKBOARD STATE:\n"
    "- Global Directive: {{GLOBAL_DIRECTIVE}}\n"
    "- Interruption Event: {{EVENT_TRIGGER}}\n"
    "- Robot State: Battery at {{BATTERY}}%, Location: {{CURRENT_LOCATION}}\n"
    "- Perception Map: {{MAP_SUMMARY}}\n"
    "- Safety Rules: {{SAFETY_RULES}}\n"
    "\n"
    "INSTRUCTIONS:\n"
    "1. Evaluate the Interruption Event against the Safety Rules and the Global Directive.\n"
    "2. If the global directive is mathematically or physically impossible to complete based on the Perception Map, your intention must be to abort the current goal and return home.\n"
    "3. Formulate a single, concise mission intention string that strictly includes:\n"
    "   - Where to move (e.g., south, west, location_name, avoid_regions)\n"
    "   - How to move (e.g., careful exploration, spiral search, flood_fill)\n"
    "   - Target object (if applicable)\n"
    "   - Action to perform on the target object (e.g., follow, greet, inspect, avoid)\n"
    "   - Stop conditions (e.g., time limits, battery thresholds, object found)\n"
    "\n"
    "OUTPUT FORMAT:\n"
    "Output ONLY the raw intention text. Do not include any explanations, reasoning, "
    "introductions, JSON formatting, or markdown. Output nothing but the intention sentence."
)


# ---------------------------------------------------------------
# Inference + benchmark
# ---------------------------------------------------------------
def run_replanner(directive, event, battery, location, map_summary, safety) -> dict:
    prompt = PROMPT_TEMPLATE.replace("{{GLOBAL_DIRECTIVE}}", directive)
    prompt = prompt.replace("{{EVENT_TRIGGER}}", event)
    prompt = prompt.replace("{{BATTERY}}", str(battery))
    prompt = prompt.replace("{{CURRENT_LOCATION}}", location)
    prompt = prompt.replace("{{MAP_SUMMARY}}", map_summary)
    prompt = prompt.replace("{{SAFETY_RULES}}", safety)

    print("Evaluating Situation...")
    t0 = time.perf_counter()

    response = llm(
        prompt,
        max_tokens       = 256,
        temperature      = 0.3, # Slightly higher than EM for a bit more lateral thinking
        top_p            = 0.9,
        top_k            = 40,
        presence_penalty = 0.0,
    )

    latency = time.perf_counter() - t0
    raw     = response["choices"][0]["text"].strip()

    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in model output:\n{raw}")
    
    decision = json.loads(match.group(0))

    u = response["usage"]
    print("\n=== Replanner Benchmark Results ===")
    print(f"Latency:    {latency:.3f} s")
    print(f"Tokens in:  {u['prompt_tokens']}")
    print(f"Tokens out: {u['completion_tokens']}")
    print(f"Throughput: {u['total_tokens'] / latency:.1f} t/s")

    return decision

# ---------------------------------------------------------------
# Main - Scenario Test
# ---------------------------------------------------------------
if __name__ == "__main__":
    
    # The Blackboard State for a Pathfinding Failure
    bb_directive = "Search and find the cat, then follow it for 10 minutes. If battery is below 50%, return home."
    bb_event     = "Pathfinder error: Cannot compute valid path to cat:location."
    bb_battery   = 60
    bb_location  = "living room"
    bb_map       = "cat:location is in the south, but the known route is blocked. Unexplored frontier exists in the west."
    
    # Implicit safety constraints
    bb_safety    = "Path and ATTRACTOR are implicitly safe. Obstacle is implicitly unsafe and must be avoided."

    print("--- BLACKBOARD STATE ---")
    print(f"Event: {bb_event}")
    print(f"Map:   {bb_map}\n")

    try:
        new_plan = run_replanner(
            directive   = bb_directive,
            event       = bb_event,
            battery     = bb_battery,
            location    = bb_location,
            map_summary = bb_map,
            safety      = bb_safety
        )

        print("\n=== Executive Decision ===")
        print(new_plan)

    except Exception as e:
        print(f"Error during execution: {e}")