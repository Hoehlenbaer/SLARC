from llama_cpp import Llama
import os
import time 

# --- Configuration ---
MODEL_PATH = r"C:\daten\models\Qwen3-1.7B-Q8_0.gguf" 

# --- Goal-Oriented System Instructions ---
SYSTEM_PROMPT = """
You are a Causal Logic Engine for a robot.

--- THE CAUSAL CHAIN ---
1. [Ready] -> allows -> [Explore]
2. [Explored] -> allows -> [Find]
3. [Found] -> allows -> [Navigate]
4. [Navigated] -> allows -> [Align]
5. [Aligned] -> allows -> [Grab]
6. [Grabbed] -> allows -> [Plan Home]
7. [Planned] -> allows -> [Move Home]
8. [Arrived Home] + [Grabbed] -> allows -> [Place]

--- MISSION ---
Goal: [cup] must be [Placed].

--- TASK ---
1. Analyze the status from bottom to top.
2. Find the FIRST 'FALSE' in the Causal Chain.
3. The command is the ACTION that turns that FALSE into TRUE.

FORMAT:
<THINKING>
Chain Analysis:
- Step 1 [Ready]: Status...
- Step 2 [Explored]: Status...
Conclusion: The chain breaks at [Step].
</THINKING>
<COMMAND>
[Action]
</COMMAND>
"""

# --- Test Cases ---
# We can now test "out of order" or "broken" dependencies.
# Structure: (Name, Ready, Explored, Found, Navigated, Aligned, Grabbed, Planned, Arrived, Placed, Expected)
TEST_CASES = [
    # Normal start
    ("Start from scratch", 'TRUE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', "explore"),
    
    # Complex case: The robot has the cup, but suddenly "Arrived Home" becomes FALSE (it got pushed away)
    # Even though it already "Planned" the path, it must "move home" again.
    ("Recovery: Pushed away from home", 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'FALSE', 'FALSE', "move home"),

    # Complex case: Robot is at the cup but "Aligned" became FALSE (cup moved)
    # It should "align with cup" even if it previously thought it was aligned.
    ("Recovery: Cup nudged", 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', "align with cup"),

    # Name, Ready, Explored, Found, Nav, Align, Grab, Plan, Arrived, Placed
("Recovery: Dropped cup (Realistic)", 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'FALSE', 'FALSE', 'TRUE', 'TRUE', 'FALSE', "align with cup")
]

def generate_user_input(ready, explored, found, nav, align, grab, plan, arrived, placed):
    return f"""
Current Mission: Bring the [cup] home and go idle.

STATUS:
- Robot Ready: {ready}
- Area Explored: {explored}
- Object [cup] Found: {found}
- Navigated to [cup]: {nav}
- Aligned with [cup]: {align}
- [cup] Grabbed: {grab}
- Path Home Planned: {plan}
- Arrived Home: {arrived}
- [cup] Placed: {placed}
"""

# ... [The rest of the test_full_mission logic remains the same as your working V11/V12]

def extract_command(full_text):
    """Robustly extracts the command from the LLM output."""
    if "<COMMAND>" in full_text and "</COMMAND>" in full_text:
        start = full_text.find("<COMMAND>") + len("<COMMAND>")
        end = full_text.find("</COMMAND>")
        return full_text[start:end].strip()
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
            n_threads=2,
            chat_format="chatml" 
        )
        print("Model loaded successfully.\n")

        total_tests = len(TEST_CASES)
        passed_tests = 0

        for i, (name, ready, explored, found, nav, align, grab, plan, arrived, placed, expected) in enumerate(TEST_CASES):
            user_input = generate_user_input(ready, explored, found, nav, align, grab, plan, arrived, placed)
            
            start_time = time.perf_counter()
            print(f"--- Running Test {i+1}/{total_tests}: {name} ---")

            stream = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_input}
                ],
                max_tokens=2048,
                temperature=0.1,
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