from llama_cpp import Llama
import os
import sys
import time 

# --- Configuration ---
MODEL_PATH = r"/home/admin/.models/Qwen3-0.6B-Q8_0.gguf" 

# --- System Instructions (The "Logic") ---
SYSTEM_PROMPT = """
You are a robot mission planner. Your sole task is to determine the next immediate action based on the checklist below and output the result in the required format.

--- LOGIC CHECKLIST (The ONLY acceptable commands are on the right) ---
Scan the status of the robot from top to bottom. The first state that is FALSE dictates the next action.

1. Robot Ready?           [FALSE] -> COMMAND: "wait"
2. Area Explored?         [FALSE] -> COMMAND: "explore"
3. Found [object]         [FALSE] -> COMMAND: "Find [object]"
4. Navigated to [object]? [FALSE] -> COMMAND: "Navigate to [object]"
5. Aligned with [object]? [FALSE] -> COMMAND: "align with [object]"
6. Grabbed [object]?      [FALSE] -> COMMAND: "grab [object]"
7. Path Home Planned?     [FALSE] -> COMMAND: "plan home"
8. Arrived Home?          [FALSE] -> COMMAND: "move home"
9. Placed [object]?       [FALSE] -> COMMAND: "Place [object]"
10. All Tasks Done?       [FALSE] -> COMMAND: "go idle"

INSTRUCTIONS:
1. Review the User's CURRENT STATUS line by line.
2. Identify the FIRST state that is [FALSE].
3. Output the required action, substituting [object] with the actual item name (cup).
4. **STRICT RULE:** The command in the <COMMAND> block MUST be one of the exact COMMAND values from the checklist (e.g., "explore", "Place [object]", "move home"), with [object] replaced. 
   DO NOT add extra words like 'back' or 'the'.
5. Use this exact format:
   <THINKING>
   [Your Step-by-Step Analysis, stopping at the first FALSE]
   </THINKING>
   <COMMAND>
   [The single command]
   </COMMAND>
"""

# --- Dynamic Test Inputs and Expected Outputs ---
# Ready is always TRUE for simplicity.

TEST_CASES = [
    # (Name, Ready, Explored, Found, Navigated, Aligned, Grabbed, Planned, Arrived, Placed, Expected Command)
    # New Test: Exploration
    ("Start Exploring", 'TRUE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', "explore"),
    # New Test: Find
    ("Start Finding", 'TRUE', 'TRUE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', "Find cup"),
    # Remaining Tests
    ("Start Navigating", 'TRUE', 'TRUE', 'TRUE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', "Navigate to cup"),
    ("Start Alignment", 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', "align with cup"),
    ("Start Grabbing", 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'FALSE', 'FALSE', 'FALSE', 'FALSE', "grab cup"),
    ("Start Planning Home", 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'FALSE', 'FALSE', 'FALSE', "plan home"),
    ("Start Moving Home", 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'FALSE', 'FALSE', "move home"),
    ("Start Placing", 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'FALSE', "Place cup"),
    ("Go Idle", 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE', "go idle"),
]

def generate_user_input(ready, explored, found, nav_status, align_status, grab_status, plan_status, arrived_status, placed_status):
    """Generates the mission status string for the LLM."""
    # Using generic [object] for consistency and avoiding the model's previous confusion.
    return f"""
Mission Goal: Find the object [cup] and bring it back.

CURRENT STATUS:
1. Robot Ready?           [{ready}]
2. Area Explored?         [{explored}]
3. Object [cup] Found?    [{found}]
4. Navigated to [cup]?    [{nav_status}]
5. Aligned with [cup]?    [{align_status}]
6. [cup] Grabbed?         [{grab_status}]
7. Path Home Planned?     [{plan_status}]
8. Arrived Home?          [{arrived_status}]
9. [cup] Placed?          [{placed_status}]
"""

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
            
            # --- START TIMER ---
            start_time = time.perf_counter()
            
            print(f"--- Running Test {i+1}/{total_tests}: {name} (Expected: '{expected}') ---")

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

            # --- END TIMER ---
            end_time = time.perf_counter()
            elapsed_time = end_time - start_time
            
            # Process result
            full_text = "".join(full_output_chunks)
            extracted_command = extract_command(full_text)
            
            # Clean for comparison (normalize case and remove brackets)
            clean_extracted = extracted_command.lower().replace("[cup]", "cup").strip() if extracted_command else None
            clean_expected = expected.lower().replace("[cup]", "cup").strip()

            if clean_extracted == clean_expected:
                print(f"✅ PASS: Extracted Command '{extracted_command}' matches expected '{expected}'. (Time: {elapsed_time:.3f}s)")
                passed_tests += 1
            else:
                print(f"❌ FAIL: Extracted Command '{extracted_command}' DOES NOT match expected '{expected}'. (Time: {elapsed_time:.3f}s)")
                # --- Debugging Output for Failed Test ---
                print("\n--- Model CoT (Debugging Failures) ---")
                print(full_text)
                print("--------------------------------------\n")
            
            print("--------------------------------------------------\n")

        print(f"--- Final Results ---")
        print(f"Tests Run: {total_tests}")
        print(f"Tests Passed: {passed_tests}")
        print(f"Success Rate: {passed_tests/total_tests:.2f}")

    except Exception as e:
        print(f"\nAn error occurred during testing: {e}")

if __name__ == "__main__":
    test_full_mission(MODEL_PATH)