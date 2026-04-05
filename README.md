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
| **Power** | Zeee 9000 mAh LiPo 3S high-performance battery |
| **Chassis** | Fully 3D-printable (PETG / PLA / TPU) – *work in progress* |

The Raspberry Pi handles all AI inference and high-level planning. The ESP32 handles real-time servo control and low-level motion execution, communicating with the Pi over a serial bus.

---

## AI Architecture

### Perception – FusedHexapodModel V3.1

The core perception system is a **single multi-task neural network** with four output heads, designed to run entirely on the Hailo-8 NPU. All heads share a common MobileNetV3-Large backbone — the feature extraction cost is paid once per frame.

#### Architecture Overview

```
Stereo Camera Pair (640×480, grayscale)
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  MobileNetV3-Large Backbone (1-channel input, luminance merge)  │
│  out_indices: s4 (24ch) · s8 (40ch) · s16 (112ch) · s32 (960ch)│
└──┬──────────┬──────────┬──────────┬─────────────────────────────┘
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
   │          │    │  (64ch at all scales)│
   │          │    └──┬───────┬───────┬──┘
   │          │       │s8     │s16    │s32
   │          │       ▼       ▼       ▼
   │          │    ┌─────┐ ┌─────┐ ┌─────┐
   │          │    │CBAM │ │CBAM │ │CBAM │ Channel + Spatial Attention
   │          │    └──┬──┘ └──┬──┘ └──┬──┘
   │          │       ▼       ▼       ▼
   │          │    ┌────────────────────────┐
   │          │    │    YOLO Detection      │ 40 robot-relevant classes
   │          │    │  (3 Decoupled Heads)   │ 3 scales: s8 / s16 / s32
   │          │    └────────────────────────┘
   │          │
   ▼          ▼
┌──────────────────┐
│  Geometry Stem   │ RepConv(24→32) × 2
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
│  Stage 1: Fusion     │    │  CoarseCostVolume (s8)          │
│   s4 + s8 + geo      │    │   · Universal matching metric   │
│   CoordConv → 96→64  │    │   · 24 disparity steps          │
│   → 32 → 3 (coarse)  │    │   · CoordConv + geo features    │
│                      │    │                                 │
│  Stage 2: Refine s1  │    │  Context Network (slice-wise)   │
│   coarse + gray_img  │    │   · 1→16→16→1, RF 7×7           │
│   + Sobel edges      │    │   · No disparity mixing          │
│   DWSepConv × 2      │    │                                 │
│   + residual         │    │  Refine s4 (backbone guidance)  │
│                      │    │  Refine s1 (image + Sobel edges)│
│  Output:             │    │                                 │
│   normals_s4 → Seg   │    │  Output: disparity [0–192 px]   │
│   normals_s1 → Loss  │    │                                 │
└──────┬───────────────┘    └─────────────────────────────────┘
       │ normals_s4
       ▼
┌────────────────────────┐
│  LRASPP Seg Head       │
│  low (s4 + normals)    │
│  + high (s16 pooled)   │
│  + mid (dilated, s16   │
│    + normals)          │
│                        │
│  6 classes:            │
│  WALKABLE · STEP ·     │
│  WALL · OBSTACLE ·     │
│  VEGETATION · VOID     │
└────────────────────────┘
```

#### Building Blocks

| Block | Purpose | NPU Cost |
|---|---|---|
| **MobileNetV3-Large** | Efficient shared feature extraction (pretrained on ImageNet) | Very low — optimized for mobile NPUs |
| **SPPF** | Expands receptive field at s32 via cascaded max-pooling; helps YOLO detect large/nearby objects | Minimal — only pooling + 1×1 convs |
| **CBAM** | Channel + spatial attention after FPN; focuses YOLO on relevant regions | Low — small conv layers per scale |
| **CoordConv** | Appends normalized X/Y coordinate grids to conv input; gives the network spatial awareness for stereo offset and surface orientation | Negligible — just 2 extra input channels |
| **RepConv** | Three parallel paths during training (3×3 + 1×1 + identity); folds into a single 3×3 conv at inference | **Zero at inference** — mathematically equivalent to standard conv after folding |
| **GeometryStem** | Extracts high-frequency edge features from s4 backbone output via 2× RepConv; feeds into Stereo and Normals heads | Low — 2 convs at stride 4 |
| **DWSepConv** | Depthwise-separable convolution; used throughout for parameter efficiency | Very efficient — ~8–9× fewer FLOPs than standard conv |
| **Normals injection** | Detached normals guide the stereo refinement stage; provides geometric priors for depth boundaries | Zero — pure data flow, no extra ops |
| **SegFormer teacher fusion** | SegFormer-b2 runs on GPU during training only; enriches geometry-derived seg labels with semantic knowledge (water, vegetation, glass) | **Zero at inference** — teacher is offline |
| **EMA loss balancing** | Exponential moving average normalizes all task losses to equal scale; priority weights control relative importance | **Zero at inference** — training logic only |

