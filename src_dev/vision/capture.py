# capture.py

from picamera2 import Picamera2
import numpy as np
import time
import cv2
from multiprocessing import Process, shared_memory
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
            "FrameDurationLimits": (int(1e9 / FPS), int(1e9 / FPS)),  # lock frame rate
            "ExposureTime": 8000,       # 8 ms exposure (in µs)
            "AnalogueGain": 1.0,        # fixed gain
            "AeEnable": False,          # disable auto exposure
            "ExposureTimeMode": 1,      # manual mode
            "AnalogueGainMode": 1       # manual gain mode
        }

    )
    cam.configure(config)
    return cam

def capture_worker(index, shm_name, ts_shm_name, lock, ready_flags):
    cam = setup_camera(index)
    
    shm = shared_memory.SharedMemory(name=shm_name)
    buf = np.ndarray((HEIGHT, WIDTH), dtype=np.uint8, buffer=shm.buf)

    ts_shm = shared_memory.SharedMemory(name=ts_shm_name)
    ts_array = np.ndarray((2,), dtype=np.int64, buffer=ts_shm.buf)

    print(f"[vision: cam{index}] Setup complete.")
    ready_flags[index] = True

    while not all(ready_flags):
        time.sleep(0.000001)

    print(f"[vision: cam{index}] Starting capture loop at {time.time_ns()} ns")

    def handle_request(request):
        try:
            ts = request.get_metadata().get("SensorTimestamp", time.time_ns())
            stream_config = cam.stream_configuration("main")
            stride = stream_config["stride"]
            height = stream_config["size"][1]

            frame = request.make_buffer("main")
            y_plane = np.frombuffer(frame, dtype=np.uint8, count=stride * height).reshape((height, stride))
            visible = y_plane[:, :WIDTH]

            with lock:
                buf[:] = visible
                ts_array[index] = ts

        except Exception as e:
            print(f"[vision: cam{index}] Callback error: {e}")

    cam.post_callback = handle_request

    try:
        cam.start()
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print(f"[vision: cam{index}] Interrupted.")
    finally:
        cam.stop()
        shm.close()
        ts_shm.close()
        print(f"[vision: cam{index}] Capture stopped.")

def start_capture_process(index, shm_name, ts_shm_name, lock, ready_flags):
    return Process(target=capture_worker, args=(index, shm_name, ts_shm_name, lock, ready_flags))
