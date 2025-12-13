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
    # Add other models here
]

# Benchmarking Settings
N_THREADS = 4        
MAX_TOKENS = 1024     # Increased buffer for complex Chain-of-Thought (CoT)
TEMPERATURE = 0.0    # Deterministic output for logic tests

# --- REVISED AND EXTENDED MULTI-SCENARIO TEST CASES (9 Scenarios) ---

# The LLM must now output: COMMAND: [VERB] [ID] or COMMAND: STOP

TEST_CASES = [
    # ----------------------------------------------------
    # S1: ID-Baseline (MOVE PATH_A)
    # ----------------------------------------------------
    {
        "Name": "S1: ID-Baseline (MOVE PATH_A)",
        "Prompt": """
[SYSTEM] Act as a Vehicle Navigation System. Output: [VERB] [ID] or TURN [Direction].
[RULES] 
1. PRIORITY: If an ATTRACTOR is present (Type: ATTRACTOR), the command MUST be INVESTIGATE ID. 
2. EFFICIENCY: If no ATTRACTOR, MOVE to the PATH with the LARGEST "Free Path Width". 
3. SAFETY: If no PATH or ATTRACTOR options are present, use TURN LEFT or TURN RIGHT.
[DATA]
- Object ID: PATH_A. Type: PATH. Free Path Width: 20%.
- Object ID: PATH_B. Type: PATH. Free Path Width: 10%.
- Object ID: PEDESTRIAN_1. Type: OBSTACLE.
[INSTRUCTION] Follow the rules strictly. 
Potential answers:
- INVESTIGATE [Object ID]
- MOVE TO [Object ID]
- TURN [LEFT/RIGHT]

Your FINAL OUTPUT MUST ONLY be a single line.
""",
        "Correct Command": "MOVE PATH_A"
    },
    # ----------------------------------------------------
    # S2: Safety Turn (TURN LEFT)
    # ----------------------------------------------------
    {
        "Name": "S2: Safety Turn (TURN LEFT)",
        "Prompt": """
[SYSTEM] Act as a Vehicle Navigation System. Output: [VERB] [ID] or TURN [Direction].
[RULES] 
1. PRIORITY: If an ATTRACTOR is present (Type: ATTRACTOR), the command MUST be INVESTIGATE ID. 
2. EFFICIENCY: If no ATTRACTOR, MOVE to the PATH with the LARGEST "Free Path Width". 
3. SAFETY: If no PATH or ATTRACTOR options are present, use TURN LEFT or TURN RIGHT.
[DATA]
- Object ID: PATH_A. Type: PATH.
- Object ID: PATH_B. Type: PATH.
- Object ID: OBSTACLE_C. Type: OBSTACLE.
[INSTRUCTION] Follow the rules strictly. 
Potential answers:
- INVESTIGATE [Object ID]
- MOVE TO [Object ID]
- TURN [LEFT/RIGHT]
""",
        "Correct Command": "TURN LEFT" # Da keine Free Path Width angegeben, wird TURN ausgelöst.
    },
    # ----------------------------------------------------
    # S3: ID-Efficiency Center (MOVE PATH_B) - WALL_C Width entfernt
    # ----------------------------------------------------
    {
        "Name": "S3: ID-Efficiency Center (MOVE PATH_B)",
        "Prompt": """
[SYSTEM] Act as a Vehicle Navigation System. Output: [VERB] [ID] or TURN [Direction].
[RULES] 
1. PRIORITY: If an ATTRACTOR is present (Type: ATTRACTOR), the command MUST be INVESTIGATE ID. 
2. EFFICIENCY: If no ATTRACTOR, MOVE to the PATH with the LARGEST "Free Path Width". 
3. SAFETY: If no PATH or ATTRACTOR options are present, use TURN LEFT or TURN RIGHT.
[DATA]
- Object ID: PATH_A. Type: PATH. Free Path Width: 5%.
- Object ID: PATH_B. Type: PATH. Free Path Width: 30%.
- Object ID: WALL_C. Type: OBSTACLE.
[INSTRUCTION] Follow the rules strictly. 
Potential answers:
- INVESTIGATE [Object ID]
- MOVE TO [Object ID]
- TURN [LEFT/RIGHT]
""",
        "Correct Command": "MOVE PATH_B"
    },
    # ----------------------------------------------------
    # S4: ID-Efficiency Right (MOVE PATH_A) - WALL_C Width entfernt
    # ----------------------------------------------------
    {
        "Name": "S4: ID-Efficiency Right (MOVE PATH_A)",
        "Prompt": """
[SYSTEM] Act as a Vehicle Navigation System. Output: [VERB] [ID] or TURN [Direction].
[RULES] 
1. PRIORITY: If an ATTRACTOR is present (Type: ATTRACTOR), the command MUST be INVESTIGATE ID. 
2. EFFICIENCY: If no ATTRACTOR, MOVE to the PATH with the LARGEST "Free Path Width". 
3. SAFETY: If no PATH or ATTRACTOR options are present, use TURN LEFT or TURN RIGHT.
[DATA]
- Object ID: TRUCK_1. Type: OBSTACLE.
- Object ID: PATH_A. Type: PATH. Free Path Width: 10%.
- Object ID: WALL_C. Type: OBSTACLE.
[INSTRUCTION] Follow the rules strictly. 
Potential answers:
- INVESTIGATE [Object ID]
- MOVE TO [Object ID]
- TURN [LEFT/RIGHT]
""",
        "Correct Command": "MOVE PATH_A" # Jetzt ist PATH_A der einzige Pfad.
    },
    # ----------------------------------------------------
    # S5: Attractor Priority (INVESTIGATE ATTRACTOR_1)
    # ----------------------------------------------------
    {
        "Name": "S5: Attractor Priority (INVESTIGATE ATTRACTOR_1)",
        "Prompt": """
[SYSTEM] Act as a Vehicle Navigation System. Output: [VERB] [ID] or TURN [Direction].
[RULES] 
1. PRIORITY: If an ATTRACTOR is present (Type: ATTRACTOR), the command MUST be INVESTIGATE ID. 
2. EFFICIENCY: If no ATTRACTOR, MOVE to the PATH with the LARGEST "Free Path Width". 
3. SAFETY: If no PATH or ATTRACTOR options are present, use TURN LEFT or TURN RIGHT.
[DATA]
- Object ID: PATH_A. Type: PATH. Free Path Width: 50%.
- Object ID: ATTRACTOR_1. Type: ATTRACTOR.
- Object ID: BARRIER_C. Type: OBSTACLE.
[INSTRUCTION] Follow the rules strictly. 
Potential answers:
- INVESTIGATE [Object ID]
- MOVE TO [Object ID]
- TURN [LEFT/RIGHT]
""",
        "Correct Command": "INVESTIGATE ATTRACTOR_1"
    },
    # ----------------------------------------------------
    # S6: Investigate Blocked (INVESTIGATE ATTRACTOR_1)
    # ----------------------------------------------------
    {
        "Name": "S6: Investigate Blocked (INVESTIGATE ATTRACTOR_1)",
        "Prompt": """
[SYSTEM] Act as a Vehicle Navigation System. Output: [VERB] [ID] or TURN [Direction].
[RULES] 
1. PRIORITY: If an ATTRACTOR is present (Type: ATTRACTOR), the command MUST be INVESTIGATE ID. 
2. EFFICIENCY: If no ATTRACTOR, MOVE to the PATH with the LARGEST "Free Path Width". 
3. SAFETY: If no PATH or ATTRACTOR options are present, use TURN LEFT or TURN RIGHT.
[DATA]
- Object ID: PATH_A. Type: PATH. Free Path Width: 40%.
- Object ID: ATTRACTOR_1. Type: ATTRACTOR.
- Object ID: PATH_B. Type: PATH. Free Path Width: 20%.
[INSTRUCTION] Follow the rules strictly. 
Potential answers:
- INVESTIGATE [Object ID]
- MOVE TO [Object ID]
- TURN [LEFT/RIGHT]
""",
        "Correct Command": "INVESTIGATE ATTRACTOR_1"
    },
    # ----------------------------------------------------
    # S7: Path Competition (MOVE PATH_B) - ATTRACTOR_1 Width entfernt
    # ----------------------------------------------------
    {
        "Name": "S7: Path Competition (INVESTIGATE ATTRACTOR_1)",
        "Prompt": """
[SYSTEM] Act as a Vehicle Navigation System. Output: [VERB] [ID] or TURN [Direction].
[RULES] 
1. PRIORITY: If an ATTRACTOR is present (Type: ATTRACTOR), the command MUST be INVESTIGATE ID. 
2. EFFICIENCY: If no ATTRACTOR, MOVE to the PATH with the LARGEST "Free Path Width". 
3. SAFETY: If no PATH or ATTRACTOR options are present, use TURN LEFT or TURN RIGHT.
[DATA]
- Object ID: PATH_A. Type: PATH. Free Path Width: 20%.
- Object ID: ATTRACTOR_1. Type: ATTRACTOR.
- Object ID: PATH_B. Type: PATH. Free Path Width: 35%.
[INSTRUCTION] Follow the rules strictly. 
Potential answers:
- INVESTIGATE [Object ID]
- MOVE TO [Object ID]
- TURN [LEFT/RIGHT]
""",
        "Correct Command": "MOVE PATH_B"
    },
    # ----------------------------------------------------
    # S8: Attractor & Narrow Path (INVESTIGATE ATTRACTOR_1)
    # ----------------------------------------------------
    {
        "Name": "S8: Attractor & Narrow Path (INVESTIGATE ATTRACTOR_1)",
        "Prompt": """
[SYSTEM] Act as a Vehicle Navigation System. Output: [VERB] [ID] or TURN [Direction].
[RULES] 
1. PRIORITY: If an ATTRACTOR is present (Type: ATTRACTOR), the command MUST be INVESTIGATE ID. 
2. EFFICIENCY: If no ATTRACTOR, MOVE to the PATH with the LARGEST "Free Path Width". 
3. SAFETY: If no PATH or ATTRACTOR options are present, use TURN LEFT or TURN RIGHT.
[DATA]
- Object ID: ATTRACTOR_1. Type: ATTRACTOR.
- Object ID: PATH_A. Type: PATH. Free Path Width: 50%.
- Object ID: OBSTACLE_C. Type: OBSTACLE.
[INSTRUCTION] Follow the rules strictly. 
Potential answers:
- INVESTIGATE [Object ID]
- MOVE TO [Object ID]
- TURN [LEFT/RIGHT]
""",
        "Correct Command": "INVESTIGATE ATTRACTOR_1"
    },
    # ----------------------------------------------------
    # S9: Extreme Efficiency (MOVE PATH_C) - ATTRACTOR_1 Width entfernt
    # ----------------------------------------------------
    {
        "Name": "S9: Extreme Efficiency (INVESTIGATE ATTRACTOR_1)",
        "Prompt": """
[SYSTEM] Act as a Vehicle Navigation System. Output: [VERB] [ID] or TURN [Direction].
[RULES] 
1. PRIORITY: If an ATTRACTOR is present (Type: ATTRACTOR), the command MUST be INVESTIGATE ID. 
2. EFFICIENCY: If no ATTRACTOR, MOVE to the PATH with the LARGEST "Free Path Width". 
3. SAFETY: If no PATH or ATTRACTOR options are present, use TURN LEFT or TURN RIGHT.
[DATA]
- Object ID: PATH_A. Type: PATH. Free Path Width: 5%.
- Object ID: ATTRACTOR_1. Type: ATTRACTOR.
- Object ID: PATH_C. Type: PATH. Free Path Width: 95%.
[INSTRUCTION] Follow the rules strictly. 
Potential answers:
- INVESTIGATE [Object ID]
- MOVE TO [Object ID]
- TURN [LEFT/RIGHT]
""",
        "Correct Command": "MOVE PATH_C"
    }
]


