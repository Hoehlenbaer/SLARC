# launch_all.py
# version 2.5 - Central Resource Manager (Fix Graceful Shutdown)
#
# Launches all subsystems with proper Shared Memory and Semaphore setup.
# Cleans up resources on shutdown.


import subprocess
import os
import signal
import sys
import time
from multiprocessing import shared_memory
import posix_ipc

# --- 1. CONFIGURATION ---

# Define Paths
SRC_DEV_DIR = "/home/admin/projects/slarc/src_dev"
VISION_MAIN_PATH = os.path.join(SRC_DEV_DIR, "vision", "vision_main.py")
AI_MAIN_PATH = os.path.join(SRC_DEV_DIR, "ai", "ai_main.py")

# Vision System Shared Memory Constants
IN_WIDTH, IN_HEIGHT = 1440, 1080
RAW_BYTES_PER_FRAME = IN_WIDTH * IN_HEIGHT
OUT_WIDTH, OUT_HEIGHT = 640, 480
RGB_SIZE = OUT_WIDTH * OUT_HEIGHT * 3

# POSIX Semaphore Names (Must be unique across the OS)
FRAME_READY_SEM_NAME = "/slarc_vision_frame" # Camera -> Post-Processor
AI_READY_SEM_NAME = "/slarc_ai_ready" # Post-Processor -> AI

# Define subprocesses configuration
PROCESS_CONFIG = [
    {
        "name": "vision", 
        "venv": "/home/admin/projects/slarc/venvs/vision/bin/python",
        "script": VISION_MAIN_PATH,
        "sync_args": [FRAME_READY_SEM_NAME, AI_READY_SEM_NAME]
    },
    {
        "name": "ai", 
        "venv": "/home/admin/projects/slarc/venvs/ai/bin/python",
        "script": AI_MAIN_PATH,
        "sync_args": [AI_READY_SEM_NAME]
    },
    {
        "name": "motion_control",
        "venv": "/home/admin/projects/slarc/venvs/motion_control/bin/python",
        "script": os.path.join(SRC_DEV_DIR, "motion_control", "motion_control_main.py"),
        "sync_args": []
    },
    {
        "name": "sensors",
        "venv": "/home/admin/projects/slarc/venvs/sensors/bin/python",
        "script": os.path.join(SRC_DEV_DIR, "sensors", "sensors_main.py"),
        "sync_args": []
    },
    {
        "name": "slam",
        "venv": "/home/admin/projects/slarc/venvs/slam/bin/python",
        "script": os.path.join(SRC_DEV_DIR, "slam", "slam_main.py"),
        "sync_args": []
    }
]

# Global lists for cleanup
processes = [] # Stores dicts: [{"name": str, "process": Popen object}]
shm_list = []
sem_names = [FRAME_READY_SEM_NAME, AI_READY_SEM_NAME]

# --- 2. RESOURCE MANAGEMENT FUNCTIONS ---

def create_global_shm():
    """Creates all necessary Shared Memory blocks."""
    global shm_list
    print("[launcher] Creating Global Shared Memory Buffers...")
    
    shm_configs = [
        ("cam0_buffer", RAW_BYTES_PER_FRAME), 
        ("cam1_buffer", RAW_BYTES_PER_FRAME), 
        ("ts_buffer", 16),
        ("out_l_buffer", RGB_SIZE), 
        ("out_r_buffer", RGB_SIZE)
    ]
    
    for name, size in shm_configs:
        try:
            shm = shared_memory.SharedMemory(name=name, create=True, size=size)
            shm_list.append(shm)
        except Exception as e:
            print(f"[launcher ERROR] Failed to create SHM '{name}': {e}. Exiting.")
            shutdown_all(None, None)
            sys.exit(1)

