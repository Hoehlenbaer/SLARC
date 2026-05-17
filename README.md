# SLARC – Six‑Legged Autonomous Robot Crab

> *'Crab' is a misnomer — six legs and no claws hardly make it one, but SLARC will happily act crab‑enough whenever something needs grabbing.*

SLARC is a personal hobby project with an ambitious goal: build a **state-of-the-art hexapod robot that is fully AI-controlled** — from low-level motion to high-level mission planning — using entirely off-the-shelf hardware, a fully 3D-printable chassis, and custom-trained neural networks.

---

## What makes SLARC interesting

Most hobbyist hexapods are scripted or rely on simple remote control. SLARC aims to close the gap between hobby robotics and current research:

- **Fused multi-task perception** – a single shared neural network simultaneously performs stereo depth estimation, surface normal prediction, semantic segmentation, and object detection, all optimized for the Hailo-8 NPU
- **GPU-accelerated stereo rectification** – lens distortion correction and image scaling for both cameras runs entirely on the Raspberry Pi 5's VideoCore VII GPU via OpenGL ES shaders, freeing the CPU completely for other tasks
- **Natural language mission planning** – a quantized LLM translates spoken or typed commands into structured JSON action objects that the motion controller can execute
- **Fully self-printable** – every structural part of the chassis and legs is designed for 3D printing (PETG, PLA, TPU); no proprietary frames or expensive machined parts

---

## Hardware

| Component | Details |
|---|---|
| **Main Brain** | Raspberry Pi 5, 8 GB RAM |
| **AI Accelerator** | Hailo-8 NPU (26 TOPS) via AI HAT+ |
| **Secondary Brain** | Waveshare General Driver for Robots (ESP32) |
| **Legs** | 6 × 3-DOF, Waveshare ST3215 serial bus servos |
| **Stereo Cameras** | 2 × IMX296 (1440×1080), 2.8 mm lens, ~80 mm baseline |
| **Power** | Zeee 9000 mAh LiPo 3S high-performance battery |
| **Chassis** | Fully 3D-printable (PETG / PLA / TPU) – *work in progress* |

The Raspberry Pi handles all AI inference and high-level planning. The ESP32 handles real-time servo control and low-level motion execution, communicating with the Pi over a serial bus.

---

## AI Architecture

### Perception – FusedHexapodModel V5.0

The core perception system is a **single multi-task neural network** with four output heads, designed to run entirely on the Hailo-8 NPU. All heads share a common MobileNetV2-1.4 backbone with asymmetric channel alignment — the feature extraction cost is paid once per frame.

#### Architecture Evolution

The model has gone through several iterations, each driven by deployment constraints on the Hailo-8 NPU:

| Change | V3.1 | V4.0 | V5.0 | Reason |
|---|---|---|---|---|
| Backbone | MobileNetV3-Large | MobileNetV2-1.4 | MobileNetV2-1.4 | SE blocks caused 6× slowdown on Hailo |
| Channel Alignment | None | None | **Stereo-focused (64/128/128/256)** | Wider stereo features via 1×1 projection, preserving ImageNet weights |
| Stereo Matching | CostVolume + GroupedConv | CostVolume + GroupedConv | **Flat CostVolume + MLP reduction** | Cross-disparity learning, no per-bin isolation |
| CostVolume channels | 32 | 16 | 16 | Halved without quality loss |
| Stereo output | Full res (480×640) | s4 (120×160) | s4 (120×160) | s1 refinement added artifacts |
| Attention | CBAM after FPN | Removed | Removed | AvgPool + FC chains are NPU-hostile |
| Activations | ReLU + HardSwish | ReLU6 | ReLU6 | Pure INT8 quantization |
| Seg classes | 6 (with NAV_ANCHOR) | 6 (with NAV_ANCHOR) | **6 (FLOOR/TERRAIN split)** | Better outdoor navigation |
| Detection classes | 40 | 40 | **41 (+ UNKNOWN)** | Generalized objectness for unseen objects |
| Confidence Gate | None | Peak confidence | Peak confidence | Suppresses false stereo matches |
| NPU deployment | Not achieved | 3-HEF, 18 FPS | **3-HEF, 16.3 FPS** | Wider features trade speed for quality |

#### Architecture Overview

