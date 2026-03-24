#!/usr/bin/env python3
"""
Generate offline pseudo-labels for 35 robot-relevant COCO classes.
Runs YOLOv5l on grayscale COCO images, merges with GT, saves as new annotation file.

Usage:
    python generate_pseudo_labels.py \
        --coco_root ~/datasets/coco \
        --output ~/datasets/coco/annotations/instances_train2017_robot35_pseudo.json \
        --conf_thresh 0.50 \
        --iou_merge_thresh 0.50

Prerequisites:
    pip install ultralytics  # or use torch.hub YOLOv5

Output: COCO-format JSON with merged GT + teacher predictions for 35 classes.
"""
import os
import json
import argparse
import numpy as np
from tqdm import tqdm
import torch
import cv2
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

# =====================================================================
# 35 Robot-Relevant COCO Classes
# =====================================================================
# COCO category IDs for our 35 classes
ROBOT_CLASSES = {
    # Static SLAM landmarks — indoor
    'chair': 62, 'couch': 63, 'bed': 65, 'dining table': 67, 'tv': 72,
    'toilet': 70, 'sink': 81, 'refrigerator': 82, 'oven': 79, 'microwave': 78,
    'potted plant': 64, 'clock': 85, 'vase': 86, 'book': 84,
    # Static SLAM landmarks — outdoor
    'bench': 15, 'fire hydrant': 11, 'stop sign': 13, 'traffic light': 10,
    'parking meter': 14,
    # Moving objects — detect to exclude from SLAM
    'person': 1, 'cat': 17, 'dog': 18, 'bird': 16, 'bicycle': 2,
    'car': 3, 'motorcycle': 4, 'bus': 6, 'truck': 8,
    # Graspable / interaction objects
    'bottle': 44, 'cup': 47, 'bowl': 51, 'backpack': 27, 'handbag': 31,
    'laptop': 73, 'cell phone': 77, 'remote': 75, 'keyboard': 76,
    'suitcase': 33, 'umbrella': 28, 'teddy bear': 88,
}

# Set of valid COCO category IDs
ROBOT_CAT_IDS = set(ROBOT_CLASSES.values())

# Map from COCO 80-class index (0-79) to our category IDs
# YOLOv5 outputs class indices 0-79 which map to COCO category IDs
YOLO_IDX_TO_COCO_CAT = [
    1,2,3,4,5,6,7,8,9,10,11,13,14,15,16,17,18,19,20,21,22,23,24,25,
    27,28,31,32,33,34,35,36,37,38,39,40,41,42,43,44,46,47,48,49,50,
    51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,67,70,72,73,74,75,
    76,77,78,79,80,81,82,84,85,86,87,88,89,90
]


def box_iou(boxes1, boxes2):
    """Compute IoU between two sets of boxes [x1, y1, x2, y2]."""
    x1 = np.maximum(boxes1[:, 0:1], boxes2[:, 0])
    y1 = np.maximum(boxes1[:, 1:2], boxes2[:, 1])
    x2 = np.minimum(boxes1[:, 2:3], boxes2[:, 2])
    y2 = np.minimum(boxes1[:, 3:4], boxes2[:, 3])

    inter = np.maximum(x2 - x1, 0) * np.maximum(y2 - y1, 0)
    area1 = (boxes1[:, 2] - boxes1[:, 0]) * (boxes1[:, 3] - boxes1[:, 1])
    area2 = (boxes2[:, 2] - boxes2[:, 0]) * (boxes2[:, 3] - boxes2[:, 1])

    union = area1[:, None] + area2[None, :] - inter
    return inter / (union + 1e-6)


def load_yolov5(device='cuda'):
    """Load YOLOv5l model."""
    print("Loading YOLOv5l...")
    model = torch.hub.load('ultralytics/yolov5', 'yolov5l', pretrained=True)
    model.to(device)
    model.eval()
    model.conf = 0.01  # We'll filter ourselves
    model.iou = 0.45
    print(f"  ✅ YOLOv5l loaded on {device}")
    return model


