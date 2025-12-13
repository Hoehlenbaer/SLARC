import time
import json
import re
import sys
from io import StringIO
from typing import List, Tuple, Dict
from llama_cpp import Llama
from tabulate import tabulate

# --- CONFIGURATION: MODELS TO TEST ---
MODELS_TO_TEST = [
    {"name": "Qwen3-0.6B-instruct-Q4", "path": "/home/admin/.models/Qwen3-0.6B-Q4_K_M.gguf"},
    {"name": "Qwen3-0.6B-instruct-Q8", "path": "/home/admin/.models/Qwen3-0.6B-Q8_0.gguf"},
]

# --- HIGH-LEVEL TEST CASES ---
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
        "objects": [
            {"id": 1, "category": "Attractor", "name": "Red Button", "distance": 3.0},
            {"id": 2, "category": "Danger", "name": "Trip hazard - Cable", "distance": 1.0},
            {"id": 3, "category": "Environment", "name": "Door frame", "distance": 2.5}
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
        "objects": [
            {"id": 1, "category": "Novelty", "name": "Empty crate", "distance": 5.0},
            {"id": 2, "category": "Danger", "name": "Sheer drop/Stairs", "distance": 0.5},
            {"id": 3, "category": "Environment", "name": "Floor", "distance": 5.0}
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
        "objects": [
            {"id": 1, "category": "Attractor", "name": "Charging station", "distance": 1.0},
            {"id": 2, "category": "Novelty", "name": "Small metallic object", "distance": 0.3},
            {"id": 3, "category": "Environment", "name": "Table leg", "distance": 0.5}
        ],
        "expected_action": "INVESTIGATE(ID 2)",
        "notes": "Prioritize the Novelty based on the current mission goal."
    }
]

# --- CODE EXTRACTION AND EXECUTION ---
def extract_python_code(text: str) -> str:
    """Extract Python code from markdown code blocks or raw text."""
    # Try to find code in markdown code blocks
    code_block_pattern = r'```(?:python)?\n(.*?)```'
    matches = re.findall(code_block_pattern, text, re.DOTALL)
    
    if matches:
        return matches[0].strip()
    
    # If no code block, return the text as-is (assuming it's raw code)
    return text.strip()

def execute_generated_code(code: str, objects: List[Dict]) -> Tuple[str, bool, str]:
    """
    Execute the generated Python code and capture the action command.
    Returns: (action_command, success, error_message)
    """
    try:
        # Create a safe execution environment
        namespace = {
            'objects': objects,
            'action': None
        }
        
        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            # Execute the code
            exec(code, namespace)
            
            # Get captured output
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        
        # Try to get the action from the namespace
        action = namespace.get('action')
        
        # If action is in namespace, use it; otherwise try to parse from output
        if action:
            return action, True, ""
        elif output.strip():
            # Look for action command in output
            action_pattern = r'(MOVE_TO|INVESTIGATE|STOP_AND_REPORT)\([^)]+\)'
            match = re.search(action_pattern, output)
            if match:
                return match.group(0), True, ""
            return output.strip(), False, "No valid action command found in output"
        else:
            return "N/A", False, "No action generated"
            
    except Exception as e:
        return "N/A", False, f"Execution error: {str(e)}"

