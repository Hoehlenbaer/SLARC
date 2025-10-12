# launch_all.py

import subprocess
import os
import signal
import sys

# Define subprocesses with their venvs and entry scripts
PROCESS_CONFIG = [
    {
        "name": "vision",
        "venv": "/home/admin/projects/slarc/venvs/vision/bin/python",
        "script": "/home/admin/projects/slarc/src_dev/vision/main.py"
    },
    {
        "name": "motion_control",
        "venv": "/home/admin/projects/slarc/venvs/motion_control/bin/python",
        "script": "/home/admin/projects/slarc/src_dev/motion_control/control.py"
    },
    {
        "name": "sensors",
        "venv": "/home/admin/projects/slarc/venvs/sensors/bin/python",
        "script": "/home/admin/projects/slarc/src_dev/sensors/sensor_hub.py"
    },
    {
        "name": "slam",
        "venv": "/home/admin/projects/slarc/venvs/slam/bin/python",
        "script": "/home/admin/projects/slarc/src_dev/slam/slam_worker.py"
    },
    {
        "name": "ai",
        "venv": "/home/admin/projects/slarc/venvs/ai/bin/python",
        "script": "/home/admin/projects/slarc/src_dev/ai/ai_worker.py"
    }
]

processes = []

def launch_all():
    for config in PROCESS_CONFIG:
        print(f"[launcher] Starting {config['name']}...")
        p = subprocess.Popen([config["venv"], config["script"]])
        processes.append(p)

def shutdown_all(sig, frame):
    print("\n[launcher] Shutting down all subprocesses...")
    for p in processes:
        p.terminate()
        p.wait()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown_all)
    launch_all()
    signal.pause()
