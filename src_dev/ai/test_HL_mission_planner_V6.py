from llama_cpp import Llama
import os
import sys

# --- Configuration ---
MODEL_PATH = r"/home/admin/.models/Qwen3-0.6B-Q4_K_M.gguf"

# --- System Instructions (The "Logic") ---
SYSTEM_PROMPT = """
You are a robot mission planner. Your sole task is to determine the next immediate action based on the checklist below and output the result in the required format.

--- LOGIC CHECKLIST ---
Scan the status of the robot from top to bottom. The first state that is FALSE dictates the next action.

1. Robot Ready?           [FALSE] -> COMMAND: "wait"
2. Area Explored?         [FALSE] -> COMMAND: "explore"
3. Object Found?          [FALSE] -> COMMAND: "Find [object]"
4. Navigated to target?   [FALSE] -> COMMAND: "Navigate to [object]"
5. Aligned with target?   [FALSE] -> COMMAND: "align with [object]"
6. Object Grabbed?        [FALSE] -> COMMAND: "grab [object]"
7. Path Home Planned?     [FALSE] -> COMMAND: "plan home"
8. Arrived Home?          [FALSE] -> COMMAND: "move home"
9. Object Placed?         [FALSE] -> COMMAND: "Place [object]"

INSTRUCTIONS:
1. Review the User's CURRENT STATUS line by line.
2. Identify the FIRST state that is [FALSE].
3. State the required action, substituting [object] with the actual item name (cup).
4. Do NOT discuss subsequent actions.
5. Use this exact format:
   <THINKING>
   [Your Step-by-Step Analysis, stopping at the first FALSE]
   </THINKING>
   <COMMAND>
   [The single command]
   </COMMAND>
"""

# --- User Input (The "Data") ---
USER_INPUT = """
Mission Goal: Find the object [cup] and bring it back.

CURRENT STATUS:
1. Robot Ready?           [TRUE]
2. Area Explored?         [TRUE]
3. Object [cup] Found?    [TRUE]
4. Navigated to [cup]?    [FALSE]
5. Aligned with [cup]?    [FALSE]
6. [cup] Grabbed?         [FALSE]
7. Path Home Planned?     [FALSE]
8. Arrived Home?          [FALSE]
9. [cup] Placed?          [FALSE]
"""

# --- Script ---
def evaluate_mission_plan_chat(model_path: str):
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
            chat_format="chatml" 
        )
        print("Model loaded successfully.\n")
        print("--- Robot Brain Thinking ---")

        # Increased max_tokens to 512 to ensure command block is completed
        stream = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_INPUT}
            ],
            max_tokens=512, # Increased from 256
            temperature=0.1,
            stream=True
        )

        full_output_chunks = []

        # Stream the content
        for chunk in stream:
            delta = chunk['choices'][0]['delta']
            if 'content' in delta:
                text_chunk = delta['content']
                full_output_chunks.append(text_chunk)
                print(text_chunk, end="", flush=True)

        print("\n--------------------------")

        # --- Extraction Logic ---
        full_text = "".join(full_output_chunks)
        
        if "<COMMAND>" in full_text and "</COMMAND>" in full_text:
            start = full_text.find("<COMMAND>") + len("<COMMAND>")
            end = full_text.find("</COMMAND>")
            # Extract and clean up the command
            command = full_text[start:end].strip() 
            print(f"\n✅ Extracted Command: **{command}**")
        else:
            print(f"\n⚠️ Extraction Warning: <COMMAND> tags not found or output cut short.")
            print("\nFull Raw Output for Debugging:\n" + full_text)

    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    evaluate_mission_plan_chat(MODEL_PATH)