import time
import json
import re
from typing import List, Tuple
from llama_cpp import Llama
from tabulate import tabulate

# --- CONFIGURATION: MODELS TO TEST ---
# Test the critical Qwen2.5-1.5B variants and the lighter Qwen3.
MODELS_TO_TEST = [
    {"name": "Qwen3-0.6B-instruct-Q4", "path": "/home/admin/.models/Qwen3-0.6B-Q4_K_M.gguf"},
    {"name": "Qwen3-0.6B-instruct-Q8", "path": "/home/admin/.models/Qwen3-0.6B-Q8_0.gguf"},
    #{"name": "qwen2.5-1.5b-instruct-q3", "path": "/home/admin/.models/qwen2.5-1.5b-instruct-q3_k_m.gguf"},
    #{"name": "qwen2.5-1.5b-instruct-q4", "path": "/home/admin/.models/qwen2.5-1.5b-instruct-q4_k_m.gguf"},
    #{"name": "qwen2.5-1.5b-instruct-q5", "path": "/home/admin/.models/qwen2.5-1.5b-instruct-q5_k_m.gguf"},
    #{"name": "qwen2.5-1.5b-instruct-q6", "path": "/home/admin/.models/qwen2.5-1.5b-instruct-q6_k.gguf"},
    #{"name": "qwen2.5-1.5b-instruct-q8", "path": "/home/admin/.models/qwen2.5-1.5b-instruct-q8_0.gguf"},
    #{"name": "Qwen3-1.7B-instruct-Q4", "path": "/home/admin/.models/Qwen3-1.7B-Q4_K_M.gguf"},
    #{"name": "Qwen3-1.7B-instruct-Q8", "path": "/home/admin/.models/Qwen3-1.7B-Q8_0.gguf"},
]

# --- HIGH-LEVEL TEST CASES (Unchanged) ---
TEST_CASES = [
    {
        "name": "Mission: Find Button (Blockage)",
        "goal": "Find and interact with the 'emergency red button' in Room C.",
        "perception": [
            "Location: Hallway leading to Room C, 2.5m away.",
            "Detected Objects (YOLOv8+Depth):",
            " - ID 1: [Attractor] (Red Button, confidence 98%, located 3.0m straight ahead).",
            " - ID 2: [Danger] (Trip hazard - Cable, confidence 95%, located 1.0m straight ahead).",
            " - ID 3: [Environment] (Door frame, 2.5m ahead)."
        ],
        "expected_action": "MOVE_TO(ID 1)",
        "notes": "Prioritize the mission goal (Red Button). Danger is >= 1.0m away, so proceed."
    },
    {
        "name": "Mission: Patrol (Critical Danger)",
        "goal": "Patrol the environment and identify novel objects.",
        "perception": [
            "Location: Industrial zone, 1.0m from edge.",
            "Detected Objects (YOLOv8+Depth):",
            " - ID 1: [Novelty] (Empty crate, 5.0m ahead).",
            " - ID 2: [Danger] (Sheer drop/Stairs, confidence 100%, located 0.5m at 45 degrees left).",
            " - ID 3: [Environment] (Floor, extending 5m)."
        ],
        "expected_action": "STOP_AND_REPORT(Sheer drop/Stairs)",
        "notes": "Immediate safety override. Danger is < 1.0m (0.5m)."
    },
    {
        "name": "Mission: Investigate Novelty",
        "goal": "Patrol the environment and identify novel objects.",
        "perception": [
            "Location: Room B, near charging station.",
            "Detected Objects (YOLOv8+Depth):",
            " - ID 1: [Attractor] (Charging station, 1.0m behind).",
            " - ID 2: [Novelty] (Small metallic object, confidence 70%, 0.3m ahead).",
            " - ID 3: [Environment] (Table leg, 0.5m right)."
        ],
        "expected_action": "INVESTIGATE(ID 2)",
        "notes": "Prioritize the Novelty based on the current mission goal. Danger (ID 3) is safe (0.5m is the cut-off, and it's not a critical hazard name). Novelty is close (0.3m) so INVESTIGATE is the correct action."
    }
]

# --- REGEX AND PARSING CONSTANTS ---
# 1. Regex to extract the command string from the Python assignment output.
ASSIGNMENT_REGEX = re.compile(r"ACTION_COMMAND\s*=\s*['\"](.+?)['\"]")
# 2. Regex to validate the extracted command string format (unchanged from previous runs)
ACTION_REGEX = re.compile(r'^(MOVE_TO|INVESTIGATE|STOP_AND_REPORT)\((.+?)\)$')

# --- BENCHMARK FUNCTIONS ---

