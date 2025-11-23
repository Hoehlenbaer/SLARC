from picamera2 import Picamera2
import numpy as np
import time
import cv2
from multiprocessing import Process, shared_memory, Manager, Lock
import signal
import sys

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
            "ExposureTime": 20000,  # in microseconds (e.g., 20ms = 50 FPS)
            "AnalogueGain": 1.0,
            "DigitalGain": 1.0
        }
    )
    cam.configure(config)
    return cam


def capture_worker(index, shm_name, ts_shm_name, lock, ready_flags):
    cam = setup_camera(index)

    # Image buffer
    shm = shared_memory.SharedMemory(name=shm_name)
    buf = np.ndarray((HEIGHT, WIDTH), dtype=np.uint8, buffer=shm.buf)

    # Timestamp buffer
    ts_shm = shared_memory.SharedMemory(name=ts_shm_name)
    ts_array = np.ndarray((2,), dtype=np.int64, buffer=ts_shm.buf)

    print(f"[cam{index}] Setup complete.")
    ready_flags[index] = True

    while not all(ready_flags):
        time.sleep(0.000001)

    print(f"[cam{index}] Starting capture loop at {time.time_ns()} ns")

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
            print(f"[cam{index}] Callback error: {e}")

    cam.post_callback = handle_request

    try:
        cam.start()
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print(f"[cam{index}] Interrupted.")
    finally:
        cam.stop()
        shm.close()
        ts_shm.close()
        cv2.destroyWindow(f"cam{index}")
        print(f"[cam{index}] Capture stopped.")

if __name__ == "__main__":
    shm0 = shared_memory.SharedMemory(name="cam0_buffer", create=True, size=BYTES_PER_FRAME)
    shm1 = shared_memory.SharedMemory(name="cam1_buffer", create=True, size=BYTES_PER_FRAME)
    ts_shm = shared_memory.SharedMemory(name="ts_buffer", create=True, size=16)  # 2 × int64

    with Manager() as manager:
        ready_flags = manager.list([False, False])
        lock = Lock()

        p0 = Process(target=capture_worker, args=(0, shm0.name, ts_shm.name, lock, ready_flags))
        p1 = Process(target=capture_worker, args=(1, shm1.name, ts_shm.name, lock, ready_flags))
        p0.start()
        p1.start()

        def shutdown_handler(sig, frame):
            print("\n[main] Shutting down...")
            p0.terminate()
            p1.terminate()
            p0.join()
            p1.join()
            shm0.close(); shm1.close(); ts_shm.close()
            shm0.unlink(); shm1.unlink(); ts_shm.unlink()
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.pause()
