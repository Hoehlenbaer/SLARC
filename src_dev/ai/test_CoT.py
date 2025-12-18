import os
import time
import re
from llama_cpp import Llama

# --- Globale Konfiguration ---
# !! BITTE ANPASSEN !!
MODEL_PATHS = [
    "/home/admin/.models/Qwen3-0.6B-Q4_K_M.gguf",
    "/home/admin/.models/Qwen3-0.6B-Q8_0.gguf",
    "/home/admin/.models/Qwen3-1.7B-Q4_K_M.gguf",
    "/home/admin/.models/Qwen3-1.7B-Q8_0.gguf",
]

# Benchmarking-Einstellungen
N_THREADS = 4        
MAX_TOKENS = 384     # ERHÖHT: Genug Platz für <think> Blöcke + Antwort
TEMPERATURE = 0.0    

# --- Prompt (Bleibt kurz, um Input-Verarbeitung zu beschleunigen) ---
OPTIMIZED_PROMPT = """
[SYSTEM]
Act as a Vehicle Navigation System. Choose: LEFT, CENTER, or RIGHT.

[RULES]
1. SAFETY: REJECT paths with objects < 5m.
2. EFFICIENCY: SELECT path with highest "Free Width".

[DATA]
- LEFT:   No objects < 5m. Free Width: 20%.
- CENTER: No objects < 5m. Free Width: 10%.
- RIGHT:  Object at 4.5m. (Status: UNSAFE).

[INSTRUCTION]
Briefly analyze Safety and Efficiency.
End response with: COMMAND: [DIRECTION]
"""

def extract_command(output: str) -> str:
    """Extrahiert das Kommando robust."""
    clean_output = output.replace('**', '').strip()
    match = re.search(r"COMMAND:\s*([A-Z]+)", clean_output, re.IGNORECASE)
    if match:
        command = match.group(1).strip().upper()
        if command in ["LEFT", "CENTER", "RIGHT"]:
            return command
    return "FEHLER"

def run_benchmark(model_path: str, prompt: str, n_threads: int, max_tokens: int) -> dict:
    model_name = os.path.basename(model_path)
    print(f"\n" + "="*60)
    print(f"🚀 STARTE BENCHMARK: {model_name}")
    print("="*60)
    
    if not os.path.exists(model_path):
        print(f"WARNUNG: Modellpfad nicht gefunden: {model_name}")
        return {"Model": model_name, "Status": "FEHLT"}

    try:
        # --- 1. LADEZEIT MESSEN ---
        start_load = time.perf_counter()
        llm = Llama(
            model_path=model_path,
            n_threads=n_threads,
            n_gpu_layers=0,
            n_ctx=1024,          
            verbose=False
        )
        end_load = time.perf_counter()
        load_time = end_load - start_load
        
        # --- 2. INFERENZZEIT MESSEN ---
        print("... Generiere Antwort ...")
        start_inference = time.perf_counter()
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": "Navigate safely. Be concise."}, 
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=TEMPERATURE,
            stream=False 
        )
        end_inference = time.perf_counter()
        inference_time = end_inference - start_inference

        # Output Verarbeitung
        full_output = response['choices'][0]['message']['content'].strip()
        final_command = extract_command(full_output)

        # Tokens
        completion_tokens = response['usage']['completion_tokens']
        speed_tps = completion_tokens / inference_time if inference_time > 0 else 0.0

        # Debug Output (gekürzt auf die letzten 200 Zeichen, falls sehr lang)
        debug_snippet = full_output if len(full_output) < 300 else "..." + full_output[-300:]
        print(f"\n--- TEIL-OUTPUT (LETZTE ZEILEN) ---")
        print(debug_snippet)
        print("-" * 30)

        print(f"⏱️  Ladezeit: {load_time:.2f}s | Antwortzeit: {inference_time:.2f}s")
        print(f"🤖 Kommando: {final_command}")

        return {
            "Model": model_name,
            "Speed (t/s)": speed_tps,
            "Load Time (s)": load_time,
            "Inference Time (s)": inference_time,
            "Result": final_command,
            "Tokens": completion_tokens
        }

    except Exception as e:
        print(f"❌ FEHLER: {e}")
        return {"Model": model_name, "Result": "FEHLER", "Load Time (s)": 0, "Inference Time (s)": 0}

def display_results(results: list):
    if not results: return
    
    # Sortiere nach Inferenzgeschwindigkeit (schnellste zuerst)
    results.sort(key=lambda x: x.get('Inference Time (s)', 999))

    print("\n\n" + "#" * 80)
    print("## 📊 BENCHMARK & TIMING STATISTIK (RPi 5)")
    print("#" * 80)

    # Spalten definieren
    headers = ["Modell", "Ladezeit (s)", "Antwortzeit (s)", "Frequenz (Hz)", "Speed (t/s)", "Erg.", "OK?"]
    table = "| " + " | ".join(headers) + " |\n"
    table += "| " + " | ".join(["---"] * len(headers)) + " |\n"

    for res in results:
        if res.get("Result") == "FEHLER" or res.get("Result") == "N/A":
            correctness = "❌"
            freq = 0.0
        else:
            correctness = "✅" if res.get('Result') == "LEFT" else "❌"
            # Frequenz: Wie oft könnte der Roboter pro Sekunde entscheiden? (1 / Antwortzeit)
            inf_time = res.get('Inference Time (s)', 1)
            freq = 1.0 / inf_time if inf_time > 0 else 0.0

        # Formatierung
        row = (
            f"| {res.get('Model', '?')} "
            f"| {res.get('Load Time (s)', 0):.2f} "
            f"| {res.get('Inference Time (s)', 0):.2f} "
            f"| **{freq:.2f} Hz** "
            f"| {res.get('Speed (t/s)', 0):.1f} "
            f"| {res.get('Result', '-')} "
            f"| {correctness} |\n"
        )
        table += row

    print(table)
    print("\nLEGENDE:")
    print("- **Ladezeit:** Einmaliger Aufwand beim Start des Skripts (Modell in RAM laden).")
    print("- **Antwortzeit:** Zeit vom Absenden des Prompts bis zur fertigen Entscheidung.")
    print("- **Frequenz (Hz):** Entscheidungen pro Sekunde (Theoretisches Maximum im Dauerbetrieb).")

if __name__ == "__main__":
    all_results = []
    for path in MODEL_PATHS:
        result = run_benchmark(path, OPTIMIZED_PROMPT, N_THREADS, MAX_TOKENS)
        all_results.append(result)
        time.sleep(1) 
    display_results(all_results)