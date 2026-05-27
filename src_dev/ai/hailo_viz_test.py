#!/usr/bin/env python3
"""
V5.0 Hailo Visual Sanity Check — 16 Testbilder durch die 3-HEF Pipeline.
Erzeugt ein Dashboard pro Bild: Input | Disparity | Normals | Seg | YOLO

Vergleiche die Outputs visuell mit dem FP32-Eval auf dem PC.
"""

import numpy as np
import cv2
import os
import matplotlib
matplotlib.use('Agg')  # Headless auf dem Pi
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from hailo_platform import HEF, VDevice, InferVStreams, InputVStreamParams, OutputVStreamParams, FormatType

# =====================================================================
# KONFIGURATION
# =====================================================================
HEF_DIR = 'hefs'  # Ordner mit den 3 HEF-Dateien
TARTAN_DIR = 'test_images/tartan'
COCO_DIR = 'test_images/coco'
OUTPUT_DIR = 'viz_output'
os.makedirs(OUTPUT_DIR, exist_ok=True)

SEG_COLORS = np.array([
    [0, 200, 0],      # 0: FLOOR (grün)
    [255, 165, 0],    # 1: STEP (orange)
    [0, 100, 255],    # 2: WALL (blau)
    [255, 0, 0],      # 3: OBSTACLE (rot)
    [80, 80, 80],     # 4: VOID (dunkelgrau)
    [139, 90, 43],    # 5: TERRAIN (braun)
]) / 255.0

# YOLO
NUM_CLASSES = 41
CONF_THRESH = 0.25
NMS_THRESH = 0.45
BOX_CMAP = plt.cm.tab20

# =====================================================================
# BILD-VORBEREITUNG
# =====================================================================
'''
def load_gray_for_hailo(path, size=(640, 480)):
    """Lädt ein Bild als Grayscale UINT8 [1, H, W, 1] für den Hailo."""
    print(f"Reading: {path}")
    if path.endswith('.png'):
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    else:
        img = cv2.imread(path)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    img = cv2.resize(img, size)
    return img.reshape(1, size[1], size[0], 1).astype(np.float32)
'''
def load_gray_for_hailo(path, size=(640, 480)):
    """Lädt ein Bild exakt wie im PyTorch Training."""
    print(f"Reading: {path}")
    
    # 1. IMMER als BGR laden (ignoriere cv2.IMREAD_GRAYSCALE)
    img = cv2.imread(path)
    
    # 2. IMMER explizit konvertieren
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 3. Resize & Reshape
    img = cv2.resize(img, size)
    return img.reshape(1, size[1], size[0], 1).astype(np.float32)

def load_for_display(path, size=(320, 240)):
    """Lädt ein Bild für die Darstellung."""
    img = cv2.imread(path)
    if img is None:
        return np.zeros((size[1], size[0], 3), dtype=np.uint8)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return cv2.resize(img, size)


# =====================================================================
# HAILO PIPELINE
# =====================================================================
def setup_pipeline():
    hef_bb = HEF(os.path.join(HEF_DIR, 'hexapod_v5_backbone.hef'))
    hef_geo = HEF(os.path.join(HEF_DIR, 'hexapod_v5_geometry.hef'))
    hef_det = HEF(os.path.join(HEF_DIR, 'hexapod_v5_detection.hef'))

    target = VDevice()

    ng_bb = target.configure(hef_bb)[0]
    ng_geo = target.configure(hef_geo)[0]
    ng_det = target.configure(hef_det)[0]

    bb_in_p = InputVStreamParams.make(ng_bb, format_type=FormatType.FLOAT32)
    bb_out_p = OutputVStreamParams.make(ng_bb, format_type=FormatType.FLOAT32)
    geo_in_p = InputVStreamParams.make(ng_geo, format_type=FormatType.FLOAT32)
    geo_out_p = OutputVStreamParams.make(ng_geo, format_type=FormatType.FLOAT32)
    det_in_p = InputVStreamParams.make(ng_det, format_type=FormatType.FLOAT32)
    det_out_p = OutputVStreamParams.make(ng_det, format_type=FormatType.FLOAT32)

    return {
        'target': target,
        'ng_bb': ng_bb, 'ng_geo': ng_geo, 'ng_det': ng_det,
        'bb_in_p': bb_in_p, 'bb_out_p': bb_out_p,
        'geo_in_p': geo_in_p, 'geo_out_p': geo_out_p,
        'det_in_p': det_in_p, 'det_out_p': det_out_p,
    }


