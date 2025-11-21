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
    config = picam2.create_still_configuration(
        main={"format": "YUV420"},
        controls={"FrameRate": 30.0}
    )
    picam2.configure(config)
    picam2.start()

    # Probe actual frame shape
    request = picam2.capture_request()
    frame = request.make_array("main")
    request.release()
    shape = frame[:, :, 0].shape if frame.ndim == 3 else frame.shape
    size = np.prod(shape)

    # Create shared memory
    shm = shared_memory.SharedMemory(create=True, size=size)
    buffer = np.ndarray(shape, dtype=np.uint8, buffer=shm.buf)

    # Send metadata to consumer
    queue.put((shm.name, shape))

    frame_count = 0
    start_time = time.time()
    last_timestamp = None

    while True:
        request = picam2.capture_request()
        metadata = request.get_metadata()
        timestamp = metadata.get("SensorTimestamp", None)

        frame = request.make_array("main")
        request.release()
        y_channel = frame[:, :, 0] if frame.ndim == 3 else frame

        buffer[:] = y_channel
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

def consume_from_shared(queue, ready_event, label):
    shm_name, shape = queue.get()
    shm = shared_memory.SharedMemory(name=shm_name)
    buffer = np.ndarray(shape, dtype=np.uint8, buffer=shm.buf)

    cv2.namedWindow(label, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(label, 640, 480)

    while True:
        ready_event.wait()
        ready_event.clear()

        frame = buffer.copy()
        mean_val = frame.mean()
        print(f"{label}: Frame received, mean={mean_val:.2f}")

        cv2.imshow(label, frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cv2.destroyWindow(label)
    shm.close()

if __name__ == "__main__":
    queue0 = Queue()
    queue1 = Queue()
    event0 = Event()
    event1 = Event()

    # Start capture processes
    p0 = mp.Process(target=capture_and_share, args=(0, queue0, event0, 1))
    time.sleep(0.5)
    p1 = mp.Process(target=capture_and_share, args=(1, queue1, event1, 2))
    p0.start()
    p1.start()

    # Start consumer processes with visualization
    r0 = mp.Process(target=consume_from_shared, args=(queue0, event0, "Camera 0"))
    r1 = mp.Process(target=consume_from_shared, args=(queue1, event1, "Camera 1"))
    r0.start()
    r1.start()

    p0.join()
    p1.join()
    r0.join()
    r1.join()
