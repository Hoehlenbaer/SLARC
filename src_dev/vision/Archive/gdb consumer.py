import numpy as np
import time
import cv2
from multiprocessing.shared_memory import SharedMemory

# --- CONFIGURATION ---
RAW_WIDTH = 1456
RAW_HEIGHT = 1088
PADDED_WIDTH = 1472  # actual stride used by libcamera
FRAME_SIZE = PADDED_WIDTH * RAW_HEIGHT * 2  # R16 = 2 bytes per pixel
BUFFER_SIZE = FRAME_SIZE + 1 + 8  # frame + flag + timestamp
TARGET_PERIOD_MS = 1000 / 60.0  # 60 Hz = ~16.67 ms
TIMEOUT_SEC = 0.5
PREVIEW_INTERVAL = 4  # Show every 4th frame

BLACK_LEVEL = 256    # Adjust based on sensor calibration
WHITE_LEVEL = 4095   # 12-bit max value

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

# --- RAW TO DISPLAY CONVERSION ---
def convert_r16_to_display(raw, width, height):
    raw16 = np.frombuffer(raw, dtype=np.uint16).reshape((height, PADDED_WIDTH))
    raw12 = (raw16 >> 4).astype(np.uint16)  # discard lower 4 bits
    cropped = raw12[:, :width]
    norm = np.clip(cropped - BLACK_LEVEL, 0, WHITE_LEVEL - BLACK_LEVEL)
    disp = cv2.convertScaleAbs(norm, alpha=255.0 / (WHITE_LEVEL - BLACK_LEVEL))
    return disp

# --- MAIN LOOP ---
if __name__ == "__main__":
    print("Connecting to shared memory...")
    shm = {name: SharedMemory(name=name) for name in SHM_NAMES}
    cam0_bufs = [shm["CAM0_BUF_A"], shm["CAM0_BUF_B"]]
    cam1_bufs = [shm["CAM1_BUF_A"], shm["CAM1_BUF_B"]]

    frame_count = 0
    start_time = time.time()

    # Timestamp tracking
    last_ts0 = last_ts1 = None
    dt0_list = []
    dt1_list = []
    sync_drift_list = []

    print("Starting downstream reader...")
    try:
        while True:
            raw0, ts0 = wait_for_frame(*cam0_bufs)
            raw1, ts1 = wait_for_frame(*cam1_bufs)

            if raw0 is None or raw1 is None:
                print("⚠️ Frame timeout — no new data within 500 ms")
                continue

            frame_count += 1

            # Timestamp diagnostics
            if last_ts0 is not None and last_ts1 is not None:
                dt0 = (ts0 - last_ts0) / 1e6  # ms
                dt1 = (ts1 - last_ts1) / 1e6
                drift = abs(ts0 - ts1) / 1e6

                dt0_list.append(dt0)
                dt1_list.append(dt1)
                sync_drift_list.append(drift)

            last_ts0, last_ts1 = ts0, ts1

            # Preview every Nth frame
            if frame_count % PREVIEW_INTERVAL == 0:
                disp0 = convert_r16_to_display(raw0, RAW_WIDTH, RAW_HEIGHT)
                disp1 = convert_r16_to_display(raw1, RAW_WIDTH, RAW_HEIGHT)

                preview0 = cv2.resize(disp0, (320, 240), interpolation=cv2.INTER_AREA)
                preview1 = cv2.resize(disp1, (320, 240), interpolation=cv2.INTER_AREA)

                stacked = np.hstack((preview0, preview1))
                cv2.imshow("Preview", stacked)
                print(f"{ts0} {ts1}")
                if cv2.waitKey(1) == 27:  # ESC to quit
                    break

    except KeyboardInterrupt:
        print("Reader interrupted.")
    finally:
        for shm_obj in shm.values():
            shm_obj.close()
        cv2.destroyAllWindows()

        elapsed = time.time() - start_time
        fps = frame_count / elapsed
        print(f"\n📊 Capture Summary:")
        print(f"  • Total frames: {frame_count}")
        print(f"  • Elapsed time: {elapsed:.2f} s")
        print(f"  • Average FPS:  {fps:.2f}")

        if dt0_list and dt1_list:
            def stats(arr):
                return np.mean(arr), np.std(arr)

            mean_dt0, std_dt0 = stats(dt0_list)
            mean_dt1, std_dt1 = stats(dt1_list)
            mean_drift = np.mean(sync_drift_list)
            max_drift = np.max(sync_drift_list)
            std_drift = np.std(sync_drift_list)

            print(f"\n⏱️ Timing Diagnostics:")
            print(f"  • CAM0 Δt: mean = {mean_dt0:.2f} ms, jitter = {std_dt0:.2f} ms")
            print(f"  • CAM1 Δt: mean = {mean_dt1:.2f} ms, jitter = {std_dt1:.2f} ms")
            print(f"  • Sync drift: mean = {mean_drift:.2f} ms, max = {max_drift:.2f} ms, std = {std_drift:.2f} ms")