def run_inference(pipeline, img_left, img_right=None):
    """
    Führt die 3-HEF Pipeline aus.
    img_left/right: [1, 480, 640, 1] float32, Range [0, 255]
    
    Returns: dict mit disp_s4, normals_s4, disp_s8, seg, yolo_s8/s16/s32
    """
    p = pipeline
    
    if img_right is None:
        img_right = img_left  # COCO: gleiches Bild → Disparität ≈ 0


    # Shape-basiertes Output-Matching
    shape_to_key = {
        (120, 160): 'f_s4', (60, 80): 'f_s8',
        (30, 40): 'f_s16', (15, 20): 'f_s32',
    }
    
    # 1. Backbone L+R
    bb_in_name = list(p['ng_bb'].get_input_vstream_infos())[0].name
    with p['ng_bb'].activate(p['ng_bb'].create_params()):
        with InferVStreams(p['ng_bb'], p['bb_in_p'], p['bb_out_p']) as pipe:
            res_l = pipe.infer({bb_in_name: img_left})
            res_r = pipe.infer({bb_in_name: img_right})
    
    if isinstance(res_l, list):
        res_l = {f'out_{i}': r for i, r in enumerate(res_l)}
        res_r = {f'out_{i}': r for i, r in enumerate(res_r)}
    
    feat_l, feat_r = {}, {}
    for k, v in res_l.items():
        fk = shape_to_key.get((v.shape[1], v.shape[2]))
        if fk:
            feat_l[fk] = v
            feat_r[fk] = res_r[k]


    '''
    # 2. Geometry
    geo_inputs = sorted([i.name for i in p['ng_geo'].get_input_vstream_infos()])
    geo_feed = {
        geo_inputs[0]: feat_l['f_s4'],
        geo_inputs[1]: feat_l['f_s8'],
        geo_inputs[2]: feat_r['f_s4'],
        geo_inputs[3]: feat_r['f_s8'],
    }
    '''
    # 2. Geometry
    # Shape-basiertes Mapping aus HEF-Infos:
    geo_input_infos = {i.name: i.shape for i in p['ng_geo'].get_input_vstream_infos()}
    geo_feed = {}
    s8_count, s4_count = 0, 0
    for name, shape in sorted(geo_input_infos.items()):
        h, w = shape[0], shape[1]  # NHWC ohne Batch
        if h == 60 and w == 80:    # f_s8
            geo_feed[name] = feat_l['f_s8'] if s8_count == 0 else feat_r['f_s8']
            s8_count += 1
        elif h == 120 and w == 160 and shape[-1] != 3:  # f_s4 (nicht Normals)
            geo_feed[name] = feat_l['f_s4'] if s4_count == 0 else feat_r['f_s4']
            s4_count += 1
    
    
    with p['ng_geo'].activate(p['ng_geo'].create_params()):
        with InferVStreams(p['ng_geo'], p['geo_in_p'], p['geo_out_p']) as pipe:
            geo_out = pipe.infer(geo_feed)
    
    if isinstance(geo_out, list):
        geo_out = {f'out_{i}': r for i, r in enumerate(geo_out)}
    
    # Geo-Outputs zuordnen
    result = {}
    for k, v in geo_out.items():
        if v.shape[-1] == 1 and v.shape[1] == 120:
            result['disp_s4'] = v
        elif v.shape[-1] == 1 and v.shape[1] == 60:
            result['disp_s8'] = v
        elif v.shape[-1] == 3 and v.shape[1] == 120:
            result['normals_s4'] = v


    # 3. Detection
    det_inputs = sorted([i.name for i in p['ng_det'].get_input_vstream_infos()])
    normals = result.get('normals_s4', np.zeros((1, 120, 160, 3), dtype=np.float32))
    
    det_feed = {}
    for di in det_inputs:
        # Shape-basiertes Matching
        info = [i for i in p['ng_det'].get_input_vstream_infos() if i.name == di][0]
        shape = info.shape
        h, w = shape[0], shape[1]  # NHWC ohne Batch
        
        if h == 120 and w == 160 and shape[-1] == 3:
            det_feed[di] = normals
        elif h == 120 and w == 160:
            det_feed[di] = feat_l['f_s4']
        elif h == 60 and w == 80:
            det_feed[di] = feat_l['f_s8']
        elif h == 30 and w == 40:
            det_feed[di] = feat_l['f_s16']
        elif h == 15 and w == 20:
            det_feed[di] = feat_l['f_s32']
    
    with p['ng_det'].activate(p['ng_det'].create_params()):
        with InferVStreams(p['ng_det'], p['det_in_p'], p['det_out_p']) as pipe:
            det_out = pipe.infer(det_feed)
    
    if isinstance(det_out, list):
        det_out = {f'out_{i}': r for i, r in enumerate(det_out)}
    
    for k, v in det_out.items():
        if v.shape[-1] == 6:
            result['seg'] = v
        elif v.shape[-1] == 46:
            if v.shape[1] == 60:
                result['yolo_s8'] = v
            elif v.shape[1] == 30:
                result['yolo_s16'] = v
            elif v.shape[1] == 15:
                result['yolo_s32'] = v
    
    print(f"\n--- OUTPUT TENSOR DIAGNOSE ({img_left.shape}) ---")
    # Zuerst die Eingangs-Features des Backbones (wie gehabt)
    print(f"feat_l['f_s4']: min={feat_l['f_s4'].min():.3f}, max={feat_l['f_s4'].max():.3f}, mean={feat_l['f_s4'].mean():.3f}")
    print(f"feat_r['f_s4']: min={feat_r['f_s4'].min():.3f}, max={feat_r['f_s4'].max():.3f}, mean={feat_r['f_s4'].mean():.3f}")
    print("-" * 40)
    
    # Jetzt alle Ergebnisse der Heads dynamisch auslesen
    for key, val in result.items():
        if isinstance(val, np.ndarray):
            print(f"{key:15s}: min={val.min():.3f}, max={val.max():.3f}, mean={val.mean():.3f}, shape={val.shape}")
    print("--------------------------------------------------\n")
    return result


