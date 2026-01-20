# ai/ai_main.py
# version 2.2 - AI Subsystem with Full Parallel TAPPAS Integration
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
import cv2
from concurrent.futures import ProcessPoolExecutor

# --- Hailo TAPPAS Imports ---
from hailo_platform import (VDevice, HailoStreamInterface, InferVStreams,
                            HEF, FormatType)
# --- Hailo Model Zoo Post-processing Imports ---
from hailo_model_zoo.postprocessing.yolov5_postprocessing import yolov5_postprocessing
# NOTE: The exact names for the postprocessing functions below may vary slightly
# depending on your Hailo Model Zoo version. Adjust if necessary.
from hailo_model_zoo.postprocessing.fast_scnn_postprocessing import fast_scnn_postprocessing 
from hailo_model_zoo.postprocessing.crestereo_postprocessing import crestereo_postprocessing

# --- Configuration ---
OUT_WIDTH, OUT_HEIGHT = 640, 480
VIS_WIDTH, VIS_HEIGHT = 1280, 720

# --- IMPORTANT: Set the paths to your compiled HEF files ---
YOLO_HEF_PATH = "/path/to/your/yolov5m.hef"
SEGMENTATION_HEF_PATH = "/path/to/your/fast_scnn.hef"
STEREO_DEPTH_HEF_PATH = "/path/to/your/crestereo.hef"

# --- Global objects for the worker processes ---
# These will be initialized once per worker by init_worker()
detector = None
segmenter = None
depth_estimator = None

# --- 1. Hailo Inference Classes ---

class HailoInference:
    """Base class for managing a Hailo inference model."""
    def __init__(self, hef_path):
        if not os.path.exists(hef_path):
            raise FileNotFoundError(f"HEF file not found: {hef_path}")
            
        self.hef = HEF(hef_path)
        self.hef.activate()
        
        self.input_vstream_infos = self.hef.get_input_vstream_infos()
        self.output_vstream_infos = self.hef.get_output_vstream_infos()
        
        self.model_name = self.hef.get_config().model.model_name
        
        self.vdevice = VDevice()
        self.vstreams = InferVStreams(self.vdevice, self.hef)
        self.infer_job = self.vstreams.infer_async
        
        print(f"[AI-INIT PID: {os.getpid()}] Model '{self.model_name}' initialized.")

    def release(self):
        """Release Hailo resources."""
        self.vstreams.release()
        self.vdevice.release()
        print(f"[AI-INIT PID: {os.getpid()}] Model '{self.model_name}' resources released.")

class ObjectDetector(HailoInference):
    """Manages YOLOv5 object detection."""
    def __init__(self, hef_path):
        super().__init__(hef_path)
        self.input_shape = self.input_vstream_infos[0].shape
        self.postprocess_config = self.hef.get_config().postprocess

    def _preprocess(self, image_np: np.ndarray) -> np.ndarray:
        model_height, model_width = self.input_shape[1], self.input_shape[2]
        resized_image = cv2.resize(image_np, (model_width, model_height), interpolation=cv2.INTER_AREA)
        return np.expand_dims(resized_image, axis=0)
    
    def infer(self, image_np: np.ndarray) -> list:
        input_tensor = self._preprocess(image_np)
        raw_results = self.infer_job({self.input_vstream_infos[0].name: input_tensor})
        detections = yolov5_postprocessing(raw_results, self.postprocess_config,
                                           image_height=image_np.shape[0], image_width=image_np.shape[1])
        return [{'box': det.get_bbox(), 'class_id': det.get_label(), 'confidence': det.get_confidence()} for det in detections]

class SemanticSegmenter(HailoInference):
    """Manages Fast-SCNN semantic segmentation."""
    def __init__(self, hef_path):
        super().__init__(hef_path)
        self.input_shape = self.input_vstream_infos[0].shape

    def _preprocess(self, image_np: np.ndarray) -> np.ndarray:
        model_height, model_width = self.input_shape[1], self.input_shape[2]
        resized_image = cv2.resize(image_np, (model_width, model_height), interpolation=cv2.INTER_AREA)
        return np.expand_dims(resized_image, axis=0)

    def infer(self, image_np: np.ndarray) -> np.ndarray:
        input_tensor = self._preprocess(image_np)
        raw_results = self.infer_job({self.input_vstream_infos[0].name: input_tensor})
        # Post-processing for segmentation often returns the mask directly
        segmentation_mask = fast_scnn_postprocessing(raw_results)
        # Resize mask back to original image size
        return cv2.resize(segmentation_mask, (image_np.shape[1], image_np.shape[0]), interpolation=cv2.INTER_NEAREST)

