from llama_cpp import Llama
import os
import sys

# --- Configuration ---
# NOTE: Update this path to your specific model file location.
MODEL_PATH = r"/home/admin/.models/Qwen3-1.7B-Q8_0.gguf"

# --- Prompt ---
# The prompt is updated with a complete example mission to teach the model the required format.
PROMPT = """
You are a robot's brain. You will be the mission planner responsible for achieving the mission goal. For that you need to analyze the mission goal and actions to select the next viable action based on the current state of the robot.

Robot states show, what the robot has achieved so far. Actions show, what the robot can do next based on the current state.:
0. Ready = TRUE
1. Area explored = FALSE
2. [object] found = FALSE
3. Navigated to [[object] = FALSE
4. Body aligned = FALSE
5. [object] grabbed = FALSE
6. Home planned = FALSE
7. Arrived home = FALSE
8. [object] placed = FALSE


Actions:
1. Explore area ONLY If <Ready = TRUE> -> command: "explore"
2.  Find [object] ONLY If <Area explored= TRUE>-> command: "Find [object]"
3. Navigate to [object] ONLY If <[object] found = TRUE> -> command: "Navigate to [object]"
4. Align body with [object] ONLYIf <Navigated to [[object] = TRUE> -> command: "align with [object]"
5. Grab [object] ONLY If <Body aligned = FALSE> -> command: "grab [object]"
6. Plan way home to starting point ONLY If <[object] grabbed = TRUE> -> command: "plan home"
7. Move home ONLY If <Home planned = TRUE> -> command: "move home"
8. Place [object] on ground ONLY If <Arrived home = TRUE> -> command: "Place [object]"
9. Go idle ONLY If <[object] placed = TRUE> -> Go idle -> command: "go idle"

--- EXAMPLE MISSION ---
Mission Goal: Locate the [dog]
Robot states:
0. Ready = TRUE
1. Area explored = TRUE
2. [object] found = FALSE
3. Navigated to [[object] = FALSE
4. Body aligned = FALSE
5. [object] grabbed = FALSE
6. Home planned = FALSE
7. Arrived home = FALSE
8. [object] placed = FALSE

OUTPUT: <THINKING>
1. Analyze States: Ready is TRUE, Area explored is TRUE.
2. Check Actions: Action 1 (Explore) is skipped because Area explored is TRUE. Action 2 (Locate [object]) requires Area explored = TRUE, which is met.
3. Conclusion: The next step is to locate the object.
</THINKING>
<COMMAND>
Locate [object]
</COMMAND>
--- END EXAMPLE ---

--- CURRENT MISSION ---

Mission goal: Find the object [cup] and bring it back to the starting point.

Robot states:
0. Ready = TRUE
1. Area explored = TRUE
2. [object] found = TRUE
3. Navigated to [object] = FALSE
4. Body aligned = FALSE
5. [object] grabbed = FALSE
6. Home planned = FALSE
7. Arrived home = FALSE
8. [object] placed = FALSE

Generate the full thinking process inside a <THINKING> block.
Replace [object] with the object name in the mission goal.
Analyze states and output ONLY the next viable action as a command inside a <COMMAND> block.



OUTPUT: <THINKING>
"""

# --- Script ---
def evaluate_mission_plan_streaming(model_path: str, prompt: str):
    """
    Loads an LLM, streams the completion, and uses </COMMAND> as the stop signal.
    """
    if not os.path.exists(model_path):
        print(f"Error: Model file not found at path: {model_path}")
        return

    print(f"Loading model from: {model_path}...")
    try:
        # Initialize the Llama model
        llm = Llama(
            model_path=model_path,
            n_ctx=4096,
            n_gpu_layers=-1,
            verbose=False
        )
        print("Model loaded successfully.")

        print("\n--- LLM Streaming Output ---")
        
        full_output_chunks = []
        
        # Use create_completion with stream=True
        # Set stop to ['</COMMAND>'] to cut off generation at the tag.
        stream = llm.create_completion(
            prompt,
            max_tokens=512,
            temperature=0.0,
            stop=['</COMMAND>'], # Stops precisely on the closing command tag
            stream=True
        )

        # Iterate over the stream and print chunks
        for chunk in stream:
            text_chunk = chunk['choices'][0]['text']
            full_output_chunks.append(text_chunk)
            
            # Print the text chunk immediately
            print(text_chunk, end="", flush=True)
            
        # Manually print the stop token to complete the displayed output.
        print("</COMMAND>", end="", flush=True)

        print("\n--------------------------")
        
        # --- Extraction Logic ---
        # 1. Join the streamed chunks and manually append the stop token for accurate parsing
        full_output = "".join(full_output_chunks) + "</COMMAND>"
        
        # 2. Find the content of the <COMMAND> block
        try:
            start_tag = "<COMMAND>"
            end_tag = "</COMMAND>"
            
            # Find the command text between the tags (using rfind in case of repetition)
            command_start = full_output.rfind(start_tag)
            command_end = full_output.rfind(end_tag)
            
            if command_start != -1 and command_end != -1 and command_end > command_start:
                # Extract the string content and clean up surrounding quotes/whitespace
                extracted_command = full_output[command_start + len(start_tag) : command_end].strip().strip('"')
            else:
                extracted_command = "Error: Command block not properly found."
            
            print(f"\n✅ Extracted Command: **{extracted_command}**")

        except Exception as e:
            print(f"\n⚠️ Could not parse command from output.")
            print(f"Extraction Error: {e}")

    except Exception as e:
        print(f"\nAn error occurred during model evaluation: {e}")
        print("Ensure llama-cpp-python is installed correctly and your GGUF model is compatible.")


if __name__ == "__main__":
    evaluate_mission_plan_streaming(MODEL_PATH, PROMPT)