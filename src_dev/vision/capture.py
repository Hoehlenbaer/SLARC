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
    """
    Configures the camera with fixed settings to prevent
    auto-exposure flickering during stereo capture.
    """
    cam = Picamera2(index)
    config = cam.create_video_configuration(
        main={"size": (WIDTH, HEIGHT), "format": "YUV420"},
        controls={
            "FrameDurationLimits": (int(1e9 / FPS), int(1e9 / FPS)), # Lock frame rate
            "ExposureTime": 8000,        # 8 ms exposure (in µs)
            "AnalogueGain": 1.0,         # Fixed gain
            
            # --- FIXES TO ELIMINATE FLICKERING ---
            "AeEnable": False,           # Disable Auto Exposure
            "ExposureValue": 0.0,        # No brightness offset
            "Brightness": 0.0,           # No brightness correction
            "ExposureTimeMode": 1,       # Manual mode
            "AnalogueGainMode": 1,       # Manual mode
            # --- END FIXES ---
        }
    )
    cam.configure(config)
    return cam

def capture_worker(index, shm_name, ts_shm_name, barrier, semaphore):
    """
    Worker process that captures frames, synchronizes with the partner camera,
    and writes to shared memory.
    """
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
        # Direct numpy view into shared memory
        buf = np.ndarray((HEIGHT, WIDTH), dtype=np.uint8, buffer=shm.buf)

        ts_shm = shared_memory.SharedMemory(name=ts_shm_name)
        # Timestamp array [ts_cam0, ts_cam1]
        ts_array = np.ndarray((2,), dtype=np.int64, buffer=ts_shm.buf)
    except Exception as e:
        print(f"[vision: cam{index}] SHM Attachment Error: {e}")
        return

    # 3. STARTUP SYNCHRONIZATION (Replaces ready_flags)
    # Both processes pause here until BOTH have reached this line.
    print(f"[vision: cam{index}] Waiting for partner camera...")
    try:
        barrier.wait()
    except BrokenBarrierError:
        print(f"[vision: cam{index}] Partner failed to start. Exiting.")
        return
    
    print(f"[vision: cam{index}] Sync complete. Starting capture loop...")
    cam.start()

    try:
        # We use an explicit loop (capture_requests) instead of callbacks
        # to safely handle the barrier blocking without stalling libcamera threads.
        for request in cam.capture_requests():
            
            # --- A. Data Extraction ---
            ts = request.get_metadata().get("SensorTimestamp", time.time_ns())
            
            # Handle stride (padding) which differs from logical width
            stream_config = cam.stream_configuration("main")
            stride = stream_config["stride"]
            h = stream_config["size"][1]

            # Get buffer and extract Y-plane (Grayscale)
            frame = request.make_buffer("main")
            y_plane = np.frombuffer(frame, dtype=np.uint8, count=stride * h).reshape((h, stride))
            
            # --- B. Write to Shared Memory ---
            # Crop to actual width (removes stride padding)
            buf[:] = y_plane[:, :WIDTH]
            ts_array[index] = ts
            
            # IMPORTANT: Release request back to driver *before* waiting.
            # This allows the hardware to start capturing the next frame immediately.
            request.release()

            # --- C. FRAME SYNCHRONIZATION ---
            try:
                # Wait for the other camera to finish writing its frame
                barrier.wait()
                
                # Once both are done, signal post-processing (Only Cam 0 does this)
                if index == 0:
                    semaphore.release()
                    
            except BrokenBarrierError:
                print(f"[vision: cam{index}] Barrier broken (shutdown?). Exiting loop.")
                break

    except KeyboardInterrupt:
        print(f"[vision: cam{index}] Interrupted.")
    except Exception as e:
        print(f"[vision: cam{index}] Error in loop: {e}")
    finally:
        # Cleanup
        cam.stop()
        shm.close()
        ts_shm.close()
        print(f"[vision: cam{index}] Capture stopped.")

def start_capture_process(index, shm_name, ts_shm_name, barrier, semaphore):
    """
    Launcher for the capture worker.
    """
    return Process(
        target=capture_worker, 
        args=(index, shm_name, ts_shm_name, barrier, semaphore)
    )