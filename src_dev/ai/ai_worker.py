# ai_worker.py

import time

def main():
    print("[ai] AI worker started.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[ai] Shutting down.")

if __name__ == "__main__":
    main()
