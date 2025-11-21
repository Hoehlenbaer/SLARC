import numpy as np
import time
import threading
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

# --- SHARED MEMORY ALLOCATION (REUSE IF EXISTS) ---
def get_or_create_shm(name, size):
    try:
        return SharedMemory(name=name, create=True, size=size)
    except FileExistsError:
        print(f"⚠️ Shared memory '{name}' already exists — reusing.")
        return SharedMemory(name=name, create=False)

# --- CAMERA SETUP ---
def setup_camera(camera_id, frame_rate):
    try:
        picam2 = Picamera2(camera_num=camera_id)
        config = picam2.create_still_configuration(
            raw={"size": (RAW_WIDTH, RAW_HEIGHT), "format": RAW_FORMAT},
            buffer_count=6
        )
        config.setdefault("controls", {}).update({
            "FrameRate": frame_rate,
            "ExposureTime": 10000,
            "AnalogueGain": 1.0
        })
        picam2.configure(config)
        print(f"Camera {camera_id} configured: {RAW_FORMAT} @ {RAW_WIDTH}x{RAW_HEIGHT}")
        return picam2
    except Exception as e:
        print(f"Error setting up camera {camera_id}: {e}")
        exit(1)

# --- CAPTURE THREAD ---
def start_capture_thread(picam, shm_bufs, cam_id, stop_event):
    toggle = 0
    def capture_loop():
        nonlocal toggle
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
                    frame[:] = data
                    timestamp[0] = time.monotonic_ns()
                    flag[0] = 1
                    toggle = 1 - toggle
                except Exception as e:
                    print(f"Capture error on CAM{cam_id}: {e}")
        finally:
            try: picam.stop()
            except: print(f"Warning: Failed to stop camera {cam_id}")
            print(f"Camera {cam_id} stopped.")

    thread = threading.Thread(target=capture_loop, daemon=True)
    thread.start()
    return thread

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    cameras = [setup_camera(cid, FPS) for cid in CAM_IDS]

    shm_objects = {}
    try:
        print("Initializing shared memory buffers...")
        for name in SHM_NAMES.values():
            shm_objects[name] = get_or_create_shm(name, BUFFER_SIZE)

        shm0_bufs = [shm_objects[SHM_NAMES["CAM0_A"]], shm_objects[SHM_NAMES["CAM0_B"]]]
        shm1_bufs = [shm_objects[SHM_NAMES["CAM1_A"]], shm_objects[SHM_NAMES["CAM1_B"]]]

        stop_event = threading.Event()
        threads = [
            start_capture_thread(cameras[0], shm0_bufs, CAM_IDS[0], stop_event),
            start_capture_thread(cameras[1], shm1_bufs, CAM_IDS[1], stop_event)
        ]

        print("Capture threads running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopping capture...")
            stop_event.set()
            for t in threads:
                t.join()

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
