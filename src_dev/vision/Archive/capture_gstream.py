# capture.py (Modified GStreamer Version)

from picamera2 import Picamera2 # No longer strictly needed for capture, but keeping for reference
import numpy as np
import time
import cv2
from multiprocessing import Process, shared_memory, Lock, Array
import signal
import sys
import os

# --- Image and capture settings (MUST match GStreamer pipeline and shared memory) ---
WIDTH, HEIGHT = 1440, 1080
# YUV420 format has 1.5 bytes per pixel (1440 * 1080 * 1.5 = 2332800)
# We will use the Y-plane only (Monochrome) as requested in the original code's buffer setup (1440*1080)
BYTES_PER_FRAME = WIDTH * HEIGHT
FPS = 50

# GStreamer pipeline configuration for the Raspberry Pi Camera Module 3
# The "v4l2src" element is used to capture video from the camera module.
# The 'format=I420' ensures a standard YUV420 output.
# The 'appsink' element is used to pull the frames into Python.
def build_gstreamer_pipeline(index):
    # Using libcamera's V4L2 interface through /dev/video*
    # Since we are using the Y-plane (Monochrome), we only need 1 byte per pixel.
    # The pipeline will output the full frame (YUV420), but cv2.VideoCapture will handle
    # the format negotiation, and we will extract the Y-plane from the resulting buffer.
    
    # We use 'v4l2src' which provides the video device (e.g., /dev/video0)
    # The 'index' corresponds to the video device number.
    # capsfilter sets the specific format, size, and framerate.
    pipeline = (
        f"v4l2src device=/dev/video{index} ! "
        f"video/x-raw, width={WIDTH}, height={HEIGHT}, framerate={FPS}/1 ! "
        f"videoconvert ! " # Ensure compatibility
        f"appsink drop=1 max-buffers=1 buffer-time=100000000" # drop frames if slow, keep one buffer
    )
    return pipeline

def capture_worker(index, shm_name, ts_shm_name, lock, ready_flags):
    # --- Shared Memory Setup ---
    # The original code used the Y-plane only (np.uint8 array of size WxH). 
    # We maintain this structure for compatibility.
    try:
        shm = shared_memory.SharedMemory(name=shm_name)
        # Buffer for the Y-plane (Monochrome)
        buf = np.ndarray((HEIGHT, WIDTH), dtype=np.uint8, buffer=shm.buf)

        ts_shm = shared_memory.SharedMemory(name=ts_shm_name)
        # Buffer for timestamps
        ts_array = np.ndarray((2,), dtype=np.int64, buffer=ts_shm.buf)
    except Exception as e:
        print(f"[vision: cam{index}] Shared Memory Error: {e}")
        sys.exit(1)

    # --- GStreamer/OpenCV Setup ---
    pipeline = build_gstreamer_pipeline(index)
    
    # Use cv2.CAP_GSTREAMER to tell OpenCV to use the GStreamer pipeline
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

    if not cap.isOpened():
        print(f"[vision: cam{index}] ERROR: GStreamer pipeline failed to open or camera device /dev/video{index} not found.")
        sys.exit(1)
        
    # --- Synchronization and Main Loop ---
    print(f"[vision: cam{index}] GStreamer setup complete for /dev/video{index}.")
    ready_flags[index] = True

    # Wait for all processes to be ready
    while not all(ready_flags):
        time.sleep(0.000001)

    print(f"[vision: cam{index}] Starting capture loop at {time.time_ns()} ns")
    
    # Note: OpenCV's VideoCapture (GStreamer backend) provides frames 
    # in the BGR format by default. Since the shared memory is expecting 
    # a monochrome Y-plane, we convert it to grayscale (Y-plane equivalent) 
    # before copying.
    
    try:
        while True:
            # ret: boolean success flag, frame: captured frame (BGR or whatever GStreamer defaulted to)
            ret, frame = cap.read() 
            
            if not ret or frame is None:
                print(f"[vision: cam{index}] ERROR: Failed to read frame from GStreamer.")
                time.sleep(0.001)
                continue
            
            # --- Convert to Grayscale (Y-plane equivalent) ---
            # The original code expected a Y-plane (grayscale). 
            # We convert the OpenCV frame (likely BGR) to grayscale.
            grayscale_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # --- Update Shared Memory ---
            with lock:
                # Copy the grayscale frame (size WxH, dtype uint8) into the shared buffer
                buf[:] = grayscale_frame 
                
                # Timestamping: GStreamer/OpenCV doesn't easily expose the precise SensorTimestamp.
                # We use the system time upon frame reception as a close approximation.
                ts_array[index] = time.time_ns() 

    except KeyboardInterrupt:
        print(f"[vision: cam{index}] Interrupted.")
    except Exception as e:
        print(f"[vision: cam{index}] Runtime error: {e}")
    finally:
        # Cleanup
        cap.release()
        shm.close()
        ts_shm.close()
        print(f"[vision: cam{index}] Capture stopped and resources released.")

def start_capture_process(index, shm_name, ts_shm_name, lock, ready_flags):
    return Process(target=capture_worker, args=(index, shm_name, ts_shm_name, lock, ready_flags))


# --- Example Main Execution Structure (Not requested, but useful for testing) ---
# The main process would set up shared memory and locks, then start the processes.
if __name__ == '__main__':
    NUM_CAMS = 2
    SHM_SIZE = BYTES_PER_FRAME * NUM_CAMS
    TS_SHM_SIZE = 8 * 2  # 2 x int64 (8 bytes each)

    # Create Shared Memory Segments
    try:
        shm = shared_memory.SharedMemory(create=True, size=SHM_SIZE)
        ts_shm = shared_memory.SharedMemory(create=True, size=TS_SHM_SIZE)
    except Exception as e:
        print(f"Failed to create shared memory: {e}")
        sys.exit(1)

    # Create synchronization primitives
    lock = Lock()
    ready_flags = Array('b', [False] * NUM_CAMS) # Shared array of booleans

    # Start capture workers
    processes = []
    for i in range(NUM_CAMS):
        p = start_capture_process(
            i, 
            shm.name, 
            ts_shm.name, 
            lock, 
            ready_flags
        )
        processes.append(p)
        p.start()

    # Handle termination signal
    def termination_handler(signum, frame):
        print("\n[Main] Terminating processes...")
        for p in processes:
            if p.is_alive():
                p.terminate()
        for p in processes:
            p.join()
        
        shm.close()
        shm.unlink()
        ts_shm.close()
        ts_shm.unlink()
        print("[Main] Cleanup complete. Exiting.")
        sys.exit(0)

    signal.signal(signal.SIGINT, termination_handler)
    signal.signal(signal.SIGTERM, termination_handler)
    
    # Keep the main process alive
    try:
        while True:
            time.sleep(1)
            # You can check the shared memory buffers here, e.g.:
            # frame_data = np.ndarray((HEIGHT * NUM_CAMS, WIDTH), dtype=np.uint8, buffer=shm.buf)
            # print(f"Current timestamps: {np.ndarray((2,), dtype=np.int64, buffer=ts_shm.buf)}")
    except KeyboardInterrupt:
        termination_handler(None, None)