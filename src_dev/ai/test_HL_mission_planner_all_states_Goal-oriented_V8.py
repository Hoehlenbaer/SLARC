from llama_cpp import Llama
import os
import time 

# --- Configuration ---
MODEL_PATH = r"/home/admin/.models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf" 

# --- Goal-Oriented System Instructions ---
SYSTEM_PROMPT = """
You are a Robot Logic Controller. 
Your goal is to find, grab, and place the [object] at home. The name of the current [object] is [cup].
To achieve this goal, you need to fulfill certain steps in order.

--- EXECUTION PIPELINE ---
Check conditions in order. The FIRST FALSE condition is the ONLY action to take.

1. Area Explored? (FALSE -> COMMAND: explore)
2. [object] Found? (FALSE -> COMMAND: find [object])
3. Arrived at [object]? (FALSE -> COMMAND: move [object])
4. [object]Grabbed? (FALSE -> COMMAND: grab [object])
5. Arrived at home? (FALSE -> COMMAND: move home)
6. [object] Placed? (FALSE -> COMMAND: place [object])

If no condition is FALSE, the command is "none".
Replace [object] with the name of the object.

--- TASK ---
Analyze the STATUS. 
Rule: Evaluation MUST STOP at the first FALSE condition. 


FORMAT:
<THINKING>
- [Step Name]: [TRUE/FALSE]
Conclusion: [First FALSE condition found], therefore [Action].
</THINKING>
<COMMAND>
[Action]
</COMMAND>
"""
# Updated for the simplified 6-step flow
# Name, Explored, Found, Arrived_Obj, Grabbed, Arrived_Home, Placed, Expected
TEST_CASES = [
    # (Name, Explored, Found, Arrived_Obj, Grabbed, Arrived_Home, Placed, Expected)
    #("Start", 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', "explore"),
    #("Not found", 'TRUE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', "find cup"),
    ("Not arrived at object", 'TRUE', 'TRUE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', "move cup"),
    #("Dropped mid-move", 'TRUE', 'TRUE', 'TRUE', 'FALSE', 'FALSE', 'FALSE', "grab cup"),
    #("Pushed away", 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'FALSE', 'FALSE', "move home"),
    #("At home, not placed", 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'FALSE', "place cup"),
    #("Already completed", 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', "none")
]

def generate_user_input(explored, found, arrived_obj, grabbed, arrived_home, placed):
    return f"""
Current Status:
- Area Explored?: {explored}
- [object] Found?: {found}
- Arrived at [object]?: {arrived_obj}
- [object]Grabbed?: {grabbed}
- Arrived at home?: {arrived_home}
- [object] Placed?: {placed}
"""
# ... [The rest of the test_full_mission logic remains the same as your working V11/V12]

def extract_command(full_text):
    """
    Finds the LAST valid <COMMAND> block in the text to avoid 
    picking up task listings or thinking-process rehearsals.
    """
    if not full_text:
        return None

    # Find the last occurrence of the opening tag
    start_tag = "<COMMAND>"
    end_tag = "</COMMAND>"
    
    last_start_index = full_text.rfind(start_tag)
    last_end_index = full_text.rfind(end_tag)

    # Validate that the tags exist and are in the correct order
    if last_start_index != -1 and last_end_index > last_start_index:
        start = last_start_index + len(start_tag)
        cmd = full_text[start:last_end_index].strip().lower()
        
        # Remove common model artifacts (like brackets or trailing periods)
        cmd = cmd.replace("[", "").replace("]", "").replace(".", "").strip()

        # Mapping to standardize the output
        if "explore" in cmd: return "explore"
        #if "find" in cmd: return "find cup"
        if "move home" in cmd or "arrive home" in cmd: return "move home"
        #if "move" in cmd: return "move cup"  # Order matters: check 'move home' first
        #if "grab" in cmd: return "grab cup"
        #if "place" in cmd: return "place cup"
        if "none" in cmd: return "none"
        
        return cmd
        
    return None