```
Stereo Camera Pair (640×480, grayscale)
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  MobileNetV2-1.4 Backbone (1-channel input, luminance merge) │
│  out_indices: s4 (32ch) · s8 (48ch) · s16 (136ch) · s32 (448ch)│
└──┬──────────┬──────────┬──────────┬──────────────────────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
┌──────────────────────────────────────────────────────────────┐
│  Channel Aligner (stereo-focused)                            │
│  1×1 Conv projections: 32→64 · 48→128 · 136→128 · 448→256   │
│  Wider s4/s8 for stereo, slimmer s32 saves compute           │
└──┬──────────┬──────────┬──────────┬──────────────────────────┘
   │s4(64)    │s8(128)   │s16(128)  │s32(256)
   │          │          │          ▼
   │          │          │    ┌───────────┐
   │          │          │    │   SPPF    │ Spatial Pyramid Pooling
   │          │          │    │  (k=5)    │ Expands receptive field
   │          │          │    └─────┬─────┘
   │          │          │          │
   │          │          ▼          ▼
   │          │    ┌─────────────────────┐
   │          │    │   Light FPN Neck    │ Bi-directional feature fusion
   │          │    │  (64ch, RepConv)    │ 4× RepConv (folded at deploy)
   │          │    └──┬───────┬───────┬──┘
   │          │       │s8     │s16    │s32
   │          │       ▼       ▼       ▼
   │          │    ┌────────────────────────┐
   │          │    │    YOLO Detection      │ 41 classes (40 known + UNKNOWN)
   │          │    │  (3 Decoupled Heads)   │ 3 scales: s8 / s16 / s32
   │          │    │  CoordConv + RepConv   │
   │          │    └────────────────────────┘
   │          │
   ▼          ▼
┌──────────────────┐
│  Geometry Stem   │ RepConv(64→32) + RepConv(32→32)
│  (s4, 32ch out)  │ High-res edge features
└──┬───────────────┘
   │ geo_features
   │
   ├───────────────────────────────────┐
   │                                   │
   ▼                                   ▼
┌──────────────────────┐    ┌─────────────────────────────────┐
│   NormalsHead        │    │   Correlation Stereo Head (V5)  │
│                      │    │                                 │
│  Fusion: s4 + s8     │    │  Flat CostVolume (s8)           │
│   + geo (CoordConv)  │    │   · Shift+Concat all disparities│
│   96 → 64 → 32 → 3  │    │   · 16ch × 24 bins = 384ch     │
│                      │    │                                 │
│  L2 normalize        │    │  MLP Reduction (384 → 96 → 24) │
│  (deploy-safe sqrt)  │    │   · Cross-disparity learning    │
│                      │    │   · Learns correlations across  │
│  Output:             │    │     all disparity bins jointly  │
│   normals_s4         │    │                                 │
│   [1, 3, 120, 160]   │    │  Confidence Gate (eval only)    │
│                      │    │                                 │
└──────┬───────────────┘    │  Refine s4 (backbone guidance)  │
       │ normals_s4         │                                 │
       ▼                    │  Output:                        │
┌────────────────────────┐  │   disp_s4  [1, 1, 120, 160]    │
│  LRASPP Seg Head       │  │   disp_s8  [1, 1,  60,  80]    │
│  low (s4 + normals)    │  └─────────────────────────────────┘
│  + high (s16, pooled   │
│    via LearnablePool)  │
│  + mid (dilated + norm)│
│                        │
│  Output:               │
│   seg [1, 6, 120, 160] │
│                        │
│  6 classes:            │
│  FLOOR · STEP ·        │
│  WALL · OBSTACLE ·     │
│  VOID · TERRAIN        │
└────────────────────────┘
```

#### Model Summary

| Property | Value |
|---|---|
| Total parameters | 5.90 M |
| Backbone (MobileNetV2-1.4) | 3.45 M |
| Channel Aligner | 0.14 M |
| YOLO Head | 1.46 M |
| Seg Head | 0.21 M |
| Normals Head | 0.16 M |
| Input | 1 × 480 × 640 grayscale (×2 for stereo) |
| Outputs | 7 tensors (disp_s4, seg, disp_s8, normals_s4, yolo_s8/s16/s32) |

#### Building Blocks