class StereoDepthEstimator(HailoInference):
    """Manages CREStereo depth estimation."""
    def __init__(self, hef_path):
        super().__init__(hef_path)
        self.input_shape = self.input_vstream_infos[0].shape # e.g., (1, H, W, 6)

    def _preprocess(self, left_img: np.ndarray, right_img: np.ndarray) -> np.ndarray:
        model_height, model_width = self.input_shape[1], self.input_shape[2]
        # Resize both images
        left_resized = cv2.resize(left_img, (model_width, model_height), interpolation=cv2.INTER_AREA)
        right_resized = cv2.resize(right_img, (model_width, model_height), interpolation=cv2.INTER_AREA)
        # Concatenate along the channel axis (from 3+3 to 6)
        input_tensor = np.concatenate([left_resized, right_resized], axis=2)
        return np.expand_dims(input_tensor, axis=0)

    def infer(self, left_img: np.ndarray, right_img: np.ndarray) -> np.ndarray:
        input_tensor = self._preprocess(left_img, right_img)
        raw_results = self.infer_job({self.input_vstream_infos[0].name: input_tensor})
        # Post-processing returns the disparity or depth map
        depth_map = crestereo_postprocessing(raw_results)
        # Resize map back to original image size
        return cv2.resize(depth_map, (left_img.shape[1], left_img.shape[0]), interpolation=cv2.INTER_AREA)

# --- 2. Worker Initialization and Inference Functions ---

def init_worker():
    """Initializer for each worker in the ProcessPoolExecutor."""
    global detector, segmenter, depth_estimator
    print(f"[Worker PID: {os.getpid()}] Initializing Hailo models...")
    detector = ObjectDetector(YOLO_HEF_PATH)
    segmenter = SemanticSegmenter(SEGMENTATION_HEF_PATH)
    depth_estimator = StereoDepthEstimator(STEREO_DEPTH_HEF_PATH)

def run_object_detection(image_np: np.ndarray) -> list:
    """Worker function to perform object detection."""
    start_time = time.time()
    detections = detector.infer(image_np)
    duration = time.time() - start_time
    print(f"    [AI-YOLO PID: {os.getpid()}] Inference complete in {duration:.3f}s. Found {len(detections)} objects.")
    return detections

def run_semantic_segmentation(image_np: np.ndarray) -> np.ndarray:
    """Worker function to perform semantic segmentation."""
    start_time = time.time()
    mask = segmenter.infer(image_np)
    duration = time.time() - start_time
    print(f"    [AI-SEG PID: {os.getpid()}] Inference complete in {duration:.3f}s.")
    return mask

def run_stereo_depth(left_img: np.ndarray, right_img: np.ndarray) -> np.ndarray:
    """Worker function to perform stereo depth estimation."""
    start_time = time.time()
    depth_map = depth_estimator.infer(left_img, right_img)
    duration = time.time() - start_time
    print(f"    [AI-DEPTH PID: {os.getpid()}] Inference complete in {duration:.3f}s.")
    return depth_map

# --- 3. Data Processing & Visualization (Unchanged) ---
def combine_and_extract_data(detections: list, depth_map: np.ndarray) -> list:
    """Combines detection and depth data to estimate 3D coordinates."""
    processed_objects = []
    for det in detections:
        box = det['box']
        cx, cy = int((box[0] + box[2]) / 2), int((box[1] + box[3]) / 2)
        
        # Ensure coordinates are within bounds
        if 0 <= cy < depth_map.shape[0] and 0 <= cx < depth_map.shape[1]:
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
                'estimated_depth_m': float(depth_value),
                'estimated_coords_3d': [0.0, 0.0, float(depth_value)] # Replace with calculated (X,Y,Z)
            })
    print("[AI] Combined detection and depth data.")
    return processed_objects

