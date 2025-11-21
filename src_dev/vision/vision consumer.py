import numpy as np
import cv2
import time
from multiprocessing import shared_memory

# Image dimensions
WIDTH, HEIGHT = 1440, 1080
BYTES_PER_FRAME = WIDTH * HEIGHT

# Shared memory names (must match capture script)
SHM_NAME0 = "cam0_buffer"
SHM_NAME1 = "cam1_buffer"

def consumer(shm_name0, shm_name1):
    shm0 = shared_memory.SharedMemory(name=shm_name0)
    shm1 = shared_memory.SharedMemory(name=shm_name1)

    buf0 = np.ndarray((HEIGHT, WIDTH), dtype=np.uint8, buffer=shm0.buf)
    buf1 = np.ndarray((HEIGHT, WIDTH), dtype=np.uint8, buffer=shm1.buf)

    print("[consumer] Starting display loop. Press 'q' to quit.")

    try:
        while True:
            frame0 = cv2.resize(buf0.copy(), (320, 240))
            frame1 = cv2.resize(buf1.copy(), (320, 240))

            cv2.imshow("cam0", frame0)
            cv2.imshow("cam1", frame1)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            time.sleep(0.001)
    except KeyboardInterrupt:
        print("\n[consumer] Interrupted.")
    finally:
        shm0.close()
        shm1.close()
        cv2.destroyAllWindows()
        print("[consumer] Shutdown complete.")

if __name__ == "__main__":
    consumer(SHM_NAME0, SHM_NAME1)
