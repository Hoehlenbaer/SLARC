from picamera2 import Picamera2
import multiprocessing as mp
import numpy as np
import time
import os
import cv2
import signal
import sys
from multiprocessing import shared_memory, Event, Queue

def unpack_raw10(raw_bytes, width, height):
    raw = np.frombuffer(raw_bytes, dtype=np.uint8)
    valid_length = (raw.size // 5) * 5  # Trim to nearest multiple of 5
    raw = raw[:valid_length].reshape(-1, 5)

    pixels = np.zeros((raw.shape[0], 4), dtype=np.uint16)
    pixels[:, 0] = (raw[:, 0] << 2) | ((raw[:, 4] >> 0) & 0x03)
    pixels[:, 1] = (raw[:, 1] << 2) | ((raw[:, 4] >> 2) & 0x03)
    pixels[:, 2] = (raw[:, 2] << 2) | ((raw[:, 4] >> 4) & 0x03)
    pixels[:, 3] = (raw[:, 3] << 2) | ((raw[:, 4] >> 6) & 0x03)

    unpacked = pixels.flatten()[:width * height].reshape((height, width))
    return (unpacked >> 2).astype(np.uint8)  # Downscale to 8-bit for display

def capture_and_share(camera_index, queue, ready_event, core_id):
    try:
        os.sched_setaffinity(0, {core_id})
    except AttributeError:
        pass

    shape = (1088, 1456)
    size = shape[0] * shape[1]

    shm = shared_memory.SharedMemory(create=True, size=size)
    buffer = np.ndarray(shape, dtype=np.uint8, buffer=shm.buf)
    queue.put((shm.name, shape))

    picam2 = Picamera2(camera_num=camera_index)
    config = picam2.create_still_configuration(
        raw={"size": shape[::-1]},
        controls={"FrameRate": 60.0}
    )
    picam2.configure(config)
    picam2.start()

    frame_count = 0
    start_time = time.time()
    last_timestamp = None

    try:
        while True:
            request = picam2.capture_request()
            metadata = request.get_metadata()
            timestamp = metadata.get("SensorTimestamp", None)

            raw_bytes = request.make_buffer("raw").data
            request.release()

            unpacked = unpack_raw10(raw_bytes, shape[1], shape[0])
            buffer[:] = unpacked
            ready_event.set()

            frame_count += 1
            elapsed = time.time() - start_time
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                delta = (timestamp - last_timestamp) / 1e9 if last_timestamp else 0
                print(f"[Camera {camera_index}] FPS: {fps:.2f} | Δt: {delta:.3f}s")
                frame_count = 0
                start_time = time.time()
                last_timestamp = timestamp
    except KeyboardInterrupt:
        print(f"[Camera {camera_index}] Shutting down...")
    finally:
        picam2.stop()
        shm.close()
        shm.unlink()

def consume_from_shared(queue, ready_event, label):
    shm_name, shape = queue.get()
    shm = shared_memory.SharedMemory(name=shm_name)
    buffer = np.ndarray(shape, dtype=np.uint8, buffer=shm.buf)

    cv2.namedWindow(label, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(label, 640, 480)

    try:
        while True:
            ready_event.wait()
            ready_event.clear()

            frame = buffer.copy()
            mean_val = frame.mean()
            print(f"{label}: Frame received, mean={mean_val:.2f}")

            cv2.imshow(label, frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        print(f"{label}: Visualization interrupted.")
    finally:
        cv2.destroyWindow(label)
        shm.close()
        shm.unlink()

if __name__ == "__main__":
    queue0 = Queue()
    queue1 = Queue()
    event0 = Event()
    event1 = Event()

    try:
        p0 = mp.Process(target=capture_and_share, args=(0, queue0, event0, 1))
        time.sleep(0.5)
        p1 = mp.Process(target=capture_and_share, args=(1, queue1, event1, 2))
        p0.start()
        p1.start()

        r0 = mp.Process(target=consume_from_shared, args=(queue0, event0, "Camera 0"))
        r1 = mp.Process(target=consume_from_shared, args=(queue1, event1, "Camera 1"))
        r0.start()
        r1.start()

        p0.join()
        p1.join()
        r0.join()
        r1.join()
    except KeyboardInterrupt:
        print("Main process interrupted. Terminating...")
        for proc in [p0, p1, r0, r1]:
            if proc.is_alive():
                proc.terminate()
                proc.join()
