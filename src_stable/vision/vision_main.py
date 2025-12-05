# vision_main.py
# version 2.4 (Fixing TypeError: Semaphore.__init__ missing 'ctx')

import sys
import os
import signal
import time
# WICHTIG: Importiere get_context
from multiprocessing import shared_memory, Process, get_context
# Importiere die Typen für die lokale Verwendung, wenn nötig
from multiprocessing.synchronize import Semaphore, Barrier 
import posix_ipc 

# --- CONFIGURATION ---
RUN_HEADLESS = False 

# Input (Camera Raw)
IN_WIDTH, IN_HEIGHT = 1440, 1080
RAW_BYTES_PER_FRAME = IN_WIDTH * IN_HEIGHT

# Output (AI/Post-Process)
OUT_WIDTH, OUT_HEIGHT = 640, 480
RGB_SIZE = OUT_WIDTH * OUT_HEIGHT * 3

# Dynamically resolve vision module path
VISION_DIR = os.path.join(os.path.dirname(__file__), "vision")
if VISION_DIR not in sys.path:
    sys.path.insert(0, VISION_DIR)

# Import capture and post_process modules
from vision_capture import start_capture_process
from vision_processor import start_post_process  

def main():
    # --- 0. Multiprocessing Context Setup ---
    # NEU: Expliziter Kontext ist in Python 3.11+ notwendig.
    try:
        # 'spawn' ist auf den meisten Systemen der sicherste Kontext
        mp_ctx = get_context("spawn")
    except ValueError:
        # Fallback, falls 'spawn' nicht unterstützt wird
        mp_ctx = get_context()

    # --- 1. Argument Handling for POSIX Semaphores ---
    if len(sys.argv) < 3:
        print("[vision ERROR] Missing semaphore names. Usage: python vision_main.py <frame_ready_sem_name> <ai_ready_sem_name>")
        sys.exit(1)
        
    FRAME_READY_SEM_NAME = sys.argv[1]
    AI_READY_SEM_NAME = sys.argv[2]
    
    shm_list = [] 
    
    # --- 2. Shared Memory Setup (Attach) ---
    shm_names = [
        ("cam0_buffer", RAW_BYTES_PER_FRAME), 
        ("cam1_buffer", RAW_BYTES_PER_FRAME), 
        ("ts_buffer", 16),
        ("out_l_buffer", RGB_SIZE), 
        ("out_r_buffer", RGB_SIZE)
    ]
    
    shms = {}
    print("[vision] Attaching to Shared Memory Buffers (created by launcher)...")
    for name, size in shm_names:
        try:
            shm = shared_memory.SharedMemory(name=name) 
        except (FileNotFoundError, Exception):
            print(f"[vision ERROR] SHM '{name}' not found. Did launch_all.py run first?")
            sys.exit(1)
             
        shms[name] = shm
        shm_list.append(shm)

    # --- 3. Synchronization Primitives (Barrier & Python Semaphore Connect) ---
    # KORREKTUR: Erstellung von Barrier und Semaphore MUSS über den Kontext erfolgen.
    sync_barrier = mp_ctx.Barrier(parties=2) 
    frame_ready_sem = mp_ctx.Semaphore(0)
    
    # --- 4. Start Processes ---
    # Die start_capture_process Funktion erwartet standardmäßige multiprocessing-Objekte.
    p0 = start_capture_process(0, shms["cam0_buffer"].name, shms["ts_buffer"].name, sync_barrier, frame_ready_sem)
    p1 = start_capture_process(1, shms["cam1_buffer"].name, shms["ts_buffer"].name, sync_barrier, frame_ready_sem)
    
    p0.start(); p1.start()
    print("[vision] Capture workers started.")

    # Post-Process Worker
    pp = start_post_process(
        shms["cam0_buffer"].name, 
        shms["cam1_buffer"].name, 
        shms["ts_buffer"].name, 
        shms["out_l_buffer"].name, 
        shms["out_r_buffer"].name, 
        frame_ready_sem,
        AI_READY_SEM_NAME,
        headless=RUN_HEADLESS
    )
    pp.start()
    print(f"[vision] Post process worker started (Headless={RUN_HEADLESS}).")


    def shutdown_handler(sig, frame):
        print("\n[vision] Shutting down...")
        
        # Terminate processes
        for p in [p0, p1, pp]:
            if p.is_alive():
                p.terminate()
                p.join()
        
        # Clean up Shared Memory (Only close, launch_all.py unlinks)
        try:
            for shm in shm_list:
                shm.close()
        except Exception: 
            pass 
            
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    
    print("[vision] System running. Press Ctrl+C to stop.")
    signal.pause()

if __name__ == "__main__":
    main()