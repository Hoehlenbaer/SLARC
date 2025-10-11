from picamera2 import Picamera2
import numpy as np
import time
from multiprocessing import Process, shared_memory, Manager, Event, Lock

# Image and capture settings
WIDTH, HEIGHT = 1440, 1080
BYTES_PER_FRAME = WIDTH * HEIGHT
FPS = 50
NUM_FRAMES = 50

def setup_camera(index):
    cam = Picamera2(index)
    config = cam.create_video_configuration(
        main={"size": (WIDTH, HEIGHT), "format": "YUV420"},
        controls={"FrameDurationLimits": (int(1e9 / FPS), int(1e9 / FPS))}
    )
    cam.configure(config)
    return cam

def capture_worker(index, shm_name, timestamps, ready_flags, done_event, lock):
    cam = setup_camera(index)
    shm = shared_memory.SharedMemory(name=shm_name)
    buf = np.ndarray((HEIGHT, WIDTH), dtype=np.uint8, buffer=shm.buf)

    print(f"[cam{index}] Setup complete.")
    ready_flags[index] = True

    while not all(ready_flags):
        time.sleep(0.000001)  # 1 µs polling

    print(f"[cam{index}] Starting capture loop at {time.time_ns()} ns")

    frame_count = 0

    def handle_request(request):
        nonlocal frame_count
        if frame_count >= NUM_FRAMES:
            return
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
                timestamps.append(ts)

            frame_count += 1
            if frame_count == NUM_FRAMES:
                done_event.set()
        except Exception as e:
            print(f"[cam{index}] Callback error: {e}")

    cam.post_callback = handle_request
    cam.start()
    done_event.wait()
    cam.stop()
    shm.close()
    print(f"[cam{index}] Finished capturing {NUM_FRAMES} frames.")

if __name__ == "__main__":
    shm0 = shared_memory.SharedMemory(create=True, size=BYTES_PER_FRAME)
    shm1 = shared_memory.SharedMemory(create=True, size=BYTES_PER_FRAME)

    with Manager() as manager:
        ts0 = manager.list()
        ts1 = manager.list()
        ready_flags = manager.list([False, False])
        done0 = Event()
        done1 = Event()
        lock = Lock()

        p0 = Process(target=capture_worker, args=(0, shm0.name, ts0, ready_flags, done0, lock))
        p1 = Process(target=capture_worker, args=(1, shm1.name, ts1, ready_flags, done1, lock))
        p0.start()
        p1.start()
        done0.wait()
        done1.wait()
        p0.join()
        p1.join()

        print("\n=== Timestamps ===")
        print("cam0:")
        for i, ts in enumerate(ts0):
            print(f"  [{i}] {ts}")
        print("cam1:")
        for i, ts in enumerate(ts1):
            print(f"  [{i}] {ts}")

        def compute_fps(ts_list):
            if len(ts_list) < 2:
                return 0.0
            duration_ns = ts_list[-1] - ts_list[0]
            return (len(ts_list) - 1) * 1e9 / duration_ns

        fps0 = compute_fps(ts0)
        fps1 = compute_fps(ts1)
        print(f"\nStreaming performance:")
        print(f"cam0: {len(ts0)} frames @ {fps0:.2f} FPS")
        print(f"cam1: {len(ts1)} frames @ {fps1:.2f} FPS")

    shm0.close(); shm1.close()
    shm0.unlink(); shm1.unlink()
