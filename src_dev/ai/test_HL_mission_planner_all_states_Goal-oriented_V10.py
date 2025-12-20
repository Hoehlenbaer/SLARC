# version 19 - Reasoning & Distance-Aware Planner
from llama_cpp import Llama
import os
import sys
import re

# ANSI Colors
COLOR_THINK = "\033[90m" 
COLOR_CMD = "\033[92m"
COLOR_RESET = "\033[0m"


# System Prompt defining the "Neuro-Symbolic" logic
# Concise, Success-Oriented System Prompt
SYSTEM_PROMPT = """
You are a Robot Logic Controller. Your goal is 'Mission_Complete'.
Check the following requirements in order. The FIRST requirement that is FALSE is your current bottleneck.

### MISSION CHAIN (Action -> Requirement):
1. explore     -> Environment_Mapped
2. find cup    -> Target_Visible
3. move cup    -> In_Grasping_Range (Target_Visible is TRUE AND Distance < 25cm)
4. grab cup    -> Object_In_Gripper (In_Grasping_Range is TRUE)
5. move home   -> Robot_At_Home     (Object_In_Gripper is TRUE)
6. place cup   -> Mission_Complete  (Robot_At_Home is TRUE)

### RECOVERY PROTOCOL:
- If a drop occurs (Object_In_Gripper: T -> F), verify Target_Visible.
- If Target_Visible is False, you MUST 'find cup' before you can 'move' or 'grab'.

### OUTPUT:
<think>Briefly identify the first FALSE requirement in the chain.</think>
<COMMAND>action</COMMAND>
"""

TEST_CASES = [
    (
        "Smart Recovery (Close Drop)", 
        {"Object_In_Gripper": True, "Distance_cm": 0},  # LAST
        {"Object_In_Gripper": False, "Distance_cm": 12}, # CURRENT
        "grab cup"
    ),
    (
        "Smart Recovery (Far Drop)", 
        {"Object_In_Gripper": True, "Distance_cm": 0},  # LAST
        {"Object_In_Gripper": False, "Distance_cm": 85}, # CURRENT
        "move cup"
    ),
    (
        "Total Loss (Lost sight)", 
        {"Target_Visible": True, "Object_In_Gripper": True}, # LAST
        {"Target_Visible": False, "Object_In_Gripper": False}, # CURRENT
        "find cup"
    )
]

def generate_table(last, current):
    table = f"{'State':<25} | {'Last':<7} | {'Current':<7}\n"
    table += "-" * 45 + "\n"
    for k in current:
        l_val = "TRUE" if last.get(k) else "FALSE"
        c_val = "TRUE" if current.get(k) else "FALSE"
        table += f"{k:<25} | {l_val:<7} | {c_val:<7}\n"
    return table

def stream_and_capture(llm, messages):
    full_text = ""
    print("\n--- LIVE THINKING PROCESS ---")
    
    # Increase max_tokens to 800 for RPi5 to ensure it finishes the thought
    stream = llm.create_chat_completion(
        messages=messages,
        max_tokens=4096,
        temperature=0.0,
        stream=True
    )

    for chunk in stream:
        if 'content' in chunk['choices'][0]['delta']:
            token = chunk['choices'][0]['delta']['content']
            full_text += token
            
            # Formatting tags for visibility
            if "<think>" in token: sys.stdout.write(COLOR_THINK)
            if "</think>" in token: sys.stdout.write(COLOR_RESET)
            if "<COMMAND>" in token: sys.stdout.write(COLOR_CMD)
            
            sys.stdout.write(token)
            sys.stdout.flush()
            
            if "</COMMAND>" in token: sys.stdout.write(COLOR_RESET)
    return full_text

# ... [Include the rest of the benchmark runner logic]

def run_live_benchmark(model_path):
    print(f"Loading {os.path.basename(model_path)}...")
    llm = Llama(model_path=model_path, n_ctx=8192, n_gpu_layers=-1, verbose=False)
    
    for name, last, current, expected in TEST_CASES:
        print(f"\n[TEST: {name}]")
        
        # Combine the states into a clear "Delta" for the LLM to read
        user_input = "STATE TRANSITION:\n"
        for key in current:
            prev = last.get(key, "Unknown")
            now = current.get(key)
            user_input += f"- {key}: {prev} -> {now}\n"
            
        full_output = stream_and_capture(llm, [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ])
        
        # Validation
        cmd_match = re.search(r"<COMMAND>(.*?)</COMMAND>", full_output, re.DOTALL | re.IGNORECASE)
        cmd = cmd_match.group(1).strip().lower() if cmd_match else "none"
        
        if cmd == expected.lower():
            print(f"RESULT: ✅ Success")
        else:
            print(f"RESULT: ❌ Fail (Got: {cmd})")

# --- Configuration ---
MODEL_PATH = "H:\SLARC_resources\models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf"

if __name__ == "__main__":
    run_live_benchmark(MODEL_PATH)