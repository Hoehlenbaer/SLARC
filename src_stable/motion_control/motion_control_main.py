# control.py

import time

def main():
    print("[motion_control] Control module started.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[motion_control] Shutting down.")

if __name__ == "__main__":
    main()
