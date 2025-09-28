import time
import numpy as np
from icm20948 import ICM20948

imu = ICM20948()

start_time = time.time()
duration = 30  # Sekunden

# Initial min/max values set to None
mag_min = [None, None, None]
mag_max = [None, None, None]

# Example soft-iron scale matrix (diagonal)
soft_iron_matrix = np.array([
    [1.05, 0.0, 0.0],
    [0.0, 0.95, 0.0],
    [0.0, 0.0, 1.10]
])

print("Messung gestartet...")

while time.time() - start_time < duration:
    acc_gyro = imu.read_accelerometer_gyro_data()
    temp = imu.read_temperature()
    mag = imu.read_magnetometer_data()

    # Rundung auf eine Nachkommastelle
    acc_gyro_rounded = tuple(round(val, 1) for val in acc_gyro)
    temp_rounded = round(temp, 1)
    mag_rounded = tuple(round(val, 1) for val in mag)

    # Update min/max values
    for i in range(3):
        if mag_min[i] is None or mag[i] < mag_min[i]:
            mag_min[i] = mag[i]
        if mag_max[i] is None or mag[i] > mag_max[i]:
            mag_max[i] = mag[i]

    # Compute hard-iron bias
    bias = [(mag_max[i] + mag_min[i]) / 2 for i in range(3)]
    bias_rounded = tuple(round(val, 2) for val in bias)

    # Apply hard-iron correction
    mag_corrected = [mag[i] - bias[i] for i in range(3)]

    # Apply soft-iron correction
    mag_corrected_np = np.array(mag_corrected)
    mag_calibrated = soft_iron_matrix @ mag_corrected_np
    mag_calibrated_rounded = tuple(round(val, 1) for val in mag_calibrated)

    # Round min/max for display
    mag_min_rounded = tuple(round(val, 1) for val in mag_min)
    mag_max_rounded = tuple(round(val, 1) for val in mag_max)

    print("Accelerometer:", acc_gyro_rounded)
    print("Temperature:", temp_rounded)
    print("Magnetometer:", mag_rounded)
    print("Magnetometer Min:", mag_min_rounded)
    print("Magnetometer Max:", mag_max_rounded)
    print("Hard-Iron Bias:", bias_rounded)
    print("Soft-Iron Matrix:\n", soft_iron_matrix)
    print("Calibrated Magnetometer:", mag_calibrated_rounded)
    print("-" * 50)

    time.sleep(1)

# Final output
final_bias = [(mag_max[i] + mag_min[i]) / 2 for i in range(3)]
final_bias_rounded = tuple(round(val, 2) for val in final_bias)

print("\n? Messung abgeschlossen nach 30 Sekunden.")
print("Final Magnetometer Min:", tuple(round(val, 1) for val in mag_min))
print("Final Magnetometer Max:", tuple(round(val, 1) for val in mag_max))
print("Final Hard-Iron Bias:", final_bias_rounded)
print("Final Soft-Iron Matrix:\n", soft_iron_matrix)
