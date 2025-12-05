# sensor_hub.py

import time

def main():
    print("[sensors] Sensor hub started.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[sensors] Shutting down.")

if __name__ == "__main__":
    main()
