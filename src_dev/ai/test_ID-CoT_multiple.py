import os
import time
import re
from llama_cpp import Llama
from typing import List, Dict, Any

# --- GLOBAL CONFIGURATION ---
MODEL_PATHS = [
    "/home/admin/.models/Qwen3-0.6B-Q4_K_M.gguf",
]

N_THREADS = 4        
MAX_TOKENS = 1024   
TEMPERATURE = 0.0    

# --- PROMPT TEMPLATE ---
PROMPT_TEMPLATE = """
[MISSION]
1. PRIORITY: If object type is ATTRACTOR -> INVESTIGATE [ID].
2. PATROL: Else, MOVE to PATH with highest 'width'.
3. SAFETY: If no PATH/ATTRACTOR -> TURN.

[DATA]
{data_block}

[INSTRUCTION]
Analyze [DATA]. Output the single best command.
Format: [VERB] [ID] or TURN
"""

# --- TEST CASES ---
TEST_CASES = [
    {
        "Name": "S1: Patrol (Wide Path)",
        "Data": """- ID: PATH_A | Type: PATH | width: 25
- ID: PATH_B | Type: PATH | width: 10
- ID: CHAIR_1 | Type: OBSTACLE""",
        "Correct Command": "MOVE PATH_A"
    },
    {
        "Name": "S2: Dead End (Safety)",
        "Data": """- ID: WALL_1 | Type: OBSTACLE
- ID: TABLE_1 | Type: OBSTACLE""",
        "Correct Command": "TURN" 
    },
    {
        "Name": "S3: Attractor Spotting",
        "Data": """- ID: PATH_A | Type: PATH | width: 50
- ID: CUP_1  | Type: ATTRACTOR""",
        "Correct Command": "INVESTIGATE CUP_1"
    },
    {
        "Name": "S4: Obstacle Avoidance",
        "Data": """- ID: TRUCK_1 | Type: OBSTACLE
- ID: PATH_C  | Type: PATH | width: 15""",
        "Correct Command": "MOVE PATH_C"
    },
    {
        "Name": "S5: Priority Test",
        "Data": """- ID: PATH_1 | Type: PATH | width: 99
- ID: KEYS_1    | Type: ATTRACTOR""",
        "Correct Command": "INVESTIGATE KEYS_1"
    }
]

def extract_command(output: str) -> str:
    """
    Robust command extractor handling both "VERB ID" and standalone "TURN".
    """
    # 1. Remove Chain-of-Thought blocks (<think>...</think>)
    clean_output = re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL)
    
    # 2. Clean formatting
    clean_output = clean_output.replace('**', '').replace('COMMAND:', '').strip()

    # 3. Define Regex
    # Pattern looks for: (MOVE or INVESTIGATE) followed by an ID, OR standalone (TURN)
    pattern = r"(MOVE(?: TO)?|INVESTIGATE)\s+\[?([A-Z0-9_]+)\]?|\b(TURN)\b"
    
    matches = re.findall(pattern, clean_output, re.IGNORECASE)

    valid_commands = []
    for verb_id_match, target_id, turn_match in matches:
        if turn_match:
            valid_commands.append("TURN")
        elif verb_id_match and target_id:
            verb = verb_id_match.upper().strip()
            target = target_id.upper().strip()
            
            if "MOVE" in verb:
                valid_commands.append(f"MOVE {target}")
            elif "INVESTIGATE" in verb:
                valid_commands.append(f"INVESTIGATE {target}")

    if valid_commands:
        return valid_commands[-1] 
        
    return "ERROR"

def run_benchmark(model_path: str, data_block: str, expected_result: str, n_threads: int, max_tokens: int) -> Dict[str, Any]:
    model_name = os.path.basename(model_path)
    final_prompt = PROMPT_TEMPLATE.format(data_block=data_block)

    if not os.path.exists(model_path):
        return {"Result": "MISSING"}

    try:
        # Load Model
        start_load = time.perf_counter()
        llm = Llama(
            model_path=model_path,
            n_threads=n_threads,
            max_tokens=max_tokens,
            n_gpu_layers=0,
            n_ctx=1024,
            verbose=False
        )
        
        # Inference
        start_inference = time.perf_counter()
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": "You are a robot navigation logic engine. Be concise."},
                {"role": "user", "content": final_prompt}
            ],
            max_tokens=max_tokens,
            temperature=TEMPERATURE, 
            stream=False 
        )
        inference_time = time.perf_counter() - start_inference

        # Processing
        full_output = response['choices'][0]['message']['content'].strip()
        final_command = extract_command(full_output)
        completion_tokens = response['usage']['completion_tokens']

        # --- DEBUG OUTPUT ---
        print(f"\n[Scenario Data]:\n{data_block.strip()}")
        print(f"[Raw LLM Output]: {full_output.replace(chr(10), ' ')}") # Print full output on one line
        
        # Real-time comparison
        print(f"🎯 Expected: {expected_result}")
        print(f"👉 Actual:   {final_command}")
        
        if expected_result == final_command:
            print("Status:      ✅ PASS")
        else:
            print("Status:      ❌ FAIL")
        # --------------------

        return {
            "Model": model_name,
            "Inference Time (s)": inference_time,
            "Result": final_command,
            "Tokens": completion_tokens
        }

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return {"Result": "ERROR", "Inference Time (s)": 0}

def display_results(results):
    print("\n" + "="*80)
    print(f"{'TEST NAME':<30} | {'EXPECTED':<20} | {'ACTUAL':<20} | {'STATUS'}")
    print("-" * 80)
    
    score = 0
    for r in results:
        status = "✅ PASS" if r['Result'] == r['Expected'] else "❌ FAIL"
        if status == "✅ PASS": score += 1
        print(f"{r['Name']:<30} | {r['Expected']:<20} | {r['Result']:<20} | {status}")
    
    print("-" * 80)
    print(f"Accuracy: {score}/{len(results)} ({(score/len(results))*100:.1f}%)")

# --- EXECUTION ---
if __name__ == "__main__":
    final_results = []
    
    for path in MODEL_PATHS:
        print(f"\n🚀 Testing Logic Model: {os.path.basename(path)}")
        for case in TEST_CASES:
            res = run_benchmark(path, case["Data"], case["Correct Command"], N_THREADS, MAX_TOKENS)
            res["Name"] = case["Name"]
            res["Expected"] = case["Correct Command"]
            final_results.append(res)
            
    display_results(final_results)