# =====================================================================
# YOLO POSTPROCESSING
# =====================================================================
def decode_yolo_scale(yolo_output, stride, conf_thresh=CONF_THRESH):
    """Dekodiert YOLO-Output einer Scale. Input: [1, H, W, 46] NHWC."""
    output = yolo_output[0]  # [H, W, 46]
    H, W = output.shape[0], output.shape[1]
    
    boxes, scores, class_ids = [], [], []
    
    for gy in range(H):
        for gx in range(W):
            obj = 1.0 / (1.0 + np.exp(-output[gy, gx, 4]))  # Sigmoid
            if obj < conf_thresh:
                continue
            
            cls_logits = output[gy, gx, 5:]
            cls_probs = 1.0 / (1.0 + np.exp(-cls_logits))
            cls_id = np.argmax(cls_probs)
            conf = obj * cls_probs[cls_id]
            
            if conf < conf_thresh:
                continue
            
            dx = 1.0 / (1.0 + np.exp(-output[gy, gx, 0]))
            dy = 1.0 / (1.0 + np.exp(-output[gy, gx, 1]))
            dw = np.exp(min(output[gy, gx, 2], 5.0)) * stride
            dh = np.exp(min(output[gy, gx, 3], 5.0)) * stride
            
            cx = (gx + dx) * stride
            cy = (gy + dy) * stride
            
            boxes.append([cx - dw/2, cy - dh/2, cx + dw/2, cy + dh/2])
            scores.append(conf)
            class_ids.append(cls_id)
    
    return boxes, scores, class_ids


def nms(boxes, scores, class_ids, iou_thresh=NMS_THRESH):
    """Einfache NMS."""
    if len(boxes) == 0:
        return [], [], []
    
    import torchvision
    import torch
    keep = torchvision.ops.nms(
        torch.tensor(boxes, dtype=torch.float32),
        torch.tensor(scores, dtype=torch.float32),
        iou_thresh
    ).numpy()
    
    return [boxes[i] for i in keep], [scores[i] for i in keep], [class_ids[i] for i in keep]


