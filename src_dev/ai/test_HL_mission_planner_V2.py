
# next_action_planner.py
# Hexabot Next-Action Policy using llama-cpp-python with Qwen3-0.6B-Q4_K_M.gguf
# - Emits exactly ONE next action as JSON, given mission goal + performed actions.
# - Keeps CoT (<think>...</think>) visible, but strips it before JSON parsing.
# - Grammar-constrained JSON when supported; otherwise falls back gracefully.
# - All settings are defined below (no command-line arguments needed).

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from llama_cpp import Llama

# =========================
# User-configurable Settings
# =========================

# Update this to the actual location of your model file:
MODEL_PATH = r"C:/daten/models/Qwen3-0.6B-Q4_K_M.gguf"

# Inference / runtime settings
N_CTX = 2048                     # context window
N_THREADS = max(1, os.cpu_count() or 8)
N_GPU_LAYERS = 0                 # >0 if using CUDA build
SEED = 1234
TEMPERATURE = 0.2
MAX_TOKENS = 384
POLICY_STEPS = 8                 # how many next-action decisions to simulate

# NOTE: No stop tokens — we want to allow CoT output (<think>...</think>).
# If you ever want to suppress prefaces, you can add stop tokens like "<think>".

# =========================
# Constants & Prompts
# =========================

SYSTEM_PROMPT = (
    "You are the Hexabot High-Level Brain (HLB). You are a next-action policy that outputs ONLY the single next "
    "mid-level action the planner should execute, given the mission goal and the list of actions already performed.\n\n"
    "Mission constraints:\n"
    "- Hexapod with 3-DOF legs; maintain static stability.\n"
    "- Safety first: minimum obstacle clearance = 20 cm; keep pitch/roll within safe limits.\n"
    "- Sensors: depth camera, IMU, (optional) LiDAR; manipulator: single gripper.\n"
    "- Be energy-efficient; avoid unnecessary re-planning.\n\n"
    "Output rules:\n"
    "- Return ONE JSON object for the next action. You MAY include a <think>...</think> block BEFORE the JSON for reasoning.\n"
    "- Use this schema strictly:\n"
    "{\n"
    '  "next_action": {\n'
    '    "id": "string",\n'
    '    "action": "string", // one of: initialize_sensors, health_check, global_scan, build_map, frontier_explore, object_detect, approach_object, align_for_grasp, grasp_object, verify_grasp, return_to_start, place_object, finalize\n'
    '    "parameters": { "any": "object" },\n'
    '    "rationale": "string",\n'
    '    "dependencies": ["string"],\n'
    '    "success_criteria": ["string"],\n'
    '    "failure_recovery": ["string"],\n'
    '    "risk_checks": ["string"]\n'
    "  }\n"
    "}\n\n"
    "Policy:\n"
    "- Consider the mission goal and the performed actions in order.\n"
    "- If a dependency is not yet satisfied, propose the prerequisite action.\n"
    "- Stop proposing new actions once the object is placed and the mission is finalized."
)

MISSION_GOAL = (
    "Mission Goal:\n"
    "1. Explore area and identify the \"cup\" object\n"
    "2. When \"cup\"-object found, grab it\n"
    "3. Carry \"cup\"-object back to start point"
)

ALLOWED_ACTIONS = [
    "initialize_sensors",
    "health_check",
    "global_scan",
    "build_map",
    "frontier_explore",
    "object_detect",
    "approach_object",
    "align_for_grasp",
    "grasp_object",
    "verify_grasp",
    "return_to_start",
    "place_object",
    "finalize",
]

# JSON Schema used for grammar-constrained decoding (if available)
NEXT_ACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "next_action": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "action": {"type": "string", "enum": ALLOWED_ACTIONS},
                "parameters": {"type": "object"},
                "rationale": {"type": "string"},
                "dependencies": {"type": "array", "items": {"type": "string"}},
                "success_criteria": {"type": "array", "items": {"type": "string"}},
                "failure_recovery": {"type": "array", "items": {"type": "string"}},
                "risk_checks": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "id",
                "action",
                "parameters",
                "rationale",
                "dependencies",
                "success_criteria",
                "failure_recovery",
                "risk_checks",
            ],
        }
    },
    "required": ["next_action"],
}