| Block | Purpose | NPU Cost |
|---|---|---|
| **MobileNetV2-1.4** | Shared backbone — wider channels (32/48/136/448) than MNV2-1.0, no SE blocks, pure ReLU6 | Very low — ideal for INT8 NPU |
| **Channel Aligner** | 1×1 Conv projections to Hailo-optimal widths (64/128/128/256); preserves ImageNet weights, wider s4/s8 for stereo, slimmer s32 saves compute | Negligible — four 1×1 convs |
| **SPPF** | Expands receptive field at s32 via cascaded 5×5 max-pooling | Minimal — pooling + 1×1 convs |
| **CoordConv** | Appends normalized X/Y coordinate grids; spatial awareness for stereo matching and normals | Negligible — 2 extra input channels |
| **RepConv** | Three parallel paths during training (3×3 + 1×1 + identity); folds into single 3×3 conv at deploy | **Zero overhead at inference** |
| **GeometryStem** | High-frequency edge features from s4 via 2× RepConv; shared by Stereo and Normals | Low — 2 convs at stride 4 |
| **Flat CostVolume** | Shift + Concat all disparity bins into a single flat tensor (384ch); no per-bin GroupedConv | More regular memory access pattern |
| **MLP Reduction** | Two-stage 1×1 Conv (384→96→24) with ReLU6; enables cross-disparity learning — each output bin sees all 24 shifts simultaneously | Low — two small 1×1 convs |
| **DWSepConv** | Depthwise-separable convolution; ~8–9× fewer FLOPs than standard conv | Very efficient |
| **LearnablePool** | Replaces AvgPool2d with depthwise conv initialized as averaging; avoids Hailo quantization shift errors | Identical compute, better quantization |
| **Confidence Gate** | At inference: suppresses stereo matches where peak confidence is too low (repetitive textures, sky) | Negligible — max + clamp + mul |
| **SegFormer teacher fusion** | SegFormer-b2 on GPU during training only; enriches geometry-derived seg labels with semantics | **Zero at inference** |
| **EMA loss balancing** | Per-task loss normalization with priority weights and NaN guards | **Zero at inference** |

#### Head Details

**Stereo Depth** — Flat CostVolume with cross-disparity learning at stride 4 resolution:
- Flat CostVolume at stride 8: shift + concatenate left/right features for all 24 disparity bins into a single 384-channel tensor
- MLP Reduction (384→96→24): two-stage 1×1 Conv with ReLU6 — enables each output bin to see all 24 shifts simultaneously, learning cross-disparity correlations instead of isolated per-bin matching
- Post-correlation refinement: 2× Conv2d 3×3 with spatial context smoothing
- Confidence Gate: peak confidence check — suppresses false matches on repetitive textures and sky regions
- Refine s4: Upscale ×2, backbone + geo + normals guidance via CoordConv
- Output: dense disparity map at s4 (120×160); for display, multiply by 4 and upscale with OpenCV

**Surface Normals** — Multi-scale fusion at stride 4:
- s4 backbone (64ch) + adapted s8 (32ch) + GeometryStem (32ch) = 128ch fused via CoordConv
- L2 normalization (deploy-safe: max-scaling to prevent INT8 overflow, then sqrt + clamp)
- Output: per-pixel unit normal vectors at s4 resolution (120×160)

**Segmentation** — LRASPP with normals injection:
- Low path: s4 features + predicted normals
- High path: s16 features via LearnablePool + 1×1 projection
- Mid path: dilated conv on s16 + normals
- Labels fused from depth-derived geometry (floor angle, surface roughness) + SegFormer-b2 teacher predictions (semantic classes)
- 6 classes: FLOOR (smooth hard surfaces), STEP (stairs), WALL (vertical), OBSTACLE (impassable), VOID (sky/far), TERRAIN (walkable but uneven: grass, sand, dirt)

**Object Detection** — YOLO-style 3-scale:
- 3-scale decoupled heads (s8, s16, s32) with CoordConv + RepConv
- 41 classes: 40 robot-relevant COCO classes + UNKNOWN (generalized objectness for unseen objects)
- UNKNOWN class trained on all remaining ~40 COCO categories — teaches the model "there is something here" even for objects outside the 40 known classes
- GIoU box regression, focal loss for classification

