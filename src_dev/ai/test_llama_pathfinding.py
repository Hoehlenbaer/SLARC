import time
import json
import math
from typing import List, Tuple
from llama_cpp import Llama, LlamaGrammar
from tabulate import tabulate

# --- CONFIGURATION: MODELS TO TEST ---
MODELS_TO_TEST = [
    {"name": "Llama-3.2-1B-Q4", "path": "/home/admin/.models/llama-3.2-1b-instruct-q4_k_m.gguf"},
    {"name": "Llama-3.2-1B-Q8", "path": "/home/admin/.models/llama-3.2-1b-instruct-q8_0.gguf"},
    {"name": "Qwen2.5-1.5B-Q4", "path": "/home/admin/.models/qwen2.5-1.5b-instruct-q4_k_m.gguf"},
]

# --- CORRECTED GRAMMARS ---
# 1. Single-Step Grammar (We expect ONE point, [x,y])
GRAMMAR_TEXT_1_STEP = r'''
    root   ::= "[" number "," number "]"
    number ::= "-"? [0-9] [0-9]?
'''
GRAMMAR_1_STEP = LlamaGrammar.from_string(GRAMMAR_TEXT_1_STEP)

# 2. Three-Step Grammar (We expect TWO points, [x1,y1], [x2,y2], because [x0,y0] is pre-filled)
GRAMMAR_TEXT_3_STEP_PARTIAL = r'''
    root   ::= point "," point "]"
    point  ::= "[" number "," number "]"
    number ::= "-"? [0-9] [0-9]?
'''
GRAMMAR_3_STEP_PARTIAL = LlamaGrammar.from_string(GRAMMAR_TEXT_3_STEP_PARTIAL)


# --- TEST CASES (Unchanged) ---
TEST_CASES = [
    {"name": "Simple Linear", "start": [0, 0], "goal": [0, 4], "obs": []},
    {"name": "Single Obstacle", "start": [0, 0], "goal": [0, 4], "obs": [[0, 2]]},
    {"name": "The Wall", "start": [0, 0], "goal": [3, 0], "obs": [[1, -1], [1, 0], [1, 1]]}
]

# --- HELPER: Path Validation (UPDATED) ---
def validate_step(path_segment: List[List[int]], start: List[int], goal, obstacles, strategy_name: str) -> Tuple[bool, str]:
    
    required_steps = len(path_segment)
    
    if required_steps == 0:
        return False, "Empty output from LLM."

    # 1. CHECK START POSITION (Must always start at 'start')
    if path_segment[0] != start:
        return False, f"First step of plan is {path_segment[0]}, not {start}."

    # 2. CHECK MOVEMENT (For 1-Step, the first step must be a move)
    if strategy_name == "1-Step" and path_segment[0] == start:
        # Since we use the 1-Step strategy to find the *next* move, outputting [0,0] is a failure.
        return False, "Model failed to move (planned to stand still)."

    # 3. CHECK CONTINUITY, COLLISION (The rest of the path segment)
    for i in range(required_steps - 1):
        curr = path_segment[i]
        next_step = path_segment[i+1]
        
        # Continuity Check
        dist = math.sqrt((next_step[0]-curr[0])**2 + (next_step[1]-curr[1])**2)
        if dist > 1.5: 
            return False, f"Teleported from {curr} to {next_step}."
            
        # Collision Check (Check the step *after* the start)
        if next_step in obstacles:
            return False, f"Crashed into obstacle at {next_step}."
            
    return True, "Valid"

# --- THE BENCHMARK FUNCTIONS (UPDATED PROMPTING) ---