def create_posix_semaphores():
    """Creates all necessary POSIX Semaphores."""
    print("[launcher] Creating POSIX Semaphores...")
    for name in sem_names:
        try:
            # Create semaphore with initial value 0
            posix_ipc.Semaphore(name, posix_ipc.O_CREAT, initial_value=0)
            print(f" -> Created semaphore: {name}")
        except Exception as e:
            print(f"[launcher ERROR] Failed to create semaphore {name}: {e}. Exiting.")
            shutdown_all(None, None)
            sys.exit(1)

def launch_all_subsystems():
    """Launches all subsystems using subprocess.Popen."""
    print("[launcher] Starting all subsystems...")
    for config in PROCESS_CONFIG:
        script_path = config["script"]
        
        # Check if file exists before launching
        if not os.path.exists(script_path):
            print(f"[launcher WARNING] Subsystem script '{config['name']}' not found at: {script_path}. Skipping launch.")
            continue
            
        print(f"[launcher] Starting {config['name']} using VENV: {os.path.dirname(os.path.dirname(config['venv']))}...")
        
        # Build command: [venv_python_path, script_path, sync_arg1, sync_arg2, ...]
        command = [config["venv"], script_path] + config["sync_args"]
        
        # Use start_new_session=True to ensure children form their own process group.
        # This is necessary for robust signal handling using os.killpg.
        p = subprocess.Popen(command, start_new_session=True)
        
        # Store process info for clean shutdown
        processes.append({"name": config["name"], "process": p})

def shutdown_all(sig, frame):
    """
    Terminates all running processes gracefully (using SIGINT on process groups) 
    and cleans up resources (SHM/Semaphores).
    """
    print("\n[launcher] Shutting down all subsystems...")
    
    # 1. Gracefully terminate all children by sending SIGINT to their process groups
    # This allows child processes (like vision) to run cleanup code (e.g., release cameras).
    for item in processes:
        p = item["process"]
        name = item["name"] 
        
        if p.poll() is None: # Check if still running
            print(f" -> Gracefully stopping {name} (PID: {p.pid})...")
            
            try:
                # Send SIGINT to the entire process group (PGID is the PID due to start_new_session=True)
                os.killpg(p.pid, signal.SIGINT)
                
                # Wait for the process to exit gracefully
                p.wait(timeout=5)
                print(f" -> {name} terminated successfully.")
                
            except ProcessLookupError:
                 # Process already exited before we could send the signal
                 print(f" -> {name} already exited.")
            except subprocess.TimeoutExpired:
                print(f"   -> WARNING: {name} did not terminate gracefully after SIGINT. Sending SIGKILL...")
                # Fallback to hard kill
                p.kill()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                     print(f"   -> CRITICAL: {name} refused to die.")

    # 2. Clean up Shared Memory (Close and Unlink)
    print(" -> Cleaning up Shared Memory...")
    for shm in shm_list:
        try:
            shm.close()
            shm.unlink()
            print(f"   -> Unlinked {shm.name}")
        except Exception:
            print(f"   -> WARNING: Failed to unlink {shm.name}. It may have already been unlinked.")
            # Allow this to fail silently as it may have been cleaned up by a crash
            pass
            
    # 3. Clean up POSIX Semaphores (Unlink)
    print(" -> Cleaning up POSIX Semaphores...")
    for name in sem_names:
        try:
            posix_ipc.unlink_semaphore(name)
            print(f"   -> Unlinked {name}")
        except Exception:
            # Allow this to fail silently if the semaphore was already unlinked
            pass 
            
    sys.exit(0)

# --- 3. MAIN EXECUTION ---

if __name__ == "__main__":
    # Register the shutdown handler for Ctrl+C
    signal.signal(signal.SIGINT, shutdown_all)

    # 1. Create all global resources
    create_global_shm()
    create_posix_semaphores()
    
    # 2. Launch all systems via Popen
    launch_all_subsystems()
    
    print("\n[launcher] All running subsystems initiated. Press Ctrl+C to stop.")
    
    # Wait indefinitely for a signal
    signal.pause()