#### Training

| Aspect | Detail |
|---|---|
| Backbone init | MobileNetV2-1.4 pretrained on ImageNet, first conv patched 3→1 channel via luminance weight merging |
| Stereo + Seg + Normals data | TartanAir synthetic dataset (photorealistic indoor/outdoor stereo pairs with dense depth GT) |
| Detection data | COCO train2017 with offline YOLOv5 pseudo-label completion |
| Seg label fusion | Geometry (depth + normals thresholds) merged with SegFormer-b2 teacher on color images |
| Loss balancing | EMA-normalized multi-task loss with per-task priority weights and clamped effective weights [0.5, 10.0] |
| Optimizer | AdamW, per-module LR multipliers, Flat-Cosine LR schedule (warmup → hold → cosine decay) |
| Precision | Mixed FP16 via GradScaler, FP16-safe normalize (eps=1e-4), L1-norm edge maps (no sqrt) |
| Stability | NaN guards on EMA + total loss, per-module + global gradient clipping, forced `.item()` on all log values to prevent memory leaks in long training runs |
| Hardware | NVIDIA RTX 3080 Ti (12 GB), AMD Ryzen 9 5950X, WSL2 |

#### Eval Results

| Task | Metric | V3.1 | V4.0 | V5.0 | V4→V5 |
|---|---|---|---|---|---|
| **Stereo** | EPE | 2.42 px | 1.00 px | **0.97 px** | −3% |
| **Stereo** | Bad3 | — | 17.1% | **14.1%** | −18% |
| **Detection** | mAP@50 | 0.118 | 0.260 | **0.253** | −3% (41 cls) |
| **Detection** | Top10 Conf | — | 0.593 | **0.689** | +16% |
| **Segmentation** | mIoU | 23.8% | 22.7% | **22.6%** | ≈ (new classes) |
| **Normals** | Cosine Sim | 0.567 | 0.639 | **0.638** | ≈ |

**V5.0 highlights:**
- Stereo Bad3 drops from 17.1% to 14.1% — the MLP reduction and cross-disparity learning significantly improve matching quality
- YOLO confidence jumps 16% thanks to wider backbone features and the UNKNOWN class providing generalized objectness training
- YOLO mAP@50 is slightly lower (0.253 vs 0.260) because V5.0 has 41 classes instead of 40 — the additional UNKNOWN class makes classification marginally harder while improving object detection robustness
- Seg mIoU is comparable despite a complete class redefinition (WALKABLE→FLOOR, NAV_ANCHOR removed, TERRAIN added)
- VOID detection works for the first time (53.7% IoU vs 0.0% in V4.0)

*All metrics evaluated on TartanAir eval (amusement, oldtown) and COCO val2017. Stereo EPE measured at s4 resolution (120×160).*

### Hailo-8 NPU Deployment

The model is split into **3 HEF files** for deployment on the Hailo-8 NPU. Alternative splits were evaluated (2-HEF combined, 3-HEF with Normals+Detection merged) but failed due to INT8 concat zero-point mismatches or excessive inter-context bandwidth. The 3-HEF split remains the most reliable and performant approach.

#### 3-HEF Pipeline

```
img_left ──→ [HEF A: Backbone] ──→ f_s4, f_s8, f_s16, f_s32
img_right ─→ [HEF A: Backbone] ──→ f_s4_r, f_s8_r
                                         │
              features_l + features_r ───→ [HEF B: Geometry] ──→ disp_s4, normals_s4, disp_s8
                                         │
              features_l + normals_s4 ──→ [HEF C: Detection] ──→ seg, yolo_s8, yolo_s16, yolo_s32
```

#### Compilation Results

| HEF | Contexts | Weights | GOPS | Inter-Context BW | SNR (dB) |
|---|---|---|---|---|---|
| **A: Backbone** | 1 | 3.0 M | 2.57 | 0 MB | 14–18 |
| **B: Geometry** | 3 | 0.3 M | ~12 | 73.9 MB | 28–39 |
| **C: Detection** | 2 | 3.9 M | ~8 | 10.8 MB | 40–44 |
| **Total** | **6** | **7.2 M** | **~23** | — | — |

#### Cluster Utilization

**Backbone** (single context):

