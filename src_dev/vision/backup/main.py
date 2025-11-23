# main.py

import sys
import os
import signal
import sys
from multiprocessing import shared_memory, Manager, Lock

# Dynamically resolve vision module path
VISION_DIR = os.path.join(os.path.dirname(__file__), "vision")
if VISION_DIR not in sys.path:
    sys.path.insert(0, VISION_DIR)

# Import capture and post_process modules
from capture import start_capture_process
#from capture_gstream import start_capture_process
# from post_process import start_post_process  # Uncomment when post_process.py is ready

# Constants
WIDTH, HEIGHT = 1440, 1080
BYTES_PER_FRAME = WIDTH * HEIGHT

def main():
    
    
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


    with Manager() as manager:
        ready_flags = manager.list([False, False])
        lock = Lock()

        p0 = start_capture_process(0, shm0.name, ts_shm.name, lock, ready_flags)
        p1 = start_capture_process(1, shm1.name, ts_shm.name, lock, ready_flags)
        p0.start()
        p1.start()
        print("[vision] Capture and post-process workers started.")
        # Example: Launch post-processing worker
        # pp = start_post_process(shm0.name, shm1.name, ts_shm.name, lock)
        # pp.start()

        def shutdown_handler(sig, frame):
            print("\n[vision] Shutting down...")
            for p in [p0, p1]:  # Add pp if used
                p.terminate()
                p.join()
            for shm in [shm0, shm1, ts_shm]:
                shm.close()
                shm.unlink()
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.pause()
    

if __name__ == "__main__":
    main()
