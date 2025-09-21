import time
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import least_squares
from icm20948 import ICM20948

imu = ICM20948()
duration = 60
start_time = time.time()

raw_data = []

plt.ion()
fig = plt.figure(figsize=(12, 6))
ax_raw = fig.add_subplot(121, projection='3d')
ax_cal = fig.add_subplot(122, projection='3d')

def ellipsoid_residuals(params, data):
    x0, y0, z0 = params[0:3]  # center
    a, b, c = params[3:6]     # radii
    shifted = data - np.array([x0, y0, z0])
    scaled = shifted / np.array([a, b, c])
    return np.sum(scaled**2, axis=1) - 1

def fit_ellipsoid(data):
    data = np.array(data)
    x0 = np.mean(data, axis=0)
    radii = np.std(data, axis=0)
    initial = np.concatenate([x0, radii])
    result = least_squares(ellipsoid_residuals, initial, args=(data,))
    center = result.x[0:3]
    scale = result.x[3:6]

    # Preserve magnitude by rescaling
    shifted = data - center
    magnitudes = np.linalg.norm(shifted, axis=1)
    mean_mag = np.mean(magnitudes)
    soft_iron_matrix = np.diag(mean_mag / scale)

    return center, soft_iron_matrix

print("?? Starting robust magnetometer calibration...")

while time.time() - start_time < duration:
    mag = imu.read_magnetometer_data()
    raw_data.append(mag)

    raw_np = np.array(raw_data)

    if len(raw_np) >= 20:
        try:
            bias, soft_iron_matrix = fit_ellipsoid(raw_np)
        except:
            bias = np.mean(raw_np, axis=0)
            soft_iron_matrix = np.eye(3)
    else:
        bias = np.mean(raw_np, axis=0)
        soft_iron_matrix = np.eye(3)

    calibrated_data = []
    for raw in raw_np:
        corrected = np.array(raw) - bias
        calibrated = soft_iron_matrix @ corrected
        calibrated_data.append(calibrated.tolist())
    cal_np = np.array(calibrated_data)

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

    mean_cal_mag = np.mean(np.linalg.norm(cal_np, axis=1))
    print(f"Hard-Iron Bias: {[round(b, 2) for b in bias]}")
    print("Soft-Iron Matrix:\n", np.round(soft_iron_matrix, 3))
    print(f"Mean Calibrated Magnitude: {round(mean_cal_mag, 2)} �T")
    print("-" * 40)

    plt.pause(0.01)
    time.sleep(0.1)

print("? Measurement complete.")
print("Final Hard-Iron Bias:", [round(b, 2) for b in bias])
print("Final Soft-Iron Matrix:\n", np.round(soft_iron_matrix, 3))

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