def test_full_mission(model_path: str):
    if not os.path.exists(model_path):
        print(f"Error: Model file not found at path: {model_path}")
        return

    print(f"Loading model from: {model_path}...")
    try:
        llm = Llama(
            model_path=model_path,
            n_ctx=4096,
            n_gpu_layers=-1,
            verbose=False,
            n_threads=3,
            chat_format="chatml"
        )
        print("Model loaded successfully.\n")

        total_tests = len(TEST_CASES)
        passed_tests = 0

        # The list now has 8 items: 
        # (Name, Explored, Found, Arrived_Obj, Grabbed, Arrived_Home, Placed, Expected)
        model_start_time = time.perf_counter()
        for i, (name, explored, found, arrived_obj, grabbed, arrived_home, placed, expected) in enumerate(TEST_CASES):
            # Update the input generator call to match the new arguments
            user_input = generate_user_input(explored, found, arrived_obj, grabbed, arrived_home, placed)
            
            start_time = time.perf_counter()
            print(f"--- Running Test {i+1}/{total_tests}: {name} ---")

            stream = llm.create_chat_completion(
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": user_input}],
                          max_tokens=2048,
                          temperature=0.0,
                          stream=True)
                   

            full_output_chunks = []
            for chunk in stream:
                delta = chunk['choices'][0]['delta']
                if 'content' in delta:
                    full_output_chunks.append(delta['content'])

            elapsed_time = time.perf_counter() - start_time
            full_text = "".join(full_output_chunks)
            extracted_command = extract_command(full_text)
            
            # --- DISPLAY THINKING PROCESS ---
            print("\nMODEL OUTPUT:")
            print(full_text) 
            print("-" * 30)

            # Clean for comparison
            clean_extracted = extracted_command.lower().replace("[cup]", "cup").strip() if extracted_command else "none"
            clean_expected = expected.lower().replace("[cup]", "cup").strip()

            if clean_extracted == clean_expected:
                print(f"✅ PASS: Result'{extracted_command}' matches expected '{expected}'. ({elapsed_time:.2f}s)")
                passed_tests += 1  # <--- THE MISSING LINE!
            else:
                print(f"❌ FAIL: Got '{extracted_command}', expected '{expected}'.")
            
            print("=" * 50 + "\n")

        # END OF TEST LOOP
        total_time = time.perf_counter() - model_start_time

        print(f"--- Final Results ---")
        print(f"Tests Run: {total_tests}")
        print(f"Tests Passed: {passed_tests}")
        print(f"Success Rate: {passed_tests/total_tests:.2f}")

        return {
            "tests_run": total_tests,
            "tests_passed": passed_tests,
            "success_rate": passed_tests / total_tests,
            "total_time": total_time,
            "avg_time": total_time / total_tests
        }

    except Exception as e:
        print(f"\nAn error occurred during testing: {e}")

# ---------------------------------------------------------
# BENCHMARK MULTIPLE MODELS
# ---------------------------------------------------------

MODEL_LIST = [
    #"/home/admin/.models/Phi-3-mini-4k-instruct-q4.gguf",
    #"/home/admin/.models/Qwen3-1.7B-Q8_0.gguf",
    #"/home/admin/.models/Qwen3-1.7B-Q4_K_M.gguf",
    "/home/admin/.models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
    "/home/admin/.models/Qwen3-4B-Instruct-2507-Q8_0.gguf",
    "/home/admin/.models/Qwen3-4B-Thinking-2507-Q4_K_M.gguf",
    "/home/admin/.models/Qwen3-4B-Thinking-2507-Q8_0.gguf",
]

def benchmark_models(model_paths):
    results = []

    for model_path in model_paths:
        print("\n" + "="*80)
        print(f"### BENCHMARKING MODEL: {os.path.basename(model_path)}")
        print("="*80)

        stats = test_full_mission(model_path)

        results.append({
            "model": os.path.basename(model_path),
            **stats
        })

    # --- SUMMARY TABLE ---
    print("\n\n==================== BENCHMARK SUMMARY ====================")
    print(f"{'Model':40} {'Success':10} {'Avg Time (s)':15} {'Total Time (s)':15}")
    print("-"*90)

    for r in results:
        print(f"{r['model']:40} "
              f"{r['success_rate']*100:6.1f}%     "
              f"{r['avg_time']:13.2f}     "
              f"{r['total_time']:13.2f}")

    print("============================================================\n")


if __name__ == "__main__":
    benchmark_models(MODEL_LIST)