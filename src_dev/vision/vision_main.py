# vision_main.py
# version 2.2

import sys
import os
import signal
import time
from multiprocessing import shared_memory, Process, Barrier, Semaphore

# --- CONFIGURATION ---
RUN_HEADLESS = True # TOGGLE THIS: True for production, False for testing/debug

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
    shm_list = [] # List for cleanup

    # --- Shared Memory Setup (Input & Output) ---
    # (Unchanged setup logic, just organized)
    shm_names = [
        ("cam0_buffer", RAW_BYTES_PER_FRAME), 
        ("cam1_buffer", RAW_BYTES_PER_FRAME), 
        ("ts_buffer", 16),
        ("out_l_buffer", RGB_SIZE), 
        ("out_r_buffer", RGB_SIZE)
    ]
    
    shms = {}
    print("[vision] Allocating Shared Memory Buffers...")
    for name, size in shm_names:
        try:
            shm = shared_memory.SharedMemory(name=name, create=True, size=size)
        except FileExistsError:
            shm = shared_memory.SharedMemory(name=name)
        shms[name] = shm
        shm_list.append(shm)

    # --- Synchronization Primitives ---
    sync_barrier = Barrier(parties=2)
    frame_ready_sem = Semaphore(0)

    # --- Start Processes ---
    p0 = start_capture_process(0, shms["cam0_buffer"].name, shms["ts_buffer"].name, sync_barrier, frame_ready_sem)
    p1 = start_capture_process(1, shms["cam1_buffer"].name, shms["ts_buffer"].name, sync_barrier, frame_ready_sem)
    
    p0.start(); p1.start()
    print("[vision] Capture workers started.")

    # Post-Process Worker (NOW PASSING RUN_HEADLESS)
    pp = start_post_process(
        shms["cam0_buffer"].name, 
        shms["cam1_buffer"].name, 
        shms["ts_buffer"].name, 
        shms["out_l_buffer"].name, 
        shms["out_r_buffer"].name, 
        frame_ready_sem,
        headless=RUN_HEADLESS # <-- New Argument
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
        
        # Clean up Shared Memory
        try:
            for shm in shm_list:
                shm.close()
                shm.unlink()
        except FileNotFoundError:
            pass 
            
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    
    print("[vision] System running. Press Ctrl+C to stop.")
    signal.pause()

if __name__ == "__main__":
    main()