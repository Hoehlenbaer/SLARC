import time
import struct
import numpy as np
import moderngl
from multiprocessing import shared_memory

# ==========================================
# 1. CONFIGURATION
# ==========================================

# INPUT: Camera Specs (Grayscale Y-Plane)
IN_WIDTH = 1440
IN_HEIGHT = 1080
IN_CHANNELS = 1  # Y-plane only
SHM_NAME_LEFT = "shm_camera_left"
SHM_NAME_RIGHT = "shm_camera_right"
BUFFER_SIZE = IN_WIDTH * IN_HEIGHT * IN_CHANNELS

# OUTPUT: AI Model Specs
OUT_WIDTH = 320
OUT_HEIGHT = 240
OUT_CHANNELS = 3 # Converting Gray -> RGB for AI

# TEST MODE: Set to False when you have real calibration data
TEST_MODE = True 
TEST_SHRINK_SCALE = 0.8 # 1.0 = Passthrough, <1.0 = Zoom Out (Shrink)

# ==========================================
# 2. OPENGL ES SHADERS (Pi 5 Compatible)
# ==========================================

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
precision highp float; // REQUIRED for OpenGL ES

out vec4 fragColor;
in vec2 v_uv;

uniform sampler2D texImage; // Input is Red component only (Grayscale)

// Transformation Matrices
uniform mat3 K_new_inv; // Inverse of Output Camera Matrix
uniform mat3 R_inv;     // Inverse of Rectification Rotation
uniform mat3 K_old;     // Input Camera Matrix
uniform vec4 distCoeffs; // k1, k2, p1, p2

// Resolutions for Normalization
uniform vec2 out_res; 
uniform vec2 in_res;