| Cluster | Control | Compute | Memory |
|---|---|---|---|
| Total | 74.2% | 47.7% | 34.4% |

**Geometry** (3 contexts, highest utilization context shown):

| Cluster | Control | Compute | Memory |
|---|---|---|---|
| Total (ctx 1) | 71.9% | 28.1% | 26.4% |

**Detection** (2 contexts, highest utilization context shown):

| Cluster | Control | Compute | Memory |
|---|---|---|---|
| Total (ctx 0) | 60.2% | 33.6% | 43.4% |

#### Quantization Quality (SNR)

| Output | HEF | SNR (dB) | Quality |
|---|---|---|---|
| f_s4 (backbone) | A | 16.3 | Acceptable (intermediate feature) |
| f_s8 (backbone) | A | 16.0 | Acceptable (intermediate feature) |
| f_s16 (backbone) | A | 14.2 | Acceptable (intermediate feature) |
| f_s32 (backbone) | A | 15.2 | Acceptable (intermediate feature) |
| disp_s4 (stereo) | B | **39.1** | Excellent |
| normals_s4 | B | **33.1** | Very good |
| disp_s8 (coarse) | B | **27.8** | Good |
| seg | C | **44.5** | Excellent |
| yolo_s8 | C | **41.8** | Excellent |
| yolo_s16 | C | **43.6** | Excellent |
| yolo_s32 | C | **39.7** | Excellent |

*Backbone SNR is lower because intermediate features have wider value distributions. The downstream heads compensate effectively — all final output SNRs exceed 27 dB.*

#### Runtime Performance (Raspberry Pi 5, PCIe Gen 3)

| Step | V4.0 Latency | V5.0 Latency |
|---|---|---|
| Backbone (left) | 13.5 ms | 14.0 ms |
| Backbone (right) | 10.0 ms | 9.6 ms |
| Geometry (stereo + normals) | 21.8 ms | 21.7 ms |
| Detection (seg + YOLO) | 10.6 ms | 10.8 ms |
| **Pipeline total** | **56 ms → 17.9 FPS** | **56 ms → 16.3 FPS** |

*V5.0 uses stereo-focused channel alignment (64/128/128/256) which produces wider feature tensors, slightly increasing transfer overhead despite similar compute times. Measured on Raspberry Pi 5 with PCIe Gen 3 (`dtparam=pciex1_gen=3`).*

#### Lessons Learned: Hailo-8 Optimization

The path from a trained PyTorch model to a working HEF on the Hailo-8 was the most challenging part of this project. Key takeaways:

1. **Squeeze-and-Excite blocks are NPU killers.** MobileNetV3-Large with SE blocks: 35 ms per backbone pass. Without SE: 5.6 ms — a 6.3× speedup. The avgpool→fc→fc→sigmoid→multiply chain creates excessive context switches.

2. **HardSwish costs more than expected.** Even without SE, MobileNetV3 (16 FPS) was slower than MobileNetV2 (18.5 FPS) because HardSwish compiles as a multi-op sequence requiring 16-bit precision.

3. **AvgPool2d causes quantization failures.** Global average pooling with large kernel sizes (30×40, 60×80) triggers shift-delta errors in the Hailo quantizer. Solution: replace with depthwise conv initialized as averaging (`LearnablePool`), or use `pre_quantization_optimization(global_avgpool_reduction)`.

4. **The DFC renames all ONNX inputs.** Start nodes become `input_layer1`, `input_layer2`, etc., regardless of the ONNX names. Input mapping must use positional order, not name matching.

5. **Model script normalization requires assignment syntax.** `norm_0 = normalization([mean], [std], input_layer1)` — bare `normalization()` calls fail silently.

6. **Single-HEF is not always faster.** A single HEF with many contexts can have higher inter-context bandwidth than multiple smaller HEFs. Always benchmark both approaches.

7. **Calibration data must be unnormalized.** When using in-network normalization via model script, calibration data should be raw \[0, 255\] values, not pre-normalized.

8. **RepConv deploy flag must be threaded through all constructors.** If any `RepConv` module doesn't receive `deploy=True`, the folded weights won't load. Use a post-creation fix: iterate all modules and set `deploy=True` + create `rbr_reparam` manually.

