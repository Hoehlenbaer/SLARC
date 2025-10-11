import time
from multiprocessing import Process
from picamera2 import Picamera2

RAW_WIDTH = 1456
RAW_HEIGHT = 1088
RAW_FORMAT = "R16"
FPS = 60.0

def capture_loop(cam_id):
    picam = Picamera2(camera_num=cam_id)
    config = picam.create_video_configuration(
        raw={"size": (RAW_WIDTH, RAW_HEIGHT), "format": RAW_FORMAT},
        buffer_count=8
    )
    config.setdefault("controls", {}).update({
        "FrameRate": FPS,
        "AnalogueGain": 8.0
    })
    picam.configure(config)
    picam.start()
    time.sleep(0.5)

    print(f"Camera {cam_id} started.")
    try:
        while True:
            t0 = time.monotonic_ns()
            buf = picam.capture_buffer("raw")
            meta = picam.capture_metadata()
            t1 = time.monotonic_ns()

            ts = meta.get("SensorTimestamp")
            latency = (t1 - t0) / 1e6
            print(f"CAM{cam_id} latency: {latency:.2f} ms | SensorTimestamp: {ts}")
    except KeyboardInterrupt:
        print(f"Stopping CAM{cam_id}...")
    finally:
        picam.stop()

if __name__ == "__main__":
    p0 = Process(target=capture_loop, args=(0,))
    p1 = Process(target=capture_loop, args=(1,))
    p0.start()
    p1.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping both cameras...")
        p0.terminate()
        p1.terminate()
        p0.join()
        p1.join()
