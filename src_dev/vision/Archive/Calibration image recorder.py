import socket
import time

HOST = '192.168.178.44'  # IP-Adresse deines Jetbot
PORT = 65432             # Muss mit dem Server-Port �bereinstimmen

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    print("Verbunden mit Jetbot")
    while True:
        # Define coordinate ranges
        x_start, x_end, x_step = 1600, 2600, 100
        y_start, y_end, y_step = 1648, 2448, 100

        try:
            for y in range(y_start, y_end + 1, y_step):
                for x in range(x_start, x_end + 1, x_step):
                    pos1 = x
                    pos2 = y
                    message = f"{pos1},{pos2}"
                    s.sendall(message.encode())
                    time.sleep(1)
        finally:
            s.close()