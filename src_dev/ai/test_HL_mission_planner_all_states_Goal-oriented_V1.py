from llama_cpp import Llama
import os
import time 

# --- Configuration ---
MODEL_PATH = r"C:\daten\models\Qwen3-1.7B-Q8_0.gguf" 

# --- Goal-Oriented System Instructions ---
SYSTEM_PROMPT = """
You are a Robot Logic Controller. You must trace the mission status step-by-step.

--- ACTION HIERARCHY ---
1. Action: "explore" -> Condition: Area Explored is [FALSE].
2. Action: "Find [object]" -> Condition: Explored is [TRUE] and Found is [FALSE].
3. Action: "Navigate to [object]" -> Condition: Found is [TRUE] and Navigated is [FALSE].
4. Action: "align with [object]" -> Condition: Navigated is [TRUE] and Aligned is [FALSE].
5. Action: "grab [object]" -> Condition: Aligned is [TRUE] and Grabbed is [FALSE].
6. Action: "plan home" -> Condition: Grabbed is [TRUE] and Path Home Planned is [FALSE].
7. Action: "move home" -> Condition: Path Home Planned is [TRUE] and Arrived Home is [FALSE].
8. Action: "Place [object]" -> Condition: Arrived Home is [TRUE] and Placed is [FALSE].
9. Action: "go idle" -> Condition: Placed is [TRUE].

--- OUTPUT RULE ---
You MUST list every step in the <THINKING> block until you hit a FALSE condition. 
Example Thinking:
1. Ready? TRUE.
2. Explored? TRUE.
3. Found? FALSE. (Next action is Find)

FORMAT:
<THINKING>
[Your line-by-line status check here]
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
            n_threads=4,
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
                max_tokens=1024,
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