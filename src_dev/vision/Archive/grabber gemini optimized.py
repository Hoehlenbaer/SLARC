import numpy as np
import time
import threading
from multiprocessing.shared_memory import SharedMemory
from picamera2 import Picamera2
from libcamera import controls

# --- CONFIGURATION CONSTANTS ---
CAM0_ID = 0
CAM1_ID = 1
FPS = 5.0

RAW_DTYPE = np.uint8
FRAME_SIZE = 3203072
RAW_ELEMENTS = FRAME_SIZE  # 3203072 bytes
RAW_FORMAT = "R16"
RAW_HEIGHT = 1088
RAW_WIDTH = 1456

SHM_NAME0 = "CAM0_SHM"
SHM_NAME1 = "CAM1_SHM"

# --- CAMERA SETUP ---
def setup_camera(camera_id, frame_rate):
    try:
        picam2 = Picamera2(camera_num=camera_id)
        config = picam2.create_still_configuration(
            raw={"size": (RAW_WIDTH, RAW_HEIGHT), "format": RAW_FORMAT},
            buffer_count=16
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

# --- FRAME CAPTURE ---
def capture_streams(picam0, picam1, shm_cam0, shm_cam1, num_frames=10):
    shm_flat0 = np.ndarray((RAW_ELEMENTS,), dtype=RAW_DTYPE, buffer=shm_cam0.buf)
    shm_flat1 = np.ndarray((RAW_ELEMENTS,), dtype=RAW_DTYPE, buffer=shm_cam1.buf)


    try:
        picam0.start(show_preview=False)
        picam1.start(show_preview=False)
        print("Cameras started. Warming up...")

        for _ in range(3):
            picam0.capture_array("raw")
            picam1.capture_array("raw")

        print(f"Capturing {num_frames} frame pairs...")

        start_ns = time.monotonic_ns()
        for i in range(num_frames):
            def capture_and_copy(picam, shm_flat):
                frame = picam.capture_array("raw").ravel()
                shm_flat[:] = frame
                

            t0 = threading.Thread(target=capture_and_copy, args=(picam0, shm_flat0))
            t1 = threading.Thread(target=capture_and_copy, args=(picam1, shm_flat1))
            t0.start()
            t1.start()
            t0.join()
            t1.join()
        end_ns = time.monotonic_ns()
        print(f"{num_frames} frame pairs captured in {(end_ns - start_ns)/1e6:.2f} ms")

    except Exception as e:
        print(f"\n🛑 Capture failure at frame {i+1}: {type(e).__name__} - {e}")
    finally:
        print("Stopping cameras...")
        try: picam0.stop()
        except: print(f"Warning: Failed to stop camera {CAM0_ID}")
        try: picam1.stop()
        except: print(f"Warning: Failed to stop camera {CAM1_ID}")
        print("Capture complete.")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    camera0 = setup_camera(CAM0_ID, FPS)
    camera1 = setup_camera(CAM1_ID, FPS)

    shm_cam0 = shm_cam1 = None
    try:
        print("Allocating shared memory...")
        shm_cam0 = SharedMemory(name=SHM_NAME0, create=True, size=FRAME_SIZE)
        shm_cam1 = SharedMemory(name=SHM_NAME1, create=True, size=FRAME_SIZE)
        print(f"Shared memory ready: {SHM_NAME0}, {SHM_NAME1} ({FRAME_SIZE} bytes each)")

        capture_streams(camera0, camera1, shm_cam0, shm_cam1, num_frames=500)

    except FileExistsError:
        print(f"Error: Shared memory {SHM_NAME0} or {SHM_NAME1} already exists.")
    except Exception as e:
        print(f"Unhandled error: {e}")
    finally:
        if shm_cam0:
            shm_cam0.close()
            shm_cam0.unlink()
            print(f"Unlinked {SHM_NAME0}")
        if shm_cam1:
            shm_cam1.close()
            shm_cam1.unlink()
            print(f"Unlinked {SHM_NAME1}")
        print("Program finished.")
