import os
import time
import json
from llama_cpp import Llama
from typing import List, Dict, Any, Optional

# --- Global Configuration ---
# ⚠️ UPDATE YOUR MODEL PATHS HERE
MODEL_PATHS: List[str] = [
    # Qwen 2.5 1.5B (The fast leader - Q4_K_M is your baseline)
    "/home/admin/.models/qwen2.5-1.5b-instruct-q4_k_m.gguf",
    #"/home/admin/.models/qwen2.5-1.5b-instruct-q3_k_m.gguf",
    #"/home/admin/.models/qwen2.5-1.5b-instruct-q5_k_m.gguf",
    "/home/admin/.models/llama-3.2-1b-instruct-q8_0.gguf",
    "/home/admin/.models/llama-3.2-1b-instruct-q4_k_m.gguf",
    # Other Models
    "/home/admin/.models/llama-3.2-3b-instruct-q4_k_m.gguf",
    #"/home/admin/.models/Phi-3-mini-4k-instruct-q4.gguf",
    #"/home/admin/.models/gemma-2b.Q4_K_M.gguf", 
    #"/home/admin/.models/mistral-7b-instruct-v0.2.Q4_K_M.gguf",
]
CONTEXT_SIZE = 4096
N_THREADS = 4
# Temperature for deterministic logic (T=0.1 avoids T=0 sampling failure)
REASONING_TEMP = 0.1 
# IMPORTANT FIX: Removed '}' from stop tokens, as it was causing incomplete JSON output.
LLAMA_STOP_TOKENS = ["<|eot_id|>", "<|end_of_turn|>", "</s>", "[/INST]", "<|im_end|>"] 
# Characters that often precede JSON output which we will strip
JSON_PREFIXES = ["```json", "```", "{"]

# --- JSON Schema Definitions for Prompting Only (Grammar Not Used) ---
# NOTE: These are only for instructions; the JSON forcing feature is DISABLED.

TEST_2_SCHEMA: Dict[str, Any] = {
    "final_apples": "integer",
    "final_oranges": "integer",
    "final_bananas": "integer",
    "total_fruits": "integer",
    "arithmetic_success": "boolean" 
}

TEST_3_SCHEMA: Dict[str, Any] = {
    "command": "string [forward, left, right, stop, grab]",
    "value": "number [distance in meters or angle in degrees]", 
    "confidence": "number [0.0 - 1.0]"
}

# Instruction template for Test 3 to guide the model on value calculation
PROMPT_3_INSTRUCTION = (
    "TASK: Analyze the SENSOR DATA. Determine the single most appropriate command (forward, left, right, stop, grab). "
    "If the command is 'forward', calculate the distance to approach (Target Depth minus 0.5m grab buffer). "
    "If 'left' or 'right' is commanded, estimate the angle in degrees (0-30). "
    "If 'grab' is commanded, use the target's exact depth (meters) as the 'value'. "
    "If 'stop' is commanded, the 'value' must be 0.0. "
    "Your output MUST be ONLY a single JSON object. Do not include any text outside the JSON."
)

# --- Test 3 Scenario Data with Expected Value (Used for internal validation) ---
TEST_3_SCENARIOS_WITH_VALUE: List[tuple[str, str, str, float]] = [
    # (scenario_name, sensor_data_prompt, expected_command, expected_value)
    (
        "Stop_HazardousBlockage",
        """SENSOR DATA:
{
 "primary_instruction": "Navigate the workspace to the charging station.",
 "objects": [
  {"class": "hazardous_blockage", "position_xy": [490, 500], "depth_m": 0.35, "priority": 10}
 ],
 "segmentation_focus": {"class": "workspace_floor", "area_pct": 75}
}""",
        "stop",
        0.0 
    ),
    (
        "Right_TargetOffCenter",
        """SENSOR DATA:
{
 "primary_instruction": "Navigate the workspace to the charging station.",
 "objects": [
  {"class": "charging_plug", "position_xy": [750, 480], "depth_m": 2.50, "priority": 8}
 ],
 "segmentation_focus": {"class": "open_aisle", "area_pct": 85}
}""",
        "right",
        15.0 
    ),
    (
        "Left_ObstacleAvoidance",
        """SENSOR DATA:
{
 "primary_instruction": "Navigate the workspace to the charging station.",
 "objects": [
  {"class": "empty_pallet", "position_xy": [700, 800], "depth_m": 1.10, "priority": 5},
  {"class": "charging_plug", "position_xy": [300, 480], "depth_m": 4.00, "priority": 8}
 ],
 "segmentation_focus": {"class": "clear_passage", "area_pct": 60}
}""",
        "left",
        10.0 
    ),
    (
        "Forward_TargetApproach",
        """SENSOR DATA:
{
 "primary_instruction": "Navigate the workspace to the charging station.",
 "objects": [
  {"class": "charging_plug", "position_xy": [480, 510], "depth_m": 1.20, "priority": 8}
 ],
 "segmentation_focus": {"class": "charging_station_base", "area_pct": 90}
}""",
        "forward",
        0.7 # 1.2m depth - 0.5m grab buffer
    ),
    (
        "Grab_TargetReady",
        """SENSOR DATA:
{
 "primary_instruction": "Navigate the workspace to the charging station.",
 "objects": [
  {"class": "charging_plug", "position_xy": [505, 500], "depth_m": 0.40, "priority": 9}
 ],
 "segmentation_focus": {"class": "charging_port", "area_pct": 30}
}""",
        "grab",
        0.4 # Target depth
    ),
]


