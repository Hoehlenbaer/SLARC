import time
import re
import os
from llama_cpp import Llama

# ANSI Colors
COLOR_THINK = "\033[90m" 
COLOR_CMD = "\033[92m"
COLOR_RESET = "\033[0m"
COLOR_STATS = "\033[94m"


# --- Global State Definition ---
# This ensures the model always sees a complete picture of the robot
DEFAULT_STATE = {
    "Environment_Mapped": False,
    "Target_Visible": False,
    "Object_In_Gripper": False,
    "Distance_cm": 0,
    "Robot_At_Home": False,
    "Mission_Complete": False,
    "find_retries": 0
}

SYSTEM_PROMPT = """
You are a Robot Reasoning Engine. Solve the current state gap to reach 'Mission_Complete'.
Be extremely concise. Identify the first false requirement and issue the command.

### HIERARCHY:
1. explore      -> Environment_Mapped 
2. find cup     -> Target_Visible
3. move cup     -> In_Grasping_Range (Target_Visible=T AND Distance < 25cm)
4. grab cup     -> Object_In_Gripper (In_Grasping_Range=T)
5. move home    -> Robot_At_Home     (Object_In_Gripper=T)
6. place cup    -> Mission_Complete  (Robot_At_Home=T)

### REASONING RULES:
- If 'Object_In_Gripper' is False, check Distance: < 25cm = grab, >= 25cm = move.
- If 'Target_Visible' is False : command 'find cup'.
- If 'find cup' fails 3 times: command 'explore'.


FORMAT:
<think>Short reasoning</think>
<COMMAND>action</COMMAND>
"""

TEST_CASES = [
    ("Warm up", 
     {}, # Last
     {"Environment_Mapped": False, "find_retries": 4}, # Current
     "explore"),
    
    ("Start Mission", 
     {}, # Last
     {"Environment_Mapped": False, "find_retries": 4}, # Current
     "explore"),
    
    ("Map Done -> Find", 
     {"Environment_Mapped": False}, 
     {"Environment_Mapped": True, "Target_Visible": False}, 
     "find cup"),

    ("Target Found -> Move", 
     {"Target_Visible": False}, 
     {"Environment_Mapped": True, "Target_Visible": True, "Distance_cm": 150}, 
     "move cup"),

    ("In Range -> Grab", 
     {"Distance_cm": 150}, 
     {"Environment_Mapped": True, "Target_Visible": True, "Distance_cm": 15}, 
     "grab cup"),

    ("Grabbed -> Go Home", 
     {"Object_In_Gripper": False}, 
     {"Environment_Mapped": True, "Target_Visible": True, "Distance_cm": 15, "Object_In_Gripper": True, "Robot_At_Home": False}, 
     "move home"),

    ("At Home -> Place", 
     {"Robot_At_Home": False}, 
     {"Environment_Mapped": True, "Target_Visible": True, "Distance_cm": 15, "Object_In_Gripper": True, "Robot_At_Home": True, "Mission_Complete": False}, 
     "place cup"),

    ("Mid-Air Drop (Still Visible)", 
     {"Object_In_Gripper": True}, 
     {"Environment_Mapped": True, "Target_Visible": True, "Object_In_Gripper": False, "Distance_cm": 10}, 
     "grab cup"),

     ("Mid-Air Drop and moved away (Still Visible)", 
     {"Object_In_Gripper": True}, 
     {"Environment_Mapped": True, "Target_Visible": True, "Object_In_Gripper": False, "Distance_cm": 50}, 
     "move cup"),

    ("Catastrophic Drop (Lost)", 
     {"Environment_Mapped": True, "Object_In_Gripper": True}, 
     {"Environment_Mapped": True, "Object_In_Gripper": False, "Target_Visible": False}, 
     "find cup"),

    ("Repeated Find Failure", 
     {"Environment_Mapped": True, "Target_Visible": False, "find_retries": 3}, 
     {"Environment_Mapped": True, "Target_Visible": False, "find_retries": 4}, 
     "explore"),
]

def get_full_state(partial_state):
    """Merges partial test data with the full global state vector."""
    full = DEFAULT_STATE.copy()
    full.update(partial_state)
    return full

def stream_and_capture(llm, messages):
    full_text = ""
    start_time = time.time()
    token_count = 0
    
    print("\n--- LIVE THINKING PROCESS ---")
    stream = llm.create_chat_completion(messages=messages, max_tokens=128, temperature=0.0, stream=True)

    for chunk in stream:
        if 'content' in chunk['choices'][0]['delta']:
            token = chunk['choices'][0]['delta']['content']
            full_text += token
            token_count += 1
            
            if "<think>" in token: print(COLOR_THINK, end="")
            if "</think>" in token: print(COLOR_RESET, end="")
            if "<COMMAND>" in token: print(COLOR_CMD, end="")
            
            print(token, end="", flush=True)
            
            if "</COMMAND>" in token: print(COLOR_RESET, end="")
            
    end_time = time.time()
    duration = end_time - start_time
    tps = token_count / duration if duration > 0 else 0
    
    print(f"\n{COLOR_STATS}[STATS: {duration:.2f}s | {token_count} tokens | {tps:.2f} t/s]{COLOR_RESET}")
    return full_text, duration

def run_benchmark(model_path):
    print(f"Initializing model: {os.path.basename(model_path)}...")
    #llm = Llama(model_path=model_path, n_ctx=2048, n_threads=4, verbose=False)
    llm = Llama(
        model_path=model_path,
        n_ctx=512,
        n_threads=2,        # stabiler als 4 auf dem RPi5
        n_batch=128,        # verhindert Thread-Explosion
        use_mlock=True,     # wenn genug RAM frei ist
        verbose=False
        )
    #llm = Llama(model_path=model_path, n_ctx=2048,  n_gpu_layers=-1, verbose=False)

    results = []
    
    for name, last_part, current_part, expected in TEST_CASES:
        print(f"\n{'='*60}\nTEST: {name}")
        
        # GROUNDING: Ensure the model sees ALL states every time
        last = get_full_state(last_part)
        current = get_full_state(current_part)
        
        #input_data = "FULL ROBOT STATUS (PREVIOUS -> CURRENT):\n"
        #for k in DEFAULT_STATE.keys():
        #    input_data += f"- {k}: {last[k]} -> {current[k]}\n"
        input_data = "FULL ROBOT STATUS:\n"
        for k in DEFAULT_STATE.keys():
            input_data += f"- {k}: {current[k]}\n"
  
        full_output, duration = stream_and_capture(llm, [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": input_data}
        ])
        
        cmd_match = re.search(r"<COMMAND>(.*?)</COMMAND>", full_output, re.DOTALL | re.IGNORECASE)
        cmd = cmd_match.group(1).strip().lower() if cmd_match else "none"
        
        success = cmd == expected.lower()
        results.append((name, duration, success))
        print(f"RESULT: {'✅ Success' if success else '❌ Fail (Want: '+expected.lower()+' Got: ' + cmd + ')'}")

    # Final Summary Table
    print(f"\n\n{'#'*20} BENCHMARK SUMMARY {'#'*20}")
    print(f"{'Test Case':<50} | {'Time':<16} | {'Status'}")
    print("-" * 50)
    for name, dur, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{name:<50} | {dur:>6.2f}s | {status}")

# --- Configuration ---
MODEL_PATH = "/home/admin/.models/Qwen3-4B-Instruct-2507-Q8_0.gguf"

if __name__ == "__main__":
    # Ensure this path is correct for your RPi5 setup
    run_benchmark(MODEL_PATH)

