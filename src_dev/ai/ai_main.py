# ai/ai_main.py
# version 1.1 - AI Subsystem Launcher (POSIX enabled)

import sys
import os
from multiprocessing import shared_memory
import numpy as np
import posix_ipc # <-- NEW IMPORT

# Configuration constants (Needed for SHM access)
OUT_WIDTH, OUT_HEIGHT = 640, 480

# AI Worker entry point
def start_ai_subsystem(ai_ready_sem):
    """
    Entry point for the AI subsystem. Attaches to SHM and synchronizes via semaphore.

    Args:
        ai_ready_sem (posix_ipc.Semaphore): Signals from the Post-Processor (acquire).
    """
    print("[AI] AI Subsystem started. Waiting for rectified images...")
    
    # 1. ATTACH to Shared Memory Buffers
    try:
        shm_out_l = shared_memory.SharedMemory(name="out_l_buffer")
        shm_out_r = shared_memory.SharedMemory(name="out_r_buffer")
        
        # Create numpy arrays wrapping the shared memory
        left_img_array = np.ndarray((OUT_HEIGHT, OUT_WIDTH, 3), dtype=np.uint8, buffer=shm_out_l.buf)
        right_img_array = np.ndarray((OUT_HEIGHT, OUT_WIDTH, 3), dtype=np.uint8, buffer=shm_out_r.buf)
        
    except FileNotFoundError as e:
        print(f"[AI ERROR] Failed to attach to Shared Memory: {e.name}. Exiting.")
        sys.exit(1)
        
    try:
        while True:
            # 2. Synchronize (Wait for Post-Processor to signal frames are ready)
            ai_ready_sem.acquire() 
            
            # 3. PROCESS DATA
            print("[AI] New rectified stereo frame received. Starting inference...")
            
            # NOTE: Your complex AI/LLM logic goes here, operating directly on 
            # left_img_array and right_img_array.
            
            # Example: time simulation
            time.sleep(0.05) # Simulate a 50ms inference time

    except KeyboardInterrupt:
        pass
    finally:
        shm_out_l.close()
        shm_out_r.close()
        print("[AI] Subsystem shutting down.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("ERROR: Missing POSIX semaphore name. Usage: python ai_main.py <ai_sem_name>")
        sys.exit(1)
        
    ai_ready_sem_name = sys.argv[1]
    
    try:
        # ATTACH to the POSIX semaphore by name
        ai_ready_sem = posix_ipc.Semaphore(ai_ready_sem_name)
    except posix_ipc.ExistentialError:
        print("ERROR: Could not attach to POSIX semaphore. Ensure launch_all.py is running.")
        sys.exit(1)
        
    start_ai_subsystem(ai_ready_sem)