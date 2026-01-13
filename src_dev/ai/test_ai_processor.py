# ai/ai_main.py
# version 2.1 - AI Subsystem with TAPPAS-integrated Object Detector

import sys
import os
import time
from multiprocessing import shared_memory
import numpy as np
import posix_ipc
import cv2
from concurrent.futures import ProcessPoolExecutor

# --- Hailo TAPPAS Imports ---
# NOTE: Ensure the Hailo toolchain is installed and in your PYTHONPATH
from hailo_platform import (VDevice, HailoStreamInterface, InferVStreams,
                            HEF, FormatType)
# The Hailo Model Zoo provides essential post-processing functions
from hailo_model_zoo.postprocessing.yolov5_postprocessing import yolov5_postprocessing

# --- Configuration ---
OUT_WIDTH, OUT_HEIGHT = 640, 480
VIS_WIDTH, VIS_HEIGHT = 1280, 720
# --- IMPORTANT: Set the path to your compiled YOLOv5m HEF file ---
YOLO_HEF_PATH = "/path/to/your/yolov5m.hef" 

# --- Global object for the worker process ---
# This will be initialized by init_worker
detector = None

# --- 1. Hailo Inference Class for Object Detection ---

class ObjectDetector:
    """A class to manage YOLOv5 inference on the Hailo-8."""
    
    def __init__(self, hef_path):
        if not os.path.exists(hef_path):
            raise FileNotFoundError(f"HEF file not found: {hef_path}")

        # --- Device and Model Initialization ---
        self.hef = HEF(hef_path)
        # Activates network groups for inference
        self.hef.activate() 
        # Get input/output stream information
        self.input_vstream_infos = self.hef.get_input_vstream_infos()
        self.output_vstream_infos = self.hef.get_output_vstream_infos()
        
        # --- Store model metadata for pre/post-processing ---
        # Assuming a single input stream for this model
        self.input_shape = self.input_vstream_infos[0].shape 
        # For post-processing with Hailo Model Zoo utilities
        self.postprocess_config = self.hef.get_config().postprocess
        self.model_name = self.hef.get_config().model.model_name
        
        # --- VDevice and VStreams Management ---
        # The 'with' statement ensures resources are released
        self.vdevice = VDevice()
        self.vstreams = InferVStreams(self.vdevice, self.hef)
        self.infer_job = self.vstreams.infer_async

        print(f"[AI-YOLO-INIT] ObjectDetector initialized with model '{self.model_name}'")
        print(f"[AI-YOLO-INIT] Model expected input shape: {self.input_shape}")

    def _preprocess(self, image_np: np.ndarray) -> np.ndarray:
        """Resize and format the image to match the model's input requirements."""
        # The model expects a specific height and width
        model_height, model_width = self.input_shape[1], self.input_shape[2]
        
        # cv2.resize expects (width, height)
        resized_image = cv2.resize(image_np, (model_width, model_height), interpolation=cv2.INTER_AREA)
        
        # Add a batch dimension to match the model's (1, H, W, 3) shape
        input_tensor = np.expand_dims(resized_image, axis=0)
        return input_tensor
    
    def infer(self, image_np: np.ndarray) -> list:
        """Run a full inference cycle: preprocess, infer, postprocess."""
        # 1. Preprocess the image
        input_tensor = self._preprocess(image_np)
        
        # 2. Run Inference
        # Send the preprocessed tensor to the Hailo-8 hardware
        # The result is a dictionary of output tensors (raw data)
        raw_results = self.infer_job({self.input_vstream_infos[0].name: input_tensor})
        
        # 3. Postprocess the raw results
        # Use the official Hailo Model Zoo function for this
        # It handles all the complex decoding, anchor boxes, and NMS
        detections = yolov5_postprocessing(raw_results, 
                                           self.postprocess_config,
                                           image_height=image_np.shape[0], # Original height
                                           image_width=image_np.shape[1])  # Original width
        
        # 4. Format the output to our desired list of dicts
        formatted_detections = []
        for det in detections:
            formatted_detections.append({
                'box': det.get_bbox(), # Returns [xmin, ymin, xmax, ymax]
                'class_id': det.get_label(),
                'confidence': det.get_confidence()
            })
            
        return formatted_detections

    def release(self):
        """Release Hailo resources."""
        self.vstreams.release()
        self.vdevice.release()
        print("[AI-YOLO-INIT] ObjectDetector resources released.")

