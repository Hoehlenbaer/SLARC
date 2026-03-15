# vision_processor.py
# version 1.3 (Minimal change for launch_all.py compatibility)
#
# Post-Processing Worker Module
# Handles image rectification using OpenGL shaders,
# Shared Memory reading/writing, and synchronization with AI via POSIX Semaphores. 
# Requires vision_main.py to run first.

import time
import json
import os
import numpy as np
import moderngl
from multiprocessing import Process, shared_memory
import cv2
import posix_ipc # <--- NEU: Import for POSIX Semaphores

# --- CONFIGURATION ---
IN_WIDTH, IN_HEIGHT = 1440, 1080
OUT_WIDTH, OUT_HEIGHT = 640, 480 # Standard for StereoNet/YOLO
FPS_REPORT_INTERVAL = 50
CALIB_FILE = "calibration.json"
CHANNELS = 3 # RGB

# --- SHADERS (Unchanged) ---
VERTEX_SHADER = """
#version 300 es
in vec2 in_vert;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

FRAGMENT_SHADER = """
#version 300 es
precision highp float;
out vec4 fragColor;
in vec2 v_uv;
uniform sampler2D texImage; 
uniform mat3 K_new_inv;
uniform mat3 R_inv;
uniform mat3 K_old;
uniform vec4 distCoeffs;
uniform vec2 out_res; 
uniform vec2 in_res;