def process_image(model, img_path, conf_thresh=0.50):
    """
    Run YOLOv5l on a grayscale version of the image.
    Returns: list of [x1, y1, x2, y2, conf, coco_cat_id] for robot classes only.
    """
    # Load and convert to grayscale (same as training pipeline)
    img_bgr = cv2.imread(img_path)
    if img_bgr is None:
        return []

    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    # YOLOv5 expects 3-channel input
    img_3ch = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2RGB)

    # Inference
    with torch.no_grad():
        results = model(img_3ch)

    # Parse results
    preds = results.xyxy[0].cpu().numpy()  # [x1, y1, x2, y2, conf, cls_idx]

    teacher_boxes = []
    for pred in preds:
        x1, y1, x2, y2, conf, cls_idx = pred
        cls_idx = int(cls_idx)

        if conf < conf_thresh:
            continue

        # Map YOLOv5 class index to COCO category ID
        if cls_idx >= len(YOLO_IDX_TO_COCO_CAT):
            continue
        coco_cat_id = YOLO_IDX_TO_COCO_CAT[cls_idx]

        # Filter to robot classes only
        if coco_cat_id not in ROBOT_CAT_IDS:
            continue

        teacher_boxes.append([float(x1), float(y1), float(x2), float(y2),
                              float(conf), int(coco_cat_id)])

    return teacher_boxes


def merge_gt_and_teacher(gt_anns, teacher_boxes, iou_thresh=0.50):
    """
    Merge COCO GT annotations with teacher predictions.
    Teacher boxes that overlap with GT (IoU > thresh) are discarded.
    Remaining teacher boxes are added as new annotations.

    Returns: list of annotation dicts in COCO format
    """
    merged = []

    # Keep all GT annotations for robot classes
    gt_boxes = []
    for ann in gt_anns:
        if ann['category_id'] in ROBOT_CAT_IDS:
            merged.append(ann)
            x, y, w, h = ann['bbox']
            gt_boxes.append([x, y, x + w, y + h])

    if not teacher_boxes:
        return merged

    teacher_arr = np.array([[b[0], b[1], b[2], b[3]] for b in teacher_boxes])

    if gt_boxes:
        gt_arr = np.array(gt_boxes)
        ious = box_iou(teacher_arr, gt_arr)  # [N_teacher, N_gt]
        max_iou = ious.max(axis=1) if ious.size > 0 else np.zeros(len(teacher_boxes))
    else:
        max_iou = np.zeros(len(teacher_boxes))

    # Add teacher boxes that don't overlap with GT
    for i, (box, miou) in enumerate(zip(teacher_boxes, max_iou)):
        if miou < iou_thresh:
            x1, y1, x2, y2, conf, cat_id = box
            merged.append({
                'bbox': [x1, y1, x2 - x1, y2 - y1],  # COCO format [x, y, w, h]
                'category_id': cat_id,
                'area': (x2 - x1) * (y2 - y1),
                'iscrowd': 0,
                'source': 'teacher',
                'confidence': conf,
            })

    return merged


