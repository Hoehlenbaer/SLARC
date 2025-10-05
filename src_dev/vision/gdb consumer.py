import numpy as np
import time
import cv2
from multiprocessing.shared_memory import SharedMemory

# --- CONFIGURATION ---
RAW_WIDTH = 1456
RAW_HEIGHT = 1088
PADDED_WIDTH = 1536  # actual stride used by libcamera
FRAME_SIZE = 3203072  # must match capture side
BUFFER_SIZE = FRAME_SIZE + 1 + 8  # frame + flag + timestamp
TARGET_PERIOD_MS = 1000 / 60.0  # 60 Hz = ~16.67 ms
TIMEOUT_SEC = 0.5

SHM_NAMES = ["CAM0_BUF_A", "CAM0_BUF_B", "CAM1_BUF_A", "CAM1_BUF_B"]

# --- SHARED MEMORY ACCESSORS ---
def get_buffer_views(shm: SharedMemory):
    buf = shm.buf
    frame = np.ndarray((FRAME_SIZE,), dtype=np.uint8, buffer=buf[:FRAME_SIZE])
    flag = np.ndarray((1,), dtype=np.uint8, buffer=buf[FRAME_SIZE:FRAME_SIZE+1])
    timestamp = np.ndarray((1,), dtype=np.int64, buffer=buf[FRAME_SIZE+1:])
    return frame, flag, timestamp

# --- WAIT FOR FRAME WITH TIMEOUT ---
def wait_for_frame(shm_a, shm_b, timeout=TIMEOUT_SEC):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for shm in [shm_a, shm_b]:
            frame, flag, timestamp = get_buffer_views(shm)
            if flag[0] == 1:
                data = frame.copy()
                ts = timestamp[0]
                flag[0] = 0
                return data, ts
        time.sleep(0.001)
    return None, None

# --- MAIN LOOP ---
if __name__ == "__main__":
    print("Connecting to shared memory...")
    shm = {name: SharedMemory(name=name) for name in SHM_NAMES}
    cam0_bufs = [shm["CAM0_BUF_A"], shm["CAM0_BUF_B"]]
    cam1_bufs = [shm["CAM1_BUF_A"], shm["CAM1_BUF_B"]]

    last_ts0 = last_ts1 = None
    frame_count = 0
    start_time = time.time()

    print("Starting downstream reader...")
    try:
        while True:
            # Wait for fresh frames
            raw0, ts0 = wait_for_frame(*cam0_bufs)
            raw1, ts1 = wait_for_frame(*cam1_bufs)

            if raw0 is None or raw1 is None:
                print("⚠️ Frame timeout — no new data within 500 ms")
                continue

            # Convert padded R16 to grayscale image
            

            raw16_0 = np.frombuffer(raw0, dtype=np.uint16)
            img0 = raw16_0.reshape((1088, 1472))
            img0_cropped = img0[:, :1456]

            raw16_1 = np.frombuffer(raw1, dtype=np.uint16)
            img1 = raw16_1.reshape((1088, 1472))
            img1_cropped = img1[:, :1456]

            # Normalize for display
            disp0 = cv2.convertScaleAbs(img0_cropped, alpha=0.03)
            disp1 = cv2.convertScaleAbs(img1_cropped, alpha=0.03)


            # Resize to 320×240
            # Resize to 320×240
            preview0 = cv2.resize(disp0, (320, 240), interpolation=cv2.INTER_AREA)
            preview1 = cv2.resize(disp1, (320, 240), interpolation=cv2.INTER_AREA)

            # Stack side by side
            stacked = np.hstack((preview0, preview1))
            cv2.imshow("Preview", stacked)

            if cv2.waitKey(1) == 27:  # ESC to quit
                break

            # Frame rate and margin diagnostics
            if last_ts0 and last_ts1:
                dt0 = (ts0 - last_ts0) / 1e6
                dt1 = (ts1 - last_ts1) / 1e6
                margin0 = TARGET_PERIOD_MS - dt0
                margin1 = TARGET_PERIOD_MS - dt1
                sync_drift = abs((ts0 - ts1) / 1e6)
                #print(f"CAM0 Δt={dt0:.2f} ms | margin={margin0:.2f} ms   "
                #      f"CAM1 Δt={dt1:.2f} ms | margin={margin1:.2f} ms   "
                #      f"Δsync={sync_drift:.2f} ms")

            last_ts0, last_ts1 = ts0, ts1
            frame_count += 1

    except KeyboardInterrupt:
        print("Reader interrupted.")
    finally:
        for shm_obj in shm.values():
            shm_obj.close()
        cv2.destroyAllWindows()
        elapsed = time.time() - start_time
        fps = frame_count / elapsed
        print(f"Captured {frame_count} frame pairs in {elapsed:.2f} s → {fps:.2f} fps")
