import zmq
import cv2
import numpy as np
import time
import os
from picamera2 import Picamera2
import multiprocessing as mp

WIDTH, HEIGHT = 1440, 1080
HEADER_SIZE = 8  # timestamp as uint64

def unpack_raw10(packed, width, height):
    row_stride = (width // 4) * 5
    unpacked = np.zeros((height, width), dtype=np.uint16)

    for y in range(height):
        row = packed[y * row_stride : (y + 1) * row_stride]
        for x in range(0, len(row), 5):
            msbs = row[x:x+4].astype(np.uint16)
            lsbs = row[x+4]
            unpacked[y, x//5*4 + 0] = (msbs[0] << 2) | ((lsbs >> 0) & 0x03)
            unpacked[y, x//5*4 + 1] = (msbs[1] << 2) | ((lsbs >> 2) & 0x03)
            unpacked[y, x//5*4 + 2] = (msbs[2] << 2) | ((lsbs >> 4) & 0x03)
            unpacked[y, x//5*4 + 3] = (msbs[3] << 2) | ((lsbs >> 6) & 0x03)
    return unpacked

def capture_and_publish(camera_index, port, core_id):
    try:
        os.sched_setaffinity(0, {core_id})
    except AttributeError:
        pass

    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind(f"tcp://*:{port}")

    picam2 = Picamera2(camera_num=camera_index)
    config = picam2.create_video_configuration(
        raw={"size": (WIDTH, HEIGHT), "format": "RAW10"},
        controls={"FrameRate": 40.0}
    )
    picam2.configure(config)
    picam2.start()

    frame_count = 0
    start_time = time.time()

    try:
        while True:
            raw = picam2.capture_array("raw")
            unpacked = unpack_raw10(raw, WIDTH, HEIGHT)

            timestamp = time.time_ns()
            header = np.array([timestamp], dtype=np.uint64).tobytes()
            payload = unpacked.tobytes()
            socket.send(header + payload)

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
        socket.close()
        context.term()

def subscribe_and_display(port, label):
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://localhost:{port}")
    socket.setsockopt(zmq.SUBSCRIBE, b"")

    cv2.namedWindow(label, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(label, 640, 480)

    try:
        while True:
            raw = socket.recv()
            timestamp = np.frombuffer(raw[:HEADER_SIZE], dtype=np.uint64)[0]
            frame = np.frombuffer(raw[HEADER_SIZE:], dtype=np.uint16).reshape((HEIGHT, WIDTH))

            display = (frame >> 2).astype(np.uint8)  # normalize 10-bit to 8-bit
            print(f"{label}: Timestamp={timestamp} | Mean={frame.mean():.2f}")
            cv2.imshow(label, display)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyWindow(label)
        socket.close()
        context.term()

if __name__ == "__main__":
    p0 = mp.Process(target=capture_and_publish, args=(0, 5550, 1))
    p1 = mp.Process(target=capture_and_publish, args=(1, 5551, 2))
    r0 = mp.Process(target=subscribe_and_display, args=(5550, "Camera 0"))
    r1 = mp.Process(target=subscribe_and_display, args=(5551, "Camera 1"))

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
