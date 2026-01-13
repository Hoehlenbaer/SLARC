# ai/ai_main.py
# version 2.0 - AI Subsystem Launcher with Parallel Inference
#
# This script initializes the AI subsystem, runs three parallel inferences 
# (Object Detection, Semantic Segmentation, Stereo Depth) on a Hailo-8,
# and prepares the data for the post-processor.

import sys
import os
import time
from multiprocessing import shared_memory
import numpy as np
import posix_ipc 
import cv2 # <-- NEW: For visualization
from concurrent.futures import ProcessPoolExecutor # <-- NEW: For parallel execution

# --- Hailo TAPPAS Integration (Assumed) ---
# In a real application, you would import the necessary Hailo libraries here.
# from hailo_platform import VDevice, HailoStreamInterface, InferVStreams
# For this example, we will simulate the inference calls.

# Configuration constants (Needed for SHM access)
OUT_WIDTH, OUT_HEIGHT = 640, 480
# Visualization output size
VIS_WIDTH, VIS_HEIGHT = 1280, 720 # A wider canvas for side-by-side visualization

# --- 1. Inference Functions (to be run in parallel) ---

def run_object_detection(image_np: np.ndarray) -> list:
    """
    Performs object detection using YOLOv5 on the Hailo-8.
    
    Args:
        image_np (np.ndarray): The input image for inference.

    Returns:
        list: A list of detections, e.g., [{'box': [x1, y1, x2, y2], 'class_id': id, 'confidence': conf}, ...].
    """
    # NOTE: Your Hailo TAPPAS inference logic for YOLOv5 goes here.
    # This will involve preparing the input tensor, running the inference,
    # and post-processing the output tensors to get bounding boxes.
    
    print("    [AI-YOLO] Running inference...")
    time.sleep(0.025) # Simulate Hailo inference time
    print("    [AI-YOLO] Inference complete.")
    
    # --- SIMULATED DUMMY OUTPUT ---
    # In a real scenario, this data comes from the model's output.
    dummy_detections = [
        {'box': [100, 150, 250, 400], 'class_id': 2, 'confidence': 0.92},
        {'box': [400, 220, 500, 380], 'class_id': 5, 'confidence': 0.88},
    ]
    return dummy_detections