# --- 2. Worker Initialization and Inference Functions ---

def init_worker():
    """Initializer for each worker in the ProcessPoolExecutor."""
    global detector
    print(f"[Worker PID: {os.getpid()}] Initializing Hailo models...")
    detector = ObjectDetector(YOLO_HEF_PATH)
    # TODO: Initialize your other two models here as well
    # global segmenter, depth_estimator
    # segmenter = SemanticSegmenter(...)
    # depth_estimator = StereoDepthEstimator(...)

def run_object_detection(image_np: np.ndarray) -> list:
    """Worker function to perform object detection."""
    if detector is None:
        raise RuntimeError("ObjectDetector not initialized in this worker process.")
    
    print(f"    [AI-YOLO PID: {os.getpid()}] Running inference...")
    start_time = time.time()
    detections = detector.infer(image_np)
    duration = time.time() - start_time
    print(f"    [AI-YOLO PID: {os.getpid()}] Inference complete in {duration:.3f}s. Found {len(detections)} objects.")
    return detections

def run_semantic_segmentation(image_np: np.ndarray) -> np.ndarray:
    """Placeholder for semantic segmentation."""
    print(f"    [AI-SEG PID: {os.getpid()}] Running inference (SIMULATED)...")
    time.sleep(0.028)
    mask = np.ones((OUT_HEIGHT, OUT_WIDTH), dtype=np.uint8) * 2
    mask[:OUT_HEIGHT // 2, :] = 1
    return mask

def run_stereo_depth(left_img: np.ndarray, right_img: np.ndarray) -> np.ndarray:
    """Placeholder for stereo depth estimation."""
    print(f"    [AI-DEPTH PID: {os.getpid()}] Running inference (SIMULATED)...")
    time.sleep(0.035)
    depth_map = np.zeros((OUT_HEIGHT, OUT_WIDTH), dtype=np.float32)
    gradient = np.linspace(255, 0, OUT_WIDTH)
    for i in range(OUT_HEIGHT):
        depth_map[i, :] = gradient
    return depth_map

# ... (The combine_and_extract_data and create_visualization functions remain the same) ...

# --- Main AI Subsystem Logic (largely unchanged) ---
def start_ai_subsystem(ai_ready_sem, executor):
    # ... (code is the same as before)
    # ...
# ... (rest of the file remains the same)

# The following functions are unchanged from the previous version:
# - combine_and_extract_data
# - create_visualization
# - start_ai_subsystem

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("ERROR: Missing POSIX semaphore name. Usage: python ai_main.py <ai_sem_name>")
        sys.exit(1)

    # Check that the HEF file path is valid before starting
    if not os.path.exists(YOLO_HEF_PATH):
        print(f"FATAL ERROR: YOLO HEF file not found at '{YOLO_HEF_PATH}'.")
        print("Please update the YOLO_HEF_PATH variable in the script.")
        sys.exit(1)
        
    ai_ready_sem_name = sys.argv[1]
    
    try:
        ai_ready_sem = posix_ipc.Semaphore(ai_ready_sem_name)
    except posix_ipc.ExistentialError:
        print("ERROR: Could not attach to POSIX semaphore. Ensure launch_all.py is running.")
        sys.exit(1)
        
    # --- Create the Process Pool ---
    # The 'initializer' function is key. It sets up the Hailo models in each worker process.
    with ProcessPoolExecutor(max_workers=3, initializer=init_worker) as executor:
        start_ai_subsystem(ai_ready_sem, executor)