import re
# ... (andere Imports)

def extract_command(output: str) -> str:
    """
    Sucht den ZULETZT erkannten gültigen Befehl (VERB ID oder STOP) im gesamten Output
    des Modells.
    
    Diese Version sucht nach den Mustern, ignoriert das "COMMAND:"-Präfix (wie vom 
    Benutzer gewünscht) und toleriert optionale eckige Klammern um die ID.
    """
    clean_output = output.replace('**', '').strip()
    valid_commands = []
    
    # Muster 1: [VERB] [ID] (MOVE oder INVESTIGATE)
    # Sucht nach MOVE oder INVESTIGATE, gefolgt von einer optionalen Klammer und der ID.
    # Erlaubt optional COMMAND: davor (falls das Modell es doch benutzt).
    pattern_verb_id = r"(?:COMMAND:\s*)?(MOVE|INVESTIGATE)\s*\[?([A-Z0-9_]+)\]?" 
    matches_verb_id = re.findall(pattern_verb_id, clean_output, re.IGNORECASE)
    
    # Füge alle gefundenen Verb-ID-Paare zur Liste hinzu (großgeschrieben und ohne Klammern)
    for verb, target_id in matches_verb_id:
        valid_commands.append(f"{verb.upper()} {target_id.upper()}")
        
    # Muster 2: STOP
    # Sucht nach dem Wort STOP, optional mit COMMAND: davor.
    pattern_stop = r"(?:COMMAND:\s*)?\bSTOP\b"
    matches_stop = re.findall(pattern_stop, clean_output, re.IGNORECASE)
    
    # Füge alle gefundenen "STOP" Befehle zur Liste hinzu
    for _ in matches_stop:
        valid_commands.append("STOP")
        
    # ENTSCHEIDEND: Gib den LETZTEN erkannten gültigen Befehl zurück
    if valid_commands:
        return valid_commands[-1]
        
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
                {"role": "system", "content": "Navigate safely and adhere strictly to the command format."}, 
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

        # --- FULL RAW MODEL OUTPUT ---
        print(f"\n--- FULL RAW MODEL OUTPUT (Tokens: {completion_tokens}) ---")
        
        # Print full output, truncated after 2048 characters for console readability
        print(full_output[:2048]) 
        
        if len(full_output) > 2048:
            print("\n[... Output truncated after 2048 characters for console readability ...]")
            
        print("-" * 50)
        # ---------------------------

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
        # DIESER BLOCK FÄNGT AUSNAHMEN INNERHALB DES TRY-BLOCKS
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
                    error_details.append(f"❌ {res['Name'].split(': ')[0]}: Expected '{res['Correct Command']}', Got '{res['Result']}'")
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
        
        # Test each case
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