import numpy as np
import time
from multiprocessing import Process, Event
from multiprocessing.shared_memory import SharedMemory
from picamera2 import Picamera2
from libcamera import controls

# --- CONFIGURATION ---
CAM_IDS = [0, 1]
FPS = 60.0

RAW_DTYPE = np.uint8
FRAME_SIZE = 3203072  # 1456 x 1088 x 2 bytes
RAW_FORMAT = "R16"
RAW_HEIGHT = 1088
RAW_WIDTH = 1456

BUFFER_SIZE = FRAME_SIZE + 1 + 8  # frame + flag + timestamp

SHM_NAMES = {
    "CAM0_A": "CAM0_BUF_A",
    "CAM0_B": "CAM0_BUF_B",
    "CAM1_A": "CAM1_BUF_A",
    "CAM1_B": "CAM1_BUF_B"
}

# --- SHARED MEMORY ACCESSORS ---
def get_buffer_views(shm: SharedMemory):
    buf = shm.buf
    frame = np.ndarray((FRAME_SIZE,), dtype=RAW_DTYPE, buffer=buf[:FRAME_SIZE])
    flag = np.ndarray((1,), dtype=np.uint8, buffer=buf[FRAME_SIZE:FRAME_SIZE+1])
    timestamp = np.ndarray((1,), dtype=np.int64, buffer=buf[FRAME_SIZE+1:])
    return frame, flag, timestamp

# --- SHARED MEMORY ALLOCATION ---
def get_or_create_shm(name, size):
    try:
        return SharedMemory(name=name, create=True, size=size)
    except FileExistsError:
        print(f"⚠️ Shared memory '{name}' already exists — reusing.")
        return SharedMemory(name=name, create=False)

# --- CAMERA SETUP ---
def setup_camera(camera_id, frame_rate):
    picam2 = Picamera2(camera_num=camera_id)
    config = picam2.create_still_configuration(
        raw={"size": (RAW_WIDTH, RAW_HEIGHT), "format": RAW_FORMAT},
        buffer_count=6
    )
    config.setdefault("controls", {}).update({
        "FrameRate": frame_rate,
        "ExposureTime": 10000,
        "AnalogueGain": 8.0
    })
    picam2.configure(config)
    print(f"Camera {camera_id} configured: {RAW_FORMAT} @ {RAW_WIDTH}x{RAW_HEIGHT}")
    return picam2

# --- CAPTURE PROCESS ---
def capture_process(cam_id, shm_names, stop_event):
    toggle = 0
    shm_bufs = [get_or_create_shm(shm_names[0], BUFFER_SIZE),
                get_or_create_shm(shm_names[1], BUFFER_SIZE)]
    picam = setup_camera(cam_id, FPS)

    try:
        picam.start(show_preview=False)
        print(f"Camera {cam_id} started.")
        for _ in range(3):  # warm-up
            picam.capture_array("raw")

        while not stop_event.is_set():
            shm = shm_bufs[toggle]
            frame, flag, timestamp = get_buffer_views(shm)
            try:
                data = picam.capture_array("raw").ravel()
                meta = picam.capture_metadata()
                if "SensorTimestamp" not in meta:
                    print(f"⚠️ Missing SensorTimestamp on CAM{cam_id} — skipping frame")
                    continue

                frame[:] = data
                timestamp[0] = meta["SensorTimestamp"]
                flag[0] = 1
                toggle = 1 - toggle
            except Exception as e:
                print(f"Capture error on CAM{cam_id}: {e}")
    finally:
        try: picam.stop()
        except: print(f"Warning: Failed to stop camera {cam_id}")
        print(f"Camera {cam_id} stopped.")
        for shm in shm_bufs:
            shm.close()

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    shm_objects = {}
    try:
        print("Initializing shared memory buffers...")
        for name in SHM_NAMES.values():
            shm_objects[name] = get_or_create_shm(name, BUFFER_SIZE)

        stop_event = Event()
        processes = [
            Process(target=capture_process, args=(CAM_IDS[0], [SHM_NAMES["CAM0_A"], SHM_NAMES["CAM0_B"]], stop_event)),
            Process(target=capture_process, args=(CAM_IDS[1], [SHM_NAMES["CAM1_A"], SHM_NAMES["CAM1_B"]], stop_event))
        ]

        for p in processes:
            p.start()

        print("Capture processes running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopping capture...")
            stop_event.set()
            for p in processes:
                p.join()

    except Exception as e:
        print(f"Unhandled error: {type(e).__name__} - {e}")
    finally:
        for name, shm in shm_objects.items():
            try:
                shm.close()
                shm.unlink()
                print(f"Unlinked {name}")
            except:
                print(f"Warning: Failed to unlink {name}")
        print("Program finished.")
