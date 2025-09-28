from picamera2 import Picamera2
import multiprocessing as mp
import numpy as np
import time
import os
import cv2
from multiprocessing import shared_memory, Event, Queue

def capture_and_share(camera_index, queue, ready_event, core_id):
    try:
        os.sched_setaffinity(0, {core_id})
    except AttributeError:
        pass

    picam2 = Picamera2(camera_num=camera_index)
    config = picam2.create_video_configuration(
        main={"size": (1440, 1080), "format": "R10_CSI2P"},
        controls={"FrameRate": 40.0}
    )
    picam2.configure(config)
    picam2.start()

    # Probe actual frame shape
    frame = picam2.capture_array("main")
    shape = frame[:, :, 0].shape if frame.ndim == 3 else frame.shape
    size = np.prod(shape)

    shm = shared_memory.SharedMemory(create=True, size=size)
    buffer = np.ndarray(shape, dtype=np.uint8, buffer=shm.buf)
    queue.put((shm.name, shape))

    frame_count = 0
    start_time = time.time()

    try:
        while True:
            frame = picam2.capture_array("main")
            y_channel = frame[:, :, 0] if frame.ndim == 3 else frame
            buffer[:] = y_channel
            ready_event.set()

            frame_count += 1
            elapsed = time.time() - start_time
            if elapsed >= 1.0:
                print(f"[Camera {camera_index}] FPS: {frame_count / elapsed:.2f}")
                frame_count = 0
                start_time = time.time()
    except KeyboardInterrupt:
        pass
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
        pass
    finally:
        cv2.destroyWindow(label)
        shm.close()

if __name__ == "__main__":
    queue0 = Queue()
    queue1 = Queue()
    event0 = Event()
    event1 = Event()

    p0 = mp.Process(target=capture_and_share, args=(0, queue0, event0, 1))
    p1 = mp.Process(target=capture_and_share, args=(1, queue1, event1, 2))
    r0 = mp.Process(target=consume_from_shared, args=(queue0, event0, "Camera 0"))
    r1 = mp.Process(target=consume_from_shared, args=(queue1, event1, "Camera 1"))

    p0.start()
    time.sleep(0.5)
    p1.start()
    r0.start()
    r1.start()

    try:
        p0.join()
        p1.join()
        r0.join()
        r1.join()
    except KeyboardInterrupt:
        print("Shutting down...")
