# slam_worker.py

import time

def main():
    print("[slam] SLAM worker started.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[slam] Shutting down.")

if __name__ == "__main__":
    main()
