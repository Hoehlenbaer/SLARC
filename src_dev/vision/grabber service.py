from picamera2 import Picamera2
import multiprocessing as mp
import zmq
import numpy as np
import time

def capture_and_send(camera_index, port):
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.connect(f"tcp://localhost:{port}")

    picam2 = Picamera2(camera_num=camera_index)
    config = picam2.create_still_configuration(main={"size": (1456, 1088), "format": "YUV420"})
    picam2.configure(config)
    picam2.start()

    frame_count = 0
    start_time = time.time()

    while True:
        frame = picam2.capture_array("main")

        # Handle both grayscale and YUV420 formats
        if frame.ndim == 3:
            y_channel = frame[:, :, 0]
        elif frame.ndim == 2:
            y_channel = frame
        else:
            continue

        socket.send(y_channel.tobytes())

        # FPS logging
        frame_count += 1
        elapsed = time.time() - start_time
        if elapsed >= 1.0:
            fps = frame_count / elapsed
            print(f"[Camera {camera_index}] FPS: {fps:.2f}")
            frame_count = 0
            start_time = time.time()

def receive_and_unpack(port, name):
    context = zmq.Context()
    socket = context.socket(zmq.PULL)
    socket.bind(f"tcp://*:{port}")

    while True:
        raw = socket.recv()
        img = np.frombuffer(raw, dtype=np.uint8).reshape((1088, 1456))
        # Optional: visualize or process
        print(f"{name}: Frame received, mean={img.mean():.2f}")

if __name__ == "__main__":
    p0 = mp.Process(target=capture_and_send, args=(0, 5555))
    p1 = mp.Process(target=capture_and_send, args=(1, 5556))
    p0.start()
    p1.start()

    r0 = mp.Process(target=receive_and_unpack, args=(5555, "Camera 0"))
    r1 = mp.Process(target=receive_and_unpack, args=(5556, "Camera 1"))
    r0.start()
    r1.start()

    p0.join()
    p1.join()
    r0.join()
    r1.join()