9. **Classification backbones waste channels for dense prediction.** MobileNetV2-1.4 puts 448 channels at s32 (for ImageNet classification) but only 48 at s8 (where stereo matching happens). A simple 1×1 projection ("Channel Aligner") redistributes capacity: wider s4/s8 for stereo, slimmer s32 for detection. ImageNet weights are preserved — only the projection layers are new.

10. **Grouped Convolutions in Cost Volumes limit stereo quality.** V4.0's GroupedConv processed each disparity bin in isolation — bin 5 had no information about bins 4 or 6. Replacing this with a flat Concat + MLP reduction (384→96→24) lets each output bin see all 24 shifts simultaneously, enabling cross-disparity learning. This changed the learning dynamics fundamentally: the model learns global depth structure instead of local bin-by-bin matching.

11. **Concat zero-point mismatches block HEF merging.** Combining Normals (range [-1, 1]) and Backbone features (range [-3, 3]) in a single HEF causes INT8 quantization conflicts at Concat nodes. Keeping them in separate HEFs lets the compiler resolve zero-points at HEF boundaries. A 2-HEF approach (Backbone + Combined) failed for this reason; 3-HEF remains the most reliable split.

### Mission Planning – Qwen3 LLM

High-level command interpretation uses a quantized LLM running locally on the Pi 5:

- **Model**: `Qwen3-4B-Instruct-2507-Q4_K_M.gguf`
- **Runtime**: `llama-cpp-python` with OpenBLAS acceleration
- **Role**: translates natural language commands (e.g. *"go to the kitchen and find a red cup"*) into structured JSON objects that the motion controller can execute
- **Inference**: Currently CPU-only on the Pi 5. As far as I'm aware, there is no SLM/LLM solution available for the Hailo-8 yet, but I'd be happy to hear otherwise.

---

## Camera Pipeline & GPU-Accelerated Rectification

> **This may be of independent interest as a standalone technique.**

Stereo vision requires both camera images to be rectified before depth estimation — distortion must be removed and the images aligned so that corresponding points sit on the same horizontal scanline. On a Raspberry Pi, doing this in software (OpenCV `remap`) consumes a significant portion of the CPU budget at high resolution.

SLARC offloads the entire rectification and rescaling pipeline to the **VideoCore VII GPU** using OpenGL ES 3.0 fragment shaders via `moderngl`. The approach:

```
picamera2 (1440×1080, YUV420)
    │  Y-plane only → Shared Memory
    ▼
OpenGL ES Fragment Shader (VideoCore VII)
    │  Inverse camera model per output pixel:
    │   1. Map output pixel → ray (K_new⁻¹)
    │   2. Rotate ray into camera frame (R⁻¹)
    │   3. Apply radial + tangential distortion (k1, k2, p1, p2)
    │   4. Project back to source pixel (K_old)
    │   5. Bilinear texture sample
    ▼
Rectified + scaled output (640×480, RGB)
    │  → Shared Memory → Hailo-8 inference
    ▼
POSIX Semaphore signals AI process
```

**Why this matters on a Raspberry Pi:**
- The VideoCore VII has its own memory bus and shader cores that are otherwise completely idle during inference workloads
- CPU load for rectification at 50 fps drops from ~40% (OpenCV) to ~0% (GPU shader)
- Both cameras are processed sequentially in a single OpenGL framebuffer pass
- The pipeline handles arbitrary stereo calibration matrices loaded from a JSON file, or falls back to identity matrices for testing

The implementation lives in `vision/vision_processor.py` and `vision/vision_capture.py`. Synchronization between the two camera capture processes and the GPU worker uses a `multiprocessing.Barrier` and POSIX semaphores, keeping latency deterministic.

If you are working on stereo vision on Raspberry Pi and looking for a way to free up CPU time, this approach should transfer directly to any project using `picamera2` + `moderngl`.

---

## Software Stack

### Virtual Environments

All Python components run in isolated venvs under `~/projects/slarc/venvs/`:

| Venv | Purpose | Key packages |
|---|---|---|
| `slarc_base` | Shared IPC / messaging | `posix_ipc` |
| `vision` | Camera, OpenCV, rendering | `picamera2`, `opencv-python`, `moderngl`, `pyzmq` |
| `ai` | LLM + perception inference | `llama-cpp-python`, `onnxruntime`, `ollama`, `hailort` |
| `sensors` | IMU, I²C sensors | `smbus2`, `icm20948`, `scipy` |
| `motion_control` | Servo / GPIO control | `RPi.GPIO`, `scipy` |
| `slam` | Mapping and localization | `opencv-python`, `matplotlib` |