def main():
    parser = argparse.ArgumentParser(description='Generate YOLO pseudo-labels for 35 robot classes')
    parser.add_argument('--coco_root', type=str, default='../datasets/coco')
    parser.add_argument('--output', type=str,
                        default='../datasets/coco/annotations/instances_train2017_robot35_pseudo.json')
    parser.add_argument('--conf_thresh', type=float, default=0.50)
    parser.add_argument('--iou_merge_thresh', type=float, default=0.50)
    parser.add_argument('--device', type=str, default='cuda')
    parser.add_argument('--max_images', type=int, default=0, help='0 = all')
    args = parser.parse_args()

    coco_root = os.path.expanduser(args.coco_root)
    ann_file = os.path.join(coco_root, 'annotations', 'instances_train2017.json')
    img_dir = os.path.join(coco_root, 'train2017')

    assert os.path.exists(ann_file), f"Not found: {ann_file}"
    assert os.path.exists(img_dir), f"Not found: {img_dir}"

    # Load COCO annotations
    print(f"Loading COCO annotations: {ann_file}")
    with open(ann_file) as f:
        coco_data = json.load(f)

    # Build image_id → annotations mapping
    img_to_anns = {}
    for ann in coco_data['annotations']:
        img_id = ann['image_id']
        if img_id not in img_to_anns:
            img_to_anns[img_id] = []
        img_to_anns[img_id].append(ann)

    # Filter categories to robot classes only
    robot_categories = [cat for cat in coco_data['categories']
                        if cat['id'] in ROBOT_CAT_IDS]
    print(f"Robot categories: {len(robot_categories)}/{len(coco_data['categories'])}")
    for cat in sorted(robot_categories, key=lambda c: c['id']):
        print(f"  {cat['id']:>3}: {cat['name']}")

    # Load YOLOv5
    model = load_yolov5(args.device)

    # Process images
    images = coco_data['images']
    if args.max_images > 0:
        images = images[:args.max_images]

    print(f"\nProcessing {len(images)} images...")

    all_merged_anns = []
    ann_id_counter = 1
    stats = {'gt_kept': 0, 'teacher_added': 0, 'teacher_filtered': 0, 'images_with_teacher': 0}

    for img_info in tqdm(images, desc="Pseudo-labels"):
        img_id = img_info['id']
        img_path = os.path.join(img_dir, img_info['file_name'])

        if not os.path.exists(img_path):
            continue

        # GT annotations for this image
        gt_anns = img_to_anns.get(img_id, [])

        # Teacher predictions
        teacher_boxes = process_image(model, img_path, args.conf_thresh)

        # Count teacher boxes before filtering
        n_teacher_raw = len(teacher_boxes)

        # Merge
        merged = merge_gt_and_teacher(gt_anns, teacher_boxes, args.iou_merge_thresh)

        # Assign annotation IDs and image_id
        n_teacher_added = 0
        for ann in merged:
            ann['id'] = ann_id_counter
            ann['image_id'] = img_id
            ann_id_counter += 1

            if ann.get('source') == 'teacher':
                n_teacher_added += 1
                stats['teacher_added'] += 1
            else:
                stats['gt_kept'] += 1

        stats['teacher_filtered'] += (n_teacher_raw - n_teacher_added)
        if n_teacher_added > 0:
            stats['images_with_teacher'] += 1

        all_merged_anns.extend(merged)

    # Build output COCO JSON
    output_data = {
        'info': {
            'description': f'COCO train2017 + YOLOv5l pseudo-labels, 35 robot classes, '
                           f'conf>{args.conf_thresh}, IoU merge>{args.iou_merge_thresh}',
            'version': '1.0',
        },
        'images': images,
        'annotations': all_merged_anns,
        'categories': robot_categories,
    }

    # Save
    os.makedirs(os.path.dirname(os.path.expanduser(args.output)), exist_ok=True)
    output_path = os.path.expanduser(args.output)
    with open(output_path, 'w') as f:
        json.dump(output_data, f)

    print(f"\n✅ Saved: {output_path}")
    print(f"   Images: {len(images)}")
    print(f"   Total annotations: {len(all_merged_anns)}")
    print(f"   GT kept (robot classes): {stats['gt_kept']}")
    print(f"   Teacher added: {stats['teacher_added']}")
    print(f"   Teacher filtered (IoU overlap): {stats['teacher_filtered']}")
    print(f"   Images with teacher additions: {stats['images_with_teacher']}/{len(images)}")
    print(f"   Avg annotations/image: {len(all_merged_anns)/len(images):.1f}")

    # Per-class stats
    print(f"\nPer-class annotation counts:")
    cat_counts = {}
    for ann in all_merged_anns:
        cid = ann['category_id']
        src = ann.get('source', 'gt')
        key = (cid, src)
        cat_counts[key] = cat_counts.get(key, 0) + 1

    cat_names = {cat['id']: cat['name'] for cat in robot_categories}
    for cat_id in sorted(ROBOT_CAT_IDS):
        if cat_id in cat_names:
            gt_n = cat_counts.get((cat_id, 'gt'), 0)
            teacher_n = cat_counts.get((cat_id, 'teacher'), 0)
            total = gt_n + teacher_n
            pct_teacher = teacher_n / total * 100 if total > 0 else 0
            print(f"  {cat_names[cat_id]:<20}: {total:>6} ({gt_n} GT + {teacher_n} teacher, {pct_teacher:.0f}% teacher)")


if __name__ == '__main__':
    main()
