import numpy as np
import time
import os
from multiprocessing.shared_memory import SharedMemory
from picamera2 import Picamera2
from libcamera import controls

# --- CONFIGURATION CONSTANTS (FINAL CORRECTION) ---
CAM0_ID = 0
CAM1_ID = 1
FPS = 5.0 

# RAW Data Type and Format
RAW_DTYPE = np.uint16 # 2 bytes per element
RAW_FORMAT = "R16" 

# CRITICAL CORRECTION: Use the exact 'framesize' reported by the camera.
# This value (3203072) is the total BYTES required for a single raw frame.
FRAME_SIZE = 3203072 

# The number of 16-bit elements (pixels) the camera buffer contains.
# This is the size in elements for the 1D NumPy array view (shm_flat0).
# Calculation: 3203072 bytes / 2 bytes/element = 1601536 elements
RAW_ELEMENTS = FRAME_SIZE // RAW_DTYPE().itemsize # Should be 1601536 

# Nominal Resolution (Used ONLY for camera configuration, not for memory size)
# You can keep this for configuration purposes, but do NOT use them 
# to calculate memory size, as the stride/padding is included in FRAME_SIZE.
RAW_HEIGHT = 1088
RAW_WIDTH = 1456


# Shared Memory Names
SHM_NAME0 = "CAM0_SHM"
SHM_NAME1 = "CAM1_SHM"


# --- CAMERA SETUP FUNCTION ---

def setup_camera(camera_id, frame_rate):
    """Initializes and configures a single Picamera2 for raw capture (R16) and external control."""
    try:
        # CORRECTION: Use 'camera_num' based on troubleshooting
        picam2 = Picamera2(camera_num=camera_id)
        
        # 1. Create a configuration for a high-resolution raw stream (R16)
        config = picam2.create_still_configuration(
            # Request the full resolution raw stream with the R16 format
            raw={"size": (RAW_WIDTH, RAW_HEIGHT), "format": RAW_FORMAT},
            buffer_count=4 # Use multiple buffers for smooth capture
        )
        
        # 2. Configure controls (Assuming external trigger is set in libcamera JSON config)
        trigger_controls = {
            "FrameRate": frame_rate,
            "ExposureTime": 10000,      # Example exposure time (10ms)
            "AnalogueGain": 1.0         # Minimal gain
            # WARNING: FrameTrigger is REMOVED as libcamera does not advertise it
        }
        
        # Merge the controls into the configuration dictionary
        if "controls" not in config:
            config["controls"] = {}
        config["controls"].update(trigger_controls)
        
        # 3. Apply the configuration
        picam2.configure(config)
        print(f"Camera {camera_id} configured. Raw format: {RAW_FORMAT} @ {RAW_WIDTH}x{RAW_HEIGHT}.")
        print(picam2.camera_configuration()['raw'])
        print(picam2.camera_configuration()['sensor'])
        return picam2

    except Exception as e:
        print(f"Error setting up camera {camera_id}: {e}")
        # Terminate if setup fails
        exit(1)

# --- CAPTURE LOOP FUNCTION ---

def capture_streams(picam0: Picamera2, picam1: Picamera2, shm_cam0: SharedMemory, shm_cam1: SharedMemory, num_frames=10):
    
    # 1. Create a 1D, flat view of the shared memory buffers (shape: 1601536, dtype: np.uint16)
    shm_flat0 = np.ndarray((RAW_ELEMENTS,), dtype=RAW_DTYPE, buffer=shm_cam0.buf)
    shm_flat1 = np.ndarray((RAW_ELEMENTS,), dtype=RAW_DTYPE, buffer=shm_cam1.buf)

    try:
        # ... (start cameras) ...
        picam0.start()
        picam1.start()
        print(f"\nCameras started. Awaiting external triggers for {num_frames} frames...")

        for i in range(num_frames):
            
            
            # --- Capture Requests ---
            request0 = picam0.capture_request()
            request1 = picam1.capture_request()

            # --- Process Camera 0 ---
            # Step 1: Get the array. This is returning a 2D array (1088, 1472) of np.uint16, 
            # OR a 1D array of np.uint8 (3203072,) that you need to fix.
            # We will use the most explicit method: get the array, then ensure the type is correct.
            buffer0 = request0.make_array('raw')
            
            # Step 2: Use .view(RAW_DTYPE).flatten() for maximum safety.
            # The .view() interprets the underlying data as 16-bit elements.
            # The .flatten() ensures the final shape is 1D (1601536,) for the copy.
            buffer0_aligned = buffer0.view(RAW_DTYPE).flatten() 
            
            # Diagnostic check (optional, but highly recommended)
            #print(f"[DIAG] Source Aligned Shape: {buffer0_aligned.shape}")
            #print(f"[DIAG] Source Aligned Dtype: {buffer0_aligned.dtype}")

            # The shapes now match: (1601536,) into (1601536,)
            np.copyto(shm_flat0, buffer0_aligned) 
            
            # --- Process Camera 1 ---
            buffer1 = request1.make_array('raw')
            buffer1_aligned = buffer1.view(RAW_DTYPE).flatten()
            np.copyto(shm_flat1, buffer1_aligned)

            # --- Cleanup and Timing ---
            request0.release()
            request1.release()
            
            
            
    except Exception as e:
        print(f"\n🛑 !!! CAPTURE FAILURE at Frame {i+1} !!!")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {e}")
        print("Check shared memory size and array dimensions.")
        
    finally:
        # Ensure cameras are stopped regardless of error
        print("\nStopping cameras and cleaning up...")
        try:
            picam0.stop()
        except:
            print(f"Warning: Failed to cleanly stop picam0 ({CAM0_ID}).")
        try:
            picam1.stop()
        except:
            print(f"Warning: Failed to cleanly stop picam1 ({CAM1_ID}).")
        
        print("Capture streams terminated.")

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    
    # 1. Setup Cameras
    camera0 = setup_camera(CAM0_ID, FPS)
    camera1 = setup_camera(CAM1_ID, FPS)

    # 2. Setup Shared Memory
    shm_cam0 = None
    shm_cam1 = None

    try:
        print("\nSetting up shared memory...")
        # Create shared memory segments (create=True)
        shm_cam0 = SharedMemory(name=SHM_NAME0, create=True, size=FRAME_SIZE)
        shm_cam1 = SharedMemory(name=SHM_NAME1, create=True, size=FRAME_SIZE)
        
        print(f"Shared Memory allocated: {SHM_NAME0} and {SHM_NAME1} ({FRAME_SIZE} bytes each).")

        # 3. Run Capture Loop
        num_frames=50
        start_time = time.time()
        capture_streams(camera0, camera1, shm_cam0, shm_cam1, num_frames=num_frames) # Capture 50 frames
        end_time = time.time()
        print(f"{num_frames} frames captured and copied in {(end_time - start_time)*1000:.2f}ms.")
    except FileExistsError:
        print(f"\nError: Shared memory segments {SHM_NAME0} or {SHM_NAME1} already exist.")
        print("Please ensure any previous run has properly unlinked the shared memory.")
        
    except Exception as e:
        print(f"\nAn unhandled error occurred in the main script: {e}")

    finally:
        # 4. Clean up shared memory: UNLINK (This MUST happen only when you are completely done)
        if shm_cam0:
            shm_cam0.close()
            shm_cam0.unlink()
            print(f"Shared memory {SHM_NAME0} unlinked.")
        if shm_cam1:
            shm_cam1.close()
            shm_cam1.unlink()
            print(f"Shared memory {SHM_NAME1} unlinked.")
            
        print("\nProgram finished.")