def run_strategy_benchmark(model_cfg, strategy_name: str, test_cases: List[dict], llm: Llama):
    results = []
    
    for case in test_cases:
        
        # 1. Define LLM Parameters and Output Assembly based on Strategy
        if strategy_name == "1-Step":
            grammar = GRAMMAR_1_STEP
            max_tokens = 12
            output_format_desc = "Output ONLY the single best coordinate [x,y] for the next step:"
            prompt_suffix = f"""<|im_start|>assistant\n"""
            
        else: # 3-Step (Pipelined)
            grammar = GRAMMAR_3_STEP_PARTIAL
            max_tokens = 30
            output_format_desc = "Output ONLY the next two coordinates [[x1,y1],[x2,y2]] to complete the sequence:"
            
            # CRITICAL FIX: PRE-FILL the output list with the starting position.
            start_point_str = str(case['start']).replace(" ", "")
            prompt_suffix = f"""<|im_start|>assistant\n[{start_point_str},"""
        
        # 2. Construct the Full Prompt
        prompt = f"""<|im_start|>system
You are a rigid grid path planner. Start: {case['start']}. Goal: {case['goal']}. Obstacles: {case['obs']}. {output_format_desc}
<|im_end|>
<|im_start|>user
Current Position: {case['start']}
<|im_end|>
{prompt_suffix}
"""
        # 3. Run Generation and Time it
        start_time = time.time()
        try:
            output = llm(
                prompt,
                grammar=grammar,
                max_tokens=max_tokens,
                temperature=0.0
            )
            end_time = time.time()
            text_output = output['choices'][0]['text'] 
            
            
            # 4. ASSEMBLE THE FULL PATH SEGMENT FOR VALIDATION
            if strategy_name == "1-Step":
                # Raw output is [x,y]. Assemble as [[start], [x,y]].
                raw_next_step = json.loads(text_output)
                path_segment = [case['start'], raw_next_step]
                
            else: # 3-Step (Pipelined)
                # Raw output is [x1,y1],[x2,y2]]. Assemble as [[start], [x1,y1], [x2,y2]].
                # We prepend the first pre-filled part and wrap the whole thing in outer brackets.
                full_json_str = f"[{str(case['start']).replace(' ', '')},{text_output}"
                # The validator needs a clean list of lists: [[x0, y0], [x1, y1], [x2, y2]]
                path_segment = json.loads(full_json_str) 

            # 5. Validate the assembled segment
            is_valid, reason = validate_step(path_segment, case['start'], case['goal'], case['obs'], strategy_name)
            
            # Prepare Output Segment for display
            path_display = str(path_segment) if len(path_segment) <= 3 else f"{path_segment[0]} -> ... -> {path_segment[-1]}"

        except Exception as e:
            end_time = time.time()
            is_valid = False
            reason = f"Crash/Parse Error: {str(e)}"
            path_display = text_output.strip() if 'text_output' in locals() else "N/A"

        duration = (end_time - start_time) * 1000

        results.append({
            "Model": model_cfg['name'],
            "Strategy": strategy_name,
            "Test Case": case['name'],
            "Pass": "✅" if is_valid else "❌",
            "Latency (ms)": f"{duration:.0f}",
            "Output Segment": path_display,
            "Note": reason
        })
        
    return results

# --- EXECUTION (Unchanged) ---
if __name__ == "__main__": 
    
    all_results = []
    
    print(f"Starting Benchmark on {len(MODELS_TO_TEST)} models (1-Step and 3-Step strategies) with fixed prompt engineering...")
    
    for model_cfg in MODELS_TO_TEST:
        model_name = model_cfg["name"]
        model_path = model_cfg["path"]
        
        print(f"\n--- Loading Model: {model_name} ---")
        try:
            llm = Llama(
                model_path=model_path,
                n_ctx=2048,
                n_threads=4, 
                verbose=False,
                n_gpu_layers=-1
            )
        except Exception as e:
            print(f"Failed to load {model_name}: {e}. Skipping.")
            continue
        
        # Run 1-Step (Reactive) Benchmarks
        print(f"  Running 1-Step tests...")
        all_results.extend(run_strategy_benchmark(model_cfg, "1-Step", TEST_CASES, llm))
        
        # Run 3-Step (Pipelined) Benchmarks
        print(f"  Running 3-Step tests...")
        all_results.extend(run_strategy_benchmark(model_cfg, "3-Step", TEST_CASES, llm))

        del llm
        
    print("\n\n=== FINAL COMBINED BENCHMARK RESULTS (Prompt-Engineered) ===")
    
    # --- Performance Summary ---
    summary_data = []
    for model_cfg in MODELS_TO_TEST:
        model_name = model_cfg['name']
        
        model_data = [r for r in all_results if r['Model'] == model_name]
        
        one_step_data = [r for r in model_data if r['Strategy'] == '1-Step']
        three_step_data = [r for r in model_data if r['Strategy'] == '3-Step']

        if one_step_data:
            avg_1_latency = sum(float(r['Latency (ms)']) for r in one_step_data) / len(one_step_data)
            acc_1_step = sum(1 for r in one_step_data if r['Pass'] == '✅') / len(one_step_data) * 100
            summary_data.append([model_name, "1-Step (Reactive)", f"{avg_1_latency:.0f} ms", f"{acc_1_step:.1f}%"])

        if three_step_data:
            avg_3_latency = sum(float(r['Latency (ms)']) for r in three_step_data) / len(three_step_data)
            acc_3_step = sum(1 for r in three_step_data if r['Pass'] == '✅') / len(three_step_data) * 100
            summary_data.append([model_name, "3-Step (Pipelined)", f"{avg_3_latency:.0f} ms", f"{acc_3_step:.1f}%"])

    print("\n--- Summary: Latency vs. Accuracy ---")
    print(tabulate(summary_data, headers=["Model", "Strategy", "Avg Latency (Per Plan)", "Success Rate"], tablefmt="fancy_grid"))
    
    print("\n--- Detailed Results (Includes Output) ---")
    print(tabulate(all_results, headers="keys", tablefmt="grid"))
    
    print("\n")