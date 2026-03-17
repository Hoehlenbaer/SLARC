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
    "Target_Found": False,
    "Distance_cm": 0,
    "Object_In_Gripper": False,
    "Robot_At_Home": False,
    "Mission_Complete": False,
    "find_retries": 0
}

SYSTEM_PROMPT = """
You are a High‑Level Mission Planner for a robot.
This is a SEQUENTIAL finite‑state mission.
Each phase represents a milestone.
Phases are evaluated IN ORDER.


Your task:
1. Read the robot state EXACTLY as provided.
2. For each phase, decide if it is DONE or NOT DONE.
3. Select the FIRST phase that is NOT DONE.
4. Output ONLY the command for that phase.
5. Output the command inside <COMMAND>...</COMMAND>.
6. Output NOTHING after </COMMAND>.

You may output a <think> section before the command.
The <think> section is ignored.
Only the final <COMMAND>...</COMMAND> is graded.

------------------------------------------------------------
PHASE DEFINITIONS (EXTENSIBLE)

PHASE 1 — Mapping Phase
DONE if:
- Environment_Mapped == True
AND find_retries <= 3
Command if NOT DONE:
<COMMAND>explore</COMMAND>

PHASE 2 — Search Phase
DONE if:
- Target_Found == True
Command if NOT DONE:
<COMMAND>find cup</COMMAND>

PHASE 3 — Approach Phase
DONE if:
- Distance_cm < 25
Command if NOT DONE:
<COMMAND>move robot to cup</COMMAND>

PHASE 4 — Manipulation Phase
DONE if:
- Object_In_Gripper == True
Command if NOT DONE:
<COMMAND>grab cup</COMMAND>

PHASE 5 — Return Phase
DONE if:
- Robot_At_Home == True
AND Object_In_Gripper == True
Command if NOT DONE:
<COMMAND>move robot home</COMMAND>

PHASE 6 — Completion Phase
DONE if:
- Mission_Complete == True
Command if NOT DONE:
<COMMAND>place cup</COMMAND>

------------------------------------------------------------
ALLOWED OUTPUTS (EXACT)

<COMMAND>explore</COMMAND>
<COMMAND>find cup</COMMAND>
<COMMAND>move robot to cup</COMMAND>
<COMMAND>grab cup</COMMAND>
<COMMAND>move robot home</COMMAND>
<COMMAND>place cup</COMMAND>

------------------------------------------------------------
HARD RULES

• Evaluate phases IN ORDER.
• Select the FIRST phase that is NOT DONE.
• NEVER output phase names.
• NEVER invent commands.
• Output EXACTLY ONE <COMMAND>.


STATE-ONLY RULE (MANDATORY)
• Use ONLY the provided robot state to decide DONE/NOT DONE.
• NEVER assume a phase is not done because an action was not “executed yet”.
• NEVER invent history. Treat the state snapshot as ground truth.


------------------------------------------------------------
FINAL RESPONSE FORMAT

<COMMAND>...</COMMAND>

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
     {"Environment_Mapped": True, "Target_Found": False}, 
     "find cup"),

    ("Target Found -> Move", 
     {"Target_Found": False}, 
     {"Environment_Mapped": True, "Target_Found": True, "Distance_cm": 150}, 
     "move robot to cup"),

    ("In Range -> Grab", 
     {"Distance_cm": 150}, 
     {"Environment_Mapped": True, "Target_Found": True, "Distance_cm": 15}, 
     "grab cup"),

    ("Grabbed -> Go Home", 
     {"Object_In_Gripper": False}, 
     {"Environment_Mapped": True, "Target_Found": True, "Distance_cm": 15, "Object_In_Gripper": True, "Robot_At_Home": False}, 
     "move robot home"),

    ("At Home -> Place", 
     {"Robot_At_Home": False}, 
     {"Environment_Mapped": True, "Target_Found": True, "Distance_cm": 15, "Object_In_Gripper": True, "Robot_At_Home": True, "Mission_Complete": False}, 
     "place cup"),

    ("Mid-Air Drop (Still Visible)", 
     {"Object_In_Gripper": True}, 
     {"Environment_Mapped": True, "Target_Found": True, "Object_In_Gripper": False, "Distance_cm": 10}, 
     "grab cup"),

     ("Mid-Air Drop and moved away (Still Visible)", 
     {"Object_In_Gripper": True}, 
     {"Environment_Mapped": True, "Target_Found": True, "Object_In_Gripper": False, "Distance_cm": 50}, 
     "move robot to cup"),

    ("Catastrophic Drop (Lost)", 
     {"Environment_Mapped": True, "Object_In_Gripper": True}, 
     {"Environment_Mapped": True, "Object_In_Gripper": False, "Target_Visible": False}, 
     "find cup"),

    ("Repeated Find Failure", 
     {"Environment_Mapped": True, "Target_Found": False, "find_retries": 3}, 
     {"Environment_Mapped": False, "Target_Found": False, "find_retries": 4}, 
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
    #print(messages)
    print("\n--- LIVE THINKING PROCESS ---")
    stream = llm.create_chat_completion(messages=messages, max_tokens=2048, temperature=0.0, stream=True)

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

def strip_thinking_prefix(text: str) -> str:
    end_tag = "</think>"
    idx = text.lower().rfind(end_tag)
    if idx != -1:
        return text[idx + len(end_tag):]
    return text


def extract_command(text: str) -> str:
    matches = re.findall(
        r"<COMMAND>(.*?)</COMMAND>",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )
    return matches[-1].strip().lower() if matches else "none"


def run_benchmark(model_path):
    print(f"Initializing model: {os.path.basename(model_path)}...")
    #llm = Llama(model_path=model_path, n_ctx=2048, n_threads=4, verbose=False)
    #llm = Llama(
    #    model_path=model_path,
    #    n_ctx=1024,
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
        
        clean_output = strip_thinking_prefix(full_output)
        cmd = extract_command(clean_output)


        
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
MODEL_PATH = "H:\SLARC_resources\models\DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf"


if __name__ == "__main__":
    # Ensure this path is correct for your RPi5 setup
    run_benchmark(MODEL_PATH)

