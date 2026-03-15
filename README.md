# SLARC – Self-Localizing Autonomous Robot Crab

> *"Crab" is a slight misnomer — SLARC has six legs, not ten, and will use its front two limbs for grasping rather than walking. But "SLARC" has a better ring to it than "SLARG".*

SLARC is a personal hobby project with an ambitious goal: build a **state-of-the-art hexapod robot that is fully AI-controlled** — from low-level motion to high-level mission planning — using entirely off-the-shelf hardware, a fully 3D-printable chassis, and custom-trained neural networks.

---

## What makes SLARC interesting

Most hobbyist hexapods are scripted or rely on simple remote control. SLARC aims to close the gap between hobby robotics and current research:

- **Fused multi-task perception** – a single shared neural network simultaneously performs stereo depth estimation, semantic segmentation, and object detection, all optimized for the Hailo-8 NPU
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

### Perception – FusedHexapodModel

The core perception system is a **single multi-task neural network** designed to run entirely on the Hailo-8 NPU:

```
Stereo Camera Pair
    │
    ▼
MobileNetV3-large Backbone  (shared feature extractor)
    │
    ├── Light FPN Neck  ──────────────►  YOLO-derived Object Detection Head
    │                                    (3-scale: s8 / s16 / s32)
    ├── LRASPP Segmentation Head
    │   (low-res s4 + high-res s16 features)
    │
    └── Hierarchical Stereo Head
        (coarse s8 disparity → refined s4 disparity)
```

**Why one shared network?**
Running three separate models would exceed the Hailo-8's memory bandwidth. Sharing the MobileNetV3 backbone means the feature extraction cost is paid once per frame, and all three heads run on top of that for free.

**Training:**
- **Stereo + Segmentation**: [TartanAir](https://theairlab.org/tartanair-dataset/) dataset (simulated photorealistic indoor/outdoor environments)
- **Object Detection**: COCO, with pseudo-label completion via a YOLOv5 teacher model to suppress false negatives on unlabeled objects
- **Deployment target**: Hailo-8 NPU via Hailo Dataflow Compiler export

### Mission Planning – Qwen3 LLM

High-level command interpretation uses a quantized LLM running locally on the Pi 5:

- **Model**: `Qwen3-4B-Instruct-2507-Q4_K_M.gguf`
- **Runtime**: `llama-cpp-python` with OpenBLAS acceleration
- **Role**: translates natural language commands (e.g. *"go to the kitchen and find a red cup"*) into structured JSON objects that the motion controller can execute
- **Inference**: CPU-only on Pi 5 – the Hailo-8 is fully occupied by the perception model during operation

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
git clone https://github.com/Hoehlenbaer/SLARC.git ~/projects/slarc
cd ~/projects/slarc/utilities
sudo bash setup_venvs.sh
```

That's it. The script handles everything in the correct order:

1. **System packages** – installs `git`, `build-essential`, `cmake`, `ninja-build`, `libopenblas-dev`, `python3-venv` and others if missing
2. **Hailo stack** – installs `hailo-all` via apt if not already present, then verifies the hardware connection
3. **Virtual environments** – creates all project venvs
4. **Python packages** – installs all pip dependencies per venv, including a custom OpenBLAS-accelerated build of `llama-cpp-python`

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

### PCIe speed

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
| FusedHexapodModel – Stereo head | ✅ Converging (Phase 2 training) |
| FusedHexapodModel – Segmentation | ✅ Converging |
| FusedHexapodModel – Object detection | 🔧 Active training / tuning |
| Hailo NPU export | ⏳ Planned after training completion |
| LLM mission planner | ✅ Prototype running |
| System setup scripts | ✅ Complete |

---

## Troubleshooting

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