`vision` and `ai` use `--system-site-packages` to access `hailort` and `picamera2`, which are installed system-wide by the Hailo stack.

### Shell Shortcuts

`setup_venvs.sh` automatically adds convenience aliases to `~/.bashrc`:

```bash
venv-ai       # source .../venvs/ai/bin/activate
venv-vision   # source .../venvs/vision/bin/activate
venv-sensors  # source .../venvs/sensors/bin/activate
venv-motion   # source .../venvs/motion_control/bin/activate
venv-slam     # source .../venvs/slam/bin/activate
venv-base     # source .../venvs/slarc_base/bin/activate
venv-off      # deactivate
```

Active after the next login, or immediately with `source ~/.bashrc`.

---

## Raspberry Pi 5 Configuration

### Boot without button press

To allow the Pi to boot automatically when power is applied (e.g. when the Waveshare driver board enables the relay), add to `/boot/firmware/config.txt`:

```
POWER_OFF_ON_HALT=0
```

Without this setting, the Pi enters a low-power halt state on shutdown and requires a physical button press to boot again.

### PCIe Gen 3

For optimal Hailo-8 transfer speeds, enable PCIe Gen 3:

```
dtparam=pciex1_gen=3
```

This is already configured automatically by the AI HAT+. If using an M.2 AI Kit, enable it manually via `raspi-config → Advanced Options → PCIe Speed → Yes` or by adding the line above to `/boot/firmware/config.txt`.

---

## Requirements

| Component | Requirement |
|---|---|
| Hardware | Raspberry Pi 5 |
| AI Accelerator | Hailo-8 (AI HAT+ or AI Kit) |
| Operating System | Raspberry Pi OS **Trixie** – 64-bit |
| Kernel | ≥ 6.6.31 |

