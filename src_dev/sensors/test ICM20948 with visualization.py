import time
import numpy as np
import matplotlib.pyplot as plt
from icm20948 import ICM20948

imu = ICM20948()

duration = 30  # seconds
start_time = time.time()

raw_data = []
mag_min = [None, None, None]
mag_max = [None, None, None]

# Soft-iron scale matrix (diagonal)
soft_iron_matrix = np.array([
    [1.05, 0.0, 0.0],
    [0.0, 0.95, 0.0],
    [0.0, 0.0, 1.10]
])

# Setup live plot
plt.ion()
fig = plt.figure(figsize=(12, 6))
ax_raw = fig.add_subplot(121, projection='3d')
ax_cal = fig.add_subplot(122, projection='3d')

print("?? Starting live magnetometer visualization...")

while time.time() - start_time < duration:
    mag = imu.read_magnetometer_data()
    raw_data.append(mag)

    # Update min/max
    for i in range(3):
        if mag_min[i] is None or mag[i] < mag_min[i]:
            mag_min[i] = mag[i]
        if mag_max[i] is None or mag[i] > mag_max[i]:
            mag_max[i] = mag[i]

    # Compute current bias
    bias = [(mag_max[i] + mag_min[i]) / 2 for i in range(3)]

    # Recompute calibrated data from all raw points
    calibrated_data = []
    for raw in raw_data:
        corrected = np.array([raw[i] - bias[i] for i in range(3)])
        calibrated = soft_iron_matrix @ corrected
        calibrated_data.append(calibrated.tolist())

    # Convert to numpy arrays
    raw_np = np.array(raw_data)
    cal_np = np.array(calibrated_data)

    # Clear and redraw plots
    ax_raw.cla()
    ax_raw.set_title("Raw Magnetometer Data")
    ax_raw.set_xlabel("X (�T)")
    ax_raw.set_ylabel("Y (�T)")
    ax_raw.set_zlabel("Z (�T)")
    ax_raw.scatter(raw_np[:,0], raw_np[:,1], raw_np[:,2], c='r')

    ax_cal.cla()
    ax_cal.set_title("Calibrated Magnetometer Data")
    ax_cal.set_xlabel("X (�T)")
    ax_cal.set_ylabel("Y (�T)")
    ax_cal.set_zlabel("Z (�T)")
    ax_cal.scatter(cal_np[:,0], cal_np[:,1], cal_np[:,2], c='g')

    plt.pause(0.01)

    print(f"Hard-Iron Bias: {[round(b, 2) for b in bias]}")
    print("Soft-Iron Matrix:\n", soft_iron_matrix)
    print("-" * 40)
    time.sleep(1)

# Final bias and calibration
final_bias = [(mag_max[i] + mag_min[i]) / 2 for i in range(3)]
final_bias_rounded = [round(b, 2) for b in final_bias]

calibrated_data = []
for raw in raw_data:
    corrected = np.array([raw[i] - final_bias[i] for i in range(3)])
    calibrated = soft_iron_matrix @ corrected
    calibrated_data.append(calibrated.tolist())

raw_np = np.array(raw_data)
cal_np = np.array(calibrated_data)

print("? Measurement complete.")
print("Final Magnetometer Min:", [round(val, 1) for val in mag_min])
print("Final Magnetometer Max:", [round(val, 1) for val in mag_max])
print("Final Hard-Iron Bias:", final_bias_rounded)
print("Final Soft-Iron Matrix:\n", soft_iron_matrix)

# Final static plot
plt.ioff()
fig_final = plt.figure(figsize=(12, 6))

ax1 = fig_final.add_subplot(121, projection='3d')
ax1.scatter(raw_np[:,0], raw_np[:,1], raw_np[:,2], c='r')
ax1.set_title("Final Raw Magnetometer Data")
ax1.set_xlabel("X (�T)")
ax1.set_ylabel("Y (�T)")
ax1.set_zlabel("Z (�T)")

ax2 = fig_final.add_subplot(122, projection='3d')
ax2.scatter(cal_np[:,0], cal_np[:,1], cal_np[:,2], c='g')
ax2.set_title("Final Calibrated Magnetometer Data")
ax2.set_xlabel("X (�T)")
ax2.set_ylabel("Y (�T)")
ax2.set_zlabel("Z (�T)")

plt.tight_layout()
plt.show()