# --- BENCHMARK FUNCTIONS ---
def run_cognitive_benchmark(model_cfg, test_cases: List[dict], llm: Llama):
    results = []
    
    for case in test_cases:
        perception_report = "\n".join([f" * {line}" for line in case['perception']])
        
        # Create objects data structure description
        objects_desc = "[\n"
        for obj in case['objects']:
            objects_desc += f"  {{'id': {obj['id']}, 'category': '{obj['category']}', 'name': '{obj['name']}', 'distance': {obj['distance']}}},\n"
        objects_desc += "]"
        
        # --- SYSTEM PROMPT FOR CODE GENERATION ---
        prompt = f"""<|im_start|>system
You are a Python code generator for the SLARC hexapod robot's decision-making system.

**TASK**: Write a complete Python program that analyzes the scene and determines the next action.

**DECISION LOGIC**:
1. **SAFETY OVERRIDE (Priority 1)**: If ANY object with category 'Danger' has distance < 1.0m, return: STOP_AND_REPORT(danger_name)
2. **MISSION GOAL (Priority 2)**: {case['goal']}
   - For Attractors or mission-relevant objects > 1.0m away: MOVE_TO(ID X)
   - For Novelty objects < 1.0m away: INVESTIGATE(ID X)

**INPUT DATA**: You will receive a list called 'objects' with this structure:
{objects_desc}

**OUTPUT REQUIREMENT**: 
Your code MUST set a variable called 'action' to one of:
- "MOVE_TO(ID X)"
- "INVESTIGATE(ID X)"  
- "STOP_AND_REPORT(reason)"

**EXAMPLE CODE**:
```python
# Analyze objects
for obj in objects:
    if obj['category'] == 'Danger' and obj['distance'] < 1.0:
        action = f"STOP_AND_REPORT({{obj['name']}})"
        break
else:
    # Find mission target
    target = min([o for o in objects if o['category'] == 'Attractor'], key=lambda x: x['distance'])
    action = f"MOVE_TO(ID {{target['id']}})"
```

Write ONLY the Python code, no explanations.
<|im_end|>
<|im_start|>user
Perception Report:
{perception_report}

Generate the Python decision code:
<|im_end|>
<|im_start|>assistant
```python
"""
        
        start_time = time.time()
        text_output = "N/A"
        generated_code = "N/A"
        action_output = "N/A"
        is_pass = False
        reason = "N/A"
        
        try:
            output = llm(
                prompt,
                max_tokens=512,  # More tokens for code generation
                temperature=0.1,
                stop=["<|im_end|>", "```\n\n"]
            )
            end_time = time.time()
            text_output = output['choices'][0]['text'].strip()
            
            # Extract Python code
            generated_code = extract_python_code(text_output)
            
            if not generated_code or len(generated_code) < 10:
                is_pass = False
                action_output = "N/A"
                reason = "No code generated"
            else:
                # Execute the generated code
                action_output, success, error = execute_generated_code(
                    generated_code, 
                    case['objects']
                )
                
                if success:
                    # Check if action matches expected
                    is_pass = (action_output == case['expected_action'])
                    reason = "Correct" if is_pass else f"Wrong action (expected: {case['expected_action']})"
                else:
                    is_pass = False
                    reason = error

        except Exception as e:
            end_time = time.time()
            is_pass = False
            action_output = "N/A"
            reason = f"Generation error: {str(e)}"

        duration = (end_time - start_time) * 1000

        results.append({
            "Model": model_cfg['name'],
            "Test Case": case['name'],
            "Goal": case['goal'][:50] + "..." if len(case['goal']) > 50 else case['goal'],
            "Pass": "✅" if is_pass else "❌",
            "Latency (ms)": f"{duration:.0f}",
            "Action Output": action_output,
            "Expected": case['expected_action'],
            "Code Length": f"{len(generated_code)} chars" if generated_code != "N/A" else "N/A",
            "Note": reason
        })
        
    return results

# --- EXECUTION ---
if __name__ == "__main__": 
    all_results = []
    
    print("=" * 80)
    print("SLM CODE GENERATION BENCHMARK FOR ROBOT DECISION-MAKING")
    print("=" * 80)
    
    print(f"\nTesting {len(MODELS_TO_TEST)} models on {len(TEST_CASES)} test cases...")
    print("Models will generate Python code that analyzes scenes and makes decisions.\n")
    
    for model_cfg in MODELS_TO_TEST:
        model_name = model_cfg["name"]
        model_path = model_cfg["path"]
        
        print(f"\n{'─' * 80}")
        print(f"Loading Model: {model_name} (CPU-ONLY)")
        print(f"{'─' * 80}")
        
        try:
            llm = Llama(
                model_path=model_path,
                n_ctx=2048,
                n_threads=4, 
                verbose=False,
                n_gpu_layers=0
            )
        except Exception as e:
            print(f"❌ Failed to load {model_name}: {e}")
            continue
        
        print(f"✓ Model loaded successfully")
        print(f"Running code generation tests...")
        
        all_results.extend(run_cognitive_benchmark(model_cfg, TEST_CASES, llm))
        del llm
        
    print("\n\n" + "=" * 80)
    print("FINAL RESULTS: CODE GENERATION BENCHMARK")
    print("=" * 80)
    
    # --- Performance Summary ---
    summary_data = []
    for model_cfg in MODELS_TO_TEST:
        model_name = model_cfg['name']
        model_data = [r for r in all_results if r['Model'] == model_name]
        
        if model_data:
            valid_latencies = [float(r['Latency (ms)']) for r in model_data]
            avg_latency = sum(valid_latencies) / len(valid_latencies) if valid_latencies else 0
            
            passes = sum(1 for r in model_data if r['Pass'] == '✅')
            accuracy = (passes / len(model_data)) * 100
            
            summary_data.append([
                model_name, 
                f"{avg_latency:.0f} ms", 
                f"{passes}/{len(model_data)}",
                f"{accuracy:.1f}%"
            ])

    print("\n📊 SUMMARY")
    print(tabulate(
        summary_data, 
        headers=["Model", "Avg Latency", "Passed", "Accuracy"], 
        tablefmt="fancy_grid"
    ))
    
    # --- Detailed Results ---
    print("\n📋 DETAILED RESULTS")
    print(tabulate(all_results, headers="keys", tablefmt="grid"))
    
    print("\n✓ Benchmark complete!\n")