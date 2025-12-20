from llama_cpp import Llama
import os
import time 

# --- Configuration ---
MODEL_PATH = r"/home/admin/.models/Qwen3-1.7B-Q8_0.gguf" 

# --- Goal-Oriented System Instructions ---
SYSTEM_PROMPT = """
You are a Robot Logic Controller.
Goal: Place [object]

--- BACKWARD LOGIC CHAIN ---
To "Place", you must first have "Arrived Home".
To "Arrived Home", you must first have "Grabbed [object]".
To "Grabbed [object]", you must first have "Arrived [object]".
To "Arrived [object]", you must first have "Found [object]".
To "Found [object]", you must first have "Explored".

--- TASK ---
Start at the Goal (Place). Work backwards through the chain. 
The FIRST requirement you find that is FALSE is the command you must issue.

--- COMMAND MAPPING ---
- If not Explored -> "explore"
- If not Found -> "find [object]"
- If not Arrived [object] -> "move [object]"
- If not Grabbed -> "grab [object]"
- If not Arrived Home -> "move home"
- If all above TRUE -> "place [object]"

FORMAT:
<THINKING>
Goal: Place cup.
Constraint Check:
- Can I place? No, because [Blocker].
- Can I move home? No, because [Blocker].
...
Conclusion: I must first [Action].
</THINKING>
<COMMAND>
[Action]
</COMMAND>
"""
# Updated for the simplified 6-step flow
# Name, Explored, Found, Arrived_Obj, Grabbed, Arrived_Home, Placed, Expected
TEST_CASES = [
    # (Name, Explored, Found, Arrived_Obj, Grabbed, Arrived_Home, Placed, Expected)
    ("Start", 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', "explore"),
    ("Dropped mid-move", 'TRUE', 'TRUE', 'TRUE', 'FALSE', 'FALSE', 'FALSE', "grab [object]"),
    ("Pushed away", 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'FALSE', 'FALSE', "move home")
]
def generate_user_input(explored, found, arrived_obj, grabbed, arrived_home, placed):
    return f"""
Current Status:
- Explored: {explored}
- Found [object]: {found}
- Arrived [object]: {arrived_obj}
- Grabbed [object]: {grabbed}
- Arrived Home: {arrived_home}
- Placed [object]: {placed}
"""
# ... [The rest of the test_full_mission logic remains the same as your working V11/V12]

def extract_command(full_text):
    """Robustly extracts and cleans the command from the LLM output."""
    if "<COMMAND>" in full_text and "</COMMAND>" in full_text:
        start = full_text.find("<COMMAND>") + len("<COMMAND>")
        end = full_text.find("</COMMAND>")
        cmd = full_text[start:end].strip().lower()
        
        # Mapping to standardize the output
        if "explore" in cmd: return "explore"
        if "find" in cmd: return "find cup"
        if "navigate" in cmd: return "navigate to cup"
        if "align" in cmd: return "align with cup"
        if "grab" in cmd: return "grab cup"
        if "plan" in cmd: return "plan path"
        if "move home" in cmd or "arrive" in cmd: return "move home"
        if "place" in cmd: return "place cup"
        
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
            n_threads=4,
            chat_format="chatml" 
        )
        print("Model loaded successfully.\n")

        total_tests = len(TEST_CASES)
        passed_tests = 0

        # The list now has 8 items: 
        # (Name, Explored, Found, Arrived_Obj, Grabbed, Arrived_Home, Placed, Expected)

        for i, (name, explored, found, arrived_obj, grabbed, arrived_home, placed, expected) in enumerate(TEST_CASES):
            # Update the input generator call to match the new arguments
            user_input = generate_user_input(explored, found, arrived_obj, grabbed, arrived_home, placed)
            
            start_time = time.perf_counter()
            print(f"--- Running Test {i+1}/{total_tests}: {name} ---")

            stream = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_input}
                ],
                max_tokens=2048,
                temperature=0.0,
                stream=True
            )

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
                print(f"✅ PASS: Result matches expected '{expected}'. ({elapsed_time:.2f}s)")
                passed_tests += 1  # <--- THE MISSING LINE!
            else:
                print(f"❌ FAIL: Got '{extracted_command}', expected '{expected}'.")
            
            print("=" * 50 + "\n")

        print(f"--- Final Results ---")
        print(f"Tests Run: {total_tests}")
        print(f"Tests Passed: {passed_tests}")
        print(f"Success Rate: {passed_tests/total_tests:.2f}")

    except Exception as e:
        print(f"\nAn error occurred during testing: {e}")

if __name__ == "__main__":
    test_full_mission(MODEL_PATH)