class LLMTester:
    """A class to manage configuration, testing, and result summarization for multiple GGUF models."""

    def __init__(self, model_paths: List[str], n_ctx: int, n_threads: int):
        self.model_paths = model_paths
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.results_summary: List[Dict[str, Any]] = []

    def _calculate_metrics(self, start_time: float, end_time: float, prompt_tokens: int, completion_tokens: int, test_name: str) -> Dict[str, float]:
        """Calculates and prints performance metrics."""
        gen_duration = end_time - start_time
        
        if completion_tokens > 0 and gen_duration > 0.001:
            tokens_per_second = completion_tokens / gen_duration
        else:
            tokens_per_second = 0

        print(f"\n✨ {test_name} Performance Stats:")
        print("-" * 35)
        print(f"  - Prompt Tokens: {prompt_tokens}")
        print(f"  - Completion Tokens: {completion_tokens}")
        print(f"  - Total Time: {gen_duration:.3f} seconds")
        print(f"  - **Tokens/Second (Speed): {tokens_per_second:.2f} t/s**")
        print("-" * 35)
        
        return {"tps": tokens_per_second, "completion_tokens": completion_tokens}

    def _run_single_test(self, llm: Llama, prompt: str, max_tokens: int, temperature: float, test_name: str, 
                         echo: bool = False, model_name: str = "") -> Dict[str, Any]:
        """Executes a single model call."""
        
        start_gen_time = time.time()
        
        output = llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            echo=echo,
            stop=LLAMA_STOP_TOKENS,
        )
        end_gen_time = time.time()
        
        completion_text = output["choices"][0]["text"]
        
        prompt_tokens = len(llm.tokenize(prompt.encode('utf-8')))
        completion_tokens = output["usage"]["completion_tokens"]
        
        metrics = self._calculate_metrics(
            start_gen_time, end_gen_time, prompt_tokens, completion_tokens, test_name
        )
        
        return {
            "text": completion_text,
            "metrics": metrics,
        }
    
    def _robust_json_parse(self, completion_text: str) -> Dict[str, Any]:
        """
        Attempts to find and parse a valid JSON block, stripping surrounding text/markdown.
        """
        clean_text = completion_text.strip()
        
        # 1. Clean common markdown prefixes
        for prefix in JSON_PREFIXES:
            if clean_text.startswith(prefix):
                clean_text = clean_text[len(prefix):].strip()

        # 2. Find the start and end delimiters
        start = clean_text.find('{')
        end = clean_text.rfind('}')
        
        if start != -1 and end != -1 and end > start:
             json_block = clean_text[start:end+1]
             
             # Clean up potential newlines or spaces before parsing
             return json.loads(json_block.strip())
        else:
             # Handle cases where the model starts with a brace but doesn't finish, or vice-versa
             raise json.JSONDecodeError("JSON block delimiters not found or malformed.", clean_text, 0)


    def _run_test_1_simple(self, llm: Llama, model_name: str, current_results: Dict[str, Any]):
        """Runs the Simple Completion (Baseline) test."""
        print("\n=== 🧪 TEST 1: Simple Completion (Baseline) ===")
        prompt_1 = "Write a short, four-line poem about a robot on Mars."
        
        result_1 = self._run_single_test(llm, prompt_1, 64, 0.7, "Test 1", echo=True, model_name=model_name)
        
        print("\n" + "="*50)
        print(f"PROMPT & RESPONSE:\n{result_1['text']}")
        print("="*50)
        current_results["Test 1 TPS"] = result_1["metrics"]["tps"]


    def _run_test_2_arithmetic(self, llm: Llama, model_name: str, current_results: Dict[str, Any]):
        """Runs the Arithmetic Reasoning test with JSON output based on prompt instructions."""
        print("\n=== 🧪 TEST 2: Arithmetic Reasoning (Prompt-Based JSON Output) ===")

        # Construct the instruction template from the simplified schema
        schema_str = json.dumps(TEST_2_SCHEMA).replace('"', '').replace('{', '').replace('}', '').replace(',', ', ')
        
        prompt_2 = (
            "### Instruction:\n"
            "I have a basket containing 5 apples, 3 oranges, and 2 bananas. I give away 2 apples and 1 orange. "
            "I then receive 3 new bananas. Calculate the final count of each fruit and the total number of fruits. "
            "Your output MUST be ONLY a single JSON object. Do not include any text outside the JSON.\n"
            f"SCHEMA: {{{schema_str}}}\n"
            "### JSON Response:\n"
        )
        
        result_2 = self._run_single_test(llm, prompt_2, 300, REASONING_TEMP, "Test 2", echo=False, model_name=model_name)
        completion_text_2 = result_2["text"]
        
        parsed_data = None
        arithmetic_success = "FAILED"
        
        try:
            parsed_data = self._robust_json_parse(completion_text_2)
            
            # Validation check: Total should be 10 
            if parsed_data.get('total_fruits') == 10:
                arithmetic_success = "PASSED"
            
        except json.JSONDecodeError as e:
            arithmetic_success = "JSON_ERROR"
            print(f"❌ JSON PARSING FAILED: {e}")
        
        # Output printing
        print("\n" + "="*50)
        print(f"MODEL RESPONSE (Raw):\n{completion_text_2}")
        print("="*50)
        print(f"💡 Validation Result: {arithmetic_success}")

        current_results["Test 2 TPS"] = result_2["metrics"]["tps"]
        current_results["Arithmetic Success"] = arithmetic_success
        current_results["Test 2 Tokens"] = result_2["metrics"]["completion_tokens"]


    def _run_test_3_robotics(self, llm: Llama, model_name: str, current_results: Dict[str, Any]):
        """Runs the Robotic Direction Reasoning test with prompt-based JSON output and value validation."""
        print("\n=== 🧪 TEST 3: Robotic Direction Reasoning (Prompt-Based JSON + Value) ===")
        
        total_tps = []
        success_count = 0
        total_tokens = 0
        
        # Use a small tolerance for floating point comparison (m or deg)
        VALUE_TOLERANCE = 0.5 
        
        # Construct the instruction template from the simplified schema
        schema_str = json.dumps(TEST_3_SCHEMA).replace('"', '').replace('{', '').replace('}', '').replace(',', ', ')
        
        # Iterating over scenarios
        for i, (scenario_name, sensor_data_prompt, expected_command, expected_value) in enumerate(TEST_3_SCENARIOS_WITH_VALUE):
            
            prompt_3 = (
                f"{sensor_data_prompt}\n"
                f"{PROMPT_3_INSTRUCTION}\n" # Use the new instruction template
                f"SCHEMA: {{{schema_str}}}\n"
                f"### JSON Response:\n"
            )
            
            expected_command_upper = expected_command.upper()
            
            print(f"\n--- Scenario {i+1}: {scenario_name} (Expected: '{expected_command_upper}', Value: {expected_value:.1f}±{VALUE_TOLERANCE}) ---")
            
            # Keep max tokens low (e.g., 50) to force the model to stop right after the JSON
            result = self._run_single_test(llm, prompt_3, 50, REASONING_TEMP, f"Test 3.{i+1}", echo=False, model_name=model_name)
            completion_text = result["text"]
            
            command_output = "N/A"
            value_output = None
            is_successful = False
            
            try:
                parsed_data = self._robust_json_parse(completion_text)
                
                command_output = parsed_data.get('command', 'N/A').strip().lower()
                value_output = parsed_data.get('value', None)
                
                # 1. Check Command Match
                command_match = command_output == expected_command.lower()
                
                # 2. Check Value Match
                value_match = False
                if value_output is not None:
                    value_match = abs(value_output - expected_value) <= VALUE_TOLERANCE
                
                # Final Success: Must match command AND value (special case for stop command)
                if expected_command == "stop":
                     # Stop must match command AND have value close to 0
                     is_successful = command_match and (value_output is not None and abs(value_output - 0.0) < 0.01)
                else:
                     # All other commands must match command AND value
                     is_successful = command_match and value_match

            except json.JSONDecodeError as e:
                command_output = "JSON_ERROR"
                print(f"❌ JSON PARSING FAILED: {e}")
            
            # --- Reporting ---
            if is_successful:
                print(f"✅ Result: PASSED. Command: {command_output.upper()}, Value: {value_output:.2f}")
                success_count += 1
            else:
                status_msg = f"Command: {command_output.upper()}"
                if value_output is not None:
                     status_msg += f", Value: {value_output:.2f}"
                print(f"❌ Result: FAILED. {status_msg} (Expected: {expected_command_upper}, Value: {expected_value:.1f})")
                print(f"Raw Output: {completion_text.strip()}")

            total_tps.append(result["metrics"]["tps"])
            total_tokens += result["metrics"]["completion_tokens"]
        
        avg_tps = sum(total_tps) / len(total_tps) if total_tps else 0
        success_rate = f"{success_count}/{len(TEST_3_SCENARIOS_WITH_VALUE)}"

        print("\n" + "="*50)
        print(f"--- TEST 3 SUMMARY ---")
        print(f"  Success Rate: {success_rate}")
        print(f"  Average TPS: {avg_tps:.2f} t/s")
        print("="*50)
        
        current_results["Test 3 Success"] = success_rate
        current_results["Test 3 Avg. TPS"] = avg_tps
        current_results["Test 3 Tokens"] = total_tokens

    def run_test_suite(self, llm: Llama, model_path: str):
        """Runs all three test cases for the loaded model and collects results."""
        
        model_name = os.path.basename(model_path)
        current_results: Dict[str, Any] = {"Model": model_name}

        print(f"\n\n\n=======================================================")
        print(f"       TESTING MODEL: {model_name}")
        print(f"       Threads: {self.n_threads} | Context: {self.n_ctx}")
        print(f"=======================================================\n")
        
        self._run_test_1_simple(llm, model_name, current_results)
        self._run_test_2_arithmetic(llm, model_name, current_results)
        self._run_test_3_robotics(llm, model_name, current_results)
        
        self.results_summary.append(current_results)
        
    def print_comparison_table(self):
        """Generates and prints the final Markdown comparison table."""
        if not self.results_summary:
            print("\n\nNo test results to summarize.")
            return

        print("\n" + "#"*70)
        print("## 📊 Cross-Model Performance & Reasoning Comparison (RPi 5)")
        print("#"*70)

        # Updated headers for all three tests
        headers = ["Model", "Arithmetic Success", "Robotics Success", "Avg. TPS (Test 3)"]
        table_lines = [
            "| " + " | ".join(headers) + " |",
            "| :--- | :---: | :---: | :---: |"
        ]

        # Sort results by the most relevant metric for your robotics use case: Robotics TPS
        sorted_results = sorted(self.results_summary, key=lambda x: x.get("Test 3 Avg. TPS", 0), reverse=True)

        for result in sorted_results:
            model_display_name = os.path.basename(result["Model"]).split('.gguf')[0]
            
            # Truncate model name and append quantization
            if "qwen" in model_display_name and "instruct" in model_display_name:
                parts = model_display_name.split('-')
                quant = parts[-1].upper()
                model_display_name = f"Qwen 1.5B ({quant})"
            else:
                model_display_name = model_display_name.replace("-instruct", "").split('-q')[0].replace(".Q", " (Q")
                
            arithmetic_status = result.get("Arithmetic Success", "N/A")
            if arithmetic_status == "JSON_ERROR":
                 arithmetic_status = "JSON FAILED"

            row = [
                model_display_name,
                arithmetic_status,
                result.get("Test 3 Success", "N/A"),
                f'{result.get("Test 3 Avg. TPS", 0.0):.2f}',
            ]
            table_lines.append("| " + " | ".join(row) + " |")

        print("\n".join(table_lines))
        print("\n*Note: Tests 2 and 3 now use robust, prompt-based JSON parsing (OpenAI style) to bypass `llama-cpp-python` limitations.*")
        
    def run_all_tests(self):
        """Iterates through all models, loads them, runs tests, and prints the summary."""
        print(f"--- ⚙️ System Configuration ---")
        print(f"  Threads (OpenMP/BLAS): {self.n_threads} | Context Size: {self.n_ctx}")
        print(f"  Total Models to Test: {len(self.model_paths)}\n")

        for model_path in self.model_paths:
            if not os.path.exists(model_path):
                print(f"🛑 Skipping model: {model_path}")
                print("   File not found. Please verify the path.")
                continue

            llm = None
            try:
                start_load_time = time.time()
                llm = Llama(
                    model_path=model_path,
                    n_ctx=self.n_ctx,
                    n_threads=self.n_threads,
                    verbose=False
                )
                load_duration = time.time() - start_load_time
                print(f"✅ Loaded {os.path.basename(model_path)} in {load_duration:.2f} seconds.")
                
                self.run_test_suite(llm, model_path)

            except Exception as e:
                print(f"🛑 Failed to process model {model_path}: {e}")
                print("   Skipping to the next model.")

            finally:
                if llm:
                    del llm
                time.sleep(1) 

        self.print_comparison_table()
        print("\n\n🎉 ALL MODEL TESTS AND SUMMARY COMPLETED.")


if __name__ == "__main__":
    tester = LLMTester(
        model_paths=MODEL_PATHS,
        n_ctx=CONTEXT_SIZE,
        n_threads=N_THREADS
    )
    tester.run_all_tests()