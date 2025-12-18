import os
import time
import re
from llama_cpp import Llama
from typing import List, Dict, Any

# --- GLOBAL CONFIGURATION ---
# !! PLEASE ADJUST !! Add all GGUF models you wish to test.
MODEL_PATHS = [
    "/home/admin/.models/Qwen3-0.6B-Q4_K_M.gguf",
    "/home/admin/.models/Qwen3-0.6B-Q8_0.gguf",
    "/home/admin/.models/Qwen3-1.7B-Q4_K_M.gguf",
    "/home/admin/.models/Qwen3-1.7B-Q8_0.gguf",
]

# Benchmarking Settings
N_THREADS = 4        # Number of CPU Cores (e.g., RPi 5)
MAX_TOKENS = 512     # Sufficient tokens for internal <think> process + final command
TEMPERATURE = 0.0    # Deterministic output for logic tests

# --- MULTI-SCENARIO TEST CASES ---
# Each dictionary defines a test scene and the expected correct command.
TEST_CASES = [
    {
        "Name": "Scenario 1: Base Test (Correct: LEFT)",
        "Prompt": """
[SYSTEM] Act as a Vehicle Navigation System. Choose: LEFT, CENTER, or RIGHT.
[RULES] 1. SAFETY: REJECT paths with objects < 5m. 2. EFFICIENCY: SELECT path with highest "Free Width".
[DATA]
- LEFT:   No objects < 5m. Free Width: 20%.
- CENTER: No objects < 5m. Free Width: 10%.
- RIGHT:  Object at 4.5m. (Status: UNSAFE).
[INSTRUCTION] Briefly analyze Safety and Efficiency. End response with: COMMAND: [DIRECTION]
""",
        "Correct Command": "LEFT"
    },
    {
        "Name": "Scenario 2: Safety First (Correct: STOP - All blocked)",
        "Prompt": """
[SYSTEM] Act as a Vehicle Navigation System. Choose: LEFT, CENTER, or RIGHT.
[RULES] 1. SAFETY: REJECT paths with objects < 5m. 2. EFFICIENCY: SELECT path with highest "Free Width".
[DATA]
- LEFT:   Object at 3.0m. (Status: UNSAFE).
- CENTER: Object at 4.9m. (Status: UNSAFE).
- RIGHT:  Object at 4.5m. (Status: UNSAFE).
[INSTRUCTION] Briefly analyze Safety and Efficiency. If all paths are unsafe, output COMMAND: STOP. End response with: COMMAND: [DIRECTION]
""",
        "Correct Command": "STOP"
    },
    {
        "Name": "Scenario 3: Center Wins (Correct: CENTER)",
        "Prompt": """
[SYSTEM] Act as a Vehicle Navigation System. Choose: LEFT, CENTER, or RIGHT.
[RULES] 1. SAFETY: REJECT paths with objects < 5m. 2. EFFICIENCY: SELECT path with highest "Free Width".
[DATA]
- LEFT:   No objects < 5m. Free Width: 5%.
- CENTER: No objects < 5m. Free Width: 30%.
- RIGHT:  Object at 5.1m. (Status: SAFE). Free Width: 15%.
[INSTRUCTION] Briefly analyze Safety and Efficiency. End response with: COMMAND: [DIRECTION]
""",
        "Correct Command": "CENTER"
    },
    {
        "Name": "Scenario 4: Right Wins (Correct: RIGHT)",
        "Prompt": """
[SYSTEM] Act as a Vehicle Navigation System. Choose: LEFT, CENTER, or RIGHT.
[RULES] 1. SAFETY: REJECT paths with objects < 5m. 2. EFFICIENCY: SELECT path with highest "Free Width".
[DATA]
- LEFT:   Object at 4.0m. (Status: UNSAFE).
- CENTER: No objects < 5m. Free Width: 10%.
- RIGHT:  No objects < 5m. Free Width: 25%.
[INSTRUCTION] Briefly analyze Safety and Efficiency. End response with: COMMAND: [DIRECTION]
""",
        "Correct Command": "RIGHT"
    }
]

def extract_command(output: str) -> str:
    """Robustly extracts the command (LEFT, CENTER, RIGHT, STOP) using regex."""
    clean_output = output.replace('**', '').strip()
    # Searches for COMMAND: followed by optional spaces and an uppercase word
    match = re.search(r"COMMAND:\s*([A-Z]+)", clean_output, re.IGNORECASE)
    if match:
        command = match.group(1).strip().upper()
        if command in ["LEFT", "CENTER", "RIGHT", "STOP"]:
            return command
    return "ERROR"

