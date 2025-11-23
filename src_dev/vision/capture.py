# capture.py
# version 2.0

from picamera2 import Picamera2
import numpy as np
import time
import cv2
from multiprocessing import Process, shared_memory
from multiprocessing.synchronize import Barrier, Semaphore
from threading import BrokenBarrierError
import signal

# Image and capture settings
WIDTH, HEIGHT = 1440, 1080
BYTES_PER_FRAME = WIDTH * HEIGHT
FPS = 50

def setup_camera(index):
    cam = Picamera2(index)
    config = cam.create_video_configuration(
        main={"size": (WIDTH, HEIGHT), "format": "YUV420"},
        controls={
            "FrameDurationLimits": (int(1e9 / FPS), int(1e9 / FPS)),
            "ExposureTime": 8000,
            "AnalogueGain": 15.0,
            "AeEnable": False,
            "ExposureValue": 0.0,
            "Brightness": 0.0,
            "ExposureTimeMode": 1,
            "AnalogueGainMode": 1,
        }
    )
    cam.configure(config)
    return cam

def capture_worker(index, shm_name, ts_shm_name, barrier, semaphore):
    # 1. Initialize Hardware
    try:
        cam = setup_camera(index)
        print(f"[vision: cam{index}] Hardware initialized.")
    except Exception as e:
        print(f"[vision: cam{index}] Failed to init camera: {e}")
        return

    # 2. Attach to Shared Memory
    try:
        shm = shared_memory.SharedMemory(name=shm_name)
        buf = np.ndarray((HEIGHT, WIDTH), dtype=np.uint8, buffer=shm.buf)
        ts_shm = shared_memory.SharedMemory(name=ts_shm_name)
        ts_array = np.ndarray((2,), dtype=np.int64, buffer=ts_shm.buf)
    except Exception as e:
        print(f"[vision: cam{index}] SHM Attachment Error: {e}")
        return

    # 3. Define the Sync Callback
    # This runs on the camera's background thread for every frame
    def handle_request(request):
        try:
            # --- A. Data Extraction ---
            ts = request.get_metadata().get("SensorTimestamp", time.time_ns())
            
            stream_config = cam.stream_configuration("main")
            stride = stream_config["stride"]
            h = stream_config["size"][1]

            # Get buffer and extract Y-plane
            frame = request.make_buffer("main")
            y_plane = np.frombuffer(frame, dtype=np.uint8, count=stride * h).reshape((h, stride))
            
            # --- B. Write to Shared Memory ---
            buf[:] = y_plane[:, :WIDTH]
            ts_array[index] = ts
            
            # Note: We do NOT explicitly call request.release() here. 
            # Picamera2 handles cleanup when this function returns.

            # --- C. SYNC BARRIER ---
            # Wait for the other camera to reach this point.
            # Timeout=0.1s ensures we don't hang the camera driver if the other cam dies.
            try:
                barrier.wait(timeout=0.1)
                
                # Only Cam 0 signals the post-processor
                if index == 0:
                    semaphore.release()
                    
            except BrokenBarrierError:
                pass # Main loop will handle cleanup
            except Exception as e:
                # Timeout or other sync error - just continue to keep driver alive
                pass

        except Exception as e:
            print(f"[vision: cam{index}] Callback Error: {e}")

    # Register the callback
    cam.post_callback = handle_request

    # 4. STARTUP SYNC
    print(f"[vision: cam{index}] Waiting for partner camera...")
    try:
        barrier.wait()
    except BrokenBarrierError:
        print(f"[vision: cam{index}] Partner failed to start. Exiting.")
        return
    
    print(f"[vision: cam{index}] Sync complete. Starting capture...")
    cam.start()

    # 5. Keep Process Alive
    # Since the work happens in the background thread (handle_request),
    # this main thread just needs to sleep and handle shutdowns.
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print(f"[vision: cam{index}] Interrupted.")
    finally:
        cam.stop()
        shm.close()
        ts_shm.close()
        print(f"[vision: cam{index}] Capture stopped.")

def start_capture_process(index, shm_name, ts_shm_name, barrier, semaphore):
    return Process(
        target=capture_worker, 
        args=(index, shm_name, ts_shm_name, barrier, semaphore)
    )