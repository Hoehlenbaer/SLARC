
# test_HL_mission_planner.py

import json
import time
import os
from typing import Dict, Any, List

from llama_cpp import Llama

# ------------------ System / User Prompts ------------------

SYSTEM_PROMPT = (
    "You are the Hexabot High-Level Brain (HLB). Your responsibility is to transform a high-level mission goal "
    "into mid-level, actionable steps for the mapping and planning engine.\n\n"
    "Constraints & priorities:\n"
    "- Safety and static stability at all times (hexapod, 3-DOF legs).\n"
    "- Prefer energy-efficient paths; avoid unnecessary re-planning.\n"
    "- Maintain a minimum obstacle clearance of 20 cm and keep roll/pitch within safe bounds.\n"
    "- Sensors available: Depth camera, IMU, (optional) LiDAR. Manipulator: single gripper.\n"
    "- The mid-level planner expects clear actions with parameters and dependencies.\n\n"
    "Output format:\n"
    "Return ONLY a JSON object that strictly follows the provided schema. Do not include commentary.\n"
    "Your steps must be sufficient for a mid-level action planner to:\n"
    "- Initialize and validate sensors\n"
    "- Explore/map the area\n"
    "- Detect the \"cup\" object and approach it\n"
    "- Grasp the cup safely\n"
    "- Return to the start point and place the cup\n\n"
    "Be explicit in success criteria, failure recovery, and risk checks."
)

USER_GOAL = (
    "Mission Goal:\n"
    "1. Explore area and identify the \"cup\" object\n"
    "2. When \"cup\"-object found, grab it\n"
    "3. Carry \"cup\"-object back to start point"
)

# ------------------ JSON Schema for Grammar ------------------

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "mission_goal": {"type": "string"},
        "assumptions": {
            "type": "object",
            "properties": {
                "sensors": {"type": "array", "items": {"type": "string"}},
                "manipulator": {"type": "string"},
                "safety_margins_cm": {"type": "number"},
                "max_pitch_deg": {"type": "number"},
                "max_roll_deg": {"type": "number"},
            },
            "required": ["sensors", "manipulator", "safety_margins_cm", "max_pitch_deg", "max_roll_deg"],
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": [
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
                            "navigate_to",
                            "place_object",
                            "return_to_start",
                            "finalize",
                        ],
                    },
                    "parameters": {"type": "object"},
                    "purpose": {"type": "string"},
                    "dependencies": {"type": "array", "items": {"type": "string"}},
                    "success_criteria": {"type": "array", "items": {"type": "string"}},
                    "failure_recovery": {"type": "array", "items": {"type": "string"}},
                    "risk_checks": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "id",
                    "action",
                    "parameters",
                    "purpose",
                    "dependencies",
                    "success_criteria",
                    "failure_recovery",
                    "risk_checks",
                ],
            },
        },
        "final_state": {"type": "string"},
    },
    "required": ["mission_goal", "assumptions", "steps", "final_state"],
}

# ------------------ Helpers ------------------

def build_messages(system_prompt: str, user_goal: str) -> List[Dict[str, str]]:
    """Build chat messages. The 'content' is ONE string (no stray literals)."""
    content = f"""Follow the schema strictly and produce only JSON.

{user_goal}

Schema reminder (do NOT echo this back, just follow it):
{json.dumps(PLAN_SCHEMA)}
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


def measure_tokens(llm: Llama, text: str) -> int:
    """Count tokens using the model tokenizer."""
    return len(llm.tokenize(text.encode("utf-8")))


def run_once(
    llm: Llama,
    messages: List[Dict[str, str]],
    grammar=None,
    temperature: float = 0.2,
    max_tokens: int = 768,
) -> Dict[str, Any]:
    """Single completion with timing and basic validation."""
    start = time.perf_counter()
    kwargs = dict(messages=messages, temperature=temperature, max_tokens=max_tokens, stream=False)
    if grammar is not None:
        kwargs["grammar"] = grammar
    result = llm.create_chat_completion(**kwargs)
    elapsed = time.perf_counter() - start

    text = result["choices"][0]["message"]["content"]
    usage = result.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")

    if prompt_tokens is None:
        prompt_text = "\n".join(m.get("content", "") for m in messages)
        prompt_tokens = measure_tokens(llm, prompt_text)
    if completion_tokens is None:
        completion_tokens = measure_tokens(llm, text)

    tps = completion_tokens / elapsed if elapsed > 0 else 0.0

    parsed = None
    json_valid = False
    error = None
    try:
        parsed = json.loads(text)
        json_valid = True
    except Exception as e:
        error = str(e)

    return {
        "text": text,
        "parsed": parsed,
        "json_valid": json_valid,
        "error": error,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "elapsed_s": elapsed,
        "tokens_per_second": tps,
    }


def run_streaming(
    llm: Llama,
    messages: List[Dict[str, str]],
    grammar=None,
    temperature: float = 0.2,
    max_tokens: int = 768,
) -> str:
    """Streaming example."""
    chunks = []
    start = time.perf_counter()
    kwargs = dict(messages=messages, temperature=temperature, max_tokens=max_tokens, stream=True)
    if grammar is not None:
        kwargs["grammar"] = grammar
    for chunk in llm.create_chat_completion(**kwargs):
        delta = chunk["choices"][0].get("delta", {})
        piece = delta.get("content", "")
        if piece:
            print(piece, end="", flush=True)
            chunks.append(piece)
    elapsed = time.perf_counter() - start
    print(f"\n\n[streaming elapsed: {elapsed:.3f}s]")
    return "".join(chunks)


def main():
    # Update to your actual path (use forward slashes or r"" for raw string)
    model_path = r"C:/daten/models/Qwen3-0.6B-Q4_K_M.gguf"

    # Initialize llama.cpp binding
    llm = Llama(
        model_path=model_path,
        n_ctx=4096,
        n_threads=os.cpu_count() or 8,
        n_gpu_layers=0,      # >0 if using CUDA build
        seed=1234,
        chat_format="qwen",  # remove if your version errors; see fallback below
        verbose=False,
    )

    # Try to build a JSON grammar from schema (newer versions only)
    grammar = None
    try:
        from llama_cpp import LlamaGrammar
        grammar = LlamaGrammar.from_json_schema(PLAN_SCHEMA)
    except Exception as e:
        print(f"[info] Grammar not available or failed ({e}). Proceeding without grammar.")

    messages = build_messages(SYSTEM_PROMPT, USER_GOAL)

    # ---- Single run ----
    print("=== Single Run (non-streaming) ===")
    result = run_once(llm, messages, grammar=grammar, temperature=0.2, max_tokens=768)

    print(f"Elapsed: {result['elapsed_s']:.3f}s")
    print(f"Completion tokens: {result['completion_tokens']}")
    print(f"Tokens/sec: {result['tokens_per_second']:.2f}")
    print(f"JSON valid: {result['json_valid']}")
    if not result["json_valid"]:
        print(f"JSON parse error: {result['error']}")

    print("\n=== Model Output ===")
    print(result["text"])

    # ---- Optional streaming ----
    print("\n=== Streaming Run (optional) ===")
    _ = run_streaming(llm, messages, grammar=grammar, temperature=0.2, max_tokens=768)


if __name__ == "__main__":
    main()