def run_benchmark(model_path: str, prompt: str, n_threads: int, max_tokens: int) -> Dict[str, Any]:
    """Loads, runs inference, and collects metrics for a single model and prompt."""
    model_name = os.path.basename(model_path)
    print(f"\n" + "="*60)
    print(f"🚀 STARTING BENCHMARK: {model_name}")
    print("="*60)
    
    if not os.path.exists(model_path):
        print(f"WARNING: Model path not found: {model_name}. Skipping.")
        return {"Model": model_name, "Result": "N/A", "Status": "MISSING"}

    try:
        # --- 1. MEASURE LOAD TIME ---
        start_load = time.perf_counter()
        llm = Llama(
            model_path=model_path,
            n_threads=n_threads,
            n_gpu_layers=0,
            n_ctx=1024,          
            verbose=False
        )
        end_load = time.perf_counter()
        load_time = end_load - start_load
        
        # --- 2. MEASURE INFERENCE TIME ---
        print("... Generating response ...")
        start_inference = time.perf_counter()
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": "Navigate safely. Be concise."}, 
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=TEMPERATURE,
            stream=False 
        )
        end_inference = time.perf_counter()
        inference_time = end_inference - start_inference

        # Output Processing
        full_output = response['choices'][0]['message']['content'].strip()
        final_command = extract_command(full_output)

        # Metrics
        completion_tokens = response['usage']['completion_tokens']
        speed_tps = completion_tokens / inference_time if inference_time > 0 else 0.0

        # Debug Output (last lines of the output)
        debug_snippet = full_output if len(full_output) < 300 else "..." + full_output[-300:]
        print(f"\n--- PARTIAL RAW OUTPUT (LAST LINES) ---")
        print(debug_snippet)
        print("-" * 30)

        print(f"⏱️  Load Time: {load_time:.2f}s | Response Time: {inference_time:.2f}s")
        print(f"🤖 Command Detected: {final_command}")

        return {
            "Model": model_name,
            "Speed (t/s)": speed_tps,
            "Load Time (s)": load_time,
            "Inference Time (s)": inference_time,
            "Result": final_command,
            "Tokens": completion_tokens
        }

    except Exception as e:
        print(f"❌ ERROR: Failed to run {model_name}: {e}")
        return {"Model": model_name, "Result": "ERROR", "Load Time (s)": 0, "Inference Time (s)": 0}

def display_results(results_by_model: Dict[str, Any]):
    """Displays the aggregated benchmark results for all models and scenarios."""
    if not results_by_model: 
        print("\nNo benchmark results collected.")
        return

    # Sort by average response time (fastest first)
    sorted_models = sorted(results_by_model.keys(), key=lambda m: results_by_model[m]['Avg_Time'])

    print("\n\n" + "#" * 80)
    print("## 🚀 OVERALL SUMMARY: ROBUSTNESS & PERFORMANCE")
    print(f"**Tested Scenarios:** {len(TEST_CASES)}")
    print("#" * 80)
    # 

    # Define columns
    headers = ["Model", "Avg. Time (s)", "Frequency (Hz)", "Accuracy", "Details"]
    table = "| " + " | ".join(headers) + " |\n"
    table += "| " + " | ".join(["---"] * len(headers)) + " |\n"

    for model_name in sorted_models:
        data = results_by_model[model_name]
        
        # Calculate accuracy score
        correct_count = sum(1 for res in data['Results'] if res['Result'] == res['Correct Command'])
        total_count = len(data['Results'])
        
        accuracy_str = f"{correct_count}/{total_count}"
        accuracy_percent = (correct_count / total_count) * 100

        # Detailed error logging
        error_details = []
        if correct_count < total_count:
            for res in data['Results']:
                if res['Result'] != res['Correct Command']:
                    error_details.append(f"❌ {res['Name'].split(': ')[0]}: Expected {res['Correct Command']}, Got {res['Result']}")
            details_str = f"**{accuracy_percent:.0f}% OK** ({'; '.join(error_details)})"
        else:
            details_str = "**100% CORRECT**"

        # Formatting the row
        freq = 1.0 / data['Avg_Time'] if data['Avg_Time'] > 0 else 0.0
        row = (
            f"| {model_name} "
            f"| **{data['Avg_Time']:.2f}** "
            f"| **{freq:.2f} Hz** "
            f"| {accuracy_str} "
            f"| {details_str} |\n"
        )
        table += row

    print(table)
    print("\n---")
    print("LEGEND:")
    print("- **Avg. Time (s):** Average time taken to make one decision (Inference Time).")
    print("- **Frequency (Hz):** Decisions per second (Theoretical maximum continuous rate).")
    print("- **Accuracy:** Number of correct commands out of the total tested scenarios.")


# --- SCRIPT EXECUTION ---
if __name__ == "__main__":
    
    results_by_model = {}

    for path in MODEL_PATHS:
        model_name = os.path.basename(path)
        all_times = []
        model_results = []
        
        print(f"\n\n{'='*80}\nSTARTING MULTI-SCENARIO TEST FOR: {model_name}\n{'='*80}")
        
        for case in TEST_CASES:
            # Run benchmark for the current model and scenario
            result = run_benchmark(
                path, 
                case["Prompt"], 
                N_THREADS, 
                MAX_TOKENS
            )
            
            # Collect timing and comparison data
            if result.get('Result') != "ERROR" and result.get('Result') != "N/A" and result.get('Inference Time (s)', 0) > 0:
                all_times.append(result['Inference Time (s)'])
            
            # Extend result with the correct command for final scoring
            result["Correct Command"] = case["Correct Command"]
            result["Name"] = case["Name"]
            model_results.append(result)
            
            time.sleep(1) # Small pause between cases

        # Calculate Average Time
        avg_time = sum(all_times) / len(all_times) if all_times else 0.0

        results_by_model[model_name] = {
            "Avg_Time": avg_time,
            "Results": model_results
        }
        
    # Display the final comparison results
    display_results(results_by_model)