> **Note:** Raspberry Pi OS Bookworm is **not** supported for the current Hailo software stack (`hailo-all` ≥ 4.20). Flash a fresh Trixie image using [Raspberry Pi Imager](https://www.raspberrypi.com/software/).

---

## Quick Start

Clone this repository and run the setup script:
```bash
# git is required to clone – on a fresh Trixie image it may be missing:
sudo apt install -y git

git clone https://github.com/Hoehlenbaer/SLARC.git ~/projects/slarc
cd ~/projects/slarc/utilities
sudo bash setup_venvs.sh
```

That's it. The script handles everything in the correct order:

1. **System packages** – installs `build-essential`, `cmake`, `ninja-build`, `libopenblas-dev`, `python3-venv` and others if missing
2. **Hailo stack** – installs `hailo-all` via apt if not already present, builds the DKMS kernel module, configures autoload, and installs a post-upgrade hook so the driver survives future kernel updates automatically
3. **Virtual environments** – creates all project venvs
4. **Python packages** – installs all pip dependencies per venv, including a custom OpenBLAS-accelerated build of `llama-cpp-python`
5. **Shell shortcuts** – adds `venv-ai`, `venv-vision`, `venv-off` etc. to `~/.bashrc`
6. **LLM model** – downloads `Qwen3-4B-Instruct-2507-Q4_K_M.gguf` (~2.3 GB) to `~/.models/` if not already present; download is resumable with Ctrl+C

The script is **fully idempotent** – re-running it on an already configured system skips everything that is already in place.

> **After a fresh Hailo installation:** A reboot is required before the Hailo device becomes available. The script will remind you.

---

## llama-cpp-python

Built from source with OpenBLAS acceleration. The repository is cloned to `~/llama-cpp-python` and is handled automatically by `setup_venvs.sh`. To rebuild manually:

```bash
cd ~/llama-cpp-python
source ~/projects/slarc/venvs/ai/bin/activate
CMAKE_ARGS="-DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS" pip install . --no-cache-dir
deactivate
```

---

## Hailo NPU

### Verify the device

```bash
hailortcli fw-control identify
```

### Kernel updates

After a kernel update (`apt upgrade`), the Hailo PCIe driver is automatically rebuilt by a DKMS hook that `setup_venvs.sh` installs at `/etc/kernel/postinst.d/dkms-hailo`. No manual action required. If you suspect the driver is missing after an update:

```bash
dkms status                  # should show current kernel as 'installed'
sudo modprobe hailo_pci      # load manually if needed
hailortcli fw-control identify
```

---

## Configuration Backup & Restore

To migrate settings from a Bookworm system to Trixie (PCIe speed, PWM overlays, I²C, systemd units, etc.):

```bash
# On the old Bookworm system
sudo bash utilities/rpi_config_backup.sh

# Copy the archive to the Trixie system, then:
sudo bash utilities/rpi_config_restore.sh rpi_backup_YYYYMMDD_HHMMSS.tar.gz
```

The restore script is interactive and selective – it never blindly overwrites system files. Every file gets a `.pre-restore.bak` before being changed.

---

## Repository Structure

```
SLARC/
├── vision/
│   ├── vision_main.py          # Entry point – manages workers and shared memory
│   ├── vision_capture.py       # Camera capture workers (picamera2, dual sync)
│   └── vision_processor.py     # GPU rectification worker (OpenGL ES / moderngl)
├── utilities/
│   ├── setup_venvs.sh          # Main setup script (start here)
│   ├── rpi_config_backup.sh    # Backs up RPi config to a .tar.gz archive
│   └── rpi_config_restore.sh   # Restores config from archive (Bookworm → Trixie)
└── README.md
```

*Additional project modules (perception, motion control, SLAM, mission planner) will be added as development progresses.*

---

## Project Status

| Component | Status |
|---|---|
| Chassis / legs – 3D print design | 🔧 Work in progress |
| Servo control (ESP32) | 🔧 Work in progress |
| Camera pipeline – GPU rectification | ✅ Working |
| FusedHexapodModel V5.0 – Training | ✅ Complete |
| FusedHexapodModel V5.0 – Hailo deployment | ✅ 3-HEF pipeline, 16.3 FPS |
| FusedHexapodModel – Stereo head | ✅ EPE 0.97 px, Bad3 14.1% |
| FusedHexapodModel – Surface normals | ✅ Cosine sim 0.638 |
| FusedHexapodModel – Segmentation | ✅ mIoU 22.6% (6 classes: FLOOR/STEP/WALL/OBSTACLE/VOID/TERRAIN) |
| FusedHexapodModel – Object detection | ✅ mAP@50 0.253 (41 classes incl. UNKNOWN) |
| LLM mission planner | ✅ Prototype running |
| System setup scripts | ✅ Complete |

---

## Troubleshooting

**Hailo stops working after `apt upgrade`**
A kernel update replaced the running kernel. The DKMS hook should handle this automatically, but if it didn't:
```bash
sudo dkms build hailo_pci/4.23.0 -k $(uname -r)
sudo dkms install hailo_pci/4.23.0 -k $(uname -r)
sudo modprobe hailo_pci
```

**Hailo not detected after install**
Reboot the Raspberry Pi. The kernel module needs to load after a fresh `hailo-all` installation.

**`hailortcli fw-control identify` fails**
- Check that the AI HAT+ is properly seated
- Verify PCIe is enabled in `/boot/firmware/config.txt`
- Check kernel version: `uname -r` (must be ≥ 6.6.31)

**llama-cpp-python build fails**
- Ensure `libopenblas-dev` is installed: `dpkg -s libopenblas-dev`
- Check available disk space – the build temporarily requires several GB
- If RAM is tight, a swapfile helps: `sudo dphys-swapfile setup`

**numpy version conflicts**
`sensors` and `slam` venvs intentionally pin numpy to `1.24` for compatibility with `scipy==1.11.4`. This is isolated from the `ai` venv which uses the latest numpy.

**Pi won't boot after shutdown**
Add `POWER_OFF_ON_HALT=0` to `/boot/firmware/config.txt`. Without this, the Pi enters a halt state that requires a physical button press.

---

## License

MIT License

Copyright (c) 2026 Hoehlenbaer (https://github.com/Hoehlenbaer/SLARC)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

*If you use SLARC code or techniques in your own project, a mention or link back is always appreciated — not required, just good open-source karma.*
