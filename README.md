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

### Perception – FusedHexapodModel V4.0

The core perception system is a **single multi-task neural network** with four output heads, designed to run entirely on the Hailo-8 NPU. All heads share a common MobileNetV2-1.4 backbone — the feature extraction cost is paid once per frame.

#### V3.1 → V4.0 Migration

V4.0 is a complete architecture redesign focused on Hailo-8 NPU deployment efficiency. Key changes:

| Change | V3.1 | V4.0 | Reason |
|---|---|---|---|
| Backbone | MobileNetV3-Large | **MobileNetV2-1.4** | SE blocks caused 6× slowdown on Hailo (35 ms → 5.6 ms) |
| Attention | CBAM after FPN | **Removed** | Similar to SE — AvgPool + FC chains are NPU-hostile |
| CostVolume channels | 32 | **16** | Halved without quality loss thanks to stronger backbone features |
| Stereo output | Full res (480×640) | **s4 (120×160)** | s1 refinement added artifacts; s4 is sufficient for navigation |
| Normals output | Full res (480×640) | **s4 (120×160)** | Full-res refinement removed; upscaling moved to ARM/display |
| AvgPool2d | nn.AvgPool2d | **LearnablePool (DW Conv)** | AvgPool causes quantization shift errors on Hailo |
| Activations | ReLU + HardSwish | **ReLU6 throughout** | Pure INT8 quantization, no 16-bit fallback needed |
| SiLU in SPPF | nn.SiLU | **nn.ReLU6** | SiLU compiles as HardSwish → 16-bit on Hailo |
| Confidence Gate | None | **Top-2 ambiguity gate** | Suppresses false stereo matches on repetitive textures and sky |
| NPU deployment | Not achieved | **3-HEF split, ~18.5 FPS** | Backbone + Geometry + Detection as separate HEFs |

#### Architecture Overview

```
Stereo Camera Pair (640×480, grayscale)
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  MobileNetV2-1.4 Backbone (1-channel input, luminance merge) │
│  out_indices: s4 (32ch) · s8 (48ch) · s16 (136ch) · s32 (448ch)│
└──┬──────────┬──────────┬──────────┬──────────────────────────┘
   │s4        │s8        │s16       │s32
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
   │          │    │    YOLO Detection      │ 40 robot-relevant classes
   │          │    │  (3 Decoupled Heads)   │ 3 scales: s8 / s16 / s32
   │          │    │  CoordConv + RepConv   │
   │          │    └────────────────────────┘
   │          │
   ▼          ▼
┌──────────────────┐
│  Geometry Stem   │ RepConv(32→32) × 2
│  (s4, 32ch out)  │ High-res edge features
└──┬───────────────┘
   │ geo_features
   │
   ├───────────────────────────────────┐
   │                                   │
   ▼                                   ▼
┌──────────────────────┐    ┌─────────────────────────────────┐
│   NormalsHead        │    │   Hierarchical Stereo Head      │
│                      │    │                                 │
│  Fusion: s4 + s8     │    │  CoarseCostVolume (s8)          │
│   + geo (CoordConv)  │    │   · 16ch features, 24 disp bins │
│   96 → 64 → 32 → 3  │    │   · CoordConv + geo features    │
│                      │    │                                 │
│  L2 normalize        │    │  Context Network (slice-wise)   │
│  (deploy-safe sqrt)  │    │   · 1→16→16→1, RF 7×7           │
│                      │    │                                 │
│  Output:             │    │  Confidence Gate (eval only)    │
│   normals_s4         │    │   · Suppresses ambiguous matches │
│   [1, 3, 120, 160]   │    │                                 │
│                      │    │  Refine s4 (backbone guidance)  │
└──────┬───────────────┘    │                                 │
       │ normals_s4         │  Output:                        │
       ▼                    │   disp_s4  [1, 1, 120, 160]     │
┌────────────────────────┐  │   disp_s8  [1, 1,  60,  80]     │
│  LRASPP Seg Head       │  └─────────────────────────────────┘
│  low (s4 + normals)    │
│  + high (s16, pooled   │
│    via LearnablePool)  │
│  + mid (dilated + norm)│
│                        │
│  Output:               │
│   seg [1, 6, 120, 160] │
│                        │
│  6 classes:            │
│  WALKABLE · STEP ·     │
│  WALL · OBSTACLE ·     │
│  NAV_ANCHOR · VOID     │
└────────────────────────┘
```

#### Model Summary

| Property | Value |
|---|---|
| Total parameters | 6.09 M |
| Backbone (MobileNetV2-1.4) | 3.45 M |
| YOLO Head | 1.46 M |
| Seg Head | 0.21 M |
| Normals Head | 0.16 M |
| Input | 1 × 480 × 640 grayscale (×2 for stereo) |
| Outputs | 7 tensors (disp_s4, seg, disp_s8, normals_s4, yolo_s8/s16/s32) |

#### Building Blocks