void main() {
    vec3 pixel_dest = vec3(v_uv.x * out_res.x, v_uv.y * out_res.y, 1.0);
    vec3 ray = K_new_inv * pixel_dest;
    vec3 ray_cam = R_inv * ray;
    if (ray_cam.z <= 0.0) {             // ← Guard: Strahl hinter Kamera → schwarz
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    vec2 xn = ray_cam.xy / ray_cam.z;
    float r2 = dot(xn, xn);
    float r4 = r2 * r2;
    float rad = 1.0 + distCoeffs.x * r2 + distCoeffs.y * r4;
    float dx = 2.0 * distCoeffs.z * xn.x * xn.y + distCoeffs.w * (r2 + 2.0 * xn.x * xn.x);
    float dy = distCoeffs.z * (r2 + 2.0 * xn.y * xn.y) + 2.0 * distCoeffs.w * xn.x * xn.y;
    vec2 x_dist = xn * rad + vec2(dx, dy);
    vec3 uv_h = K_old * vec3(x_dist, 1.0);
    vec2 final_uv = uv_h.xy / in_res; 
    
    if (final_uv.x < 0.0 || final_uv.x > 1.0 || final_uv.y < 0.0 || final_uv.y > 1.0) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
    } else {
        float y = texture(texImage, final_uv).r;
        fragColor = vec4(y, y, y, 1.0);
    }
}
"""

# --- Matrix functions (Unchanged) ---

def get_scaled_K_new(K_original, target_w, target_h, original_w, original_h, shrink=1.0):
    """
    Scales an Intrinsic Matrix (K or P) to match the new output resolution.
    shrink: <1.0 zooms out (smaller image content), >1.0 zooms in/crops.
    """
    scale_x = (target_w / original_w) * shrink
    scale_y = (target_h / original_h) * shrink
    K_new = K_original.copy()
    K_new[0, 0] *= scale_x
    K_new[1, 1] *= scale_y
    K_new[0, 2] = target_w / 2.0 # Recenter principal point
    K_new[1, 2] = target_h / 2.0
    return K_new

def load_stereo_calibration(filepath):
    """Loads calibration data from JSON and returns numpy arrays."""
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        print(f"[post] Loading calibration from {filepath}...")
        
        # Helper to convert list to np array
        to_arr = lambda x: np.array(x, dtype='f4')

        mats = {
            "left": {
                "K": to_arr(data["left"]["K"]),
                "D": to_arr(data["left"]["D"]).flatten()[:4].astype('f4'),  # ← immer (4,), k3 verworfen
                "R": to_arr(data["left"]["R"]),
                "P": to_arr(data["left"]["P"])[:3, :3]
            },
            "right": {
                "K": to_arr(data["right"]["K"]),
                "D": to_arr(data["right"]["D"]).flatten()[:4].astype('f4'),  # ← immer (4,), k3 verworfen
                "R": to_arr(data["right"]["R"]),
                "P": to_arr(data["right"]["P"])[:3, :3]
            },
            "dim": data["dim"]
        }
        return mats
    except Exception as e:
        print(f"[post] Calibration load failed ({e}). using TEST MODE.")
        return None

# --- WORKER FUNCTION (Refactored) ---

def post_process_worker(shm0_name, shm1_name, ts_shm_name, out_shm_l_name, out_shm_r_name, semaphore, ai_sem_name, headless=True):
    # 1. Setup OpenGL
    try:
        ctx = moderngl.create_context(standalone=True, require=300)
    except Exception as e:
        print(f"[post] OpenGL Context Failed: {e}")
        return

    prog = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)
    quad = np.array([-1.0, -1.0, 0.0, 0.0,  1.0, -1.0, 1.0, 0.0, -1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0], dtype='f4')
    vbo = ctx.buffer(quad)
    vao = ctx.vertex_array(prog, [(vbo, '2f 2f', 'in_vert', 'in_uv')])

    tex_l = ctx.texture((IN_WIDTH, IN_HEIGHT), 1, dtype='f1'); tex_l.filter = (moderngl.LINEAR, moderngl.LINEAR)
    tex_r = ctx.texture((IN_WIDTH, IN_HEIGHT), 1, dtype='f1'); tex_r.filter = (moderngl.LINEAR, moderngl.LINEAR)
    fbo = ctx.simple_framebuffer((OUT_WIDTH, OUT_HEIGHT), components=3)
    fbo.use()

    # 2. Shared Memory
    try:
        # Inputs
        shm0 = shared_memory.SharedMemory(name=shm0_name)
        shm1 = shared_memory.SharedMemory(name=shm1_name)
        ts_shm = shared_memory.SharedMemory(name=ts_shm_name)
        
        # Outputs
        shm_out_l = shared_memory.SharedMemory(name=out_shm_l_name)
        shm_out_r = shared_memory.SharedMemory(name=out_shm_r_name)

        # Numpy Wrappers
        raw_l = np.ndarray((IN_HEIGHT, IN_WIDTH), dtype=np.uint8, buffer=shm0.buf)
        raw_r = np.ndarray((IN_HEIGHT, IN_WIDTH), dtype=np.uint8, buffer=shm1.buf)
        out_l_array = np.ndarray((OUT_HEIGHT, OUT_WIDTH, 3), dtype=np.uint8, buffer=shm_out_l.buf)
        out_r_array = np.ndarray((OUT_HEIGHT, OUT_WIDTH, 3), dtype=np.uint8, buffer=shm_out_r.buf)
        
    except Exception as e:
        print(f"[post] SHM Error: {e}")
        return

    # 3. Load Matrices (Unchanged)
    calib = load_stereo_calibration(CALIB_FILE)
    
    if calib:
        K_l, D_l, R_l, P_l = calib["left"]["K"], calib["left"]["D"], calib["left"]["R"], calib["left"]["P"]
        K_r, D_r, R_r, P_r = calib["right"]["K"], calib["right"]["D"], calib["right"]["R"], calib["right"]["P"]
        calib_w, calib_h = calib["dim"]

        K_l_new = get_scaled_K_new(P_l, OUT_WIDTH, OUT_HEIGHT, calib_w, calib_h, shrink=1.0)
        K_r_new = get_scaled_K_new(P_r, OUT_WIDTH, OUT_HEIGHT, calib_w, calib_h, shrink=1.0)

        u_kl_old = K_l.T.tobytes()
        u_kl_new_inv = np.linalg.inv(K_l_new).T.tobytes()
        u_rl_inv = np.linalg.inv(R_l).T.tobytes()
        u_dl = D_l.tobytes()
        
        u_kr_old = K_r.T.tobytes()
        u_kr_new_inv = np.linalg.inv(K_r_new).T.tobytes()
        u_rr_inv = np.linalg.inv(R_r).T.tobytes()
        u_dr = D_r.tobytes()

    else:
        print("[post] No JSON found. Using IDENTITY matrices.")
        K_raw = np.array([[IN_WIDTH, 0, IN_WIDTH/2], [0, IN_WIDTH, IN_HEIGHT/2], [0, 0, 1]], dtype='f4')
        K_new = get_scaled_K_new(K_raw, OUT_WIDTH, OUT_HEIGHT, IN_WIDTH, IN_HEIGHT, shrink=0.8)
        R_eye = np.eye(3, dtype='f4'); D_zero = np.zeros(4, dtype='f4')
        
        u_kl_old = u_kr_old = K_raw.T.tobytes()

        # Shader test: Apply 180° rotation to input images 
        #K_rot = np.array([[-IN_WIDTH,        0, IN_WIDTH/2],
        #                  [0,          -IN_WIDTH, IN_HEIGHT/2],
        #                  [0,                 0,          1]], dtype='f4')
        #u_kl_old = u_kr_old = K_rot.T.tobytes()

        u_kl_new_inv = u_kr_new_inv = np.linalg.inv(K_new).T.tobytes()
        u_rl_inv = u_rr_inv = np.linalg.inv(R_eye).T.tobytes()
        u_dl = u_dr = D_zero.tobytes()

    # Set Uniforms (Unchanged)
    prog['in_res'].value = (IN_WIDTH, IN_HEIGHT)
    prog['out_res'].value = (OUT_WIDTH, OUT_HEIGHT)
    prog['texImage'].value = 0
    
    # 4. Connect to AI POSIX Semaphore <--- NEU
    ai_semaphore = None
    try:
        # Attaching to an existing POSIX Semaphore (created by launch_all.py)
        ai_semaphore = posix_ipc.Semaphore(ai_sem_name)
    except Exception as e:
        print(f"[post] POSIX AI Semaphore Error: {e}")
        # Continue without signaling if we can't connect, but warn.

    print(f"[post] Worker running (Headless={headless})...")
    
    # --- Headless Mode Check ---
    if not headless:
        cv2.namedWindow("Stereo Pipeline", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Stereo Pipeline", OUT_WIDTH*2, OUT_HEIGHT)

    count = 0
    start_t = 0.0

    try:
        while True:
            semaphore.acquire()
            if count == 0: start_t = time.time()
            
            # --- RENDER LEFT & WRITE TO SHM ---
            tex_l.write(raw_l)
            tex_l.use(location=0)
            prog['K_old'].write(u_kl_old); prog['K_new_inv'].write(u_kl_new_inv)
            prog['R_inv'].write(u_rl_inv); prog['distCoeffs'].write(u_dl)
            fbo.clear()
            vao.render(moderngl.TRIANGLE_STRIP)
            fbo.read_into(shm_out_l.buf, components=3)

            # --- RENDER RIGHT & WRITE TO SHM ---
            tex_r.write(raw_r)
            tex_r.use(location=0)
            prog['K_old'].write(u_kr_old); prog['K_new_inv'].write(u_kr_new_inv)
            prog['R_inv'].write(u_rr_inv); prog['distCoeffs'].write(u_dr)
            fbo.clear()
            vao.render(moderngl.TRIANGLE_STRIP)
            fbo.read_into(shm_out_r.buf, components=3)

            # --- SIGNAL AI SYSTEM <--- NEU
            if ai_semaphore:
                # Signal the AI process that new, rectified frames are ready
                ai_semaphore.release()
            
            # --- VISUALIZE (Conditional) ---
            if not headless:
                # Use the shared memory buffers for visualization
                vis = np.hstack((cv2.cvtColor(out_l_array, cv2.COLOR_RGB2BGR), 
                                 cv2.cvtColor(out_r_array, cv2.COLOR_RGB2BGR)))
                
                # Epipolar Lines
                for y in range(0, OUT_HEIGHT, 24):
                    cv2.line(vis, (0, y), (OUT_WIDTH * 2, y), (0, 255, 0), 1)

                cv2.imshow("Stereo Pipeline", vis)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            count += 1
            if count % FPS_REPORT_INTERVAL == 0:
                elapsed = time.time() - start_t
                print(f"[post] Pipeline FPS: {count / elapsed:.2f}")

    except KeyboardInterrupt:
        pass
    finally:
        # Only destroy windows if they were created
        if not headless:
            cv2.destroyAllWindows()
            
        shm0.close(); shm1.close(); ts_shm.close()
        shm_out_l.close(); shm_out_r.close()
        
        # Clean up POSIX Semaphore connection <--- NEU
        if ai_semaphore:
            ai_semaphore.close()
            
        print("[post] Worker stopped.")

def start_post_process(shm0_name, shm1_name, ts_shm_name, out_shm_l_name, out_shm_r_name, semaphore, ai_sem_name, headless=True): # <--- NEUE SIGNATUR
    return Process(target=post_process_worker, args=(shm0_name, shm1_name, ts_shm_name, out_shm_l_name, out_shm_r_name, semaphore, ai_sem_name, headless))