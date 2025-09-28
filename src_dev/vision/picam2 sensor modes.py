from picamera2 import Picamera2

picam2 = Picamera2(camera_num=1)  # Change to 1 for second camera

print("Available sensor modes:")
for i, mode in enumerate(picam2.sensor_modes):
    res = f"{mode['size'][0]}x{mode['size'][1]}"
    fmt = mode['format']
    fps = mode['fps']
    unpacked = mode['unpacked']
    depth = mode['bit_depth']
    print(f"Mode {i}: {res}, Format: {fmt}, Max FPS: {fps}, unpacked: {unpacked}, depht: {depth}")