# =====================================================================
# VISUALISIERUNG
# =====================================================================
def visualize(img_display, result, title, output_path, is_stereo=True):
    """Erzeugt ein 1×5 Dashboard: Input | Disparity | Normals | Seg | YOLO."""
    TH, TW = 240, 320
    error_cmap = LinearSegmentedColormap.from_list("err", ["#1a1a1a", "#0000ff", "#ffff00", "#ff0000"])
    
    fig, axes = plt.subplots(1, 5, figsize=(25, 4))
    for ax in axes:
        ax.axis('off')
    
    # 1. Input
    axes[0].imshow(img_display)
    axes[0].set_title("Input", fontsize=10)
    
    # 2. Disparity
    if 'disp_s4' in result and is_stereo:
        disp = result['disp_s4'][0, :, :, 0]  # NHWC → HW
        disp_s1 = cv2.resize(disp * 4.0, (TW, TH))
        if (disp_s1 > 0).any():
            vmax = np.percentile(disp_s1[disp_s1 > 0], 99)
        else:
            vmax = 192.0
        axes[1].imshow(disp_s1, cmap='plasma', vmin=0, vmax=vmax)
        axes[1].set_title(f"Disparity (max={disp_s1.max():.1f}px)", fontsize=10)
    else:
        axes[1].set_title("Disparity (N/A)", fontsize=10)
    
    # 3. Normals
    if 'normals_s4' in result:
        n = result['normals_s4'][0]  # [120, 160, 3]
        n_vis = cv2.resize(np.clip((n + 1) / 2, 0, 1), (TW, TH))
        axes[2].imshow(n_vis)
        axes[2].set_title("Normals", fontsize=10)
    
    # 4. Seg
    if 'seg' in result:
        seg = result['seg'][0]  # [120, 160, 6]
        seg_class = np.argmax(seg, axis=-1)
        seg_rgb = cv2.resize(SEG_COLORS[seg_class], (TW, TH), interpolation=cv2.INTER_NEAREST)
        axes[3].imshow(seg_rgb)
        axes[3].set_title("Segmentation", fontsize=10)
    
    # 5. YOLO
    axes[4].imshow(img_display)
    all_boxes, all_scores, all_ids = [], [], []
    for scale_key, stride in [('yolo_s8', 8), ('yolo_s16', 16), ('yolo_s32', 32)]:
        if scale_key in result:
            b, s, c = decode_yolo_scale(result[scale_key], stride)
            all_boxes.extend(b)
            all_scores.extend(s)
            all_ids.extend(c)
    
    if all_boxes:
        boxes, scores, ids = nms(all_boxes, all_scores, all_ids)
        sx, sy = TW / 640, TH / 480
        for box, score, cls_id in zip(boxes, scores, ids):
            x1, y1, x2, y2 = box[0]*sx, box[1]*sy, box[2]*sx, box[3]*sy
            color = BOX_CMAP(cls_id % 20)
            label = f"{'UNK' if cls_id == 40 else cls_id}:{score:.2f}"
            axes[4].add_patch(plt.Rectangle((x1, y1), x2-x1, y2-y1,
                              fill=False, edgecolor=color, linewidth=1.5))
            axes[4].text(x1, y1-2, label, fontsize=7, color=color,
                        bbox=dict(boxstyle='round,pad=0.1', facecolor='black', alpha=0.5))
    
    axes[4].set_title(f"YOLO ({len(boxes) if all_boxes else 0} detections)", fontsize=10)
    
    plt.suptitle(title, fontsize=12, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  💾 {output_path}")


# =====================================================================
# MAIN
# =====================================================================
if __name__ == '__main__':
    from hailo_platform import Device, FormatType
    
    print("🔧 Setup Pipeline...")
    pipeline = setup_pipeline()
    
    # TartanAir (echte Stereo-Paare)
    print("\n📸 TartanAir Bilder:")
    tartan_files = sorted([f for f in os.listdir(TARTAN_DIR) if f.endswith('_left.png')])
    for i, fname in enumerate(tartan_files):
        left_path = os.path.join(TARTAN_DIR, fname)
        right_path = left_path.replace('_left', '_right').replace('image_left', 'image_right')
        
        img_left = load_gray_for_hailo(left_path)
        img_right = load_gray_for_hailo(right_path) if os.path.exists(right_path) else img_left
        img_display = load_for_display(left_path)
        
        result = run_inference(pipeline, img_left, img_right)
        visualize(img_display, result, f"TartanAir: {fname}", 
                  os.path.join(OUTPUT_DIR, f"tartan_{i:02d}.png"), is_stereo=True)
    
    # COCO (L=R, kein Stereo)
    print("\n📸 COCO Bilder:")
    coco_files = sorted([f for f in os.listdir(COCO_DIR) if f.endswith('.jpg')])
    for i, fname in enumerate(coco_files):
        img_path = os.path.join(COCO_DIR, fname)
        img_left = load_gray_for_hailo(img_path)
        img_display = load_for_display(img_path)
        
        result = run_inference(pipeline, img_left, img_left)  # L=R
        visualize(img_display, result, f"COCO: {fname}",
                  os.path.join(OUTPUT_DIR, f"coco_{i:02d}.png"), is_stereo=False)
    
    print(f"\n✅ Fertig! {len(tartan_files) + len(coco_files)} Bilder visualisiert in {OUTPUT_DIR}/")
    print("Vergleiche mit dem FP32-Eval auf dem PC!")