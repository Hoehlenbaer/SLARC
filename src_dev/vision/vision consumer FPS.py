import numpy as np
import cv2
from multiprocessing import shared_memory
import time 

# --- CONFIGURATION ---
WIDTH, HEIGHT = 1440, 1080
FRAME_SIZE = (320, 240) # Display size for cv2.imshow
SHM_NAME0 = "cam0_buffer"
SHM_NAME1 = "cam1_buffer"
TS_SHM_NAME = "ts_buffer"
FPS_WINDOW_SEC = 1.0 # Time window for averaging FPS
# ---------------------

class SharedMemoryConsumer:
    """
    Consumes frames and timestamps from shared memory buffers 
    and displays them with an accurate FPS counter.
    """
    def __init__(self, shm_names, ts_shm_name, width, height):
        self.shm_names = shm_names
        self.ts_shm_name = ts_shm_name
        self.width = width
        self.height = height
        
        # Shared memory references
        self.shm_buffers = {}
        self.shm_ts = None
        
        # NumPy array views
        self.frame_buffers = {}
        self.ts_shm_array = None
        self.last_ts_array = np.zeros(len(shm_names), dtype=np.int64)

    def _setup_shared_memory(self):
        """Initializes connection to all shared memory segments."""
        print("[Consumer] Setting up shared memory...")
        
        # 1. Image Buffers
        for i, name in enumerate(self.shm_names):
            try:
                shm = shared_memory.SharedMemory(name=name)
                # Create a NumPy view into the shared memory buffer
                self.frame_buffers[i] = np.ndarray(
                    (self.height, self.width), dtype=np.uint8, buffer=shm.buf
                )
                self.shm_buffers[i] = shm
                cv2.namedWindow(f"cam{i}")
            except FileNotFoundError:
                print(f"[ERROR] Shared memory '{name}' not found. Is capture.py running?")
                raise
        
        # 2. Timestamp Buffer
        try:
            self.shm_ts = shared_memory.SharedMemory(name=self.ts_shm_name)
            self.ts_shm_array = np.ndarray(
                (len(self.shm_names),), dtype=np.int64, buffer=self.shm_ts.buf
            )
        except FileNotFoundError:
            print(f"[ERROR] Timestamp shared memory '{self.ts_shm_name}' not found.")
            raise
        
        print(f"[Consumer] Setup complete for {len(self.shm_names)} cameras.")

    def _cleanup(self):
        """Closes all shared memory handles and destroys windows."""
        print("\n[Consumer] Initiating shutdown...")
        for shm in self.shm_buffers.values():
            shm.close()
        if self.shm_ts:
            self.shm_ts.close()
            
        cv2.destroyAllWindows()
        print("[Consumer] Shutdown complete.")

    def run(self):
        """Main display loop with true FPS calculation."""
        try:
            self._setup_shared_memory()
        except FileNotFoundError:
            return

        # FPS Tracking variables
        frame_display_count = 0
        start_time = time.time()
        current_fps = 0.0

        print(f"[Consumer] Starting display loop. Press 'q' to quit.")

        try:
            while True:
                # 1. Read and Check Timestamps
                # Get a copy of the current timestamps from the producer
                current_ts = self.ts_shm_array.copy() 
                frame_changed = current_ts > self.last_ts_array
                
                displayed_this_cycle = False 

                # 2. Process and Display Frames
                for i, changed in enumerate(frame_changed):
                    if changed:
                        # Copy the frame data and resize for display
                        # Use .copy() to ensure the data is immutable while resizing/displaying
                        frame_data = self.frame_buffers[i].copy() 
                        display_frame = cv2.resize(frame_data, FRAME_SIZE)
                        
                        cv2.imshow(f"cam{i}", display_frame)
                        
                        # Update the last displayed timestamp
                        self.last_ts_array[i] = current_ts[i]
                        displayed_this_cycle = True
                
                # 3. True FPS Calculation
                if displayed_this_cycle:
                    # Only count a frame if at least one camera had an update
                    frame_display_count += 1
                
                elapsed_time = time.time() - start_time
                
                if elapsed_time >= FPS_WINDOW_SEC:
                    # Calculate FPS based on true updates over the window time
                    current_fps = frame_display_count / elapsed_time 
                    
                    # Reset for the next calculation window
                    frame_display_count = 0
                    start_time = time.time()

                # 4. Update Window Titles
                fps_text = f"FPS: {current_fps:.1f}" 
                
                for i in range(len(self.shm_names)):
                    status = "Updated" if frame_changed[i] else "Waiting"
                    cv2.setWindowTitle(
                        f"cam{i}", 
                        f"cam{i} - {fps_text} ({status})"
                    )

                # 5. Handle Keyboard Input
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                time.sleep(0.001)    
        except KeyboardInterrupt:
            print("\n[Consumer] Interrupted by user.")
        finally:
            self._cleanup()

if __name__ == "__main__":
    camera_names = [SHM_NAME0, SHM_NAME1]
    
    consumer_app = SharedMemoryConsumer(
        shm_names=camera_names, 
        ts_shm_name=TS_SHM_NAME, 
        width=WIDTH, 
        height=HEIGHT
    )
    consumer_app.run()