# =========================
# Helpers
# =========================

def build_messages(system_prompt: str, mission_goal: str, performed_actions: List[str]) -> List[Dict[str, str]]:
    """
    Build chat messages for chat-completion style models.
    """
    user_content = f"""Return ONE JSON object (next action). You MAY include a <think>...</think> block BEFORE the JSON.

{mission_goal}

Performed actions (chronological):
{json.dumps(performed_actions)}
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def build_fallback_prompt(system_prompt: str, mission_goal: str, performed_actions: List[str]) -> str:
    """
    Build a single-string fallback prompt for create_completion() when chat format is unavailable.
    """
    user_content = f"""Return ONE JSON object (next action). You MAY include a <think>...</think> block BEFORE the JSON.

{mission_goal}

Performed actions (chronological):
{json.dumps(performed_actions)}
"""
    return (
        f"[SYSTEM]\n{system_prompt}\n"
        f"[USER]\n{user_content}\n"
        f"[ASSISTANT]\n"
    )


def measure_tokens(llm: Llama, text: str) -> int:
    """Count tokens using the model tokenizer (bytes API)."""
    return len(llm.tokenize(text.encode("utf-8")))


def try_build_grammar() -> Optional[Any]:
    """
    Attempt to construct a JSON grammar from the schema.
    Returns LlamaGrammar instance if available, else None.
    NOTE: Some llama-cpp-python versions require a STRING to from_json_schema.
    """
    try:
        from llama_cpp import LlamaGrammar
        grammar = LlamaGrammar.from_json_schema(json.dumps(NEXT_ACTION_SCHEMA))
        return grammar
    except Exception as e:
        print(f"[info] Grammar not available or failed ({e}). Proceeding without grammar.")
        return None


def init_llm(model_path: str, n_ctx: int, n_threads: int, n_gpu_layers: int, seed: int) -> Tuple[Llama, bool]:
    """
    Initialize Llama with Qwen chat format if possible.
    Returns (llm, use_chat_api).
    """
    try:
        llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_gpu_layers=n_gpu_layers,
            seed=seed,
            chat_format="qwen",
            verbose=False,
        )
        print("[init] Using chat API with chat_format='qwen'.")
        return llm, True
    except Exception as e:
        print(f"[init] chat_format='qwen' failed ({e}). Falling back to plain completion).")
        llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_gpu_layers=n_gpu_layers,
            seed=seed,
            verbose=False,
        )
        return llm, False


def strip_think(text: str) -> Tuple[str, Optional[str]]:
    """
    Remove the first <think>...</think> block from text and return (clean_text, think_block).
    Preserves CoT for display, but ensures it doesn't interfere with JSON parsing.
    """
    pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
    match = pattern.search(text)
    think_block = None
    if match:
        think_block = match.group(1).strip()
        # Remove the block from the text used for parsing
        text = text[:match.start()] + text[match.end():]
    return text.strip(), think_block


def extract_first_json(text: str) -> Optional[str]:
    """
    Extract the first JSON object substring from text (balanced braces).
    This helps if the model emits extra prose before/after the JSON.
    """
    start = text.find("{")
    if start == -1:
        return None
    # Simple brace balancing
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None  # no balanced end brace found


def get_next_action(
    llm: Llama,
    performed_actions: List[str],
    use_chat_api: bool,
    grammar: Optional[Any],
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any]:
    """
    Query the model for the next single action as JSON.
    Returns a dict with fields: text, think, parsed, json_valid, error, prompt_tokens, completion_tokens, elapsed_s, tokens_per_second.
    """
    messages = build_messages(SYSTEM_PROMPT, MISSION_GOAL, performed_actions)
    prompt = build_fallback_prompt(SYSTEM_PROMPT, MISSION_GOAL, performed_actions)

    start = time.perf_counter()
    if use_chat_api:
        kwargs = dict(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            # No stop sequences: we keep CoT
        )
        if grammar is not None:
            kwargs["grammar"] = grammar
        result = llm.create_chat_completion(**kwargs)
        raw_text = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if prompt_tokens is None:
            prompt_text = "\n".join(m.get("content", "") for m in messages)
            prompt_tokens = measure_tokens(llm, prompt_text)
        if completion_tokens is None:
            completion_tokens = measure_tokens(llm, raw_text)
    else:
        kwargs = dict(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        if grammar is not None:
            kwargs["grammar"] = grammar
        result = llm.create_completion(**kwargs)
        raw_text = result["choices"][0]["text"]
        prompt_tokens = measure_tokens(llm, prompt)
        completion_tokens = measure_tokens(llm, raw_text)

    elapsed = time.perf_counter() - start
    tps = completion_tokens / elapsed if elapsed > 0 else 0.0

    # Preserve CoT, but strip it from the text we parse
    clean_text, think_block = strip_think(raw_text)

    # Extract the first JSON object (in case of extra text)
    json_str = extract_first_json(clean_text)

    parsed = None
    json_valid = False
    error = None
    if json_str is None:
        error = "No JSON object found in model output."
    else:
        try:
            parsed = json.loads(json_str)
            json_valid = True
        except Exception as e:
            error = f"JSON parse failed: {e}"

    return {
        "text": raw_text,
        "think": think_block,
        "json_str": json_str,
        "parsed": parsed,
        "json_valid": json_valid,
        "error": error,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "elapsed_s": elapsed,
        "tokens_per_second": tps,
    }


def simulate_execution(history: List[str], next_action_json: Dict[str, Any]) -> None:
    """
    Simulate executing the action: append 'ID: action' to the history.
    Replace this with calls to your actual mid-level planner in production.
    """
    na = next_action_json.get("next_action", {})
    action_id = na.get("id", "S?")
    action_name = na.get("action", "unknown")
    history.append(f"{action_id}: {action_name}")


# =========================
# Main
# =========================

def main():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model file not found: {MODEL_PATH}")

    # Warn if n_ctx smaller than model's train context (harmless; informative)
    print(f"llama_context: n_ctx_per_seq ({N_CTX}) — if smaller than model's train context, full capacity won't be used.")

    llm, use_chat_api = init_llm(
        model_path=MODEL_PATH,
        n_ctx=N_CTX,
        n_threads=N_THREADS,
        n_gpu_layers=N_GPU_LAYERS,
        seed=SEED,
    )

    grammar = try_build_grammar()

    performed_actions: List[str] = []  # Start at origin; nothing done yet.

    for i in range(1, POLICY_STEPS + 1):
        print(f"\n=== Policy step {i} ===")
        result = get_next_action(
            llm=llm,
            performed_actions=performed_actions,
            use_chat_api=use_chat_api,
            grammar=grammar,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )

        print(f"Elapsed: {result['elapsed_s']:.3f}s | Tokens/sec: {result['tokens_per_second']:.2f} | JSON valid: {result['json_valid']}")

        # Show CoT (reasoning) for inspection
        if result["think"]:
            print("\n--- Model CoT (<think>) ---")
            print(result["think"])

        # Show raw model text
        print("\n--- Raw Model Output ---")
        print(result["text"])

        if not result["json_valid"]:
            print("\n--- Extracted JSON (failed or missing) ---")
            print(result["json_str"])
            print(f"\nParse error: {result['error']}")
            break

        print("\n--- Extracted JSON ---")
        print(result["json_str"])

        print("\n--- Parsed JSON ---")
        print(json.dumps(result["parsed"], indent=2))

        # Simulate successful execution and append to history
        simulate_execution(performed_actions, result["parsed"])
        print("\nPerformed actions:", performed_actions)

        # Stop early if the model proposes finalize
        action = result["parsed"].get("next_action", {}).get("action", "")
        if action == "finalize":
            print("Model proposed 'finalize'. Stopping.")
            break


if __name__ == "__main__":
    main()