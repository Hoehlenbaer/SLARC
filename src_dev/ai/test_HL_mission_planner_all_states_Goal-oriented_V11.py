# Goal oriented mission planner V1.0
# 
# 

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
You are a High‑Level Mission Planner for a robot. 
Your ONLY task is to determine the robot’s next action based on the mission phases, state transitions, and action mapping.

The robot operates as a finite‑state machine. 
You must ALWAYS determine the robot’s CURRENT PHASE first, then output the ACTION associated with that phase.

============================================================
### MISSION PHASE MODEL
The robot’s behavior is organized into ordered phases. 
Each phase represents a distinct stage of the mission.

1. Mapping Phase
2. Search Phase
3. Approach Phase
4. Manipulation Phase
5. Return Phase
6. Completion Phase

Phases are evaluated IN THIS ORDER. 
The FIRST phase whose conditions are satisfied becomes the active phase.

============================================================
### PHASE TRANSITIONS (State → Phase)

• Mapping Phase:
    - Environment_Mapped == False
    - OR find_retries > 3

• Search Phase:
    - Environment_Mapped == True
    - AND Target_Visible == False

• Approach Phase:
    - Target_Visible == True
    - AND Object_In_Gripper == False
    - AND Distance_cm >= 25

• Manipulation Phase:
    - Target_Visible == True
    - AND Object_In_Gripper == False
    - AND Distance_cm < 25

• Return Phase:
    - Object_In_Gripper == True
    - AND Robot_At_Home == False

• Completion Phase:
    - Object_In_Gripper == True
    - AND Robot_At_Home == True
    - AND Mission_Complete == False

============================================================
### ACTION MAPPING (Phase → Command)

• Mapping Phase → <COMMAND>explore</COMMAND>
• Search Phase → <COMMAND>find cup</COMMAND>
• Approach Phase → <COMMAND>move robot to cup</COMMAND>
• Manipulation Phase → <COMMAND>grab cup</COMMAND>
• Return Phase → <COMMAND>move robot home</COMMAND>
• Completion Phase → <COMMAND>place cup</COMMAND>

============================================================
### HARD RULES

- ALWAYS determine the CURRENT PHASE first.
- The FIRST matching phase in the list is the correct one.
- STOP after selecting the phase; do NOT evaluate lower phases.
- Output EXACTLY ONE command.
- Use ONLY the commands defined above.
- Reasoning must be under 3 sentences and enclosed in <think> tags.

============================================================
### EXAMPLE

User: Environment_Mapped: True, Target_Visible: True, Distance_cm: 50, Object_In_Gripper: False
<think>Target is visible, object not in gripper, distance >=25 → Approach Phase.</think>
<COMMAND>move robot to cup</COMMAND>

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
     "move robot to cup"),

    ("In Range -> Grab", 
     {"Distance_cm": 150}, 
     {"Environment_Mapped": True, "Target_Visible": True, "Distance_cm": 15}, 
     "grab cup"),

    ("Grabbed -> Go Home", 
     {"Object_In_Gripper": False}, 
     {"Environment_Mapped": True, "Target_Visible": True, "Distance_cm": 15, "Object_In_Gripper": True, "Robot_At_Home": False}, 
     "move robot home"),

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
     "move robot to cup"),

    ("Catastrophic Drop (Lost)", 
     {"Environment_Mapped": True, "Object_In_Gripper": True}, 
     {"Environment_Mapped": True, "Object_In_Gripper": False, "Target_Visible": False}, 
     "find cup"),

    ("Repeated Find Failure", 
     {"Environment_Mapped": True, "Target_Visible": False, "find_retries": 3}, 
     {"Environment_Mapped": False, "Target_Visible": False, "find_retries": 4}, 
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
    stream = llm.create_chat_completion(messages=messages, max_tokens=1024, temperature=0.0, stream=True)

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
    #llm = Llama(
    #    model_path=model_path,
    #    n_ctx=512,
    #    n_threads=2,        # stabiler als 4 auf dem RPi5
    #    n_batch=128,        # verhindert Thread-Explosion
    #    use_mlock=True,     # wenn genug RAM frei ist
    #    verbose=False
    #    )
    llm = Llama(model_path=model_path, n_ctx=2048,  n_gpu_layers=-1, verbose=False)

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
MODEL_PATH = "H:\SLARC_resources\models\DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf"

if __name__ == "__main__":
    # Ensure this path is correct for your RPi5 setup
    run_benchmark(MODEL_PATH)

