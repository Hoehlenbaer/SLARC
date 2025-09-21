import time
import sys
from icm20948 import ICM20948

# Sensor initialisieren
imu = ICM20948()

try:
    while True:
        # Magnetometer-Werte abfragen
        mag_x, mag_y, mag_z = imu.read_magnetometer_data()

        # Ausgabe in einer Zeile mit �berschreiben
        sys.stdout.write(f"\rMagnetometer: X={mag_x:.2f} �T  Y={mag_y:.2f} �T  Z={mag_z:.2f} �T")
        sys.stdout.flush()

        time.sleep(0.1)  # kleine Pause f�r bessere Lesbarkeit
except KeyboardInterrupt:
    print("\nMessung beendet.")