| Block | Purpose | NPU Cost |
|---|---|---|
| **MobileNetV2-1.4** | Shared backbone — wider channels (32/48/136/448) than MNV2-1.0, no SE blocks, pure ReLU6 | Very low — ideal for INT8 NPU |
| **SPPF** | Expands receptive field at s32 via cascaded 5×5 max-pooling | Minimal — pooling + 1×1 convs |
| **CoordConv** | Appends normalized X/Y coordinate grids; spatial awareness for stereo matching and normals | Negligible — 2 extra input channels |
| **RepConv** | Three parallel paths during training (3×3 + 1×1 + identity); folds into single 3×3 conv at deploy | **Zero overhead at inference** |
| **GeometryStem** | High-frequency edge features from s4 via 2× RepConv; shared by Stereo and Normals | Low — 2 convs at stride 4 |
| **DWSepConv** | Depthwise-separable convolution; ~8–9× fewer FLOPs than standard conv | Very efficient |
| **LearnablePool** | Replaces AvgPool2d with depthwise conv initialized as averaging; avoids Hailo quantization shift errors | Identical compute, better quantization |
| **Confidence Gate** | At inference: suppresses stereo matches where top-2 peaks are ambiguous (repetitive textures, sky) | Negligible — topk + clamp + mul |
| **SegFormer teacher fusion** | SegFormer-b2 on GPU during training only; enriches geometry-derived seg labels with semantics | **Zero at inference** |
| **EMA loss balancing** | Per-task loss normalization with priority weights and NaN guards | **Zero at inference** |

#### Head Details

**Stereo Depth** — Hierarchical coarse-to-fine at stride 4 resolution:
- Coarse: Cost volume at stride 8 (24 disparity bins, 16 feature channels), universal matching metric, slice-wise spatial context smoothing
- Confidence Gate: top-2 peak ambiguity check — suppresses false matches on repetitive textures and sky regions
- Refine s4: Upscale ×2, backbone + geo + normals guidance via CoordConv
- Output: dense disparity map at s4 (120×160); for display, multiply by 4 and upscale with OpenCV

**Surface Normals** — Multi-scale fusion at stride 4:
- s4 backbone (32ch) + adapted s8 (32ch) + GeometryStem (32ch) = 96ch fused via CoordConv
- L2 normalization (deploy-safe: max-scaling to prevent INT8 overflow, then sqrt + clamp)
- Output: per-pixel unit normal vectors at s4 resolution (120×160)

**Segmentation** — LRASPP with normals injection:
- Low path: s4 features + predicted normals
- High path: s16 features via LearnablePool + 1×1 projection
- Mid path: dilated conv on s16 + normals
- Labels fused from depth-derived geometry + SegFormer-b2 teacher predictions
- 6 classes: WALKABLE, STEP, WALL, OBSTACLE, NAV_ANCHOR, VOID

**Object Detection** — YOLO-style 3-scale:
- 3-scale decoupled heads (s8, s16, s32) with CoordConv + RepConv
- 40 robot-relevant COCO classes
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

#### V4.0 Eval Results

| Task | Metric | V3.1 | V4.0 | Change |
|---|---|---|---|---|
| **Stereo** | EPE | 2.42 px | **1.00 px** | −59% |
| **Stereo** | mAP@50 | — | — | — |
| **Detection** | mAP@50 | 0.118 | **0.260** | +120% |
| **Segmentation** | mIoU | 23.8% | 22.7% | −1.1% |
| **Normals** | Cosine Similarity | 0.567 | **0.639** | +13% |

*V4.0 stereo EPE is measured at s4 resolution (120×160). V3.1 EPE was at full resolution (480×640). Direct comparison is not meaningful for stereo — the improvement comes from removing artifact-prone full-res refinement. All other metrics are comparable.*

*Evaluated on TartanAir eval (amusement, oldtown) and COCO val2017 (40 robot-relevant classes).*

### Hailo-8 NPU Deployment

The model is split into **3 HEF files** for deployment on the Hailo-8 NPU. A single-HEF approach was not possible due to the SE-block-induced context explosion in V3.1; the V4.0 architecture (SE-free, no CBAM) was designed specifically for clean NPU compilation.

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

| Step | Latency (median) |
|---|---|
| Backbone (left) | ~5.6 ms |
| Backbone (right) | ~5.6 ms |
| Geometry (stereo + normals) | ~28.7 ms |
| Detection (seg + YOLO) | ~7.3 ms |
| Host overhead (activate, transfer) | ~7 ms |
| **Pipeline total** | **~54 ms → 18.5 FPS** |

*Measured with random input data. Real-world performance may vary slightly. PCIe Gen 3 (`dtparam=pciex1_gen=3`) is required for optimal transfer speeds.*

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
| FusedHexapodModel V4.0 – Training | ✅ Complete |
| FusedHexapodModel V4.0 – Hailo deployment | ✅ 3-HEF pipeline, 18.5 FPS |
| FusedHexapodModel – Stereo head | ✅ EPE 1.00 px (s4) |
| FusedHexapodModel – Surface normals | ✅ Cosine sim 0.639 |
| FusedHexapodModel – Segmentation | ✅ mIoU 22.7% |
| FusedHexapodModel – Object detection | ✅ mAP@50 0.260 |
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
