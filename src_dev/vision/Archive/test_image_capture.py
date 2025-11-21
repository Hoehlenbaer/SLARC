from picamera2 import Picamera2
import time
import cv2

# Initialize both cameras
cam1 = Picamera2(0)
cam2 = Picamera2(1)

# Fixed exposure and gain settings
controls = {
    "ExposureTime": 15000,         # in microseconds
    "AnalogueGain": 16.0
}

# Configure both cameras for still capture with fixed timing
config1 = cam1.create_video_configuration(controls=controls)
config2 = cam2.create_video_configuration(controls=controls)

cam1.configure(config1)
cam2.configure(config2)

cam1.start()
cam2.start()

# Warm-up
time.sleep(2)

# Capture loop
num_frames = 10
start_time = time.time()

for i in range(num_frames):
    # Capture synchronized frames
    req1 = cam1.capture_request()
    req2 = cam2.capture_request()

    img1 = req1.make_array("main")
    img2 = req2.make_array("main")

    req1.release()
    req2.release()
    cv2.imwrite(f"left{i}.jpg", img1)
    cv2.imwrite(f"right{i}.jpg", img2)
    # Resize for display
    #img1_resized = cv2.resize(img1, (320, 240))
    #img2_resized = cv2.resize(img2, (320, 240))
    #combined = cv2.hconcat([img1_resized, img2_resized])

    #cv2.imshow("HW Triggered Dual Capture", combined)
    #print(f"Frame {i+1} captured")

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

end_time = time.time()
fps = (num_frames) / (end_time - start_time)
print(f"\nAverage FPS: {fps:.2f}")

cam1.stop()
cam2.stop()
cv2.destroyAllWindows()
