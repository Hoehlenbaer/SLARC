# main.py
# version 2.0
import sys
import os
import signal
import time
from multiprocessing import shared_memory, Process, Barrier, Semaphore

# Dynamically resolve vision module path
VISION_DIR = os.path.join(os.path.dirname(__file__), "vision")
if VISION_DIR not in sys.path:
    sys.path.insert(0, VISION_DIR)

# Import capture and post_process modules
from capture import start_capture_process
# from post_process import start_post_process  # Uncomment when ready

# Constants
WIDTH, HEIGHT = 1440, 1080
BYTES_PER_FRAME = WIDTH * HEIGHT

def main():
    # --- Shared Memory Setup ---
    try:
        shm0 = shared_memory.SharedMemory(name="cam0_buffer", create=True, size=BYTES_PER_FRAME)
    except FileExistsError:
        print("[vision] Shared memory 'cam0_buffer' already exists. Attaching...")
        shm0 = shared_memory.SharedMemory(name="cam0_buffer", create=False)

    try:
        shm1 = shared_memory.SharedMemory(name="cam1_buffer", create=True, size=BYTES_PER_FRAME)
    except FileExistsError:
        print("[vision] Shared memory 'cam1_buffer' already exists. Attaching...")
        shm1 = shared_memory.SharedMemory(name="cam1_buffer", create=False)

    try:
        ts_shm = shared_memory.SharedMemory(name="ts_buffer", create=True, size=16)
    except FileExistsError:
        print("[vision] Shared memory 'ts_buffer' already exists. Attaching...")
        ts_shm = shared_memory.SharedMemory(name="ts_buffer", create=False)

    # --- Synchronization Primitives ---
    
    # Barrier(2): Ensures Cam 0 and Cam 1 reach the "check-in" point together.
    # They will wait for each other before proceeding.
    sync_barrier = Barrier(parties=2)

    # Semaphore(0): Starts at 0. Post-process waits (acquires). 
    # Capture process releases (increments) it when a pair is ready.
    frame_ready_sem = Semaphore(0)

    # --- Start Processes ---
    
    # Note: We pass the barrier and semaphore to the capture processes
    p0 = start_capture_process(0, shm0.name, ts_shm.name, sync_barrier, frame_ready_sem)
    p1 = start_capture_process(1, shm1.name, ts_shm.name, sync_barrier, frame_ready_sem)
    
    p0.start()
    p1.start()
    
    print("[vision] Capture workers started.")

    # Example: Launch post-processing worker
    # pp = start_post_process(shm0.name, shm1.name, ts_shm.name, frame_ready_sem)
    # pp.start()

    def shutdown_handler(sig, frame):
        print("\n[vision] Shutting down...")
        
        # Terminate processes
        for p in [p0, p1]: # Add pp here later
            if p.is_alive():
                p.terminate()
                p.join()
        
        # Clean up Shared Memory
        # Note: On Linux/Pi, unlinking is crucial or SHM stays in RAM until reboot
        try:
            for shm in [shm0, shm1, ts_shm]:
                shm.close()
                shm.unlink()
        except FileNotFoundError:
            pass # Already cleaned up
            
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    
    # Keep main thread alive to handle signals
    print("[vision] System running. Press Ctrl+C to stop.")
    signal.pause()

if __name__ == "__main__":
    main()