void main() {
    // 1. Map UV (0..1) to Output Pixel Coordinates (e.g., 0..400, 0..300)
    vec3 pixel_dest = vec3(v_uv.x * out_res.x, v_uv.y * out_res.y, 1.0);
    
    // 2. Unproject to 3D Ray (Ideal Rectified Camera)
    vec3 ray = K_new_inv * pixel_dest;
    
    // 3. Rotate (Undo Rectification)
    vec3 ray_cam = R_inv * ray;
    
    // 4. Normalize to Normalized Image Coordinates (z=1 plane)
    vec2 xn = ray_cam.xy / ray_cam.z;
    
    // 5. Apply Lens Distortion Model (Brown-Conrady)
    float r2 = dot(xn, xn);
    float r4 = r2 * r2;
    
    // Radial
    float rad = 1.0 + distCoeffs.x * r2 + distCoeffs.y * r4;
    
    // Tangential
    float dx = 2.0 * distCoeffs.z * xn.x * xn.y + distCoeffs.w * (r2 + 2.0 * xn.x * xn.x);
    float dy = distCoeffs.z * (r2 + 2.0 * xn.y * xn.y) + 2.0 * distCoeffs.w * xn.x * xn.y;
    
    // Distorted Coordinates
    vec2 x_dist = xn * rad + vec2(dx, dy);
    
    // 6. Project back to Input Pixel Coordinates (using Raw Camera Matrix)
    vec3 uv_h = K_old * vec3(x_dist, 1.0);
    
    // 7. Normalize back to 0..1 UV for Texture Sampling
    vec2 final_uv = uv_h.xy / in_res; 
    
    // 8. Sample
    if (final_uv.x < 0.0 || final_uv.x > 1.0 || final_uv.y < 0.0 || final_uv.y > 1.0) {
        // Black border for out of bounds
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
    } else {
        // Sample the Red channel (Y-plane)
        float y = texture(texImage, final_uv).r;
        // Output RGB (Gray duplicated 3 times)
        fragColor = vec4(y, y, y, 1.0);
    }
}
"""

# ==========================================
# 3. MATRIX HELPERS
# ==========================================

def get_scaled_K_new(K_original, target_w, target_h, original_w, original_h, shrink_factor=1.0):
    """
    Creates a new Camera Matrix scaled for the target resolution and shrink factor.
    """
    scale_x = (target_w / original_w) * shrink_factor
    scale_y = (target_h / original_h) * shrink_factor
    
    K_scaled = K_original.copy()
    K_scaled[0, 0] *= scale_x # fx
    K_scaled[1, 1] *= scale_y # fy
    K_scaled[0, 2] *= scale_x # cx
    K_scaled[1, 2] *= scale_y # cy
    
    # Re-center the principal point for the new image center
    K_scaled[0, 2] = target_w / 2.0
    K_scaled[1, 2] = target_h / 2.0
    
    return K_scaled

def generate_test_data(width, height):
    """Generates dummy matrices for testing without calibration files."""
    fx, fy = width, width # Arbitrary focal length
    cx, cy = width / 2.0, height / 2.0
    
    K_raw = np.array([
        [fx, 0, cx],
        [0, fy, cy],
        [0, 0, 1]
    ], dtype='f4')
    
    # Scale K_new to match the output resolution (400x300)
    K_new = get_scaled_K_new(K_raw, OUT_WIDTH, OUT_HEIGHT, width, height, TEST_SHRINK_SCALE)
    
    R = np.eye(3, dtype='f4')
    D = np.zeros(4, dtype='f4')
    
    return K_raw, K_new, R, D

# ==========================================
# 4. MAIN EXECUTION
# ==========================================

def main():
    # --- A. Setup Context ---
    # standalone=True uses EGL (Headless) - Essential for Pi 5
    # require=300 requests OpenGL ES 3.0
    try:
        ctx = moderngl.create_context(standalone=True, require=300)
        print(f"Context Loaded: {ctx.info['GL_RENDERER']}")
    except Exception as e:
        print("Error: Could not create GLES context. Ensure 'glcontext' is installed.")
        return

    # --- B. Setup Shader & Buffers ---
    prog = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)
    
    # Full Screen Quad (NDC coordinates)
    quad = np.array([
        -1.0, -1.0, 0.0, 0.0,
         1.0, -1.0, 1.0, 0.0,
        -1.0,  1.0, 0.0, 1.0,
         1.0,  1.0, 1.0, 1.0,
    ], dtype='f4')
    
    vbo = ctx.buffer(quad)
    vao = ctx.vertex_array(prog, [(vbo, '2f 2f', 'in_vert', 'in_uv')])

    # --- C. Setup Textures ---
    # Input Textures (Grayscale / GL_R8)
    tex_l = ctx.texture((IN_WIDTH, IN_HEIGHT), 1, dtype='f1')
    tex_r = ctx.texture((IN_WIDTH, IN_HEIGHT), 1, dtype='f1')
    
    # Important: Linear filtering for smooth downscaling
    tex_l.filter = (moderngl.LINEAR, moderngl.LINEAR) 
    tex_r.filter = (moderngl.LINEAR, moderngl.LINEAR)

    # Output Framebuffer (Target Resolution)
    # We output 3 channels (RGB)
    fbo_tex = ctx.texture((OUT_WIDTH, OUT_HEIGHT), OUT_CHANNELS, dtype='f1')
    fbo = ctx.framebuffer(fbo_tex)
    fbo.use()

    # --- D. Load Matrices ---
    if TEST_MODE:
        print("Running in TEST MODE (No Calibration Loaded)")
        K_raw, K_new, R, D = generate_test_data(IN_WIDTH, IN_HEIGHT)
        # Assign same to left and right for testing
        K_l_raw = K_r_raw = K_raw
        K_l_new = K_r_new = K_new
        R_l = R_r = R
        D_l = D_r = D
    else:
        # TODO: Load your JSON/YAML here
        pass

    # Pre-calculate inverses on CPU
    K_l_new_inv = np.linalg.inv(K_l_new).astype('f4')
    R_l_inv = np.linalg.inv(R_l).astype('f4')
    K_r_new_inv = np.linalg.inv(K_r_new).astype('f4')
    R_r_inv = np.linalg.inv(R_r).astype('f4')

    # Set Constant Uniforms
    prog['in_res'].value = (IN_WIDTH, IN_HEIGHT)
    prog['out_res'].value = (OUT_WIDTH, OUT_HEIGHT)
    prog['texImage'].value = 0

    # --- E. Shared Memory Connection ---
    try:
        shm_l = shared_memory.SharedMemory(name=SHM_NAME_LEFT)
        shm_r = shared_memory.SharedMemory(name=SHM_NAME_RIGHT)
        print("Connected to existing Shared Memory.")
    except FileNotFoundError:
        print("Shared Memory not found. Creating DUMMY memory for testing.")
        shm_l = shared_memory.SharedMemory(create=True, size=BUFFER_SIZE, name=SHM_NAME_LEFT)
        shm_r = shared_memory.SharedMemory(create=True, size=BUFFER_SIZE, name=SHM_NAME_RIGHT)
        # Fill with dummy noise/gradient
        dummy_data = np.random.randint(0, 255, (IN_HEIGHT, IN_WIDTH), dtype=np.uint8)
        shm_l.buf[:] = dummy_data.tobytes()
        shm_r.buf[:] = dummy_data.tobytes()

    # --- F. Render Loop ---
    print("Starting Processing Loop...")
    try:
        frame_count = 0
        start_time = time.time()

        while True:
            # 1. Create numpy view of shared memory (Zero Copy)
            #    Assumes tightly packed 8-bit Grayscale
            raw_l = np.ndarray((IN_HEIGHT, IN_WIDTH), dtype='uint8', buffer=shm_l.buf)
            raw_r = np.ndarray((IN_HEIGHT, IN_WIDTH), dtype='uint8', buffer=shm_r.buf)

            # -----------------------------
            # PROCESS LEFT IMAGE
            # -----------------------------
            # Upload texture
            tex_l.write(raw_l)
            tex_l.use(location=0)
            
            # Update Uniforms for Left Camera
            prog['K_old'].write(K_l_raw.T.tobytes())
            prog['K_new_inv'].write(K_l_new_inv.T.tobytes())
            prog['R_inv'].write(R_l_inv.T.tobytes())
            prog['distCoeffs'].write(D_l.tobytes())
            
            # Render
            fbo.clear()
            vao.render(moderngl.TRIANGLE_STRIP)
            
            # Read Result (400x300x3 bytes)
            # This is the data you pass to your AI
            result_bytes_l = fbo.read(components=OUT_CHANNELS)
            
            # -----------------------------
            # PROCESS RIGHT IMAGE
            # -----------------------------
            tex_r.write(raw_r)
            tex_r.use(location=0)
            
            # Update Uniforms for Right Camera
            prog['K_old'].write(K_r_raw.T.tobytes())
            prog['K_new_inv'].write(K_r_new_inv.T.tobytes())
            prog['R_inv'].write(R_r_inv.T.tobytes())
            prog['distCoeffs'].write(D_r.tobytes())
            
            # Render
            fbo.clear()
            vao.render(moderngl.TRIANGLE_STRIP)
            
            # Read Result
            result_bytes_r = fbo.read(components=OUT_CHANNELS)

            # -----------------------------
            # AI INFERENCE PLACEHOLDER
            # -----------------------------
            # To use in PyTorch/TF, convert to numpy (very fast for small img)
            # ai_input_r = np.frombuffer(result_bytes_r, dtype='uint8').reshape((OUT_HEIGHT, OUT_WIDTH, 3))
            
            frame_count += 1
            if frame_count % 100 == 0:
                elapsed = time.time() - start_time
                print(f"FPS: {frame_count / elapsed:.2f}")

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        shm_l.close()
        shm_r.close()
        # shm_l.unlink() # Uncomment if you created the memory and need to destroy it

if __name__ == "__main__":
    main()