import os
import time
import re
from llama_cpp import Llama
from typing import List, Dict, Any

# --- GLOBAL CONFIGURATION ---
MODEL_PATHS = [
    "C:/daten/models/Qwen3-0.6B-Q4_K_M.gguf",
    #"C:/daten/models/Qwen3-0.6B-Q8_0.gguf",
    #"/home/admin/.models/Qwen3-1.7B-Q4_K_M.gguf",
    #"/home/admin/.models/Qwen3-1.7B-Q8_0.gguf",
    #"/home/admin/.models/Qwen3-0.6B-Q5_K_M.gguf",
    #"/home/admin/.models/Qwen3-0.6B-Q6_K.gguf",
]

N_THREADS = 8        
MAX_TOKENS = 1024    # High token count to allow CoT to complete and ensure command generation.
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

# --- TEST CASES (REVISED with explicit absence markers) ---
TEST_CASES = [
    {
        "Name": "S1: Patrol (Wide Path)",
        "Data": """* NO ATTRACTORS FOUND
- ID: PATH_A | Type: PATH | width: 25
- ID: PATH_B | Type: PATH | width: 10
- ID: CHAIR_1 | Type: OBSTACLE""", # Explicitly state no attractors
        "Correct Command": "MOVE PATH_A"
    },
    {
        "Name": "S2: Dead End (Safety)",
        "Data": """* NO PATHS FOUND
* NO ATTRACTORS FOUND
- ID: WALL_1 | Type: OBSTACLE
- ID: TABLE_1 | Type: OBSTACLE""", # Crucial change for the slow case
        "Correct Command": "TURN" 
    },
    {
        "Name": "S3: Attractor Spotting",
        "Data": """* NO OBSTACLES FOUND
- ID: PATH_A | Type: PATH | width: 50
- ID: CUP_1  | Type: ATTRACTOR""", # Both present, no change needed
        "Correct Command": "INVESTIGATE CUP_1"
    },
    {
        "Name": "S4: Obstacle Avoidance",
        "Data": """* NO ATTRACTORS FOUND
- ID: TRUCK_1 | Type: OBSTACLE
- ID: PATH_C  | Type: PATH | width: 15""", # Explicitly state no attractors
        "Correct Command": "MOVE PATH_C"
    },
    {
        "Name": "S5: Priority Test",
        "Data": """* NO OBSTACLES FOUND
- ID: PATH_1 | Type: PATH | width: 90
- ID: KEYS_1    | Type: ATTRACTOR""", # Explicitly state no obstacles
        "Correct Command": "INVESTIGATE KEYS_1"
    }
]

def extract_command(output: str) -> str:
    """
    Robust command extractor handling both "VERB ID" and standalone "TURN",
    designed to strip the long Chain-of-Thought block.
    """
    # 1. Remove Chain-of-Thought blocks (<think>...</think>)
    clean_output = re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL)
    
    # 2. Clean formatting (remove bolding, command labels, and extraneous text)
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
        # Return the last valid command found
        return valid_commands[-1] 
        
    return "ERROR"

def run_benchmark(model_path: str, data_block: str, expected_result: str, n_threads: int, max_tokens: int) -> Dict[str, Any]:
    model_name = os.path.basename(model_path)
    final_prompt = PROMPT_TEMPLATE.format(data_block=data_block)

    if not os.path.exists(model_path):
        return {"Result": "MISSING"}

    try:
        # Load Model
        llm = Llama(
            model_path=model_path,
            n_threads=n_threads,
            n_gpu_layers=0,
            n_ctx=max_tokens, # Set n_ctx equal to max_tokens (1024)
            verbose=False
        )
        
        # Inference
        start_inference = time.perf_counter()
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": "You are a robot navigation logic engine. Be concise and prioritize the command format."},
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
        print(f"[Raw LLM Output]: {full_output.replace(chr(10), ' ')}") 
        
        # Real-time comparison
        print(f"🎯 Expected: {expected_result}")
        print(f"👉 Actual:   {final_command}")
        print(f"⏱️ Time:     {inference_time:.4f}s") # Time output added
        
        if expected_result == final_command:
            print("Status:      ✅ PASS")
        else:
            print("Status:      ❌ FAIL")
        # --------------------

        return {
            "Model": model_name,
            "Inference Time (s)": inference_time,
            "Result": final_command,
            "Expected": expected_result, 
            "Name": case["Name"],
            "Tokens": completion_tokens
        }

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return {"Result": "ERROR", "Inference Time (s)": 0, "Expected": expected_result, "Name": "ERROR"}

def display_results(results):
    # Group results by model
    model_results: Dict[str, List[Dict[str, Any]]] = {}
    for r in results:
        model = r.get('Model', 'UNKNOWN')
        if model not in model_results:
            model_results[model] = []
        model_results[model].append(r)

    # Display results per model
    for model_name, res_list in model_results.items():
        total_time = sum(r.get('Inference Time (s)', 0) for r in res_list if r.get('Result') != 'ERROR')
        total_tokens = sum(r.get('Tokens', 0) for r in res_list if r.get('Result') != 'ERROR')
        valid_tests = len([r for r in res_list if r.get('Result') != 'ERROR' and 'Inference Time (s)' in r])
        
        avg_time = total_time / valid_tests if valid_tests > 0 else 0
        tokens_per_sec = total_tokens / total_time if total_time > 0 else 0
        
        print("\n" + "="*80)
        print(f"MODEL BENCHMARK: {model_name}")
        print("="*80)
        
        print(f"{'TEST NAME':<30} | {'EXPECTED':<20} | {'ACTUAL':<20} | {'TIME (s)':<10} | {'STATUS'}")
        print("-" * 80)
        
        score = 0
        for r in res_list:
            actual = r.get('Result', 'N/A')
            expected = r.get('Expected', 'N/A')
            status = "✅ PASS" if actual == expected else "❌ FAIL"
            if status == "✅ PASS": score += 1
            time_str = f"{r.get('Inference Time (s)', 0):.4f}" if 'Inference Time (s)' in r else "N/A"
            print(f"{r['Name']:<30} | {expected:<20} | {actual:<20} | {time_str:<10} | {status}")
        
        print("-" * 80)
        print(f"Accuracy: {score}/{len(res_list)} ({(score/len(res_list))*100:.1f}%)")
        print(f"Total Inference Time: {total_time:.4f}s")
        print(f"Average Inference Time per Test: {avg_time:.4f}s")
        print(f"Tokens/Second (tok/s): {tokens_per_sec:.2f}")
        print("="*80)

# --- EXECUTION ---
if __name__ == "__main__":
    final_results = []
    
    # Store the results and rerun the loop to collect all data before displaying.
    for path in MODEL_PATHS:
        # Load the model outside the inner loop to avoid reloading for every test case.
        # However, the current run_benchmark function reloads the model inside the try block, 
        # which is necessary if the models are truly different (as they are).
        print(f"\n🚀 Testing Logic Model: {os.path.basename(path)}")
        for case in TEST_CASES:
            res = run_benchmark(path, case["Data"], case["Correct Command"], N_THREADS, MAX_TOKENS)
            # Add expected and name back to the result dictionary for the final summary display
            res["Name"] = case["Name"]
            res["Expected"] = case["Correct Command"]
            final_results.append(res)
            
    display_results(final_results)