def create_visualization(left_img: np.ndarray, detections: list, seg_mask: np.ndarray, depth_map: np.ndarray) -> np.ndarray:
    """Creates a combined visualization image."""
    vis_img = left_img.copy()
    
    # Draw detections
    for det in detections:
        box = [int(c) for c in det['box']]
        cv2.rectangle(vis_img, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
        label = f"ID: {det['class_id']} ({det['confidence']:.2f})"
        cv2.putText(vis_img, label, (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
    # Overlay segmentation mask
    seg_color_map = np.zeros((OUT_HEIGHT, OUT_WIDTH, 3), dtype=np.uint8)
    # Example colors (customize based on your model's classes)
    seg_color_map[seg_mask == 1] = [255, 0, 0] # Class 1: Blue
    seg_color_map[seg_mask == 7] = [0, 255, 0] # Class 7: Green (e.g., vegetation)
    vis_img = cv2.addWeighted(vis_img, 0.6, seg_color_map, 0.4, 0)

    # Colorize depth map
    depth_vis = cv2.applyColorMap(np.clip(depth_map, 0, 255).astype(np.uint8), cv2.COLORMAP_JET)
    
    # Combine images side-by-side
    combined_vis = np.zeros((VIS_HEIGHT, VIS_WIDTH, 3), dtype=np.uint8)
    resized_vis = cv2.resize(vis_img, (OUT_WIDTH, OUT_HEIGHT))
    combined_vis[0:OUT_HEIGHT, 0:OUT_WIDTH] = resized_vis
    resized_depth = cv2.resize(depth_vis, (OUT_WIDTH, OUT_HEIGHT))
    combined_vis[0:OUT_HEIGHT, OUT_WIDTH:OUT_WIDTH*2] = resized_depth
    
    print("[AI] Created visualization frame.")
    return combined_vis

# --- 4. Main AI Subsystem Logic (Unchanged) ---
def start_ai_subsystem(ai_ready_sem, executor):
    """Entry point for the AI subsystem."""
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
            
            future_yolo = executor.submit(run_object_detection, left_img_array)
            future_seg = executor.submit(run_semantic_segmentation, left_img_array)
            future_depth = executor.submit(run_stereo_depth, left_img_array, right_img_array)
            
            detections = future_yolo.result()
            segmentation_mask = future_seg.result()
            depth_map = future_depth.result()
            
            print("[AI] All inferences complete. Processing results.")
            
            final_output_data = combine_and_extract_data(detections, depth_map)
            print(f"[AI] Final Processed Data sample: {final_output_data[:2]}") # Print first 2 objects

            vis_frame = create_visualization(left_img_array, detections, segmentation_mask, depth_map)
            if frame_count % 10 == 0: # Save visualization every 10 frames
                cv2.imwrite(f"ai_visualization_output_{frame_count}.jpg", vis_frame)
                print(f"[AI] Saved visualization of frame {frame_count}")
            
            frame_count += 1
    except KeyboardInterrupt:
        pass
    finally:
        shm_out_l.close()
        shm_out_r.close()
        print("[AI] Subsystem shutting down.")

if __name__ == "__main__":
    # --- Pre-launch checks ---
    hef_paths = [YOLO_HEF_PATH, SEGMENTATION_HEF_PATH, STEREO_DEPTH_HEF_PATH]
    for path in hef_paths:
        if not os.path.exists(path):
            print(f"FATAL ERROR: HEF file not found at '{path}'.")
            print("Please update the HEF path variables at the top of the script.")
            sys.exit(1)

    if len(sys.argv) < 2:
        print("ERROR: Missing POSIX semaphore name. Usage: python ai_main.py <ai_sem_name>")
        sys.exit(1)
        
    ai_ready_sem_name = sys.argv[1]
    
    try:
        ai_ready_sem = posix_ipc.Semaphore(ai_ready_sem_name)
    except posix_ipc.ExistentialError:
        print("ERROR: Could not attach to POSIX semaphore. Ensure launch_all.py is running.")
        sys.exit(1)
        
    # --- Create the Process Pool with the worker initializer ---
    with ProcessPoolExecutor(max_workers=3, initializer=init_worker) as executor:
        start_ai_subsystem(ai_ready_sem, executor)