def run_cognitive_benchmark(model_cfg, test_cases: List[dict], llm: Llama):
    results = []
    
    for case in test_cases:
        
        perception_report = "\n".join([f" * {line}" for line in case['perception']])
        
        # --- NEW HIGH-PRIORITY SYSTEM PROMPT (Python Assignment Format) ---
        prompt = f"""<|im_start|>system
You are the high-level brain for a hexapod robot named SLARC. Your job is to decide the next immediate action based on the Perception Report and the Mission Goal.

**ABSOLUTE PRIORITY 1: SAFETY OVERRIDE**
If ANY [Danger] object is detected closer than 1.0m (e.g., 0.5m, 0.3m), you MUST immediately choose: STOP_AND_REPORT(reason). The reason must be the name of the danger object, e.g., 'Sheer drop/Stairs'.

**PRIORITY 2: MISSION GOAL**
If the Safety Override is NOT triggered, prioritize the mission: {case['goal']}
---
Available Actions (Choose ONE):
1. MOVE_TO(ID X): Move the robot to a target ID (Use for long-distance goals like Attractors > 1.0m away).
2. INVESTIGATE(ID X): Engage with a target that requires closer inspection (Use for nearby Novelty, < 1.0m away).
3. STOP_AND_REPORT(reason): Halt movement and report danger (Use ONLY for Safety Override).
---
Respond ONLY with a single line of Python code that sets the variable 'ACTION_COMMAND' to the final action string.

Example Output: ACTION_COMMAND = 'MOVE_TO(ID 1)'
Example Output: ACTION_COMMAND = 'STOP_AND_REPORT(Sheer drop/Stairs)'
<|im_end|>
<|im_start|>user
Perception Report:
{perception_report}

Generate the ACTION_COMMAND:
<|im_end|>
<|im_start|>assistant
"""
        
        start_time = time.time()
        text_output = "N/A"
        extracted_command = "N/A"
        action_output = "N/A"
        is_valid_format = False
        is_accurate = False
        is_pass = False
        reason = "N/A"
        
        try:
            output = llm(
                prompt,
                max_tokens=100, # Max tokens reduced since output is a single line
                temperature=0.0,
                # *** LlamaGrammar is intentionally OMITTED to prevent the Segmentation Fault ***
            )
            end_time = time.time()
            text_output = output['choices'][0]['text'].strip()
            
            # --- POST-PROCESSING AND VALIDATION ---
            
            # 1. Extract the string literal from the Python assignment
            assignment_match = ASSIGNMENT_REGEX.search(text_output)
            
            if assignment_match:
                extracted_command = assignment_match.group(1).strip()
            else:
                # Fallback: if no assignment, assume the model output the action directly
                # This handles cases like: MOVE_TO(ID 1)
                extracted_command = text_output 
            
            # 2. Validate the extracted string's function call format
            action_match = ACTION_REGEX.match(extracted_command)
            
            if action_match:
                # The grammar should ensure this format: ACTION(ID X) or ACTION(reason)
                action_output = f"{action_match.group(1)}({action_match.group(2).strip()})"
                is_valid_format = True
            else:
                # Invalid function call format (chatter, incomplete, or wrong syntax)
                action_output = extracted_command
                is_valid_format = False

            # 3. Check for core logic match
            if is_valid_format:
                is_accurate = (action_output == case['expected_action'])
                is_pass = is_accurate
                reason = "Valid" if is_pass else "Incorrect Action"
            else:
                is_pass = False
                reason = "Invalid Format/Chatter"

        except Exception as e:
            end_time = time.time()
            is_pass = False
            action_output = text_output 
            reason = f"Crash/Runtime Error: {str(e)}"

        duration = (end_time - start_time) * 1000

        results.append({
            "Model": model_cfg['name'],
            "Test Case": case['name'],
            "Goal": case['goal'],
            "Pass": "✅" if is_pass else "❌",
            "Latency (ms)": f"{duration:.0f}",
            "Action Output": action_output,
            "Expected": case['expected_action'],
            "Note": reason
        })
        
    return results

# --- EXECUTION ---
if __name__ == "__main__": 
    
    all_results = []
    
    print("-------------------------------------------------------------------")
    print("!!! FINAL STABLE RPi5 COGNITIVE BENCHMARK (EXPLICIT PYTHON OUTPUT) !!!")
    print("-------------------------------------------------------------------")
    
    print(f"\nStarting COGNITIVE BENCHMARK on {len(MODELS_TO_TEST)} models (RPi5 CPU-ONLY MODE)...")
    
    for model_cfg in MODELS_TO_TEST:
        model_name = model_cfg["name"]
        model_path = model_cfg["path"]
        
        print(f"\n--- Loading Model: {model_name} (CPU-ONLY) ---")
        try:
            llm = Llama(
                model_path=model_path,
                n_ctx=2048,
                n_threads=4, 
                verbose=False,
                n_gpu_layers=0 # Ensures execution is CPU-only
            )
        except Exception as e:
            print(f"Failed to load {model_name}: {e}. Skipping.")
            continue
        
        print(f"  Running Cognitive tests...")
        all_results.extend(run_cognitive_benchmark(model_cfg, TEST_CASES, llm))

        del llm
        
    print("\n\n=== FINAL COGNITIVE BENCHMARK RESULTS ===")
    
    # --- Performance Summary ---
    summary_data = []
    for model_cfg in MODELS_TO_TEST:
        model_name = model_cfg['name']
        
        model_data = [r for r in all_results if r['Model'] == model_name]
        
        if model_data:
            valid_latencies = [float(r['Latency (ms)']) for r in model_data if r['Action Output'] != "N/A"]
            if valid_latencies:
                avg_latency = sum(valid_latencies) / len(valid_latencies)
            else:
                avg_latency = float('inf')
                
            acc = sum(1 for r in model_data if r['Pass'] == '✅') / len(model_data) * 100
            
            summary_data.append([model_name, f"{avg_latency:.0f} ms" if avg_latency != float('inf') else "N/A", f"{acc:.1f}%"])

    print("\n--- Summary: Strategic Speed vs. Accuracy ---")
    print(tabulate(summary_data, headers=["Model", "Avg Latency (Per Decision)", "Cognitive Accuracy"], tablefmt="fancy_grid"))
    
    # --- Detailed Results (Strategic Output) ---
    print("\n--- Detailed Results (Strategic Output) ---")
    
    print(tabulate(all_results, headers="keys", tablefmt="grid"))
    
    print("\n")