import time
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from icm20948 import ICM20948

imu = ICM20948()

start_time = time.time()
duration = 30  # Sekunden

mag_min = [None, None, None]
mag_max = [None, None, None]
mag_data = []

while time.time() - start_time < duration:
    mag = imu.read_magnetometer_data()
    mag_rounded = tuple(round(val, 1) for val in mag)
    mag_data.append(mag_rounded)

    for i in range(3):
        if mag_min[i] is None or mag[i] < mag_min[i]:
            mag_min[i] = mag[i]
        if mag_max[i] is None or mag[i] > mag_max[i]:
            mag_max[i] = mag[i]

    print("Magnetometer:", mag_rounded)
    print("Magnetometer Min:", tuple(round(val, 1) for val in mag_min))
    print("Magnetometer Max:", tuple(round(val, 1) for val in mag_max))
    print("-" * 40)

    time.sleep(1)

print("Messung abgeschlossen nach 30 Sekunden.")
print("Final Magnetometer Min:", tuple(round(val, 1) for val in mag_min))
print("Final Magnetometer Max:", tuple(round(val, 1) for val in mag_max))

# ?? Visualization
x_vals = [point[0] for point in mag_data]
y_vals = [point[1] for point in mag_data]
z_vals = [point[2] for point in mag_data]

fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')
ax.scatter(x_vals, y_vals, z_vals, c='blue', marker='o')

ax.set_xlabel('Mag X (�T)')
ax.set_ylabel('Mag Y (�T)')
ax.set_zlabel('Mag Z (�T)')
ax.set_title('3D Magnetometer Readings (Raw)')

plt.show()