def run_semantic_segmentation(image_np: np.ndarray) -> np.ndarray:
    """
    Performs semantic segmentation using Fast-SCNN on the Hailo-8.
    
    Args:
        image_np (np.ndarray): The input image for inference.

    Returns:
        np.ndarray: A 2D numpy array (mask) where each pixel value is the class ID.
    """
    # NOTE: Your Hailo TAPPAS inference logic for Fast-SCNN goes here.
    # This involves pre-processing, inference, and getting the segmentation map.
    
    print("    [AI-SEG] Running inference...")
    time.sleep(0.028) # Simulate Hailo inference time
    print("    [AI-SEG] Inference complete.")

    # --- SIMULATED DUMMY OUTPUT ---
    # Create a dummy segmentation map (e.g., class 1 for top half, class 2 for bottom)
    mask = np.ones((OUT_HEIGHT, OUT_WIDTH), dtype=np.uint8) * 2
    mask[:OUT_HEIGHT // 2, :] = 1
    return mask

def run_stereo_depth(left_img: np.ndarray, right_img: np.ndarray) -> np.ndarray:
    """
    Performs stereo depth estimation using CREStereo on the Hailo-8.
    
    Args:
        left_img (np.ndarray): The left stereo image.
        right_img (np.ndarray): The right stereo image.

    Returns:
        np.ndarray: A 2D numpy array representing the depth map.
    """
    # NOTE: Your Hailo TAPPAS inference logic for CREStereo goes here.
    # The two images will need to be pre-processed into a single tensor for the model.
    
    print("    [AI-DEPTH] Running inference...")
    time.sleep(0.035) # Simulate Hailo inference time
    print("    [AI-DEPTH] Inference complete.")

    # --- SIMULATED DUMMY OUTPUT ---
    # Create a dummy depth map (gradient from far to near)
    depth_map = np.zeros((OUT_HEIGHT, OUT_WIDTH), dtype=np.float32)
    gradient = np.linspace(255, 0, OUT_WIDTH)
    for i in range(OUT_HEIGHT):
        depth_map[i, :] = gradient
    return depth_map

# --- 2. Data Processing & Visualization ---

def combine_and_extract_data(detections: list, depth_map: np.ndarray) -> list:
    """
    Combines detection and depth data to estimate 3D coordinates.
    
    Args:
        detections (list): List of object detections from YOLO.
        depth_map (np.ndarray): Depth map from CREStereo.
        
    Returns:
        list: A list of objects with combined data, including estimated 3D coords.
    """
    processed_objects = []
    for det in detections:
        box = det['box']
        # Get the center of the bounding box
        cx = int((box[0] + box[2]) / 2)
        cy = int((box[1] + box[3]) / 2)
        
        # Get depth value at the center of the box
        # NOTE: A more robust method would average depth over a small area
        # or use a more advanced fusion technique.
        depth_value = depth_map[cy, cx]
        
        # NOTE: To get real-world 3D coordinates (X, Y, Z), you need the
        # camera's intrinsic parameters (focal length, principal point).
        # Z = depth_value
        # X = (cx - principal_point_x) * Z / focal_length_x
        # Y = (cy - principal_point_y) * Z / focal_length_y
        
        processed_objects.append({
            'class_id': det['class_id'],
            'bounding_box_2d': box,
            'confidence': det['confidence'],
            'estimated_depth_m': float(depth_value), # Replace with calculated Z
            'estimated_coords_3d': [0.0, 0.0, float(depth_value)] # Replace with (X,Y,Z)
        })
    print("[AI] Combined detection and depth data.")
    return processed_objects

def create_visualization(left_img: np.ndarray, detections: list, seg_mask: np.ndarray, depth_map: np.ndarray) -> np.ndarray:
    """Creates a combined visualization image."""
    
    # 1. Draw detections on the left image
    vis_img = left_img.copy()
    for det in detections:
        box = [int(c) for c in det['box']]
        cv2.rectangle(vis_img, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
        label = f"ID: {det['class_id']} ({det['confidence']:.2f})"
        cv2.putText(vis_img, label, (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
    # 2. Overlay segmentation mask
    # Create a color map for segmentation classes (e.g., class 1: blue, class 2: green)
    seg_color_map = np.zeros((OUT_HEIGHT, OUT_WIDTH, 3), dtype=np.uint8)
    seg_color_map[seg_mask == 1] = [255, 0, 0] # Blue
    seg_color_map[seg_mask == 2] = [0, 255, 0] # Green
    vis_img = cv2.addWeighted(vis_img, 0.6, seg_color_map, 0.4, 0)

    # 3. Create a colorized depth map for visualization
    depth_vis = cv2.applyColorMap((depth_map / np.max(depth_map) * 255).astype(np.uint8), cv2.COLORMAP_JET)
    
    # 4. Combine the two images side-by-side into a wider canvas
    combined_vis = np.zeros((VIS_HEIGHT, VIS_WIDTH, 3), dtype=np.uint8)
    # Resize and place main visualization
    resized_vis = cv2.resize(vis_img, (OUT_WIDTH, OUT_HEIGHT))
    combined_vis[0:OUT_HEIGHT, 0:OUT_WIDTH] = resized_vis
    # Resize and place depth map
    resized_depth = cv2.resize(depth_vis, (OUT_WIDTH, OUT_HEIGHT))
    combined_vis[0:OUT_HEIGHT, OUT_WIDTH:OUT_WIDTH*2] = resized_depth
    
    print("[AI] Created visualization frame.")
    # You could write this image to another SHM buffer for a display process.
    
    return combined_vis

# --- 3. Main AI Subsystem ---

def start_ai_subsystem(ai_ready_sem, executor):
    """
    Entry point for the AI subsystem. Attaches to SHM and synchronizes via semaphore.
    """
    print("[AI] AI Subsystem started. Waiting for rectified images...")
    
    try:
        shm_out_l = shared_memory.SharedMemory(name="out_l_buffer")
        shm_out_r = shared_memory.SharedMemory(name="out_r_buffer")
        
        left_img_array = np.ndarray((OUT_HEIGHT, OUT_WIDTH, 3), dtype=np.uint8, buffer=shm_out_l.buf)
        right_img_array = np.ndarray((OUT_HEIGHT, OUT_WIDTH, 3), dtype=np.uint8, buffer=shm_out_r.buf)
        
    except FileNotFoundError as e:
        print(f"[AI ERROR] Failed to attach to Shared Memory: {e.name}. Exiting.")
        sys.exit(1)
        
    try:
        frame_count = 0
        while True:
            ai_ready_sem.acquire() 
            
            print(f"\n[AI] Frame {frame_count}: New stereo frame received. Launching parallel inferences...")
            
            # --- PARALLEL INFERENCE ---
            # Submit all three tasks to the process pool executor
            future_yolo = executor.submit(run_object_detection, left_img_array)
            future_seg = executor.submit(run_semantic_segmentation, left_img_array)
            future_depth = executor.submit(run_stereo_depth, left_img_array, right_img_array)
            
            # --- COLLECT RESULTS ---
            # .result() blocks until the respective future is complete
            detections = future_yolo.result()
            segmentation_mask = future_seg.result()
            depth_map = future_depth.result()
            
            print("[AI] All inferences complete. Processing results.")
            
            # --- PROCESS & VISUALIZE ---
            # This data can be sent to another subprogram via SHM or other IPC
            final_output_data = combine_and_extract_data(detections, depth_map)
            print(f"[AI] Final Processed Data: {final_output_data}")

            # Create a visualization image
            vis_frame = create_visualization(left_img_array, detections, segmentation_mask, depth_map)
            
            # For demonstration, we'll just save the first frame
            if frame_count == 0:
                cv2.imwrite("ai_visualization_output.jpg", vis_frame)
                print("[AI] Saved visualization of first frame to 'ai_visualization_output.jpg'")

            frame_count += 1

    except KeyboardInterrupt:
        pass
    finally:
        shm_out_l.close()
        shm_out_r.close()
        print("[AI] Subsystem shutting down.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("ERROR: Missing POSIX semaphore name. Usage: python ai_main.py <ai_sem_name>")
        sys.exit(1)
        
    ai_ready_sem_name = sys.argv[1]
    
    try:
        ai_ready_sem = posix_ipc.Semaphore(ai_ready_sem_name)
    except posix_ipc.ExistentialError:
        print("ERROR: Could not attach to POSIX semaphore. Ensure launch_all.py is running.")
        sys.exit(1)
        
    # --- Create a process pool that will run the inference tasks ---
    # Using max_workers=3 ensures one process for each of our three tasks.
    with ProcessPoolExecutor(max_workers=3) as executor:
        start_ai_subsystem(ai_ready_sem, executor)