#### Head Details

**Stereo Depth** — Hierarchical coarse-to-fine with edge guidance:
- Coarse: Cost volume at stride 8 (24 disparity bins), single universal matching metric, slice-wise spatial context smoothing
- Refine s4: Upscale ×2, backbone + geo + normals guidance via CoordConv
- Refine s1: Upscale ×4, grayscale image + Sobel edge guidance
- Output: dense disparity map [0–192 px], equivalent to ~0.4–200 m depth range

**Surface Normals** — Multi-scale fusion with image-guided refinement:
- Coarse: s4 backbone (24ch) + adapted s8 (32ch) + GeometryStem (32ch) = 88ch fused via CoordConv
- Refine: Bilinear upscale to full res, then DWSepConv guided by grayscale image + Sobel edges
- Output: per-pixel unit normal vectors at full resolution (640×480)

**Segmentation** — LRASPP with normals injection:
- Low path: s4 features + predicted normals (provides geometric surface cues)
- High path: s16 features pooled + projected
- Mid path: dilated conv on s16 + normals
- Labels fused from depth-derived geometry + SegFormer-b2 teacher predictions on color images
- 6 classes: WALKABLE (includes grass), STEP, WALL, OBSTACLE (includes water), VEGETATION, VOID

**Object Detection** — YOLO-style with attention:
- 3-scale decoupled heads (s8, s16, s32) after CBAM attention
- 40 robot-relevant COCO classes (subset of 80, selected for indoor/outdoor navigation)
- GIoU box regression, focal loss for classification
- Pseudo-labels from YOLOv5 teacher fill missing COCO annotations

#### Training

| Aspect | Detail |
|---|---|
| Backbone init | MobileNetV3-Large pretrained on ImageNet, first conv patched 3→1 channel via luminance weight merging |
| Stereo + Seg + Normals data | TartanAir synthetic dataset (photorealistic indoor/outdoor stereo pairs with dense depth GT) |
| Detection data | COCO train2017 with offline YOLOv5 pseudo-label completion |
| Seg label fusion | Geometry (depth + normals thresholds) merged with SegFormer-b2 teacher on color images |
| Loss balancing | EMA-normalized multi-task loss with per-task priority weights and clamped effective weights [0.5, 10.0] |
| Optimizer | AdamW, per-module LR multipliers, Flat-Cosine LR schedule (warmup → hold → cosine decay) |
| Precision | Mixed FP16 via GradScaler, FP16-safe normalize (eps=1e-4), L1-norm edge maps (no sqrt) |
| Stability | NaN guards on EMA + total loss, EMA init clamp, per-module + global gradient clipping |
| Hardware | NVIDIA RTX 3080 Ti (12 GB), AMD Ryzen 9 5950X, WSL2 |

#### V3.0 Eval Results

| Task | Metric | Value |
|---|---|---|
| **Stereo** | EPE | 2.42 px |
| **Stereo** | Bad3px | 15.5% |
| **Detection** | mAP@50 | 0.118 |
| **Segmentation** | mIoU | 23.8% |
| **Segmentation** | Pixel Accuracy | ~82% |
| **Normals** | Cosine Similarity | 0.567 |

*Evaluated on TartanAir eval (amusement, oldtown) and COCO val2017. Training ongoing — these numbers reflect an early checkpoint.*

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

For best performance, PCIe should run at Gen 3. The AI HAT+ configures this automatically. If you are using an M.2 AI Kit, enable Gen 3 manually:

```bash
sudo raspi-config
# → Advanced Options → PCIe Speed → Yes
```

Or add this to `/boot/firmware/config.txt`:

```
dtparam=pciex1_gen=3
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
| FusedHexapodModel – Stereo head | ✅ Converging (V3.1 training) |
| FusedHexapodModel – Surface normals | ✅ Converging |
| FusedHexapodModel – Segmentation | ✅ Converging |
| FusedHexapodModel – Object detection | 🔧 Active training / tuning |
| Hailo NPU export | ⏳ Planned after training completion |
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

---

## License

MIT License

Copyright (c) 2026 Hoehlenbaer (https://github.com/Hoehlenbaer/SLARC)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

*If you use SLARC code or techniques in your own project, a mention or link back is always appreciated — not required, just good open-source karma.*
