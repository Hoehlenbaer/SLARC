#!/usr/bin/env python
# coding: utf-8

# # FusedHexapodModel V5.0 — Phase 1 Full Training
# 1 shared backbone: MNV2-1.4
# 4 Heads: Stereo + YOLO (35 classes) + Seg (6 depth-derived classes) + Surface Normals
# Single-channel grayscale input. No teacher dependencies for Seg.

# In[1]:


from albumentations.pytorch import ToTensorV2
from contextlib import nullcontext
from mpl_toolkits.axes_grid1 import make_axes_locatable
from matplotlib.colors import PowerNorm
from torch.utils.data import Dataset, DataLoader
from torch.utils.tensorboard import SummaryWriter
from tqdm.auto import tqdm
from scipy.ndimage import sobel as scipy_sobel, uniform_filter
import torch, torchvision, timm
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import cv2, os, glob, re, math, time

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Device: {DEVICE}")
if DEVICE.type == 'cuda':
    print(f"  GPU: {torch.cuda.get_device_name(0)}")
    print(f"  VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

# =====================================================================
# V5 CONFIG
# =====================================================================
CONFIG = {
    'img_height': 480, 'img_width': 640,
    'num_det_classes': 41,   # ✅ V5.0: 40 robot-relevant classes + 1 "unknown object"  
    'num_seg_classes': 6,    # ✅ V2.9: depth-derived geometric classes (was 11)
    'max_disp_pixel': 192,
    'backbone_stride': 4,
    'internal_disp_steps': 24,
    'batch_size': 8,           #formerly 4 
    'ACCUMULATION_STEPS': 12,  #not touched
    'lr': 2e-4,                # Reduced: 4e-4 caused inf gradients at step 0
    'start_epoch': 0,         # Offset für TensorBoard und Scheduler
    'num_epochs': 25,
    'normals_to_stereo_epoch': 5,  # <--- NEU: Ab dieser Epoche bekommt Stereo die Normalen!
    'num_workers': 3,
    'save_dir': "./checkpoints",
    'PHASE2_EPOCH': 25,     # Phase 2 starts after Phase 1
    # TartanAir camera params (after resize to 640x480)
    'tartan_fx': 320.0,
    'tartan_fy': 320.0,      # ✅ FIXED: Depth is natively 480x640, no resize → fy=fx=320
    'tartan_baseline': 0.25,
    # Seg class weights (inverse frequency, tune after first epoch)
    'seg_class_weights': [1.0, 2.0, 1.0, 1.0, 0.5, 1.0],  # Index: FLR  STP  WAL  OBS  VOI  TER
    'VIS_THRESH': 0.30,
    'start_step': 0,
}
# =====================================================================
# V5.0 TEST CONFIG — Architektur-Varianten für Hailo-Compile-Test
# =====================================================================
V5_CONFIG = {
    'use_correlation_stereo': True,   # True = CorrelationStereoHead, False = V4.0 CostVolume
    'channel_alignment': 'stereo_focused',      # 'none' | 'moderate' | 'wide' | 'stereo_focused'
    # 'none':           32/48/136/448 (MNV2-1.4 raw, wie V4.0)
    # 'moderate':       32/64/128/256 (Hailo-aligned, minimale Änderung)
    # 'wide':           64/128/256/512 (maximale Cluster-Auslastung)
    # 'stereo_focused': 64/128/128/256 (Stereo optimiert)
}

SEG_CLASS_NAMES = ['WALKABLE', 'STEP', 'WALL', 'OBSTACLE', 'VOID', 'TERRAIN']


# 40 Robot-Relevant COCO Classes
ROBOT_CAT_IDS = [1,2,3,4,6,8,10,11,13,14,15,16,17,18,27,28,31,33,44,47,51,
                  62,63,64,65,67,70,72,73,75,76,77,78,79,81,82,84,85,86,88]

UNKNOWN_CLASS_ID = 40  # Index 40 = "da ist etwas"

# Bekannte Klassen → 0-39, alles andere → 40 (UNKNOWN)
robot_cat_to_continuous = {cid: idx for idx, cid in enumerate(ROBOT_CAT_IDS)}

def map_coco_to_robot(coco_cat_id):
    """Mappt COCO category ID auf Robot-Klasse 0-40."""
    return robot_cat_to_continuous.get(coco_cat_id, UNKNOWN_CLASS_ID)

print(f"V5.0 Config: {CONFIG['num_det_classes']} det classes, {CONFIG['num_seg_classes']} seg classes")
print(f"Seg classes: {SEG_CLASS_NAMES}")


# ## V5.0 Architecture
# 1-channel input, NormalsHead, modified LRASPPHead with normals input, 35-class YOLO

# In[2]:


import torch
import torch.nn as nn
import torch.nn.functional as F
import timm
import math
# Update Version 4.0: Introduce helper to replace AvgPool2D for Hailo performance optimization
class LearnablePool(nn.Module):
    """Ersetzt AvgPool durch eine Conv, die der NPU schneller verarbeitet."""
    def __init__(self, ch, kernel_size, stride=None):
        super().__init__()
        stride = stride or kernel_size
        self.pool = nn.Conv2d(ch, ch, kernel_size, stride=stride,
                              groups=ch, bias=False)  # Depthwise!
        # Initialisiere als gleichmäßige Mittelung
        with torch.no_grad():
            self.pool.weight.fill_(1.0 / (kernel_size * kernel_size 
                if isinstance(kernel_size, int) else kernel_size[0]*kernel_size[1]))
    def forward(self, x):
        return self.pool(x)

# --- Hailo-8 Compatible Building Blocks (unchanged from V2.5) ---
class DWSepConv(nn.Module):
    def __init__(self, in_ch, out_ch, kernel_size, stride=1, padding=0, bias=True, dilation=1):
        super().__init__()
        self.dw = nn.Conv2d(in_ch, in_ch, kernel_size, stride=stride, padding=padding,
                            dilation=dilation, groups=in_ch, bias=False)
        self.pw = nn.Conv2d(in_ch, out_ch, 1, bias=bias)
    def forward(self, x):
        return self.pw(self.dw(x))

# --- FPN Neck (unchanged from V2.5) ---
FPN_CH = 64

class LightFPNNeck(nn.Module):
    def __init__(self, ch_s8, ch_s16, ch_s32, fpn_ch=FPN_CH):
        super().__init__()
        self.lat_s8  = nn.Conv2d(ch_s8,  fpn_ch, 1, bias=False)
        self.lat_s16 = nn.Conv2d(ch_s16, fpn_ch, 1, bias=False)
        self.lat_s32 = nn.Conv2d(ch_s32, fpn_ch, 1, bias=False)
        
        # 🚨 PATCH V3.0: RepConv statt DWSepConv für kräftigere Features!
        self.smooth_s8  = RepConv(fpn_ch, fpn_ch)
        self.smooth_s16 = RepConv(fpn_ch, fpn_ch)
        self.bu_s16 = RepConv(fpn_ch, fpn_ch, stride=2)
        self.bu_s32 = RepConv(fpn_ch, fpn_ch, stride=2)

    def forward(self, f_s8, f_s16, f_s32):
        p32 = self.lat_s32(f_s32)
        p16 = self.lat_s16(f_s16) + F.interpolate(p32, scale_factor=2, mode='nearest')
        p8  = self.lat_s8(f_s8) + F.interpolate(p16, scale_factor=2, mode='nearest')
        p8  = self.smooth_s8(p8)
        p16 = self.smooth_s16(p16) + self.bu_s16(p8)
        p32 = p32 + self.bu_s32(p16)
        return p8, p16, p32

class SPPF(nn.Module):
    def __init__(self, c1, c2, k=5):
        super().__init__()
        c_ = c1 // 2  # Hidden Channels
        self.cv1 = nn.Sequential(nn.Conv2d(c1, c_, 1, 1, bias=False), nn.BatchNorm2d(c_), nn.ReLU6(inplace=True))
        self.cv2 = nn.Sequential(nn.Conv2d(c_ * 4, c2, 1, 1, bias=False), nn.BatchNorm2d(c2), nn.ReLU6(inplace=True))
        self.m = nn.MaxPool2d(kernel_size=k, stride=1, padding=k // 2)

    def forward(self, x):
        x = self.cv1(x)
        y1 = self.m(x)
        y2 = self.m(y1)
        y3 = self.m(y2)
        # Cat von Original + 3 MaxPool-Stufen
        return self.cv2(torch.cat((x, y1, y2, y3), 1))


class GeometryStem(nn.Module):
    def __init__(self, in_ch=32, out_ch=32): # MobileNetV3 s4 hat oft 24 ch
        super().__init__()
        # Zwei Schichten für mehr Reife in den Features
        self.stem = nn.Sequential(
            RepConv(in_ch, out_ch, kernel_size=3, stride=1, padding=1),
            nn.ReLU(inplace=False),
            RepConv(out_ch, out_ch, kernel_size=3, stride=1, padding=1),
            nn.ReLU(inplace=False)
        )

    def forward(self, x):
        return self.stem(x)

import torch
import torch.nn as nn

class AddCoords(nn.Module):
    def __init__(self, h, w, deploy=False):
        super().__init__()
        self.deploy = deploy
        y = torch.linspace(-1, 1, h).view(1, 1, h, 1).expand(1, 1, h, w).contiguous().clone()
        x = torch.linspace(-1, 1, w).view(1, 1, 1, w).expand(1, 1, h, w).contiguous().clone()
        self.register_buffer('y_coords', y)
        self.register_buffer('x_coords', x)

    def forward(self, x_in):
        if self.deploy:
            return torch.cat([x_in, self.y_coords, self.x_coords], dim=1)
        else:
            b = x_in.shape[0]
            return torch.cat([
                x_in,
                self.y_coords.expand(b, -1, -1, -1),
                self.x_coords.expand(b, -1, -1, -1)
            ], dim=1)

class CoordConv2d(nn.Module):
    def __init__(self, in_channels, out_channels, h, w, deploy=False, kernel_size=3, stride=1, padding=1, bias=False):
        super().__init__()
        self.add_coords = AddCoords(h, w, deploy=deploy)
        self.conv = nn.Conv2d(in_channels + 2, out_channels, kernel_size=kernel_size, 
                              stride=stride, padding=padding, bias=bias)
        
    def forward(self, x):
        return self.conv(self.add_coords(x))
    
import torch
import torch.nn as nn
import torch.nn.functional as F

class RepConv(nn.Module):
    """
    Re-Parameterized Convolution:
    Training: 3x3 Conv + 1x1 Conv + Identity (Parallel)
    Inferenz: Eine einzige 3x3 Conv (zusammengefaltet)
    """
    def __init__(self, c1, c2, kernel_size=3, stride=1, padding=1, deploy=False):
        super().__init__()
        self.deploy = deploy
        self.c1 = c1
        self.c2 = c2
        self.stride = stride
        self.padding = padding
        self.act = nn.ReLU(inplace=True)

        if deploy:
            self.rbr_reparam = nn.Conv2d(c1, c2, kernel_size, stride, padding, bias=True)
        else:
            # Identity Branch (nur möglich wenn Dimensionen gleich bleiben)
            self.rbr_identity = nn.BatchNorm2d(c1) if c2 == c1 and stride == 1 else None
            # 3x3 Branch
            self.rbr_dense = nn.Sequential(
                nn.Conv2d(c1, c2, kernel_size, stride, padding, bias=False),
                nn.BatchNorm2d(c2)
            )
            # 1x1 Branch
            self.rbr_1x1 = nn.Sequential(
                nn.Conv2d(c1, c2, 1, stride, 0, bias=False),
                nn.BatchNorm2d(c2)
            )

    def forward(self, x):
        if self.deploy:
            return self.act(self.rbr_reparam(x))
        
        id_out = 0 if self.rbr_identity is None else self.rbr_identity(x)
        return self.act(self.rbr_dense(x) + self.rbr_1x1(x) + id_out)

    def get_equivalent_kernel_bias(self):
        # 3x3 Kernel extrahieren
        kernel3x3, bias3x3 = self._fuse_bn_tensor(self.rbr_dense)
        # 1x1 Kernel extrahieren und auf 3x3 padden
        kernel1x1, bias1x1 = self._fuse_bn_tensor(self.rbr_1x1)
        kernel1x1 = F.pad(kernel1x1, [1, 1, 1, 1])
        # Identity Kernel erstellen (nur 1en in der Mitte)
        kernelid, biasid = self._fuse_bn_tensor(self.rbr_identity)
        
        return kernel3x3 + kernel1x1 + kernelid, bias3x3 + bias1x1 + biasid

    def _fuse_bn_tensor(self, branch):
        if branch is None:
            return torch.zeros((self.c2, self.c1, 3, 3), device=self.rbr_dense[0].weight.device), torch.zeros(self.c2, device=self.rbr_dense[0].weight.device)
        if isinstance(branch, nn.BatchNorm2d):
            # Trick: Fake-Kernel für Identity
            kernel = torch.zeros((self.c1, self.c1, 3, 3), device=branch.weight.device)
            for i in range(self.c1): kernel[i, i, 1, 1] = 1.0
            return self._fuse_bn(kernel, branch.running_mean, branch.running_var, branch.weight, branch.bias, branch.eps)
        else:
            return self._fuse_bn(branch[0].weight, branch[1].running_mean, branch[1].running_var, branch[1].weight, branch[1].bias, branch[1].eps)

    def _fuse_bn(self, kernel, mean, var, gamma, beta, eps):
        std = (var + eps).sqrt()
        t = (gamma / std).reshape(-1, 1, 1, 1)
        return kernel * t, beta - mean * gamma / std
        
    def switch_to_deploy(self):
        if self.deploy: return
        kernel, bias = self.get_equivalent_kernel_bias()
        self.rbr_reparam = nn.Conv2d(self.c1, self.c2, 3, self.stride, self.padding, bias=True)
        self.rbr_reparam.weight.data = kernel
        self.rbr_reparam.bias.data = bias
        # Lösche Trainings-Branches, um RAM zu befreien!
        for attr in ['rbr_dense', 'rbr_1x1', 'rbr_identity']:
            if hasattr(self, attr): delattr(self, attr)
        self.deploy = True
    
# --- Cost Volume (Korrigiert: Universelle Metrik) ---
class CoarseCostVolume(nn.Module):
    def __init__(self, max_disp, in_channels, deploy=False):
        super().__init__()
        self.max_disp = max_disp
        self.deploy = deploy
        self.corr = nn.Conv2d(in_channels * 2, 1, 1, bias=True)
        if self.deploy:
            self.corr_grouped = nn.Conv2d(max_disp * in_channels * 2, max_disp, 1, groups=max_disp)
        
    def forward(self, feat_l, feat_r):
        if self.deploy:
            all_shifted = []
            for d in range(self.max_disp):
                if d == 0:
                    shifted = feat_r
                else:
                    shifted = F.pad(feat_r, (d, 0, 0, 0))[:, :, :, :-d]
                all_shifted.append(torch.cat([feat_l, shifted], dim=1))
            
            # 🚀 KANAL-STACK statt BATCH-STACK
            # Shape: [1, 24 * (C*2), 60, 80] -> z.B. [1, 1536, 60, 80]
            x = torch.cat(all_shifted, dim=1)
            
            # Die Grouped Conv rechnet alle 24 Blöcke strikt getrennt in einem Rutsch
            x = self.corr_grouped(x) # Shape: [1, 24, 60, 80]
            return x
            
        else:
            # 🧠 TRAINING (GPU)
            B, C, H, W = feat_l.shape # Hier ist das Auslesen von B völlig okay!
            cost_slices = []
            for d in range(self.max_disp):
                if d == 0:
                    cost_slices.append(torch.cat([feat_l, feat_r], dim=1))
                else:
                    shifted = torch.zeros_like(feat_r)
                    shifted[:, :, :, d:] = feat_r[:, :, :, :-d]
                    cost_slices.append(torch.cat([feat_l, shifted], dim=1))
            
            cost = torch.stack(cost_slices, dim=2)
            B, C2, D, H, W = cost.shape
            cost = cost.permute(0, 2, 1, 3, 4).reshape(B * D, C2, H, W)
            out = self.corr(cost) 
            return out.view(B, D, H, W)

# --- Refinement Stage with Edge Guidance (from V2.5 Phase 2) ---
class RefinementStage(nn.Module):
    def __init__(self, guidance_channels, scale_factor, use_edge_guidance=False, deploy=False):
        super().__init__()
        self.deploy = deploy
        self.scale_factor = scale_factor
        self.use_edge_guidance = use_edge_guidance
        extra = 1 if use_edge_guidance else 0
        self.net = nn.Sequential(
            nn.Conv2d(1 + guidance_channels + extra, 32, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(32, 32, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(32, 1, 3, padding=1)
        )
        kx = torch.tensor([[-1,0,1],[-2,0,2],[-1,0,1]], dtype=torch.float32).view(1,1,3,3)
        ky = torch.tensor([[-1,-2,-1],[0,0,0],[1,2,1]], dtype=torch.float32).view(1,1,3,3)
        self.register_buffer('kx', kx)
        self.register_buffer('ky', ky)

    def _edge_map(self, img):
        gx = F.conv2d(img, self.kx, padding=1)
        gy = F.conv2d(img, self.ky, padding=1)
        return torch.abs(gx) + torch.abs(gy)       # <-- NEU (L1-Trick)

    # In class RefinementStage(nn.Module):
    def forward(self, disparity_low, guidance, max_disp, gray_img=None): # <--- NEU: max_disp hinzugefügt
        mode = 'nearest' if self.deploy else 'bilinear' # Dynamisch umschalten
        disparity_up = F.interpolate(
            disparity_low, scale_factor=self.scale_factor,
            mode=mode, 
            align_corners=False if mode == 'bilinear' else None
        ) * self.scale_factor
        
        # ✅ PHYSIKALISCH FUNDIERTE NORMALISIERUNG
        # Wir bringen die Disparität für das CNN auf einen Prozentwert (0.0 bis 1.0)
        norm_disp = disparity_up / max_disp
        
        # Das CNN kriegt jetzt die normierte Disparität + die Guidance-Features
        inp = [norm_disp, guidance]
        
        if self.use_edge_guidance:
            assert gray_img is not None
            if gray_img.shape[-2:] != disparity_up.shape[-2:]:
                # Im Deployment 'nearest' nutzen
                if self.deploy:
                    gray_img = F.interpolate(
                        gray_img, 
                        size=disparity_up.shape[-2:],
                        mode='nearest',
                        align_corners= None
                    )
                else:
                    gray_img = F.interpolate(
                        gray_img, 
                        size=disparity_up.shape[-2:],
                        mode='bilinear',
                        align_corners= False
                    )
                
            inp.append(self._edge_map(gray_img))
            
        # Das berechnete Detail-Residual wird zur ORIGINALEN (unskalierten) Disparität addiert!
        return F.relu(disparity_up + self.net(torch.cat(inp, dim=1)))

# --- Stereo Head with Context Network ---
class HierarchicalStereoHead(nn.Module):
    def __init__(self, ch_s8, ch_s4, max_disp_s8, use_normals=True, deploy=False):
        super().__init__()
        self.max_disp_s8 = max_disp_s8
        self.use_normals = use_normals
        self.deploy = deploy
        # ====================================================================
        # 🚨 PATCH V3.0: CoordConv für absolutes räumliches Bewusstsein!
        # kernel_size=1, padding=0 sorgt dafür, dass deine Architektur 
        # exakt gleich bleibt, nur dass X/Y elegant miteingemischt werden.
        # ====================================================================
        
        # 🚨 V3.1 GEOMETRY UPGRADE: 
        # 🚨 V4.0 GEOMETRY Optimization for Hailo deployment: Reduce cost volume channels 32 -> 16 
        # Wir fügen geo_features (32 ch) hinzu. 
        # Für s8 müssen wir sie erst poolen, für s4 passen sie direkt.
        self.reduce_s8 = CoordConv2d(ch_s8 + 32, 16, h=60, w=80, deploy=deploy, kernel_size=1, padding=0, bias=False)


        # S4 Guidance: Normalen (3) + Geo (32) + Backbone (ch_s4)
        s4_guidance_ch = ch_s4 + 32 + (3 if use_normals else 0)
        self.reduce_s4 = CoordConv2d(s4_guidance_ch, 16, h=120, w=160, deploy=deploy, kernel_size=1, padding=0, bias=False)
      
        self.stereo_coarse = CoarseCostVolume(max_disp=self.max_disp_s8, in_channels=16, deploy=deploy)
        self.stereo_refine_s4 = RefinementStage(guidance_channels=16, scale_factor=2.0, deploy=deploy)
        # Update 4.0_ Remove S1 refiner
        #self.stereo_refine_s1 = RefinementStage(guidance_channels=1, scale_factor=4.0, use_edge_guidance=True)
        
        self.register_buffer('disp_reg', torch.arange(self.max_disp_s8, dtype=torch.float32).view(1, -1, 1, 1))
        self.temperature = 0.7
        self.context_weight = 0.8
        
        # ====================================================================
        # 🚨 PATCH V3.0: Refactoring des Context-Blocks (Fix 2)
        # Sauberer Code, nutzt DWSepConv für die teure mittlere Schicht!
        # ====================================================================
        self.context = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1),        # 1 auf 16: normale Conv
            nn.ReLU(inplace=True),
            DWSepConv(16, 16, 3, padding=1),       # 16 auf 16: schlankes DWSepConv!
            nn.ReLU(inplace=True),
            nn.Conv2d(16, 1, 3, padding=1)         # 16 auf 1: Output
        )
        # 🚀 Grouped COntext für Deployment
        # Wird später von prep_stereo_for_deploy() mit Gewichten gefüllt.
        if self.deploy:
            self.context_grouped = nn.Sequential(
                nn.Conv2d(self.max_disp_s8, self.max_disp_s8 * 16, 3, padding=1, groups=self.max_disp_s8),
                nn.ReLU(inplace=True),
                nn.Conv2d(self.max_disp_s8 * 16, self.max_disp_s8 * 16, 3, padding=1, groups=self.max_disp_s8 * 16, bias=False),
                nn.Conv2d(self.max_disp_s8 * 16, self.max_disp_s8 * 16, 1, groups=self.max_disp_s8),
                nn.ReLU(inplace=True),
                nn.Conv2d(self.max_disp_s8 * 16, self.max_disp_s8, 3, padding=1, groups=self.max_disp_s8)
            )
    
        # Lernbare Parameter für GeometryStem
        self.geo_downsample = nn.Conv2d(32, 32, kernel_size=3, stride=2, padding=1, bias=False)

    # 🚨 V3.1: Signatur um geo_features_l und geo_features_r erweitert
    def forward(self, l_s8, r_s8, l_s4, l_img_raw, normals_s4=None, geo_features_l=None, geo_features_r=None):
        
        # --- SICHERHEITSNETZ (Für TensorBoard Tracer / Alte Checkpoints) ---
        if geo_features_l is None:
            B, _, H_s4, W_s4 = l_s4.shape
            geo_features_l = torch.zeros(B, 32, H_s4, W_s4, device=l_s4.device, dtype=l_s4.dtype)
        if geo_features_r is None:
            B, _, H_s4, W_s4 = l_s4.shape
            geo_features_r = torch.zeros(B, 32, H_s4, W_s4, device=l_s4.device, dtype=l_s4.dtype)

        # --- STUFE 1: S8 Coarse Matching ---
        # Da geo_features auf s4 (z.B. 160x120) sind, poolen wir sie für s8 (80x60)
        #geo_l_s8 = F.avg_pool2d(geo_features_l, kernel_size=2, stride=2)
        #geo_r_s8 = F.avg_pool2d(geo_features_r, kernel_size=2, stride=2)
        
        # geo_downsample statt avg_pool2d, um die Kantenschärfe zu erhalten
        geo_l_s8 = self.geo_downsample(geo_features_l)
        geo_r_s8 = self.geo_downsample(geo_features_r)
        
        # Jetzt mit Backbone-Features mischen (+ 32 Kanäle!)
        feat_l_s8 = self.reduce_s8(torch.cat([l_s8, geo_l_s8], dim=1))
        feat_r_s8 = self.reduce_s8(torch.cat([r_s8, geo_r_s8], dim=1))
        
        # --- STUFE 2: S4 Refinement Guidance ---
        if self.use_normals:
            if normals_s4 is not None:
                norm_in = normals_s4
            else:
                norm_in = torch.zeros(l_s4.size(0), 3, l_s4.size(2), l_s4.size(3), device=l_s4.device, dtype=l_s4.dtype)
            
            # Alle drei Quellen: Backbone (s4) + GeoStem (s4) + Normals (s4)
            l_s4_combined = torch.cat([l_s4, geo_features_l, norm_in], dim=1)
        else:
            l_s4_combined = torch.cat([l_s4, geo_features_l], dim=1)
            
        feat_l_s4 = self.reduce_s4(l_s4_combined)
        
        # --- STUFE 3: Stereo Prozess ---
        vol_s8 = self.stereo_coarse(feat_l_s8, feat_r_s8)
        
        # Kontext-Netzwerk
        if self.deploy:
            # Das gesamte Context-Netz wird als eine große GroupedConv ausgeführt!
            vol_ctx = self.context_grouped(vol_s8)
            #print("deploy")
            #print("vol_s8 shape:", vol_s8.shape)
            #print("vol_ctx shape:", vol_ctx.shape)
            #print("vol_s8 max:", vol_s8.abs().max().item())
            #print("vol_ctx max:", vol_ctx.abs().max().item())
            
        else:
            # 🧠 TRAINING FÜR GPU (mit Batch-Logik)
            B, D, H, W = vol_s8.shape
            vol_reshaped = vol_s8.view(B * D, 1, H, W)
            vol_ctx = self.context(vol_reshaped).view(B, D, H, W)
            #print("training")
            #print("vol_s8 shape:", vol_s8.shape)
            #print("vol_ctx shape:", vol_ctx.shape)
            #print("vol_s8 max:", vol_s8.abs().max().item())
            #print("vol_ctx max:", vol_ctx.abs().max().item())
        
        vol_s8 = self.context_weight * vol_ctx + (1.0 - self.context_weight) * vol_s8


        # ====================================================================
        # 🚀 AUFGELÖSTE SOFTMAX-BERECHNUNG FÜR HAILO
        # ====================================================================
        if self.deploy:
            # 1. Skalierung mit Temperature
            vol_scaled = vol_s8 / self.temperature
            # 2. Maximum für numerische Stabilität (INT8 Overflow verhindern)
            v_max, _ = torch.max(vol_scaled, dim=1, keepdim=True)
            # 3. Exponentialfunktion
            v_exp = torch.exp(vol_scaled - v_max)
            # 4. Summe + Anti-Fusion Trick (1e-6 verhindert, dass ONNX es wieder zu Softmax macht)
            v_sum = torch.sum(v_exp, dim=1, keepdim=True) + 1e-6
            # 5. Wahrscheinlichkeit
            prob_s8 = v_exp / v_sum
            disp_s8 = torch.sum(prob_s8 * self.disp_reg, dim=1, keepdim=True)
            #print("prob deploy:", (prob_s8).abs().max().item())
            #print("disp_s8 deploy:", (disp_s8).abs().max().item())
        else:
            # 🧠 TRAINING: PyTorch Standard Softmax
            prob_s8 = F.softmax(vol_s8 / self.temperature, dim=1)
            disp_s8 = torch.sum(prob_s8 * self.disp_reg, dim=1, keepdim=True)
            #print("prob train:", (prob_s8).abs().max().item())
            #print("disp_s8 train:", (disp_s8).abs().max().item())
        
        # ✅ V4.0: Confidence Gate — NUR bei Inferenz, nicht beim Training
        if not self.training:
            confidence = prob_s8.max(dim=1, keepdim=True)[0]
            gate = torch.clamp((confidence - 0.10) / 0.10, 0.0, 1.0)
            disp_s8 = disp_s8 * gate


        max_disp_s4 = self.max_disp_s8 * 2.0
        disp_s4 = self.stereo_refine_s4(disp_s8, feat_l_s4, max_disp=max_disp_s4)
        
        # max_disp_s1 = max_disp_s4 * 4.0
        # final_disp = self.stereo_refine_s1(disp_s4, l_img_raw, max_disp=max_disp_s1, gray_img=l_img_raw)
        #print("disp_s4 max:", disp_s4.abs().max().item())
        #print("final_disp max:", final_disp.abs().max().item())
        return disp_s4, disp_s8
# =====================================================================
# V5.0: Correlation Layer + Channel Aligner
# =====================================================================

import torch
import torch.nn as nn
import torch.nn.functional as F

# (Dein CoordConv2d und RefinementStage müssen natürlich importiert bleiben)

class HailoCostVolume(nn.Module):
    """CostVolume: Nur Shift & Concat. Hailo-freundlich, da keine pixelweise Multiplikation nötig ist."""
    def __init__(self, max_disp, deploy=False):
        super().__init__()
        self.max_disp = max_disp
        self.deploy = deploy

    def forward(self, feat_l, feat_r):
        B, C, H, W = feat_l.shape
        
        if self.deploy:
            volume_slices = []
            for d in range(self.max_disp):
                if d == 0:
                    shifted = feat_r
                else:
                    shifted = F.pad(feat_r, (d, 0, 0, 0))[:, :, :, :-d]
                
                # Bisher: torch.sum(feat_l * shifted, dim=1)
                # NEU: Wir kleben die linke und verschobene rechte Feature-Map einfach aneinander
                # Output Shape pro Slice: [B, 2*C, H, W]
                volume_slices.append(torch.cat([feat_l, shifted], dim=1))
                
            # Alles zu einem riesigen, flachen Tensor zusammenfügen
            # Output Shape gesamt: [B, max_disp * 2 * C, H, W]
            return torch.cat(volume_slices, dim=1)
        else:
            # Pre-Allocation für effizientes Training auf der GPU
            volume = torch.zeros(B, self.max_disp * 2 * C, H, W, device=feat_l.device, dtype=feat_l.dtype)
            for d in range(self.max_disp):
                start_idx = d * 2 * C
                end_idx = start_idx + 2 * C
                
                if d == 0:
                    volume[:, start_idx:end_idx] = torch.cat([feat_l, feat_r], dim=1)
                else:
                    # Alternativ zu F.pad: Effiziente Slice-Zuweisung für PyTorch Autograd
                    shifted = torch.zeros_like(feat_r)
                    shifted[:, :, :, d:] = feat_r[:, :, :, :-d]
                    volume[:, start_idx:end_idx] = torch.cat([feat_l, shifted], dim=1)
            return volume


class CorrelationStereoHead(nn.Module):
    """V5.0 Stereo Head: Hailo-optimiertes flaches CostVolume + 1x1 Reduktion."""
    def __init__(self, ch_s8, ch_s4, max_disp_s8, use_normals=True, deploy=False):
        super().__init__()
        self.max_disp_s8 = max_disp_s8
        self.use_normals = use_normals
        self.deploy = deploy

        # reduce_s8 komprimiert auf 16 Kanäle (C=16)
        self.reduce_s8 = CoordConv2d(ch_s8 + 32, 16, h=60, w=80, deploy=deploy, kernel_size=1, padding=0, bias=False)
        s4_guidance_ch = ch_s4 + 32 + (3 if use_normals else 0)
        self.reduce_s4 = CoordConv2d(s4_guidance_ch, 16, h=120, w=160, deploy=deploy, kernel_size=1, padding=0, bias=False)

        # 1. Das neue "dumme" CostVolume instanziieren
        self.cost_volume = HailoCostVolume(max_disp=max_disp_s8, deploy=deploy)
        
        # 2. Die Brücke: Lernt die Korrelation (ersetzt das alte Dot-Product)
        # In-Channels = 32 (16 Kanäle links + 16 Kanäle rechts) * max_disp
        # Out-Channels = max_disp (damit post_corr genau wie vorher arbeiten kann)
        #self.cv_reduction = nn.Conv2d(
        #    in_channels=32 * max_disp_s8, 
        #    out_channels=max_disp_s8, 
        #    kernel_size=1, 
        #    bias=False
        #)
        # Introduce 2-step reduction (additional layer) to give more room for information flow 768 -> 96 -> 32
        self.cv_reduction = nn.Sequential(
            nn.Conv2d(32 * max_disp_s8, 4 * max_disp_s8, 1, bias=False),  # 768 → 96
            nn.ReLU6(inplace=True),
            nn.Conv2d(4 * max_disp_s8, max_disp_s8, 1, bias=False),       # 96 → 24
        )

        self.post_corr = nn.Sequential(
            nn.Conv2d(max_disp_s8, max_disp_s8, 3, padding=1),
            nn.ReLU6(inplace=True),
            nn.Conv2d(max_disp_s8, max_disp_s8, 3, padding=1),
            nn.ReLU6(inplace=True),
        )
        self.context_weight = 0.8

        self.stereo_refine_s4 = RefinementStage(guidance_channels=16, scale_factor=2.0, deploy=deploy)
        self.register_buffer('disp_reg', torch.arange(max_disp_s8, dtype=torch.float32).view(1, -1, 1, 1))
        self.temperature = 0.5 #reduce from 0.7 to sharpen Soft-Argmax
        self.geo_downsample = nn.Conv2d(32, 32, kernel_size=3, stride=2, padding=1, bias=False)

    def forward(self, l_s8, r_s8, l_s4, l_img_raw, normals_s4=None, geo_features_l=None, geo_features_r=None):
        if geo_features_l is None:
            B, _, H, W = l_s4.shape
            geo_features_l = torch.zeros(B, 32, H, W, device=l_s4.device, dtype=l_s4.dtype)
        if geo_features_r is None:
            B, _, H, W = l_s4.shape
            geo_features_r = torch.zeros(B, 32, H, W, device=l_s4.device, dtype=l_s4.dtype)

        geo_l_s8 = self.geo_downsample(geo_features_l)
        geo_r_s8 = self.geo_downsample(geo_features_r)
        feat_l_s8 = self.reduce_s8(torch.cat([l_s8, geo_l_s8], dim=1))
        feat_r_s8 = self.reduce_s8(torch.cat([r_s8, geo_r_s8], dim=1))

        if self.use_normals:
            norm_in = normals_s4 if normals_s4 is not None else \
                torch.zeros(l_s4.size(0), 3, l_s4.size(2), l_s4.size(3), device=l_s4.device, dtype=l_s4.dtype)
            l_s4_combined = torch.cat([l_s4, geo_features_l, norm_in], dim=1)
        else:
            l_s4_combined = torch.cat([l_s4, geo_features_l], dim=1)
        feat_l_s4 = self.reduce_s4(l_s4_combined)

        # L2-Normalisierung vor dem CostVolume
        feat_l_norm = F.normalize(feat_l_s8, p=2, dim=1, eps=1e-4)
        feat_r_norm = F.normalize(feat_r_s8, p=2, dim=1, eps=1e-4)

        # -----------------------------------------------------------------
        # NEU: Cost Volume aufbauen und durch die Reduktion schicken
        # raw_volume hat die Shape: [B, 32 * max_disp, H, W]
        raw_volume = self.cost_volume(feat_l_norm, feat_r_norm)
        
        # corr hat wieder die vertraute Shape: [B, max_disp, H, W]
        corr = self.cv_reduction(raw_volume)
        # -----------------------------------------------------------------

        corr_refined = self.post_corr(corr)
        vol_s8 = self.context_weight * corr_refined + (1.0 - self.context_weight) * corr

        # Soft-Argmax
        if self.deploy:
            vol_scaled = vol_s8 / self.temperature
            v_max, _ = torch.max(vol_scaled, dim=1, keepdim=True)
            v_exp = torch.exp(vol_scaled - v_max)
            v_sum = torch.sum(v_exp, dim=1, keepdim=True) + 1e-6
            prob_s8 = v_exp / v_sum
            disp_s8 = torch.sum(prob_s8 * self.disp_reg, dim=1, keepdim=True)
        else:
            prob_s8 = F.softmax(vol_s8 / self.temperature, dim=1)
            disp_s8 = torch.sum(prob_s8 * self.disp_reg, dim=1, keepdim=True)

        # Confidence Gate (nur bei Inferenz)
        if not self.training:
            confidence = prob_s8.max(dim=1, keepdim=True)[0]
            gate = torch.clamp((confidence - 0.10) / 0.10, 0.0, 1.0)
            disp_s8 = disp_s8 * gate

        max_disp_s4 = self.max_disp_s8 * 2.0
        disp_s4 = self.stereo_refine_s4(disp_s8, feat_l_s4, max_disp=max_disp_s4)
        return disp_s4, disp_s8


class ChannelAligner(nn.Module):
    """Projiziert Backbone-Outputs auf Hailo-optimale Channel-Breiten."""
    def __init__(self, ch_s4, ch_s8, ch_s16, ch_s32,
                 target_s4=32, target_s8=64, target_s16=128, target_s32=256):
        super().__init__()
        self.align_s4 = nn.Conv2d(ch_s4, target_s4, 1, bias=False) if ch_s4 != target_s4 else nn.Identity()
        self.align_s8 = nn.Conv2d(ch_s8, target_s8, 1, bias=False) if ch_s8 != target_s8 else nn.Identity()
        self.align_s16 = nn.Conv2d(ch_s16, target_s16, 1, bias=False) if ch_s16 != target_s16 else nn.Identity()
        self.align_s32 = nn.Conv2d(ch_s32, target_s32, 1, bias=False) if ch_s32 != target_s32 else nn.Identity()
        self.out_channels = (target_s4, target_s8, target_s16, target_s32)

    def forward(self, features):
        return (self.align_s4(features[0]), self.align_s8(features[1]),
                self.align_s16(features[2]), self.align_s32(features[3]))
        
# ✅ V3.0 Normals Head - Multi-Scale Fusion (s4 + s8), Up-Sampling, Image-Guided Refinement, CoordConv
class NormalsHead(nn.Module):
    def __init__(self, ch_s4, ch_s8, deploy=False): # NEU: deploy flag
        super().__init__()
        self.deploy = deploy
        # Stage 1: Multi-Scale Fusion (s4 + s8)
        self.s8_adapt = nn.Conv2d(ch_s8, 32, kernel_size=1)
        
        # 🚨 V3.1 FIX: Backbone (ch_s4) + s8_adapt (32) + geo_features (32)
        fused_ch = ch_s4 + 32 + 32 
        
        # ====================================================================
        # 🚨 PATCH V3.0: CoordConv für den NormalsHead!
        # ====================================================================
        self.stage1 = nn.Sequential(
            CoordConv2d(fused_ch, 96, h=120, w=160, deploy=deploy, kernel_size=3, padding=1), 
            nn.ReLU(inplace=True),
            nn.Conv2d(96, 64, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(64, 32, 3, padding=1), nn.ReLU(inplace=True)
        )
        self.coarse_out = nn.Conv2d(32, 3, 3, padding=1)

        
    def forward(self, l_s4, l_s8, gray_img, geo_features=None):
        s8_adapted = self.s8_adapt(l_s8)
        #s8_adapted = F.interpolate(s8_adapted, size=l_s4.shape[2:], 
        #                           mode='bilinear', align_corners=False)
        s8_adapted = F.interpolate(s8_adapted, size=l_s4.shape[2:], 
                                   mode='nearest', align_corners=None)
        
        if geo_features is not None:
            l_s4_combined = torch.cat([l_s4, s8_adapted, geo_features], dim=1)
        else:
            dummy_geo = torch.zeros(l_s4.size(0), 32, l_s4.size(2), l_s4.size(3),
                                    device=l_s4.device, dtype=l_s4.dtype)
            l_s4_combined = torch.cat([l_s4, s8_adapted, dummy_geo], dim=1)
        
        feat_s4 = self.stage1(l_s4_combined)
        coarse_normals_s4 = self.coarse_out(feat_s4)
        
        # L2-Normalisierung direkt auf s4 (Training + Deploy identisch!)
        if self.deploy:
            v_max, _ = torch.max(torch.abs(coarse_normals_s4), dim=1, keepdim=True)
            scaled = coarse_normals_s4 / (v_max + 1e-6)
            l2 = torch.sqrt(torch.sum(scaled * scaled, dim=1, keepdim=True))
            divisor = torch.clamp(l2 * (v_max + 1e-6), min=1e-4)
            normals_s4 = coarse_normals_s4 / divisor
        else:
            normals_s4 = F.normalize(coarse_normals_s4, p=2, dim=1, eps=1e-4)
        
        # Nur s4 zurückgeben — kein s1 mehr!
        return normals_s4

# ✅ V3.1: LRASPPHead with Normals input + 6 classes
class LRASPPHead(nn.Module):
    def __init__(self, low_ch, high_ch, num_classes, normals_ch=3):
        super().__init__()
        self.cbr_high = nn.Sequential(
            nn.Conv2d(high_ch, 128, 1, bias=False), nn.BatchNorm2d(128), nn.ReLU(inplace=True)
        )
        self.scale_high = nn.Sequential(
            LearnablePool(high_ch, kernel_size=(30, 40)),
            nn.Conv2d(high_ch, 128, 1, bias=False),
            nn.Sigmoid()
        )
        
        # Statt Concat: separate Convs die erst danach addiert werden
        # Das vermeidet den Concat mit unterschiedlichen Zero-Points komplett!
        self.low_feat_conv = nn.Conv2d(low_ch, num_classes, 1)
        self.low_norm_conv = nn.Conv2d(normals_ch, num_classes, 1)
        self.high_classifier = nn.Conv2d(128, num_classes, 1)
        
        self.mid_feat_conv = nn.Conv2d(128, num_classes, 3, padding=2, dilation=2)
        self.mid_norm_conv = nn.Conv2d(normals_ch, num_classes, 3, padding=2, dilation=2)
        self.use_mid = True
        
    def forward(self, x_low, x_high, normals_s4=None):
        out = self.cbr_high(x_high) * self.scale_high(x_high)
        out = F.interpolate(out, scale_factor=4.0, mode='nearest', align_corners=None)
        
        # Low path: Features und Normals separat verarbeiten, dann addieren
        result = self.low_feat_conv(x_low) + self.high_classifier(out)
        
        if normals_s4 is not None:
            result = result + self.low_norm_conv(normals_s4)
        else:
            dummy = torch.zeros(x_low.size(0), 3, x_low.size(2), x_low.size(3), device=x_low.device)
            result = result + self.low_norm_conv(dummy)
        
        if self.use_mid:
            result = result + self.mid_feat_conv(out)
            if normals_s4 is not None:
                result = result + self.mid_norm_conv(normals_s4)
            else:
                dummy = torch.zeros(out.size(0), 3, out.size(2), out.size(3), device=out.device)
                result = result + self.mid_norm_conv(dummy)
        
        return result

# --- YOLO Heads (unchanged structure, 40 classes) ---
class DecoupledHead(nn.Module):
    def __init__(self, ch_in, num_classes, h, w, deploy=False, width=128):
        super().__init__()
        
        self.coord_conv_cls = CoordConv2d(ch_in, width, h=h, w=w, deploy=deploy, kernel_size=3, padding=1)
        self.coord_conv_reg = CoordConv2d(ch_in, width, h=h, w=w, deploy=deploy, kernel_size=3, padding=1)
        
        # 🚨 PATCH V3.0: RepConv integriert die ReLU bereits intern!
        self.cls_convs = nn.Sequential(
            self.coord_conv_cls,
            nn.BatchNorm2d(width),
            nn.ReLU(inplace=True),
            RepConv(width, width) # ⬅️ RepConv statt DWSepConv
        )
        
        self.reg_convs = nn.Sequential(
            self.coord_conv_reg,
            nn.BatchNorm2d(width),
            nn.ReLU(inplace=True),
            RepConv(width, width) # ⬅️ RepConv statt DWSepConv
        )
        
        self.cls_pred = nn.Conv2d(width, num_classes, 1)
        self.reg_pred = nn.Conv2d(width, 4, 1)
        self.obj_pred = nn.Conv2d(width, 1, 1)
    def forward(self, x):
        cls_feat = self.cls_convs(x); reg_feat = self.reg_convs(x)
        return torch.cat([self.reg_pred(reg_feat), self.obj_pred(reg_feat), self.cls_pred(cls_feat)], dim=1)

class YOLOHead(nn.Module):
    def __init__(self, fpn_ch=FPN_CH, num_classes=40, deploy=False):
        super().__init__()
        self.head_s8  = DecoupledHead(fpn_ch, num_classes, h=60, w=80, deploy=deploy, width=128)
        self.head_s16 = DecoupledHead(fpn_ch, num_classes, h=30, w=40, deploy=deploy, width=128)
        self.head_s32 = DecoupledHead(fpn_ch, num_classes, h=15, w=20, deploy=deploy, width=128)
    def forward(self, x_s8, x_s16, x_s32):
        return [self.head_s8(x_s8), self.head_s16(x_s16), self.head_s32(x_s32)]

# =====================================================================
# ✅ V5.0: FusedHexapodModel — mit Correlation + optionalem Channel-Alignment
# =====================================================================
class FusedHexapodModel(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.deploy_mode = config.get('deploy', False)
        v5 = config.get('v5', V5_CONFIG)

        # Backbone
        self.backbone = timm.create_model('mobilenetv2_140.ra_in1k', pretrained=True,
                                           features_only=True, out_indices=(1, 2, 3, 4))
        feat_info = self.backbone.feature_info.channels()
        ch_s4, ch_s8, ch_s16, ch_s32 = feat_info  # 32, 48, 136, 448

        # Patch 1ch grayscale
        old_conv = self.backbone.conv_stem
        new_conv = nn.Conv2d(1, old_conv.out_channels, kernel_size=old_conv.kernel_size,
                              stride=old_conv.stride, padding=old_conv.padding, bias=False)
        with torch.no_grad():
            w = old_conv.weight.data
            new_conv.weight.data = w[:, 0:1]*0.299 + w[:, 1:2]*0.587 + w[:, 2:3]*0.114
        self.backbone.conv_stem = new_conv
        print(f"  ✅ Backbone first conv: 3→1 channel (luminance merge)")

        # Channel Alignment (optional)
        alignment = v5.get('channel_alignment', 'none')
        if alignment == 'moderate':
            self.aligner = ChannelAligner(ch_s4, ch_s8, ch_s16, ch_s32, 32, 64, 128, 256)
            ch_s4, ch_s8, ch_s16, ch_s32 = self.aligner.out_channels
            print(f"  ✅ Channel Alignment: moderate (32/64/128/256)")
        elif alignment == 'wide':
            self.aligner = ChannelAligner(ch_s4, ch_s8, ch_s16, ch_s32, 64, 128, 256, 512)
            ch_s4, ch_s8, ch_s16, ch_s32 = self.aligner.out_channels
            print(f"  ✅ Channel Alignment: wide (64/128/256/512)")
        # In ChannelAligner — neuer Modus 'stereo_focused':
        # s4/s8 breit (für Stereo), s16/s32 schlank (für Detection)
        elif alignment == 'stereo_focused':
            self.aligner = ChannelAligner(ch_s4, ch_s8, ch_s16, ch_s32, 64, 128, 128, 256)
            ch_s4, ch_s8, ch_s16, ch_s32 = self.aligner.out_channels  # ← FEHLT!
            print(f"  ✅ Channel Alignment: stereo focused (64/128/128/256)")
        else:
            self.aligner = None
            print(f"  ℹ️  Channel Alignment: none (raw MNV2-1.4: {ch_s4}/{ch_s8}/{ch_s16}/{ch_s32})")

        # SPPF
        self.sppf = SPPF(c1=ch_s32, c2=ch_s32, k=5)
        print(f"  ✅ SPPF Module injected at s32 ({ch_s32} channels)")

        # Stereo Head (V5.0 Correlation oder V4.0 CostVolume)
        disp_steps = config.get('internal_disp_steps', 24)
        if v5.get('use_correlation_stereo', False):
            self.stereo_head = CorrelationStereoHead(ch_s8, ch_s4, max_disp_s8=disp_steps, deploy=self.deploy_mode)
            print(f"  ✅ Stereo Head: CorrelationStereoHead (V5.0)")
        else:
            self.stereo_head = HierarchicalStereoHead(ch_s8, ch_s4, max_disp_s8=disp_steps, deploy=self.deploy_mode)
            print(f"  ✅ Stereo Head: HierarchicalStereoHead (V4.0)")

        # Other Heads
        self.normals_head = NormalsHead(ch_s4, ch_s8, deploy=self.deploy_mode)
        self.seg_head = LRASPPHead(ch_s4, ch_s16, config['num_seg_classes'], normals_ch=3)
        self.fpn_neck = LightFPNNeck(ch_s8, ch_s16, ch_s32, fpn_ch=FPN_CH)
        self.geo_stem = GeometryStem(in_ch=ch_s4, out_ch=32)
        print(f"  ✅ Geometry Stem Modules injected after Backbone")
        self.yolo_head = YOLOHead(fpn_ch=FPN_CH, num_classes=config['num_det_classes'], deploy=self.deploy_mode)

        total_params = sum(p.numel() for p in self.parameters())
        print(f"  Total parameters: {total_params:,}")
        print(f"  Normals Head: {sum(p.numel() for p in self.normals_head.parameters()):,}")
        print(f"  Seg Head: {sum(p.numel() for p in self.seg_head.parameters()):,}")
        print(f"  YOLO Head: {sum(p.numel() for p in self.yolo_head.parameters()):,}")
        if self.aligner:
            print(f"  Channel Aligner: {sum(p.numel() for p in self.aligner.parameters()):,}")
        

    def forward(self, x_left, x_right, use_normals_for_stereo=False):
        features_l = self.backbone(x_left)
        if self.aligner:
            features_l = self.aligner(features_l)

        geo_feat_l = self.geo_stem(features_l[0])
        normals_s4 = self.normals_head(features_l[0], features_l[1], x_left, geo_features=geo_feat_l)

        disp_s4, disp_s8 = None, None
        if x_right is not None:
            with torch.no_grad():
                features_r = self.backbone(x_right)
                if self.aligner:
                    features_r = self.aligner(features_r)
                geo_feat_r = self.geo_stem(features_r[0])

            if not self.deploy_mode:
                normals_s4_for_stereo = normals_s4.detach() if (use_normals_for_stereo and normals_s4 is not None) else None
            else:
                normals_s4_for_stereo = normals_s4

            disp_s4, disp_s8 = self.stereo_head(
                features_l[1], features_r[1], features_l[0], x_left,
                normals_s4=normals_s4_for_stereo,
                geo_features_l=geo_feat_l,
                geo_features_r=geo_feat_r
            )
        else:
            disp_s4, disp_s8 = None, None

        if self.deploy_mode:
            normals_for_others = normals_s4
        else:
            normals_for_others = normals_s4.detach() if (use_normals_for_stereo and normals_s4 is not None) else None
        seg = self.seg_head(features_l[0], features_l[2], normals_s4=normals_for_others)

        f_s32_sppf = self.sppf(features_l[3])
        fpn_s8, fpn_s16, fpn_s32 = self.fpn_neck(features_l[1], features_l[2], f_s32_sppf)
        det = self.yolo_head(fpn_s8, fpn_s16, fpn_s32)
        yolo_s8, yolo_s16, yolo_s32 = det

        return disp_s4, seg, disp_s8, normals_s4, yolo_s8, yolo_s16, yolo_s32




model = FusedHexapodModel(CONFIG).to(DEVICE)
print(f"\n✅ V5.0 Model created on {DEVICE}")




# ## V2.10 Loss Functions
# SimpleYOLOLoss (35 cls) + Stereo Smooth-L1 + Seg CrossEntropy + Normals Cosine

# In[1]:


# --- 1. Define Helper Blocks ---
class SimpleYOLOLoss(nn.Module):
    def __init__(self, num_classes, stride):
        super().__init__()
        self.num_classes = num_classes
        self.stride = stride
        self.bce = nn.BCEWithLogitsLoss(reduction='none')
        
    
    def _get_targets(self, targets, cls_preds, reg_preds):
        """
        Vektorisierte Version:
        Erzeugt die Target-Tensoren für Objectness, Regression und Klassifizierung
        komplett ohne For-Schleifen über Boxen oder Nachbarn.
        """
        B, _, H, W = cls_preds.shape
        device = cls_preds.device
        
        # Initialisierung der Target-Tensoren
        cls_t = torch.zeros_like(cls_preds)
        reg_t = torch.zeros_like(reg_preds)
        obj_mask = torch.zeros((B, 1, H, W), device=device) 
        
        # 1. Targets flachklopfen und Batch-Index hinzufügen
        batch_targets = []
        for b in range(B):
            if targets[b].numel() > 0:
                t = targets[b].clone()
                # Batch-Index als erste Spalte hinzufügen: [b, class_id, xc, yc, w, h]
                b_idx = torch.full((t.shape[0], 1), b, device=device, dtype=t.dtype)
                batch_targets.append(torch.cat([b_idx, t], dim=1))
                
        # Wenn der ganze Batch leer ist, sind wir fertig
        if not batch_targets:
            return cls_t, reg_t, obj_mask
            
        gt = torch.cat(batch_targets, dim=0) # Shape: [Alle_Boxen_im_Batch, 6]
        
        # Variablen extrahieren (alles auf einmal!)
        b_idx  = gt[:, 0].long()
        cls_id = gt[:, 1].long()
        gx     = gt[:, 2] * W
        gy     = gt[:, 3] * H
        gw     = gt[:, 4] * W
        gh     = gt[:, 5] * H
        
        # Basis-Grid-Zelle
        ix = gx.long()
        iy = gy.long()
        
        # 2. 5 Nachbarn generieren (Cross Assignment)
        # Offsets für Zentrum, Links, Rechts, Oben, Unten
        offsets = torch.tensor([
            [0, 0], [-1, 0], [1, 0], [0, -1], [0, 1]
        ], device=device, dtype=torch.long)
        
        # Wir berechnen die Nachbar-Koordinaten (nx, ny) für alle Boxen gleichzeitig
        # unsqueeze() hilft uns, die Matrix zu erweitern und offsets zu addieren
        nx = (ix.unsqueeze(1) + offsets[:, 0].unsqueeze(0)).flatten()
        ny = (iy.unsqueeze(1) + offsets[:, 1].unsqueeze(0)).flatten()
        
        # Da wir nun aus jeder Box 5 Nachbarn gemacht haben, 
        # müssen wir die anderen Werte (Batch-ID, Zielwerte) ebenfalls 5-mal wiederholen.
        b_idx_rep  = b_idx.repeat_interleave(5)
        cls_id_rep = cls_id.repeat_interleave(5)
        gx_rep     = gx.repeat_interleave(5)
        gy_rep     = gy.repeat_interleave(5)
        gw_rep     = gw.repeat_interleave(5)
        gh_rep     = gh.repeat_interleave(5)
        
        # 3. Boundary Check AND Class Check
        num_classes = cls_preds.shape[1]  # Hole die Anzahl der Klassen vom Tensor
        
        valid_mask = (
            (nx >= 0) & (nx < W) & 
            (ny >= 0) & (ny < H) & 
            (cls_id_rep >= 0) & (cls_id_rep < num_classes) # 🚨 NEU: Verhindert CUDA Crash!
        )
        
        # Wir behalten nur die Werte, wo valid_mask True ist
        b_v   = b_idx_rep[valid_mask]
        c_v   = cls_id_rep[valid_mask]
        nx_v  = nx[valid_mask]
        ny_v  = ny[valid_mask]
        gx_v  = gx_rep[valid_mask]
        gy_v  = gy_rep[valid_mask]
        gw_v  = gw_rep[valid_mask]
        gh_v  = gh_rep[valid_mask]
        
        # 4. Vorbereiten der logarithmischen Größen
        # 🚨 FP16-Safe: min=1e-4 statt 1e-6 (verhindert log(0.0) = -inf)
        lw_v = torch.log(torch.clamp(gw_v, min=1e-4))
        lh_v = torch.log(torch.clamp(gh_v, min=1e-4))
        
        # 5. Werte in die Tensoren schreiben (Phase 2: Center-Weighting)
        # Erst alle 5 Nachbarn auf 0.8 setzen
        obj_mask[b_v, 0, ny_v, nx_v] = 0.8
        
        # Dann die exakten Zentren (ix, iy) auf 1.0 überschreiben.
        # Da ix/iy aus den GT-Koordinaten kommen, sind sie immer das Herz des Hotspots.
        obj_mask[b_idx, 0, iy, ix] = 1.0
        
        reg_t[b_v, 0, ny_v, nx_v] = gx_v - nx_v
        reg_t[b_v, 1, ny_v, nx_v] = gy_v - ny_v
        reg_t[b_v, 2, ny_v, nx_v] = lw_v
        reg_t[b_v, 3, ny_v, nx_v] = lh_v
        
        cls_t[b_v, c_v, ny_v, nx_v] = 1.0
        
        return cls_t, reg_t, obj_mask
        
    def sigmoid_focal_loss(self, inputs, targets, alpha=0.75, gamma=2.0, reduction='none'): # ⬅️ Changed default to 0.75
        p = torch.sigmoid(inputs)
        ce_loss = F.binary_cross_entropy_with_logits(inputs, targets, reduction="none")
        p_t = p * targets + (1 - p) * (1 - targets)
        loss = ce_loss * ((1 - p_t) ** gamma)

        if alpha >= 0:
            # If target=1, alpha_t = 0.75. If target=0, alpha_t = 0.25. 
            # This properly boosts the rare positive anchors!
            alpha_t = alpha * targets + (1 - alpha) * (1 - targets) 
            loss = alpha_t * loss

        if reduction == "mean":
            return loss.mean()
        elif reduction == "sum":
            return loss.sum()
        else:
            return loss

    def forward(self, preds, targets):
        # Slice components: [B, 5 + Num_Classes, H, W]
        reg_p = preds[:, :4, :, :]   # [dx, dy, log_w, log_h]
        obj_p = preds[:, 4:5, :, :]  # [objectness]
        cls_p = preds[:, 5:, :, :]   # [classes]

        # 1. Get Ground Truth Targets
        cls_t, reg_t, obj_mask = self._get_targets(targets, cls_p, reg_p)
        
        # 🚨 METRICS EXTRACTION FOR TENSORBOARD
        num_targets_val = obj_mask.sum().item()
        max_cls_val = cls_t.max().item() if num_targets_val > 0 else 0
        
        # 🚨 NEU: Top-10 Mean Confidence berechnen (mit Sigmoid für 0-1 Wahrscheinlichkeiten)
        with torch.no_grad():
            B = obj_p.size(0)
            # Flatten auf [Batch, Alle_Pixel], dann Top 10 pro Bild holen und Durchschnitt bilden
            flat_obj = torch.sigmoid(obj_p).view(B, -1)
            k = min(10, flat_obj.size(1)) # Sicherheitsabfrage falls Feature-Map < 10 Pixel groß wäre
            top10_mean_conf = flat_obj.topk(k, dim=1).values.mean().item() if k > 0 else 0.0

        num_pos = torch.clamp(obj_mask.sum(), min=1.0)

        # 🚨 Protect against empty TartanAir targets overwriting the weights
        if num_targets_val == 0:
            return {
                'total': torch.tensor(0.0, requires_grad=True, device=preds.device),
                'box': 0.0, 'obj': 0.0, 'cls': 0.0,
                'num_targets': 0,     
                'max_cls': 0,         
                'top10_conf': top10_mean_conf  # ⬅️ NEU: Auch beim Early Exit loggen!
            }
        
        # 2. OBJECTNESS LOSS (Verschärft für Phase 2)
        # Gamma 2.5 oder 3.0 drückt "unsichere" Hotspots massiv weg.
        # Alpha 0.80 gibt den echten Treffern mehr Gewicht gegenüber dem Rauschen.
        l_obj = self.sigmoid_focal_loss(obj_p, obj_mask, 
                                        alpha=0.80, 
                                        gamma=3.0, 
                                        reduction='sum') / num_pos
        
        # 3. REGRESSION LOSS (GIoU statt L1)
        if num_pos > 0:
            # Positive Samples als Boolean-Maske extrahieren
            pos_mask = obj_mask.squeeze(1).bool()  # Shape: [B, H, W]
            
            # Tensoren umformen [B, 4, H, W] -> [Num_Pos, 4]
            # Das filtert sofort alle Hintergrund-Pixel weg und spart enorm Rechenzeit!
            p_pos = reg_p.permute(0, 2, 3, 1)[pos_mask]
            t_pos = reg_t.permute(0, 2, 3, 1)[pos_mask]
            
            # Dekodieren (Log-Werte für Breite/Höhe mit exp() in echte Werte zurückrechnen)
            # WICHTIG: torch.clamp bei den Preds verhindert NaNs durch explodierende Werte beim Start
            p_cx, p_cy = p_pos[:, 0], p_pos[:, 1]
            p_w = torch.exp(torch.clamp(p_pos[:, 2], max=6.0))
            p_h = torch.exp(torch.clamp(p_pos[:, 3], max=6.0))
            
            t_cx, t_cy = t_pos[:, 0], t_pos[:, 1]
            t_w, t_h = torch.exp(t_pos[:, 2]), torch.exp(t_pos[:, 3])
            
            # Eckkoordinaten berechnen (relativ zur aktuellen Grid-Zelle)
            p_x1, p_y1 = p_cx - p_w / 2, p_cy - p_h / 2
            p_x2, p_y2 = p_cx + p_w / 2, p_cy + p_h / 2
            
            t_x1, t_y1 = t_cx - t_w / 2, t_cy - t_h / 2
            t_x2, t_y2 = t_cx + t_w / 2, t_cy + t_h / 2
            
            # 1. Intersection Area (Überlappung)
            inter_x1 = torch.max(p_x1, t_x1)
            inter_y1 = torch.max(p_y1, t_y1)
            inter_x2 = torch.min(p_x2, t_x2)
            inter_y2 = torch.min(p_y2, t_y2)
            inter_area = torch.clamp(inter_x2 - inter_x1, min=0) * torch.clamp(inter_y2 - inter_y1, min=0)
            
            # 2. Union Area (Gesamtfläche)
            # 🚨 FP16-Safe: + 1e-4 statt 1e-6
            union_area = (p_w * p_h) + (t_w * t_h) - inter_area + 1e-4
            iou = inter_area / union_area
            
            # 3. Enclosing Box Area
            enc_x1 = torch.min(p_x1, t_x1)
            enc_y1 = torch.min(p_y1, t_y1)
            enc_x2 = torch.max(p_x2, t_x2)
            enc_y2 = torch.max(p_y2, t_y2)
            # 🚨 FP16-Safe: + 1e-4 statt 1e-6
            enc_area = torch.clamp(enc_x2 - enc_x1, min=0) * torch.clamp(enc_y2 - enc_y1, min=0) + 1e-4
            
            # 4. GIoU Loss berechnen
            giou = iou - ((enc_area - union_area) / enc_area)
            l_box = (1.0 - giou).sum() / num_pos
            
        else:
            # Fallback, falls in diesem Batch/Grid-Level kein Objekt existiert
            l_box = torch.tensor(0.0, device=reg_p.device)

        # 4. CLASSIFICATION LOSS (BUG FIXED: Nur auf positiven Samples!)
        l_cls_raw = self.sigmoid_focal_loss(cls_p, cls_t, alpha=0.5, gamma=2.0, reduction='none')
        l_cls = (l_cls_raw * obj_mask).sum() / num_pos

        # ANGEPASSTE Gewichtung: Box-Loss ist jetzt wichtiger
        return {
            'total': 3.0 * l_box + 5.0 * l_obj + l_cls, 
            'box': l_box.item(),
            'obj': l_obj.item(),
            'cls': l_cls.item(),
            'num_targets': num_targets_val,  
            'max_cls': max_cls_val,          
            'top10_conf': top10_mean_conf    # ⬅️ NEU: Dem Dictionary hinzufügen
        }

class EdgeAwareSmoothnessLoss(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, disp, img):
        mean_disp = disp.mean(2, True).mean(3, True)
        disp = disp / (mean_disp + 1e-7)
        
        grad_disp_x = torch.abs(disp[:, :, :, :-1] - disp[:, :, :, 1:])
        grad_disp_y = torch.abs(disp[:, :, :-1, :] - disp[:, :, 1:, :])

        grad_img_x = torch.mean(torch.abs(img[:, :, :, :-1] - img[:, :, :, 1:]), 1, keepdim=True)
        grad_img_y = torch.mean(torch.abs(img[:, :, :-1, :] - img[:, :, 1:, :]), 1, keepdim=True)

        grad_img_x = torch.exp(-torch.mean(grad_img_x, 1, keepdim=True))
        grad_img_y = torch.exp(-torch.mean(grad_img_y, 1, keepdim=True))

        return torch.mean(grad_disp_x * grad_img_x) + torch.mean(grad_disp_y * grad_img_y)

'''
# --- 2. Main Loss Class ---
class FusedHexapodLoss(nn.Module):
    def __init__(self, config):
        super().__init__()
        # YOLO Skalen-Verluste
        self.yolo_s8_loss  = SimpleYOLOLoss(config['num_det_classes'], stride=8)
        self.yolo_s16_loss = SimpleYOLOLoss(config['num_det_classes'], stride=16)
        self.yolo_s32_loss = SimpleYOLOLoss(config['num_det_classes'], stride=32)
        
        # KEIN seg_loss (CrossEntropy gegen GT) mehr hier!
        self.kl_div = nn.KLDivLoss(reduction='batchmean') 
        self.smooth_loss = EdgeAwareSmoothnessLoss()
        
        # Basis-Gewichte (statisch in StaticWeightedLoss)
        self.w_yolo = 1.0 
        self.w_kd = 1.0     # Fokus liegt jetzt auf KD für Segmentation
        self.w_stereo = 1.0

    def forward(self, preds, targets, teacher_preds, left_img=None):
        # Entpacken der Vorhersagen
        stereo_preds, seg_preds, det_preds = preds
        
        task_tensors = {} # Für Gradienten (Tensors)
        logs = {}         # Für Tensorboard (Floats)

        # --- 1. STEREO LOSS ---
        if stereo_preds is not None and targets.get('disp') is not None:
            gt_disp = targets['disp']
            if gt_disp.dim() == 3: gt_disp = gt_disp.unsqueeze(1)
            
            mask = (gt_disp > 0) & (gt_disp < CONFIG['max_disp_pixel'])
            if mask.sum() > 0:
                
                # 1. Erst plain L1 für die Beta-Schätzung
                with torch.no_grad():
                    current_beta = max(1.0, F.l1_loss(stereo_preds[mask], gt_disp[mask]).item() * 0.5)
                # 2. Dann Smooth L1 mit dynamischem Beta
                l_stereo_raw = F.smooth_l1_loss(stereo_preds[mask], gt_disp[mask], beta=current_beta)
                # 2. Add Edge-Aware Smoothness
                if left_img is not None:
                    l_smooth = self.smooth_loss(stereo_preds, left_img)
                    
                    # FIX: Instead of a hard 0.02, scale it relative to the raw L1 loss.
                    # This prevents the smoothness penalty from dominating when the network
                    # gets close to convergence, allowing sharp details to emerge.
                    dynamic_smooth_weight = torch.clamp(l_stereo_raw.detach() * 0.01, max=0.02)
                    l_stereo = l_stereo_raw + dynamic_smooth_weight * l_smooth
                    l_stereo = l_stereo + 0.001 * l_smooth
                    
                    logs['smooth'] = l_smooth.item()
                else:
                    l_stereo = l_stereo_raw
                
                # ✅ FIX: /2→/3 — etwas stärker gedämpft, damit Stereo nicht YOLO dominiert
                task_tensors['stereo'] = l_stereo / 3.0
                logs['stereo'] = l_stereo.item()

        # --- 2. KNOWLEDGE DISTILLATION (KD) ---
        if teacher_preds is not None and seg_preds is not None:
            T = 2.0 
            
            # Student Logits auf Teacher-Größe
            s_logits = F.interpolate(seg_preds, size=teacher_preds.shape[-2:], 
                                     mode='bilinear', align_corners=False)
            
            # STUDENT: Log-Softmax (Korrekt für KLDiv)
            p_s = F.log_softmax(s_logits / T, dim=1)
            
            # TEACHER: Numerisch stabilere Berechnung
            # Wir nehmen an, teacher_preds sind LOGITS (rohe Scores).
            # Statt exp() -> log() -> softmax() machen wir direkt Softmax auf den Logits.
            p_t = F.softmax(teacher_preds / T, dim=1)
            
            # KL Divergenz BERECHNUNG
            # WICHTIG: reduction='none', damit wir selbst über Pixel mitteln können
            kl_loss_pixelwise = F.kl_div(p_s, p_t, reduction='none') * (T**2)
            
            # Jetzt die Magie: 
            # 1. Summe über Klassen (dim=1) -> Das ist die KL-Div pro Pixel
            # 2. Mittelwert über Spatial (dim=2,3) & Batch (dim=0) -> Skalenunabhängig!
            l_kd = kl_loss_pixelwise.sum(dim=1).mean()
            
            task_tensors['seg'] = l_kd 
            logs['seg_kd'] = l_kd.item()
            
        # --- 3. YOLO LOSS ---
        if det_preds is not None and targets.get('det') is not None:
            gt_det = targets['det']
            
            # Alle 3 Skalen berechnen
            r8  = self.yolo_s8_loss(det_preds[0], gt_det)
            r16 = self.yolo_s16_loss(det_preds[1], gt_det)
            r32 = self.yolo_s32_loss(det_preds[2], gt_det)
            
            l_yolo = (r8['total'] + r16['total'] + r32['total']) / 3.0
            
            # ✅ FIX: /10→/4 — Phase 1 hatte YOLO um Faktor 2.5x zu stark gedämpft
            # Resultat: YOLO Gradient Norm war 10-18x kleiner als Stereo
            task_tensors['yolo'] = l_yolo / 4.0
            logs['yolo'] = l_yolo.item()
            
            # Helper to safely extract floats whether it's a tensor or a primitive float
            def _to_float(val): return val.item() if isinstance(val, torch.Tensor) else float(val)
            
            logs['yolo_box'] = _to_float((r8['box'] + r16['box'] + r32['box']) / 3.0)
            logs['yolo_obj'] = _to_float((r8['obj'] + r16['obj'] + r32['obj']) / 3.0)
            logs['yolo_cls'] = _to_float((r8['cls'] + r16['cls'] + r32['cls']) / 3.0)

            # 🚨 FIX: Extract the debug metrics and pass them up!
            # Sum the targets across all 3 scales
            logs['yolo_num_targets'] = r8.get('num_targets', 0) + r16.get('num_targets', 0) + r32.get('num_targets', 0)
            
            
            # Get the highest class ID found across all 3 scales
            logs['yolo_max_cls'] = max(r8.get('max_cls', 0), r16.get('max_cls', 0), r32.get('max_cls', 0))

        return task_tensors, logs
'''
print("✅ Loss function updated.")


# In[4]:


# =====================================================================
# V2.10 Losses: EMA-Balanced Multi-Task
# =====================================================================

'''
class NormalsLoss(nn.Module):
    """Angular loss for surface normals — stronger gradient than cosine near convergence."""
    def forward(self, pred, gt, valid_mask):
        cosine_sim = (pred * gt).sum(dim=1, keepdim=True)
        cosine_sim = torch.clamp(cosine_sim, -1.0 + 1e-6, 1.0 - 1e-6)
        angular_error = torch.acos(cosine_sim)
        loss = angular_error * valid_mask
        return loss.sum() / (valid_mask.sum() + 1e-6)
'''

class NormalsLoss(nn.Module):
    """Angular loss for surface normals — applies Stride-4 GT smoothing to match model capacity."""
    
    def __init__(self, smooth_gt=True):
        super().__init__()
        self.smooth_gt = smooth_gt

    def forward(self, pred, gt, valid_mask):
        
        if self.smooth_gt:
            # 1. SAFETY: Ungültige Pixel strikt auf 0 setzen, 
            # damit kein Rauschen/Garbage aus dem Hintergrund in die gültigen Pixel "blutet"
            gt = gt * valid_mask 
            
            # 2. Originalgröße merken
            _, _, H, W = gt.shape
            
            # 3. Downsample (Simuliert Stride 4 / 4x4 Average Pooling)
            gt_smooth = F.interpolate(gt, scale_factor=0.25, mode='area')
            
            # 4. Upsample zurück auf Originalgröße
            gt_smooth = F.interpolate(gt_smooth, size=(H, W), mode='bilinear', align_corners=False)
            
            # 5. Re-Normalisierung (WICHTIG: Interpolation verändert die Vektor-Länge!)
            gt = F.normalize(gt_smooth, dim=1, eps=1e-6)

        # --- Standard Angular Error Calculation ---
        # Dot product along the channel dimension (dim=1)
        cosine_sim = (pred * gt).sum(dim=1, keepdim=True)
        
        # Clamp to avoid NaN in torch.acos
        cosine_sim = torch.clamp(cosine_sim, -1.0 + 1e-6, 1.0 - 1e-6)
        angular_error = torch.acos(cosine_sim)
        
        # 6. Maske ERNEUT anwenden!
        # Durch das Upsampling werden Kanten am Himmel/Rand weichgezeichnet.
        # Wir wollen den Loss aber nur exakt da berechnen, wo das Bild wirklich gültig ist.
        loss = angular_error * valid_mask
        
        return loss.sum() / (valid_mask.sum() + 1e-6)

'''
class EdgeAwareSmoothnessLoss(nn.Module):
    def forward(self, disp, img):
        mean_disp = disp.mean(2, True).mean(3, True)
        disp = disp / (mean_disp + 1e-7)
        grad_disp_x = torch.abs(disp[:,:,:,:-1] - disp[:,:,:,1:])
        grad_disp_y = torch.abs(disp[:,:,:-1,:] - disp[:,:,1:,:])
        grad_img_x = torch.mean(torch.abs(img[:,:,:,:-1] - img[:,:,:,1:]), 1, keepdim=True)
        grad_img_y = torch.mean(torch.abs(img[:,:,:-1,:] - img[:,:,1:,:]), 1, keepdim=True)
        return (grad_disp_x * torch.exp(-grad_img_x)).mean() + \
               (grad_disp_y * torch.exp(-grad_img_y)).mean()
'''
class SobelEdgeLoss(nn.Module):
    def __init__(self):
        super().__init__()
        # Sobel-Kernel für X- und Y-Richtung
        sobel_x = torch.tensor([[-1., 0., 1.], 
                                [-2., 0., 2.], 
                                [-1., 0., 1.]]).view(1, 1, 3, 3)
        sobel_y = torch.tensor([[-1., -2., -1.], 
                                [ 0.,  0.,  0.], 
                                [ 1.,  2.,  1.]]).view(1, 1, 3, 3)
        # Als Buffer registrieren, damit sie automatisch auf die GPU geschoben werden
        self.register_buffer('sobel_x', sobel_x)
        self.register_buffer('sobel_y', sobel_y)

    def forward(self, pred, target, mask=None):
        # Format-Sicherung: [B, C, H, W] erzwingen
        if pred.dim() == 3: pred = pred.unsqueeze(1)
        if target.dim() == 3: target = target.unsqueeze(1)
        
        # 1. Gradienten (Kanten) berechnen
        pred_gx = F.conv2d(pred, self.sobel_x, padding=1)
        pred_gy = F.conv2d(pred, self.sobel_y, padding=1)
        
        target_gx = F.conv2d(target, self.sobel_x, padding=1)
        target_gy = F.conv2d(target, self.sobel_y, padding=1)
        
        # 2. Kanten-Intensität (FP16-Sicherer L1-Trick!)
        pred_edges = torch.abs(pred_gx) + torch.abs(pred_gy)
        target_edges = torch.abs(target_gx) + torch.abs(target_gy)
        
        # 3. L1-Differenz der Kanten
        loss = F.l1_loss(pred_edges, target_edges, reduction='none')
        
        # 4. Maske anwenden (nur gültige Pixel bewerten)
        if mask is not None:
            if mask.dim() == 3: mask = mask.unsqueeze(1)
            loss = loss * mask.float()
            return loss.sum() / (mask.sum() + 1e-4)
            
        return loss.mean()

class V210HexapodLoss(nn.Module):
    """
    V3.1 Loss with EMA-based gradient balancing.
    
    Each task loss is normalized by its exponential moving average (EMA).
    This ensures all tasks contribute ~equally regardless of absolute loss scale.
    
    Priority weights control relative importance:
      priority=1.0 → equal contribution
      priority=1.5 → 50% more gradient budget than others
    
    No trainable parameters. No separate optimizer. EMA adapts immediately.
    """
    def __init__(self, config):
        super().__init__()
        self.yolo_s8  = SimpleYOLOLoss(config['num_det_classes'], stride=8)
        self.yolo_s16 = SimpleYOLOLoss(config['num_det_classes'], stride=16)
        self.yolo_s32 = SimpleYOLOLoss(config['num_det_classes'], stride=32)
        self.smooth_loss = EdgeAwareSmoothnessLoss()
        self.normals_loss = NormalsLoss()
        weights = torch.tensor(config['seg_class_weights'], dtype=torch.float32)
        self.seg_ce = nn.CrossEntropyLoss(weight=weights, ignore_index=255)

        # EMA buffers (saved in checkpoint, no gradient)
        self.ema_decay = 0.99  # Adapts over ~100 steps
        self.register_buffer('ema_stereo',  torch.tensor(1.0))
        self.register_buffer('ema_yolo',    torch.tensor(1.0))
        self.register_buffer('ema_seg',     torch.tensor(1.0))
        self.register_buffer('ema_normals', torch.tensor(1.0))
        self.ema_initialized = False

        # Laplacian Kernel für Kanten-Konsistenz
        lap_kernel = torch.tensor([[0., 1., 0.], [1., -4., 1.], [0., 1., 0.]], dtype=torch.float32).view(1, 1, 3, 3)
        self.register_buffer('lap_kernel', lap_kernel)

        self.sobel_loss = SobelEdgeLoss()
        # Priority: how IMPORTANT is each task (not scale!)
        self.priority = {'stereo': 3.0, 'yolo': 3.0, 'seg': 1.0, 'normals': 1.0}

    def _update_ema(self, name, value):
        ema = getattr(self, f'ema_{name}')
        # ✅ NaN guard: a single bad batch must NOT poison the entire EMA
        if torch.isnan(value) or torch.isinf(value):
            return  # Skip this update, keep previous EMA
        if not self.ema_initialized:
            # Don't trust first batch (can be 60-100x) — clamp init
            ema.fill_(value.clamp(max=10.0))
        else:
            ema.mul_(self.ema_decay).add_(value * (1.0 - self.ema_decay))

    def forward(self, preds, targets, left_img=None, coarse_disp=None):
        disp_pred, seg_pred, det_pred, _, normals_pred = preds
        task_losses, logs = {}, {}

        # --- STEREO ---
        if disp_pred is not None and targets.get('disp') is not None:
            gt_disp = targets['disp']
            if gt_disp.dim() == 3: gt_disp = gt_disp.unsqueeze(1)
            # ✅ NEU: Falls Pred kleiner als GT, GT runterskalieren (mit /scale!)
            if disp_pred.shape[-2:] != gt_disp.shape[-2:]:
                scale = disp_pred.shape[-1] / gt_disp.shape[-1]  # z.B. 0.25 für s4
                gt_disp = F.interpolate(gt_disp, size=disp_pred.shape[-2:], mode='nearest') * scale
            
            # max_disp_pixel auch skalieren! 
            max_disp_scaled = CONFIG['max_disp_pixel'] * (disp_pred.shape[-1] / 640)
            mask = (gt_disp > 0) & (gt_disp < max_disp_scaled)
            
            if mask.sum() > 0:
                # 1. Basis-Loss (Smooth L1)
                l_stereo = F.smooth_l1_loss(disp_pred[mask], gt_disp[mask], beta=0.5)

                # --- Laplacian Loss (Treppen- und Knick-Schärfe) ---
                mask_float = mask.float()
                if mask_float.dim() == 3: mask_float = mask_float.unsqueeze(1)
                
                with torch.no_grad():
                    eroded_mask = F.avg_pool2d(mask_float, kernel_size=3, stride=1, padding=1) > 0.99
                
                if eroded_mask.sum() > 0:
                    p_disp_4d = disp_pred if disp_pred.dim() == 4 else disp_pred.unsqueeze(1)
                    gt_disp_4d = gt_disp if gt_disp.dim() == 4 else gt_disp.unsqueeze(1)
                    
                    pred_lap = F.conv2d(p_disp_4d, self.lap_kernel, padding=1)
                    gt_lap = F.conv2d(gt_disp_4d, self.lap_kernel, padding=1)

                    # Differenz berechnen (Element-wise)
                    diff_lap = torch.abs(pred_lap[eroded_mask] - gt_lap[eroded_mask])
                    
                    # ✅ CLAMP HIER: Kappt "Terrorist-Pixel" bei 5.0, damit sie den Gradienten nicht sprengen
                    loss_lap = torch.mean(torch.clamp(diff_lap, max=5.0)) 
                    
                    l_stereo = l_stereo + 0.05 * loss_lap 
                    logs['Loss_Raw/stereo_laplacian'] = loss_lap.item()

                    # Sobel (1. Ordnung - Harte Tiefensprünge)
                    loss_stereo_sobel = self.sobel_loss(disp_pred, gt_disp, eroded_mask)
                    # ✅ CLAMP HIER: Wenn das Gitter "schreit", deckeln wir den Loss bei 2.0
                    loss_stereo_sobel_safe = torch.clamp(loss_stereo_sobel, max=2.0)
                    
                    l_stereo = l_stereo + 0.1 * loss_stereo_sobel_safe
                    logs['Loss_Raw/stereo_sobel'] = loss_stereo_sobel_safe.item()

                # --- 🚨 NEU: SEG-GUIDED ARTIFACT SUPPRESSION (Aperture Fix) ---
                if seg_pred is not None:
                    with torch.no_grad():
                        # Seg-Preds auf Stereo-Auflösung (s4) herunterskalieren
                        seg_pred_s4 = F.interpolate(seg_pred, size=disp_pred.shape[-2:], mode='bilinear', align_corners=False)
                        # Maske für Klasse 5 (Void/Far Background/Sky) erstellen
                        sky_mask = (torch.argmax(seg_pred_s4, dim=1) == 4).unsqueeze(1) # Shape: [B, 1, H, W]
                    
                    if sky_mask.sum() > 0:
                        # 1. Wir berechnen den absoluten Abstand zu 0 (Himmel-Ziel)
                        abs_dist = torch.abs(disp_pred)
                        
                        # 2. ✅ CLAMP HIER: 
                        # Wir deckeln den Fehler pro Pixel bei 2.0.
                        # Warum 2.0? Weil für 'unendlich weit weg' ein Fehler von 2px 
                        # bereits ein massives Signal ist. Alles darüber (wie dein Gitter mit 15px) 
                        # würde den Gradienten nur unnötig explodieren lassen.
                        clamped_sky_dist = torch.clamp(abs_dist, max=2.0)
                        
                        # 3. Mittelwert nur über die Himmel-Pixel
                        l_stereo_sky = torch.mean(clamped_sky_dist[sky_mask.expand_as(disp_pred)])
                        
                        # 4. Gewichtung auf 1.0 senken (reicht völlig aus)
                        l_stereo = l_stereo + 1.0 * l_stereo_sky
                        logs['Loss_Raw/stereo_sky_penalty'] = l_stereo_sky.item()

                # --- 🚨 HYBRID SMOOTHNESS (Geometry + Visual) ---
                # Wir nutzen BEIDES: Normalen killen Gitter-Artefakte, 
                # das Graustufenbild erhält gestochen scharfe Objektkanten!
                if normals_pred is not None and left_img is not None:
                    _, _, H, W = disp_pred.shape
                    
                    # 1. Normalen vorbereiten
                    normals_s4 = F.interpolate(normals_pred, size=(H, W), mode='bilinear', align_corners=False)
                    normals_s4 = F.normalize(normals_s4, dim=1, eps=1e-6)
                    
                    # 2. Graustufenbild vorbereiten
                    left_img_s4 = F.interpolate(left_img, size=(H, W), mode='bilinear', align_corners=False)
            
                    # 3. Beide Losses berechnen
                    l_sm_geo = self.smooth_loss(disp_pred, normals_s4)
                    l_sm_img = self.smooth_loss(disp_pred, left_img_s4)
                    
                    # 4. Adaptive Gewichtung (Geometrie führt, Bild verfeinert)
                    w_geo = torch.clamp(l_stereo.detach() * 0.005, max=0.01)
                    w_img = torch.clamp(l_stereo.detach() * 0.001, max=0.003) # Etwas schwächer, um Gitter nicht zu triggern
                    
                    l_stereo = l_stereo + (w_geo * l_sm_geo) + (w_img * l_sm_img)
                    
                    logs['Loss_Raw/smooth_geo'] = l_sm_geo.item()
                    logs['Loss_Raw/smooth_img'] = l_sm_img.item()

                with torch.no_grad():
                    err = torch.abs(disp_pred[mask] - gt_disp[mask])
                    bad_3px = (err > 3.0).float().mean()
                    logs['Metrics/Stereo_Bad_3px_Ratio'] = bad_3px.item()

                if coarse_disp is not None:
                    gt_s8 = F.interpolate(targets['disp'].unsqueeze(1) if targets['disp'].dim()==3 else targets['disp'], 
                                          size=coarse_disp.shape[-2:], mode='nearest') / 8.0
                    
                    m8 = (gt_s8 > 0) & (gt_s8 < 24)
                    if m8.sum() > 0:
                        l_aux = F.smooth_l1_loss(coarse_disp[m8], gt_s8[m8], beta=0.5)
                        l_stereo = l_stereo + 0.1 * l_aux
                        logs['Loss_Raw/stereo_aux'] = l_aux.item()
                
                task_losses['stereo'] = l_stereo
                logs['Loss_Raw/stereo'] = l_stereo.item()
                

        # --- NORMALS ---
        if normals_pred is not None and targets.get('normals') is not None:
            gt_normals = targets['normals']
            valid_mask = targets.get('normals_valid', (gt_normals.abs().sum(dim=1, keepdim=True) > 0.5).float())
            if normals_pred.shape[-2:] != gt_normals.shape[-2:]:
                gt_normals = F.interpolate(gt_normals, size=normals_pred.shape[-2:], mode='bilinear', align_corners=False)
                gt_normals = F.normalize(gt_normals, dim=1, eps=1e-6)
                valid_mask = F.interpolate(valid_mask, size=normals_pred.shape[-2:], mode='nearest')
            
            l_normals = self.normals_loss(normals_pred, gt_normals, valid_mask)
            task_losses['normals'] = l_normals
            logs['Loss_Raw/normals'] = l_normals.item()

            with torch.no_grad():
                cos_sim = F.cosine_similarity(normals_pred, gt_normals, dim=1)
                mean_cos = (cos_sim * valid_mask.squeeze(1)).sum() / (valid_mask.sum() + 1e-6)
                logs['Metrics/Normals_Cosine_Sim'] = mean_cos.item()

        # --- SEG ---
        if seg_pred is not None and targets.get('seg') is not None:
            gt_seg = targets['seg']
            if seg_pred.shape[-2:] != gt_seg.shape[-2:]:
                seg_pred_up = F.interpolate(seg_pred, size=gt_seg.shape[-2:], mode='bilinear', align_corners=False)
            else:
                seg_pred_up = seg_pred
            
            l_seg = self.seg_ce(seg_pred_up, gt_seg)
            task_losses['seg'] = l_seg
            logs['Loss_Raw/seg_ce'] = l_seg.item()

            with torch.no_grad():
                mask_seg = (gt_seg != 255) 
                if mask_seg.sum() > 0:
                    correct = (seg_pred_up.argmax(dim=1)[mask_seg] == gt_seg[mask_seg]).float().mean()
                    logs['Metrics/Seg_Pixel_Accuracy'] = correct.item()

        # --- YOLO ---
        if det_pred is not None and targets.get('det') is not None:
            gt_det = targets['det']
            r8  = self.yolo_s8(det_pred[0], gt_det)
            r16 = self.yolo_s16(det_pred[1], gt_det)
            r32 = self.yolo_s32(det_pred[2], gt_det)
            l_yolo = (r8['total'] + r16['total'] + r32['total']) / 3.0
            
            task_losses['yolo'] = l_yolo
            logs['Loss_Raw/yolo'] = l_yolo.item()
            
            _f = lambda v: v.item() if isinstance(v, torch.Tensor) else float(v)
            logs['Loss_Raw/yolo_box'] = _f((r8['box']+r16['box']+r32['box'])/3)
            logs['Loss_Raw/yolo_obj'] = _f((r8['obj']+r16['obj']+r32['obj'])/3)
            logs['Loss_Raw/yolo_cls'] = _f((r8['cls']+r16['cls']+r32['cls'])/3)
            
            logs['Metrics/YOLO_Num_Targets'] = r8.get('num_targets', 0) + r16.get('num_targets', 0) + r32.get('num_targets', 0)
            logs['Metrics/YOLO_Top10_Conf'] = (r8.get('top10_conf', 0.0) + r16.get('top10_conf', 0.0) + r32.get('top10_conf', 0.0)) / 3.0

        # ✅ EMA-NORMALIZED WEIGHTING
        with torch.no_grad():
            for name in task_losses:
                self._update_ema(name, task_losses[name].detach())
            self.ema_initialized = True

        total_parts = []
        for name, loss in task_losses.items():
            ema_val = getattr(self, f'ema_{name}').clamp(min=1e-6)
            raw_weight = self.priority[name] / ema_val
            
            clamped_weight = raw_weight.clamp(min=0.5, max=10.0)
            total_parts.append(clamped_weight * loss)
            
            logs[f'Weights/EMA_{name}'] = ema_val.item()
            logs[f'Weights/Effective_{name}'] = clamped_weight.item()
            logs[f'Weights/Raw_{name}'] = raw_weight.item()
            
        total = sum(total_parts) if total_parts else torch.tensor(0.0)
        
        if torch.isnan(total) or torch.isinf(total):
            total = torch.tensor(0.0, device=total.device, requires_grad=True)
        logs['Loss/Total_Weighted'] = total.item()

        return total, logs

print("\u2705 V3.0 Loss with EMA balancing loaded")
print("  Priority: stereo=2.0, yolo=3.0, seg=1.0, normals=1.0")
print("  EMA decay=0.99 (~100 step adaptation)")


# ## V2.10 Data: Parsers + On-the-fly Normals/Seg

# In[5]:


import os
import glob
import numpy as np
from pycocotools.coco import COCO

def parse_tartan(root):
    """Scan TartanAir for stereo pairs + depth (normals+seg computed on-the-fly)."""
    print("   Scanning TartanAir...")
    samples = []
    for l_folder in glob.glob(os.path.join(root, '**', 'image_left'), recursive=True):
        parent = os.path.dirname(l_folder)
        for f in sorted(os.listdir(l_folder)):
            if not f.endswith('.png') or 'Zone.Identifier' in f: continue
            l_path = os.path.join(l_folder, f)
            r_path = os.path.join(parent, 'image_right', f.replace('_left', '_right'))
            d_path = os.path.join(parent, 'depth_left', f.replace('.png', '_depth.npy'))
            if os.path.exists(r_path) and os.path.exists(d_path):
                samples.append({'type':'stereo', 'source':'tartan',
                                'l': l_path, 'r': r_path, 'd': d_path, 'b': None})
    print(f"   -> Found {len(samples)} TartanAir samples.")
    return samples

def parse_coco_robot35(root, ann_file=None):
    """
    Load COCO with 40 robot-relevant classes.
    Uses pseudo-labels JSON if available, otherwise standard COCO GT.
    """
    print("   Scanning COCO (40 robot classes)...")
    if ann_file is None:
        # Try pseudo-labels first, fallback to standard GT
        pseudo_path = os.path.join(root, 'annotations', 'instances_train2017_robot41_pseudo.json')
        gt_path = os.path.join(root, 'annotations', 'instances_train2017.json')
        if os.path.exists(pseudo_path):
            ann_file = pseudo_path
            print(f"   Using pseudo-labels: {pseudo_path}")
        else:
            ann_file = gt_path
            print(f"   ⚠️ No pseudo-labels found, using raw GT: {gt_path}")

    coco = COCO(ann_file)
    img_ids = coco.getImgIds()
    samples = []

    for img_id in img_ids:
        img_info = coco.loadImgs(img_id)[0]
        img_path = os.path.join(root, 'train2017', img_info['file_name'])
        if not os.path.exists(img_path): continue

        anns = coco.loadAnns(coco.getAnnIds(imgIds=img_id))
        boxes = []
        for ann in anns:
            cat_id = ann['category_id']
            cls_idx = map_coco_to_robot(cat_id)
            x, y, w, h = ann['bbox']
            img_w, img_h = img_info['width'], img_info['height']
            cx = (x + w/2) / img_w
            cy = (y + h/2) / img_h
            nw = w / img_w
            nh = h / img_h
            if nw > 0.001 and nh > 0.001:
                boxes.append([cls_idx, cx, cy, nw, nh])

        samples.append({'type':'det', 'source':'coco', 'l': img_path,
                        'b': boxes if boxes else None})

    n_with_boxes = sum(1 for s in samples if s['b'] is not None)
    print(f"   -> Found {len(samples)} COCO images ({n_with_boxes} with robot-class boxes)")
    return samples

print("✅ V2.10 Parsers loaded")


# In[6]:


def read_pfm_fixed(file_path):
    """Reads a .pfm file and returns a numpy array."""
    with open(file_path, 'rb') as f:
        header = f.readline().decode().rstrip()
        color = (header == 'PF')
        dim_match = re.match(r'^(\d+)\s(\d+)\s$', f.readline().decode('utf-8'))
        width, height = map(int, dim_match.groups())
        scale = float(f.readline().decode().rstrip())
        endian = '<' if scale < 0 else '>'
        scale = abs(scale)
        data = np.fromfile(f, endian + 'f')
        shape = (height, width, 3) if color else (height, width)
        data = np.reshape(data, shape)
        data = np.flipud(data)
    return (data * scale).copy()

# =====================================================================
# On-the-fly Normals + Seg computation
# =====================================================================
def depth_to_normals_np(depth, fx, fy):
    """
    Compute surface normals from depth via analytical pinhole cross-product.

    Derivation:
      P(u,v) = Z · ((u-cx)/fx, (v-cy)/fy, 1)
      dP/du  = (Z/fx + a·dZ/du,  b·dZ/du,  dZ/du)       where a=(u-cx)/fx, b=(v-cy)/fy
      dP/dv  = (a·dZ/dv,  Z/fy + b·dZ/dv,  dZ/dv)
      N = dP/du × dP/dv:
        nx = -dZ/du · Z / fy
        ny = -dZ/dv · Z / fx
        nz = Z²/(fx·fy) + a·dZ/du·Z/fy + b·dZ/dv·Z/fx

    Key property: for a flat floor, the perspective terms in nz cancel exactly → nz=0.
    Unlike 3D back-projection, gradients are computed on the depth map (smooth in pixel space)
    rather than on nonlinear 3D coordinates (noisy at image edges).

    Returns: (normals[3,H,W], valid[H,W])
    """
    H, W = depth.shape
    cx, cy = W / 2.0, H / 2.0

    v_grid, u_grid = np.meshgrid(np.arange(H, dtype=np.float64),
                                  np.arange(W, dtype=np.float64), indexing='ij')
    a = (u_grid - cx) / fx  # Normalized pixel coords
    b = (v_grid - cy) / fy

    # Depth gradients in pixel space (smoother than 3D gradients)
    dZ_du = np.gradient(depth.astype(np.float64), axis=1)
    dZ_dv = np.gradient(depth.astype(np.float64), axis=0)

    # Analytical cross-product with perspective correction
    Z = depth.astype(np.float64)
    nx = -dZ_du * Z / fy
    ny = -dZ_dv * Z / fx
    nz = Z**2 / (fx * fy) + a * dZ_du * Z / fy + b * dZ_dv * Z / fx

    norm = np.sqrt(nx**2 + ny**2 + nz**2 + 1e-12)
    normals = np.stack([nx/norm, ny/norm, nz/norm], axis=0).astype(np.float32)

    # Validity
    valid = ((depth > 0.01) & (depth < 100.0)
             & np.isfinite(depth)
             & (np.abs(dZ_du) < 5.0) & (np.abs(dZ_dv) < 5.0))
    normals[:, ~valid] = 0.0
    return normals, valid


def compute_seg6_from_depth_normals(depth, normals):
    ny = normals[1]
    cos_angle = np.clip(ny, -1.0, 1.0)
    angle = np.arccos(cos_angle) * 180.0 / np.pi

    grad_x = scipy_sobel(depth, axis=1)
    grad_y = scipy_sobel(depth, axis=0)
    depth_grad = np.sqrt(grad_x**2 + grad_y**2)
    relative_grad = depth_grad / (depth + 0.5)

    valid = (depth > 0.1) & (depth < 80.0)
    nvalid = np.sqrt(normals[0]**2 + normals[1]**2 + normals[2]**2) > 0.5
    seg = np.full(depth.shape, 3, dtype=np.uint8)  # Default: OBSTACLE

    # --- FLOOR (glatt, flach) ---
    walkable_mask = valid & nvalid & (angle <= 40)
    seg[walkable_mask] = 0  # Default: FLOOR

    # --- TERRAIN (begehbar aber rau) ---
    # Lokale Varianz als Rauheits-Indikator
    depth_mean = uniform_filter(depth, size=3)
    depth_sq_mean = uniform_filter(depth**2, size=3)
    local_var = np.clip(depth_sq_mean - depth_mean**2, 0, None)

    # Moderate Rauheit auf begehbaren Flächen → TERRAIN
    rough_walkable = walkable_mask & (local_var > 0.04) & (local_var < 0.15)
    seg[rough_walkable] = 5  # TERRAIN

    # --- STEP (Stufen) ---
    step_mask = walkable_mask & (relative_grad > 0.12) & (depth < 5.0)
    seg[step_mask] = 1

    # --- WALL (vertikal) ---
    wall_mask = valid & nvalid & (angle > 70) & (angle < 110)
    seg[wall_mask] = 2

    # --- OBSTACLE (raue nicht-begehbare Flächen) ---
    rough_obstacle = valid & nvalid & (angle > 30) & (angle < 75) & (local_var > 0.15) & (depth > 1.0)
    seg[rough_obstacle] = 3

    # --- VOID ---
    seg[~valid] = 4  # ⚠️ War vorher 5, jetzt 4!

    return seg


# =====================================================================
# Seg Label Pipeline: Geometry + SegFormer Teacher (on CPU, on-the-fly)
# =====================================================================
# ADE20K class index → our 6-class mapping
# Full ADE20K has 150 classes (0-149). We map the relevant ones.
# Reference: https://docs.google.com/spreadsheets/d/1se8YEtb2detS7OuPE86fXGyD269pMycAWe2mtKUj2W8

# ADE20K class indices (0-indexed, SegFormer convention):
# 0=wall, 1=building, 2=sky, 3=floor, 4=tree, 5=ceiling, 6=road,
# 7=bed, 8=windowpane, 9=grass, 10=cabinet, 11=sidewalk, 12=person,
# 13=earth, 14=door, 15=table, 16=mountain, 17=plant, 18=curtain,
# 19=chair, 20=car, 21=water, 22=painting, 23=sofa, 24=shelf,
# 25=house, 26=sea, 27=mirror, 28=rug, 29=field, ...

def teacher_to_seg6(teacher_pred_150):
    """
    Map ADE20K 150-class prediction to our 6 classes.
    Returns: seg6 [H,W] uint8, mask [H,W] bool (True where teacher has an opinion)
    """
    H, W = teacher_pred_150.shape
    seg6 = np.full((H, W), 255, dtype=np.uint8)  # 255 = unmapped
    mapped = np.zeros((H, W), dtype=bool)
    
    for ade_idx, our_cls in ADE20K_TO_SEG6.items():
        mask = (teacher_pred_150 == ade_idx)
        if mask.any():
            seg6[mask] = our_cls
            mapped[mask] = True
    
    return seg6, mapped

# =====================================================================
# V2.9: SegFormer Teacher ON THE GPU (Ultra-Fast, VRAM-Friendly)
# =====================================================================
import torch
import torch.nn.functional as F
from transformers import SegformerForSemanticSegmentation

print("Loading SegFormer B2 to GPU...")
# Einmalig auf die GPU laden, auf eval() setzen und einfrieren!
seg_teacher_model = SegformerForSemanticSegmentation.from_pretrained(
    "nvidia/segformer-b2-finetuned-ade-512-512"
).to(DEVICE).eval()

for p in seg_teacher_model.parameters():
    p.requires_grad = False
print("✅ SegFormer Teacher loaded on GPU")
'''
# Die Mapping-Tabelle direkt als CUDA-Tensor anlegen (0 Millisekunden Suchzeit!)
ade_to_seg6_map = torch.full((150,), 255, dtype=torch.long, device=DEVICE)

for idx in [3, 6, 9, 11, 13, 28, 29, 46, 52]: ade_to_seg6_map[idx] = 0 # WALKABLE
for idx in [53, 96]: ade_to_seg6_map[idx] = 1 # STEP
for idx in [0, 1, 8, 10, 14, 25, 32, 42, 43]: ade_to_seg6_map[idx] = 2 # WALL
for idx in [7, 12, 15, 19, 20, 21, 23, 24, 38, 63, 64, 97, 116]: ade_to_seg6_map[idx] = 3 # OBSTACLE
for idx in [4, 17, 66]: ade_to_seg6_map[idx] = 4 # VEGETATION
'''

# =====================================================================
# ADE20K zu Hexapod "Pessimistic Semantic SLAM" Mapping (GPU Tensor)
# =====================================================================

# ERSETZE das gesamte ADE20K Mapping:

# =====================================================================
# ADE20K zu Hexapod 6-Klassen Mapping (V5.0)
# =====================================================================
# 0 = FLOOR    (glatt, hart: Fliesen, Asphalt, Beton, Holz)
# 1 = STEP     (Stufen, Treppen)
# 2 = WALL     (Wände, Gebäude, Zäune, Türen)
# 3 = OBSTACLE (alles unpassierbare)
# 4 = VOID     (Himmel, Ferne, kein Stereo)
# 5 = TERRAIN  (begehbar aber uneben: Gras, Sand, Erde, Kies)
# =====================================================================

ade_to_seg6_map = torch.full((256,), 3, dtype=torch.long, device=DEVICE)

# IGNORE
ade_to_seg6_map[255] = 255
ade_to_seg6_map[5] = 255    # Ceiling → ignore, Geometrie fängt es ab

# 0 = FLOOR (glatte harte Flächen)
for idx in [3, 6, 28, 52]:
    ade_to_seg6_map[idx] = 0   # floor, road, sidewalk, platform

# 1 = STEP
for idx in [53, 96]:
    ade_to_seg6_map[idx] = 1   # stairs, stairway

# 2 = WALL
for idx in [0, 1, 8, 14, 25, 32]:
    ade_to_seg6_map[idx] = 2   # wall, building, fence, door, house, railing

# 3 = OBSTACLE (Default + explizite)
for idx in [12, 15, 19, 20, 21, 23, 63, 64, 97, 116]:
    ade_to_seg6_map[idx] = 3   # person, bench, sofa, table, car, ...
# Ehem. NAV_ANCHOR → jetzt OBSTACLE
for idx in [4, 7, 10, 24, 38, 42, 43, 68, 89, 115]:
    ade_to_seg6_map[idx] = 3   # tree, chair, cabinet, bookshelf, column, ...

# 4 = VOID
for idx in [2, 16]:
    ade_to_seg6_map[idx] = 4   # sky, mountain

# 5 = TERRAIN (begehbar aber uneben/weich)
for idx in [9, 13, 29, 46, 110]:
    ade_to_seg6_map[idx] = 5   # grass, earth, field, sand, dirt

def fuse_seg_teacher_gpu(geo_seg_tensor, teacher_input_tensor):
    """ Führt SegFormer aus und mergt das Ergebnis auf der GPU. """
    if geo_seg_tensor is None or teacher_input_tensor is None:
        return geo_seg_tensor

    with torch.no_grad():
        with torch.amp.autocast('cuda', enabled=True, dtype=torch.float16):
            pixel_values = F.interpolate(teacher_input_tensor, size=(512, 512), mode='bilinear', align_corners=False)
            outputs = seg_teacher_model(pixel_values=pixel_values)
            logits = outputs.logits 
            
            # Argmax vor dem Upsampling (VRAM-sparend)
            pred_150_small = logits.argmax(dim=1) 
        
        pred_150_small = pred_150_small.unsqueeze(1).float() 
        pred_150 = F.interpolate(
            pred_150_small, 
            size=(geo_seg_tensor.shape[1], geo_seg_tensor.shape[2]), 
            mode='nearest'
        ).squeeze(1).long()
        
        teacher_seg = ade_to_seg6_map[pred_150]
        teacher_mapped = (teacher_seg != 255)
        
        # Merge Rules
        merged = geo_seg_tensor.clone()

        # 1. Wasser/Pfützen: Geometrie sagt FLOOR, Teacher sagt OBSTACLE → OBSTACLE
        merged[teacher_mapped & (geo_seg_tensor == 0) & (teacher_seg == 3)] = 3

        # 2. Terrain-Override: Geometrie sagt FLOOR (flach), Teacher sagt TERRAIN → TERRAIN
        merged[teacher_mapped & (geo_seg_tensor == 0) & (teacher_seg == 5)] = 5

        # 3. VOID Override: Geometrie-Artefakte überschreiben
        merged[teacher_mapped & (teacher_seg == 4)] = 4

    
        # 🚨 NEU: REGEL 4 — DER VOID-BUSTER (Jalousie-Fix)
        # Wenn die Geometrie "VOID" (4) sagt, aber der Teacher eine reale Klasse (0,1,2,3) erkannt hat,
        # dann überschreiben wir das Geometrie-Loch mit dem Wissen des Teachers!
        mask_void_hole = (geo_seg_tensor == 4) & teacher_mapped & (teacher_seg < 4)
        merged[mask_void_hole] = teacher_seg[mask_void_hole]
        
        return merged
    
class V27Dataset(Dataset):
    """V2.9 Dataset: 1-channel input, on-the-fly normals+seg from depth."""
    def __init__(self, roots, img_size=(480, 640)):
        self.img_size = img_size
        self.samples = []
        if 'tartan' in roots:
            self.samples.extend(parse_tartan(roots['tartan']))
        if 'coco' in roots:
            self.samples.extend(parse_coco_robot35(roots['coco']))

        # ✅ V2.9: Single-channel normalization
        self.gray_mean = 0.449  # 0.485*0.299 + 0.456*0.587 + 0.406*0.114
        self.gray_std  = 0.226  # Approximation for luminance

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        sample = self.samples[idx]
        source = sample.get('source')
        cv2_size = (self.img_size[1], self.img_size[0])

        if source == 'tartan':
            img_l = cv2.imread(sample['l'])
            img_r = cv2.imread(sample['r'])
            if img_l is None or img_r is None:
                return self.__getitem__(0)

            img_l = cv2.resize(img_l, cv2_size)
            img_r = cv2.resize(img_r, cv2_size)

            # ✅ V2.9: TRUE single-channel input
            gray_l = cv2.cvtColor(img_l, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            gray_r = cv2.cvtColor(img_r, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            t_l = torch.from_numpy((gray_l - self.gray_mean) / self.gray_std).unsqueeze(0)  # [1, H, W]
            t_r = torch.from_numpy((gray_r - self.gray_mean) / self.gray_std).unsqueeze(0)

            # Depth → Disparity
            raw_depth = np.load(sample['d']).astype(np.float32)
            if raw_depth.shape != (self.img_size[0], self.img_size[1]):
                raw_depth = cv2.resize(raw_depth, cv2_size, interpolation=cv2.INTER_NEAREST)
            valid_d = raw_depth > 1e-4
            disp = np.zeros_like(raw_depth)
            disp[valid_d] = 80.0 / raw_depth[valid_d]
            disp = np.clip(disp, 0, CONFIG['max_disp_pixel'])
            disp_tensor = torch.from_numpy(disp).unsqueeze(0).float()

            # ✅ V2.9: On-the-fly normals from depth
            normals, normals_valid = depth_to_normals_np(raw_depth, CONFIG['tartan_fx'], CONFIG['tartan_fy'])
            normals_tensor = torch.from_numpy(normals).float()  # [3, H, W]
            normals_valid_tensor = torch.from_numpy(normals_valid.astype(np.float32)).unsqueeze(0)  # [1, H, W]

            # ✅ V2.9: Nur noch Geometrie auf der CPU berechnen!
            geo_seg = compute_seg6_from_depth_normals(raw_depth, normals)
            seg_tensor = torch.from_numpy(geo_seg).long()  # [H, W]

            # ✅ Teacher Input vorbereiten (die GPU übernimmt später den Rest)
            img_l_rgb = cv2.cvtColor(img_l, cv2.COLOR_BGR2RGB)
            t_rgb = torch.from_numpy(img_l_rgb).permute(2,0,1).float() / 255.0
            imagenet_mean = torch.tensor([0.485,0.456,0.406]).view(3,1,1)
            imagenet_std = torch.tensor([0.229,0.224,0.225]).view(3,1,1)
            teacher_input = (t_rgb - imagenet_mean) / imagenet_std

            return {
                'left': t_l, 'right': t_r, 'teacher': teacher_input,
                'disp': disp_tensor, 'seg': seg_tensor,
                'normals': normals_tensor, 'normals_valid': normals_valid_tensor,
                'det': None, 'use_stereo': 1.0, 'use_seg': 1.0, 'use_yolo': 0.0
            }

        elif source == 'coco':
            img_raw = cv2.imread(sample['l'])
            if img_raw is None:
                return self.__getitem__(0)
            img_resized = cv2.resize(img_raw, cv2_size)

            # ✅ V2.9: Single-channel
            gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            t_l = torch.from_numpy((gray - self.gray_mean) / self.gray_std).unsqueeze(0)

            # Teacher Input vorbereiten
            img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
            t_rgb = torch.from_numpy(img_rgb).permute(2,0,1).float() / 255.0
            imagenet_mean = torch.tensor([0.485,0.456,0.406]).view(3,1,1)
            imagenet_std = torch.tensor([0.229,0.224,0.225]).view(3,1,1)
            teacher_input = (t_rgb - imagenet_mean) / imagenet_std

            det_tensor = torch.zeros((0, 5))
            if sample.get('b'):
                raw_boxes = np.array(sample['b'])
                if len(raw_boxes) > 0:
                    valid = (raw_boxes[:, 3] > 1e-4) & (raw_boxes[:, 4] > 1e-4)
                    clean = raw_boxes[valid]
                    if len(clean) > 0:
                        clean[:, 1:] = np.clip(clean[:, 1:], 0.0, 1.0)
                        det_tensor = torch.tensor(clean, dtype=torch.float32)

            return {
                'left': t_l, 'right': None, 'teacher': teacher_input,
                'disp': None, 'seg': None,
                'normals': None, 'normals_valid': None,
                'det': det_tensor, 'use_stereo': 0.0, 'use_seg': 0.0, 'use_yolo': 1.0
            }

print("✅ V27Dataset loaded (1-channel, on-the-fly normals+seg)")


# ## V4.00 Visualizer + Dashboard

# In[7]:


import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.colors import PowerNorm
import torchvision

'''
SEG_COLORS = np.array([
    [0, 200, 0],    [255, 165, 0],  [100, 100, 200],
    [200, 50, 50],  [0, 150, 0],    [50, 50, 50]
], dtype=np.uint8)
'''
# SEG_CLASS_NAMES = ['WALKABLE', 'STEP', 'WALL', 'OBSTACLE', 'VOID', 'TERRAIN']

'''
SEG_COLORS = np.array([
    [0, 200, 0],    # 0: WALKABLE   (Grün)
    [255, 165, 0],  # 1: STEP       (Orange)
    [0, 150, 255],  # 2: WALL       (Helles Blau)
    [255, 50, 50],  # 3: OBSTACLE   (Rot)
    [255, 0, 255],  # 4: NAV_ANCHOR (Magenta / Lila)
    [50, 50, 50]    # 5: VOID       (Dunkelgrau)
], dtype=np.uint8)
'''
SEG_COLORS = np.array([
    [0, 200, 0],      # 0: FLOOR (grün)
    [255, 165, 0],    # 1: STEP (orange)
    [0, 100, 255],    # 2: WALL (blau)
    [255, 0, 0],      # 3: OBSTACLE (rot)
    [80, 80, 80],     # 4: VOID (dunkelgrau)
    [139, 90, 43],    # 5: TERRAIN (braun)
], dtype=np.uint8)

from matplotlib.colors import PowerNorm, LinearSegmentedColormap
from matplotlib.patches import Patch
import torchvision
import matplotlib.pyplot as plt

def visualize_v29(step, writer):
    """V5.0 Professional Dashboard: Fixed Scoping, NMS & Class-Colored Boxes."""
    was_training = model.training
    model.eval()
    TW, TH = 320, 240
    
    # Farben für 20 Klassen (YOLO/COCO)
    box_cmap = plt.cm.tab20

    # Custom Colormap für Error-Maps
    error_cmap = LinearSegmentedColormap.from_list("error_cmap", ["#1a1a1a", "#0000ff", "#ffff00", "#ff0000"])

    def unnormalize_gray(tensor):
        img = tensor.squeeze().cpu().numpy()
        img = img * 0.226 + 0.449
        return np.clip(img, 0, 1)

    def unnormalize_rgb(tensor):
        mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1).to(tensor.device)
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1).to(tensor.device)
        rgb = tensor * std + mean
        rgb = rgb.squeeze(0).permute(1, 2, 0).cpu().numpy()
        return np.clip(rgb, 0, 1)

    with torch.no_grad():
        fig, axes = plt.subplots(4, 5, figsize=(24, 15))
        for ax in axes.flatten():
            ax.set_visible(False)
            ax.axis('off')
            
        def show_img(ax, img, title, cmap=None, norm=None, vmin=None, vmax=None, alpha=1.0):
            ax.set_visible(True)
            ax.imshow(img, cmap=cmap, norm=norm, vmin=vmin, vmax=vmax, alpha=alpha)
            ax.set_title(title, fontsize=10)

        # ====================================================================
        # REIHEN 1-3: TARTANAIR (Stereo, Normals, Seg)
        # ====================================================================
        t_batch = static_batches.get('tartan')
        if t_batch is not None:
            t_l = t_batch['left'].to(DEVICE)
            t_r = t_batch['right'].to(DEVICE)
            t_disp_p, t_seg_p, t_disp_s8, t_norm_p, y_s8, y_s16, y_s32 = model(t_l, t_r, use_normals_for_stereo=True)
            t_det_p = [y_s8, y_s16, y_s32]
            
            t_gray = cv2.resize(unnormalize_gray(t_l), (TW, TH))
            t_rgb = cv2.resize(unnormalize_rgb(t_batch['teacher']), (TW, TH)) if t_batch.get('teacher') is not None else cv2.cvtColor((t_gray*255).astype(np.uint8), cv2.COLOR_GRAY2RGB)

            # --- ZEILE 1: STEREO & COARSE S8 ---
            show_img(axes[0, 0], t_gray, "Tartan Input", cmap='gray')

            vmax_d = 50
            if t_batch.get('disp') is not None:
                gt_disp = cv2.resize(t_batch['disp'][0].squeeze().cpu().numpy(), (TW, TH), interpolation=cv2.INTER_NEAREST)
                vmax_d = np.percentile(gt_disp[gt_disp > 0], 98) if (gt_disp > 0).any() else 50
                show_img(axes[0, 1], gt_disp, "GT Disparity", cmap='magma', vmin=0, vmax=vmax_d)

            if t_disp_p is not None:
                # Pred ist s4 (120×160), Werte auf s1-Skala bringen (*4)
                p_disp = cv2.resize(t_disp_p[0].squeeze().cpu().numpy() * 4.0, (TW, TH))
                show_img(axes[0, 2], p_disp, "Pred Disparity (s4→s1)", cmap='magma', vmin=0, vmax=vmax_d)
                if t_batch.get('disp') is not None:
                    show_img(axes[0, 3], np.abs(gt_disp - p_disp), "Stereo Error (px)", cmap=error_cmap, vmin=0, vmax=5)

            # --- NEU: COARSE DISPARITY S8 ---
            # Hole disp_s8 aus Model-Output (im Tuple-Index anpassen!)
            if t_disp_s8 is not None:
                # disp_s8 ist 60×80 mit Werten auf s8-Skala
                # Auf s1-Skala bringen: *8 weil s8 → s1
                p_disp_s8 = cv2.resize(t_disp_s8[0].squeeze().cpu().numpy() * 8.0, (TW, TH), interpolation=cv2.INTER_NEAREST)
                show_img(axes[0, 4], p_disp_s8, "Coarse Disp (s8→s1)", cmap='magma', vmin=0, vmax=vmax_d)

            # --- ZEILE 2: NORMALS ---
            show_img(axes[1, 0], t_gray, "Tartan Input", cmap='gray')
            if t_batch.get('normals') is not None:
                gt_n_raw = t_batch['normals'][0].cpu().numpy().transpose(1, 2, 0)
                show_img(axes[1, 1], cv2.resize(np.clip((gt_n_raw+1)/2,0,1), (TW, TH)), "GT Normals")
            
            # Definition für Overlays (um UnboundLocalError zu vermeiden)
            p_norm_vis = None
            if t_norm_p is not None:
                p_n_raw = t_norm_p[0].cpu().numpy().transpose(1, 2, 0)
                p_norm_vis = cv2.resize(np.clip((p_n_raw+1)/2,0,1), (TW, TH))
                show_img(axes[1, 2], p_norm_vis, "Pred Normals")
                if t_batch.get('normals') is not None:
                    gt_n_small = cv2.resize(gt_n_raw, (p_n_raw.shape[1], p_n_raw.shape[0]))
                    gt_n_small /= (np.linalg.norm(gt_n_small, axis=-1, keepdims=True) + 1e-6)
                    dot = np.sum(gt_n_small * p_n_raw, axis=-1)
                    ang_err = np.arccos(np.clip(dot, -1, 1)) * (180/np.pi)
                    show_img(axes[1, 3], cv2.resize(ang_err, (TW, TH)), "Angular Error", cmap=error_cmap, vmin=0, vmax=30)
                # Overlay v1
                show_img(axes[1, 4], t_gray, "Normals Overlay v1", cmap='gray')
                axes[1, 4].imshow(p_norm_vis, alpha=0.5)

            # --- ZEILE 3: SEG & NORMALS-OVERLAY V2 ---
            show_img(axes[2, 0], t_rgb, "Teacher RGB")

            #if t_batch.get('seg') is not None:
            #    gt_s = t_batch['seg'][0].cpu().numpy()
            #    show_img(axes[2, 1], cv2.resize(SEG_COLORS[np.where(gt_s==255, 5, gt_s)], (TW, TH), interpolation=cv2.INTER_NEAREST), "GT Seg")
            if t_batch.get('seg') is not None:
                
                geo_seg = t_batch['seg'].to(DEVICE)
                teacher_input = t_batch['teacher'].to(DEVICE) if t_batch.get('teacher') is not None else None
                merged_seg = fuse_seg_teacher_gpu(geo_seg, teacher_input)
                gt_s = merged_seg[0].cpu().numpy()
                
                
                show_img(axes[2, 1], cv2.resize(SEG_COLORS[np.where(gt_s==255, 5, gt_s)], (TW, TH), interpolation=cv2.INTER_NEAREST), "GT Seg (merged)")

            if t_seg_p is not None:
                p_s = torch.argmax(t_seg_p.float(), dim=1)[0].cpu().numpy()
                p_s_rgb = cv2.resize(SEG_COLORS[p_s], (TW, TH), interpolation=cv2.INTER_NEAREST)
                show_img(axes[2, 2], p_s_rgb, "Pred Seg")
                show_img(axes[2, 3], t_gray, "Seg Overlay", cmap='gray')
                axes[2, 3].imshow(p_s_rgb, alpha=0.4)
            if p_norm_vis is not None:
                show_img(axes[2, 4], t_gray, "Normals Overlay v2", cmap='gray')
                axes[2, 4].imshow(p_norm_vis, alpha=0.5)

        # ====================================================================
        # REIHE 4: COCO (YOLO & SEG)
        # ====================================================================
        c_batch = static_batches.get('yolo') or static_batches.get('coco')
        if c_batch is not None:
            c_l = c_batch['left'].to(DEVICE)
            # NEU: 7 Werte abfangen (disp, seg, disp_s8, normals, yolo8, yolo16, yolo32)
            _, c_seg_p, _, _, y_s8, y_s16, y_s32 = model(c_l, None, use_normals_for_stereo=False)

            # YOLO-Outputs wieder zu einer Liste zusammenfassen
            c_det_p = [y_s8, y_s16, y_s32]
            c_gray = cv2.resize(unnormalize_gray(c_l), (TW, TH))
            c_rgb = cv2.resize(unnormalize_rgb(c_batch['teacher']), (TW, TH))
            show_img(axes[3, 0], c_rgb, "COCO RGB")
            
            # COCO GT Boxes
            ax_cg = axes[3, 1]; ax_cg.set_visible(True); ax_cg.imshow(c_gray, cmap='gray')
            if c_batch.get('det') is not None:
                for box in c_batch['det'][0]:
                    cls_id, xc, yc, bw, bh = box.tolist()
                    ax_cg.add_patch(plt.Rectangle(((xc-bw/2)*TW, (yc-bh/2)*TH), bw*TW, bh*TH, fill=False, edgecolor=box_cmap(int(cls_id)%20), linewidth=1.5))
            ax_cg.set_title("GT Boxes (Colored)", fontsize=10)
            
            # COCO Pred Boxes & Heatmap
            ax_cp = axes[3, 2]; ax_cp.set_visible(True); ax_cp.imshow(c_gray, cmap='gray')
            if c_det_p is not None:
                y_map = c_det_p[0][0]; obj = torch.sigmoid(y_map[4]); cls_p = torch.sigmoid(y_map[5:])
                conf = obj * cls_p.max(dim=0)[0]
                conf_np = conf.cpu().numpy()
                max_conf = conf_np.max()
                mask = conf > CONFIG['VIS_THRESH']
                if mask.sum() > 0:
                    ys, xs = torch.where(mask)
                    boxes, scores, ids = [], [], []
                    for i in range(len(xs)):
                        gx, gy = xs[i].item(), ys[i].item()
                        bw = torch.exp(torch.clamp(y_map[2, gy, gx], max=5)).item() * 8 * (TW/640)
                        bh = torch.exp(torch.clamp(y_map[3, gy, gx], max=5)).item() * 8 * (TH/480)
                        cx, cy = (gx + torch.sigmoid(y_map[0, gy, gx]).item()) * 8 * (TW/640), (gy + torch.sigmoid(y_map[1, gy, gx]).item()) * 8 * (TH/480)
                        boxes.append([cx-bw/2, cy-bh/2, cx+bw/2, cy+bh/2])
                        scores.append(conf[gy, gx].item())
                        ids.append(cls_p[:, gy, gx].argmax().item())
                    keep = torchvision.ops.nms(torch.tensor(boxes), torch.tensor(scores), 0.45)
                    for idx in keep:
                        b, cid = boxes[idx], ids[idx]
                        ax_cp.add_patch(plt.Rectangle((b[0], b[1]), b[2]-b[0], b[3]-b[1], fill=False, edgecolor=box_cmap(cid%20), linewidth=1.5))
                ax_cp.set_title("Pred Boxes (Colored)", fontsize=10)
                
                # ✅ Gepatchte YOLO Heatmap mit Max_Conf Titel & PowerNorm 0.6
                show_img(axes[3, 3], cv2.resize(conf_np, (TW, TH)), f"YOLO Heatmap (Max: {max_conf:.3f})", 
                         cmap='turbo', norm=PowerNorm(0.6, vmin=0, vmax=1))
            
            if c_seg_p is not None:
                cp_s = torch.argmax(c_seg_p.float(), dim=1)[0].cpu().numpy()
                show_img(axes[3, 4], cv2.resize(SEG_COLORS[cp_s], (TW, TH), interpolation=cv2.INTER_NEAREST), "COCO Pred Seg")

        plt.suptitle(f"V5.00 Dashboard — Step {step}", fontsize=14, fontweight='bold')
        plt.tight_layout(rect=[0, 0.05, 1, 0.95])
        writer.add_figure('Model_Progress/Dashboard', fig, global_step=step)
        plt.close(fig)
    if was_training: model.train()

print("✅ V5.00 Visualizer loaded")


# ## V4.00 Phase 1 Training
# All heads simultaneously. LambdaLR. Infinite epochs...

# In[8]:


def hexapod_collate(batch):
    """Custom collate for mixed TartanAir/COCO batches."""
    result = {}
    result['left'] = torch.stack([b['left'] for b in batch])
    
    # ✅ FIX: Prüfen, ob right existiert, sonst None durchreichen!
    if batch[0]['right'] is not None:
        result['right'] = torch.stack([b['right'] for b in batch])
    else:
        result['right'] = None
        
    result['teacher'] = torch.stack([b['teacher'] for b in batch])

    if batch[0]['disp'] is not None:
        result['disp'] = torch.stack([b['disp'] for b in batch])
    else:
        result['disp'] = None

    if batch[0]['seg'] is not None:
        result['seg'] = torch.stack([b['seg'] for b in batch])
    else:
        result['seg'] = None

    if batch[0]['normals'] is not None:
        result['normals'] = torch.stack([b['normals'] for b in batch])
        result['normals_valid'] = torch.stack([b['normals_valid'] for b in batch])
    else:
        result['normals'] = None
        result['normals_valid'] = None

    det_list = [b['det'] for b in batch]
    if det_list[0] is not None:
        result['det'] = det_list
    else:
        result['det'] = None

    return result

def infinite_loader(loader):
    while True:
        for batch in loader: yield batch

def get_grad_norm(params):
    total = 0.0
    for p in params:
        if p.grad is not None:
            total += p.grad.data.norm(2).item() ** 2
    return total ** 0.5
   
def save_checkpoint(model, optimizer, scheduler, scaler, step, loss, filename):
    path = os.path.join(CONFIG['save_dir'], filename)
    
    # Wir speichern das __dict__, aber entfernen das 'optimizer' Objekt selbst,
    # da man Objekte nicht gut serialisieren sollte (nur deren States)
    sched_dict = {k: v for k, v in scheduler.__dict__.items() if k != 'optimizer'}
    
    checkpoint = {
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'scheduler_state_dict': sched_dict,
        'scaler_state_dict': scaler.state_dict(),
        'global_step': step,
        'best_raw_loss': loss
    }
    torch.save(checkpoint, path)
    print(f"  💾 Saved: {path} (Best raw loss={loss:.4f})")

print("✅ Helpers loaded")


# In[9]:


# =====================================================================
# 📦 DATA LOADING
# =====================================================================
print("Loading datasets...")

tartan_ds = V27Dataset(roots={'tartan': '../datasets/TartanAir'}, img_size=(CONFIG['img_height'], CONFIG['img_width']))
coco_ds = V27Dataset(roots={'coco': '../datasets/coco'}, img_size=(CONFIG['img_height'], CONFIG['img_width']))

tartan_loader = DataLoader(tartan_ds, batch_size=CONFIG['batch_size'], shuffle=True,
    num_workers=CONFIG['num_workers'], pin_memory=False, persistent_workers=True,
    drop_last=True, collate_fn=hexapod_collate)
coco_loader = DataLoader(coco_ds, batch_size=CONFIG['batch_size'], shuffle=True,
    num_workers=CONFIG['num_workers'], pin_memory=False, persistent_workers=True,
    drop_last=True, collate_fn=hexapod_collate)

print(f"TartanAir: {len(tartan_ds)} samples, {len(tartan_loader)} batches")
print(f"COCO: {len(coco_ds)} samples, {len(coco_loader)} batches")

# =====================================================================
# 🎓 TEACHERS (optional, for comparison only — not needed for training!)
# =====================================================================
print("\nLoading teachers (for visualization only)...")

# SegFormer teacher (optional — V2.9 doesn't need it for training)
try:
    from transformers import SegformerForSemanticSegmentation
    teacher_seg = SegformerForSemanticSegmentation.from_pretrained(
        "nvidia/segformer-b2-finetuned-ade-512-512"
    ).to(DEVICE).eval()
    for p in teacher_seg.parameters(): p.requires_grad = False
    print("  SegFormer teacher loaded (for comparison only)")
except:
    teacher_seg = None
    print("  ⚠️ SegFormer not available — seg visualization will show model output only")

# YOLOv5 teacher (for COCO pseudo-label generation — already done offline)
# Not needed during training!
try:
    yolo_teacher = torch.hub.load('ultralytics/yolov5', 'yolov5l', pretrained=True).to(DEVICE).eval()
    for p in yolo_teacher.parameters(): p.requires_grad = False
    print("  YOLOv5l teacher loaded (for dashboard only)")
except:
    yolo_teacher = None
    print("  ⚠️ YOLOv5 teacher not available")

# =====================================================================
# 📸 DASHBOARD SETUP
# =====================================================================
print("\nSetting up dashboard...")

def get_batch_from_samples(dataset, target_filename):
    for i, sample in enumerate(dataset.samples):
        if target_filename in sample['l']:
            return hexapod_collate([dataset[i]])
    return hexapod_collate([dataset[0]])

TARTAN_TARGET = "/TartanAir/office2/Easy/P000/image_left/000336_left.png"
COCO_TARGET = "/coco/train2017/000000003145.jpg"

tartan_val = get_batch_from_samples(tartan_loader.dataset, TARTAN_TARGET)
coco_val = get_batch_from_samples(coco_loader.dataset, COCO_TARGET)

static_batches = {
    'tartan': tartan_val,
    'yolo': coco_val,
}

# Training state
global_step = 0
best_viz_loss = float('inf')
last_viz_step = 0
smoothed_loss = None
smoothed_losses = None
MIN_VIZ_STEPS = 100
MAX_VIZ_STEPS = 1000
LOSS_DROP_THRESH = 0.02

scaler = torch.cuda.amp.GradScaler()

# TensorBoard
writer = SummaryWriter(log_dir='./logs/ver_5-0_Phase-1')

print("✅ Dashboard ready!")


# In[10]:


import torch.optim as optim
import math
from torch.optim.lr_scheduler import LambdaLR

# =====================================================================
# 📦 Optimizer setup
# =====================================================================
os.makedirs(CONFIG['save_dir'], exist_ok=True)
criterion = V210HexapodLoss(CONFIG).to(DEVICE)

steps_per_epoch = len(coco_loader) // CONFIG['ACCUMULATION_STEPS']
total_steps = steps_per_epoch * CONFIG['num_epochs']

# ==========================================
# SCHEDULER: Flat-Cosine (15 Epochen)
# ==========================================
phase2_epochs = CONFIG['num_epochs'] - CONFIG['start_epoch']
total_steps = phase2_epochs * steps_per_epoch







print(f"Steps/epoch: {steps_per_epoch}")
print(f"Total steps: {total_steps} | Warmup: {int(0.1*total_steps)} | Hold Peak: {int(0.4*total_steps)}")

# Gradient clipping
#CLIP_NORMS = {
#    'backbone': 5.0, 'fpn_neck': 5.0, 'yolo_head': 5.0,
#    'stereo_head': 8.0, 'seg_head': 3.0, 'normals_head': 5.0,
#}
CLIP_NORMS = {
    'backbone': 20.0,     # Erhöht! Muss die Gradienten von 4 Köpfen aufnehmen.
    'fpn_neck': 10.0,      # Verteilerzentrum, braucht etwas mehr Raum als die Köpfe.
    
    'stereo_head': 10.0,  # Das Sorgenkind. Darf am stärksten ziehen, um das Cost-Volume zu formen.
    'normals_head': 5.0,  # Solide Regression, 5.0 ist ein guter Standard.
    'yolo_head': 10.0,     # Object Detection ist meist gutmütig.
    'seg_head': 3.0,      # Bleibt niedrig! Segformer konvergiert schnell und darf den Backbone nicht dominieren.
}

# --- V3.1 SETUP ---
global_step = CONFIG.get('start_step', 0)
best_raw_loss = float('inf')
smoothed_loss = None  # Für die Radar-Anzeige und Scheduler
best_viz_loss = float('inf')
last_viz_step = global_step
ema_alpha = 0.95  # Glättung für den Scheduler-Input

# Initialisiere die Iteratoren einmalig außerhalb
tartan_iter = iter(infinite_loader(tartan_loader))
coco_iter = iter(infinite_loader(coco_loader))

# Optimizer
base_lr = CONFIG['lr']

# 1. Backbone-Parameter sammeln (Haben ImageNet-Vorwissen, lernen langsamer)
backbone_params = list(model.backbone.parameters())
backbone_ids = set(id(p) for p in backbone_params)

# 2. ALLE ANDEREN Parameter sammeln (FPN, SPPF, CBAM, YOLO, Seg, Normals, Stereo)
# Der Trick: Wir nehmen einfach alle Parameter des Modells, die NICHT im Backbone sind.
# So vergessen wir absolut kein neues Layer!
head_and_neck_params = [p for p in model.parameters() if id(p) not in backbone_ids]

param_groups = [
    # Backbone darf etwas schneller lernen als beim Finetuning (0.1 statt 0.05), 
    # da es sich an 4 Aufgaben gleichzeitig anpassen muss.
    {'params': backbone_params, 'lr': base_lr * 0.1, 'name': 'Backbone_ImageNet'},
    
    # ALLES andere startet bei null und bekommt volle Power (1.0)
    {'params': head_and_neck_params, 'lr': base_lr * 1.0, 'name': 'Untrained_Modules'}
]

optimizer = torch.optim.AdamW(param_groups, weight_decay=1e-4)
# WICHTIG: initial_lr für jede Gruppe festschreiben
for group in optimizer.param_groups:
    group['initial_lr'] = group['lr']

# =====================================================================
# 📦 Scheduler setup
# =====================================================================
class MultiHeadPlateauThenDecay:
    def __init__(self, optimizer, warmup_steps, decay_steps, patience=2000, threshold=0.01):
        self.optimizer = optimizer
        self.warmup_steps = warmup_steps
        self.decay_steps = decay_steps
        self.patience = patience        
        self.threshold = threshold      
        
        self.current_step = 0
        self.decay_triggered = False
        self.decay_start_step = None
        
        # 🆕 Tracking pro Head
        self.best_losses = {} # Speichert best_loss pro Head-Key
        self.steps_without_improvement = 0
        self.current_mult = 0.0

    def step(self, head_losses_dict=None):
        """
        head_losses_dict: Dictionary mit { 'stereo': 0.5, 'yolo': 1.2, ... }
        """
        self.current_step += 1
        
        # Phase 1: Warmup
        if self.current_step < self.warmup_steps:
            self.current_mult = self.current_step / self.warmup_steps
        
        # Phase 2: Multi-Head Hold & Plateau Detection
        elif not self.decay_triggered:
            self.current_mult = 1.0
            
            if head_losses_dict is not None:
                any_improvement = False
                
                for head_name, current_val in head_losses_dict.items():
                    # Initialisiere Best-Loss für neuen Head
                    if head_name not in self.best_losses:
                        self.best_losses[head_name] = current_val
                        any_improvement = True # Initialisierung zählt als Fortschritt
                        continue
                    
                    # Prüfen auf signifikante Verbesserung in DIESEM Head
                    if current_val < self.best_losses[head_name] * (1 - self.threshold):
                        self.best_losses[head_name] = current_val
                        print(f" {head_name}: Fortschritt erkannt! Reset Patience.")
                        any_improvement = True
                
                if any_improvement:
                    # 🚀 Mindestens ein Head lernt noch! Reset Geduld.
                    if self.steps_without_improvement > 0:
                        # Optional: Logge welcher Head den Reset getriggert hat
                        pass
                    self.steps_without_improvement = 0
                else:
                    # 🛑 Stillstand in ALLEN überwachten Heads
                    self.steps_without_improvement += 1
                
                # Check ob Geduld am Ende
                if self.steps_without_improvement >= self.patience:
                    self.decay_triggered = True
                    self.decay_start_step = self.current_step
                    print(f"\n📉 [Scheduler] Globales Plateau! Alle Köpfe stagnieren seit {self.patience} Steps.")
                    print(f"Letzte Bestwerte: { {k: round(v,3) for k,v in self.best_losses.items()} }")
        
        # Phase 3: Cosine Decay
        else:
            progress = (self.current_step - self.decay_start_step) / self.decay_steps
            progress = min(progress, 1.0)
            self.current_mult = 0.5 * (1 + math.cos(math.pi * progress))
        
        # Optimizer Update
        for pg in self.optimizer.param_groups:
            pg['lr'] = pg['initial_lr'] * self.current_mult
            
        return self.current_mult

#scheduler = optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=phase2_lr_lambda)
# Scheduler Instanz
scheduler = MultiHeadPlateauThenDecay(
    optimizer, 
    warmup_steps=int(2.5 * steps_per_epoch), 
    decay_steps=int(20 * steps_per_epoch), # Wir geben ihm etwas mehr Zeit für den Auslauf
    patience=int(4.0 * steps_per_epoch), 
    threshold=0.01 # Etwas sensibler, um langsames konvergieren des flatten CV zu kompensieren (1.0%)
)

# =====================================================================
# 📦 CHECKPOINT LOADER (optional — skip if training from scratch)
# =====================================================================
import glob

RESUME_TRAINING = True  # Set to False for fresh start
RESUME_RESET_EMA = True # Reset EMA after ckpt

if RESUME_TRAINING:
    import os
    import glob
    import re

    save_dir = CONFIG.get('save_dir', '')
    
    # --- 1. Die Checkpoint-Auswahl (Step vs. Best nach Alter) ---
    search_pattern = os.path.join(save_dir, "checkpoint_v5_0_step_*.pth")
    step_checkpoints = glob.glob(search_pattern)
    
    latest_to_load = None

    if step_checkpoints:
        def get_step(filename):
            match = re.search(r'step_(\d+)', filename)
            return int(match.group(1)) if match else -1

        latest_to_load = max(step_checkpoints, key=get_step)

    best_checkpoint = os.path.join(save_dir, "checkpoint_v5_0_best.pth")
    
    if os.path.exists(best_checkpoint):
        if latest_to_load is None:
            latest_to_load = best_checkpoint
        else:
            # Vergleiche Änderungsdatum (mtime) der beiden Dateien
            time_best = os.path.getmtime(best_checkpoint)
            time_step = os.path.getmtime(latest_to_load)
            
            # Wenn 'best' später auf die Festplatte geschrieben wurde, gewinnt er
            if time_best > time_step:
                latest_to_load = best_checkpoint
                print("🏆 'best' Checkpoint ist jünger als der höchste 'step' Checkpoint.")

    # --- 2. Das Laden und Anwenden des Checkpoints ---
    if not latest_to_load:
        print("⚠️ Kein Checkpoint gefunden! Starte bei Null.")
        global_step = 0
    else:
        print(f"📥 Loading checkpoint: {latest_to_load}")
        checkpoint = torch.load(latest_to_load, map_location=DEVICE, weights_only=False)
             
        # a) Model State laden (Smart Filter)
        state_dict = checkpoint.get('model_state_dict', checkpoint.get('model_state'))
        model_dict = model.state_dict()
        
        # Smart Filter: Lädt alles, was existiert UND die gleiche Größe hat!
        filtered_state_dict = {
            k: v for k, v in state_dict.items() 
            if k in model_dict and v.shape == model_dict[k].shape
        }

        # Zähle, was übersprungen wurde (fürs Debugging)
        skipped = [k for k in state_dict.keys() if k not in filtered_state_dict]
        if skipped:
            print(f"⚠️ {len(skipped)} Layer wurden übersprungen (Shape-Mismatch oder existieren nicht mehr).")

        model.load_state_dict(filtered_state_dict, strict=False)
        print(f"✅ Model weights loaded ({len(filtered_state_dict)} Layer übernommen).")

        # b) Optimizer & Scaler laden (falls vorhanden)
        if 'optimizer_state_dict' in checkpoint:
            try:
                optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            except:
                print("⚠️ Optimizer State inkompatibel, übersprungen.")
        
        if 'scaler_state_dict' in checkpoint:
            scaler.load_state_dict(checkpoint['scaler_state_dict'])

        # c) GLOBAL STEP berechnen
        # Berücksichtigt 'step' (falls so im best gespeichert), 'global_step' oder Fallback via Epoche
        if 'global_step' in checkpoint:
            global_step = checkpoint['global_step']
        elif 'step' in checkpoint: 
            global_step = checkpoint['step']
        else:
            old_epoch = checkpoint.get('epoch', 0)
            global_step = old_epoch * steps_per_epoch
        
        # d) SCHEDULER State wiederherstellen
        if 'scheduler_state_dict' in checkpoint:
            # Bestehende Instanz mit gespeicherten Werten updaten
            scheduler.__dict__.update(checkpoint['scheduler_state_dict'])
            # 🚨 FIX: Zwingt den Scheduler, wieder den echten Optimizer zu nutzen!
            scheduler.optimizer = optimizer
            print(f"✅ Scheduler-State wiederhergestellt (Patience: {scheduler.steps_without_improvement})")
        else:
            scheduler.current_step = global_step
            # Falls der alte Checkpoint nur einen 'best_raw_loss' hatte, 
            # weisen wir ihn einfach allen Heads als Startpunkt zu
            old_best = checkpoint.get('best_raw_loss', float('inf'))
            scheduler.best_losses = {'stereo': old_best, 'yolo': old_best, 'normals': old_best, 'seg': old_best}
            print(f"ℹ️ Alter Checkpoint: Multi-Head Scheduler initialisiert.")
        if RESUME_RESET_EMA:
            # EMA und Scheduler resetten wegen geänderter Priorities
            criterion.ema_stereo.fill_(1.0)
            criterion.ema_yolo.fill_(1.0)
            criterion.ema_seg.fill_(1.0)
            criterion.ema_normals.fill_(1.0)

            criterion.ema_initialized = False

            scheduler.best_losses = {}
            scheduler.steps_without_improvement = 0

            smoothed_loss = None
            smoothed_losses = None
            scheduler.decay_steps=int(20 * steps_per_epoch) # Wir geben ihm etwas mehr Zeit für den Auslauf
            scheduler.patience=int(4.0 * steps_per_epoch) 
            scheduler.threshold=0.01 # Etwas sensibler, um langsames konvergieren des flatten CV zu kompensieren (1.0%)
            print("✅ EMA, Scheduler und Smoothed-Losses reset für V5.0 Priority-Änderung")
            print(f"EMA scheduler reset: (Patience: {scheduler.steps_without_improvement})")

            

        print(f"🚀 Resume bei Step {global_step} (ca. Epoche {global_step // steps_per_epoch})")
else:
    global_step = 0
    print("🆕 Fresh training start")

# ==========================================
# TENSORBOARD: MODELL-GRAPH SPEICHERN
# ==========================================
print("📸 Generiere Modell-Graph für TensorBoard...")

# Dummy-Tensoren im Format [Batch, Channel, Height, Width]
# Laut deiner Config nutzt du Single-Channel (1) Graustufenbilder, oft 480x640.
# Passe die Auflösung an, falls deine config['height'] / config['width'] anders sind!
H, W = 480, 640 
dummy_l = torch.randn(1, 1, H, W, device=DEVICE)
dummy_r = torch.randn(1, 1, H, W, device=DEVICE)
dummy_use_normals = torch.tensor(True, device=DEVICE) # Oder False, je nach Standard

# Für sauberes Tracing kurz in den Eval-Modus schalten
model.eval()

try:
    # Wir übergeben die Input-Parameter, wie sie deine forward() erwartet:
    # forward(self, x_left, x_right=None, use_normals_for_stereo=False)
    writer.add_graph(model, input_to_model=(dummy_l, dummy_r, dummy_use_normals))
    writer.flush()
    print("✅ Modell-Graph erfolgreich in TensorBoard gespeichert!")
except Exception as e:
    # Tracing kann manchmal zickig sein, wenn es komplexe If/Else-Verzweigungen gibt.
    print(f"⚠️ Modell-Graph konnte nicht gespeichert werden (JIT Tracer Fehler): {e}")

# Direkt wieder auf Train schalten für den Start der Epoche!
model.train();


# In[ ]:


# =====================================================================
# 🚀 V2.10 PHASE 2  TRAINING
# =====================================================================


import math
from torch.optim.lr_scheduler import LambdaLR

# Der neue adaptive pbar (ohne festes Ende, da wir auf Plateau warten)
pbar = tqdm(total=None, desc="V5.0 Adaptive Training", unit="it")

# Endlos-Schleife: Der Scheduler bricht ab, wenn der Decay durch ist
while True:
    # Epochen-Metriken (virtuell für Logging-Kompatibilität)
    epoch = global_step // steps_per_epoch
    
    # Phase 1: Stereo lernt ohne Normals | Phase 2: Stereo nutzt Normals
    inject_normals_into_stereo = epoch >= CONFIG['normals_to_stereo_epoch']
    
    model.train()
    model.backbone.eval()  # BN locked
    total_step_loss = 0.0
    step_logs = {}

    model.zero_grad(set_to_none=True)

    # =======================================================
    # --- 1. TARTANAIR (Stereo + Normals + Seg) ---
    # =======================================================
    for _ in range(CONFIG['ACCUMULATION_STEPS']):
        batch = next(tartan_iter)
        l = batch['left'].to(DEVICE)
        r = batch['right'].to(DEVICE)
        
        geo_seg = batch['seg'].to(DEVICE) if batch.get('seg') is not None else None
        teacher_input = batch['teacher'].to(DEVICE) if batch.get('teacher') is not None else None
        merged_seg = fuse_seg_teacher_gpu(geo_seg, teacher_input)
        
        targets = {
            'disp': batch['disp'].to(DEVICE),
            'normals': batch['normals'].to(DEVICE),
            'normals_valid': batch['normals_valid'].to(DEVICE),
            'seg': merged_seg,
            'det': None,
        }
        
        with torch.amp.autocast('cuda', enabled=True, dtype=torch.float16):
            # 🚨 NEU: 7 Werte entpacken
            disp_s4, seg_pred, disp_s8, normals_s4, yolo_s8, yolo_s16, yolo_s32 = model(
                l, r, use_normals_for_stereo=inject_normals_into_stereo
            )
            
            # Die preds-Reihenfolge muss exakt der deines Criterions entsprechen!
            # Original war: final_disp, seg, det, disp_s8, normals
            preds = (
                disp_s4.float() if disp_s4 is not None else None, 
                seg_pred.float() if seg_pred is not None else None, 
                None,  # det ist bei TartanAir None (YOLO wird hier nicht trainiert)
                disp_s8.float() if disp_s8 is not None else None,
                normals_s4.float() if normals_s4 is not None else None
            )

            loss, logs = criterion(preds, targets, left_img=l, coarse_disp=preds[3])
            logs = {k: (v.item() if isinstance(v, torch.Tensor) else float(v)) for k, v in logs.items()}
            loss = loss / (2.0 * CONFIG['ACCUMULATION_STEPS'])
        
        scaler.scale(loss).backward()
        total_step_loss += loss.item()
        for k, v in logs.items():
            step_logs[k] = step_logs.get(k, 0) + v / CONFIG['ACCUMULATION_STEPS']

    # =======================================================
    # --- 2. COCO (YOLO only) ---
    # =======================================================
    for _ in range(CONFIG['ACCUMULATION_STEPS']):
        batch = next(coco_iter)
        l = batch['left'].to(DEVICE)
        coco_det = [t.to(DEVICE) for t in batch['det']]
        targets = {'disp': None, 'normals': None, 'seg': None, 'det': coco_det}

        with torch.amp.autocast('cuda', enabled=True, dtype=torch.float16):
            # 🚨 NEU: Dummy-Variablen für alles außer YOLO nutzen
            _, _, _, _, yolo_s8, yolo_s16, yolo_s32 = model(
                l, None, use_normals_for_stereo=False
            )
            
            # YOLO-Outputs in eine Liste packen und nach float casten
            det_pred_float = [d.float() for d in (yolo_s8, yolo_s16, yolo_s32)]
            
            # Criterion erwartet: disp, seg, det, disp_s8, normals
            preds = (None, None, det_pred_float, None, None)

            loss, logs = criterion(preds, targets, left_img=l)
            logs = {k: (v.item() if isinstance(v, torch.Tensor) else float(v)) for k, v in logs.items()}
            
        scaler.scale(loss).backward()
        total_step_loss += loss.item()
        for k, v in logs.items():
            step_logs[k] = step_logs.get(k, 0) + v / CONFIG['ACCUMULATION_STEPS']

    # =======================================================
    # --- 🚨 SCHUTZSCHILD: Gradienten Check ---
    # =======================================================
    has_grads = any(p.grad is not None for p in model.parameters())
    if not has_grads:
        print(f"⚠️ [WARNUNG] Step {global_step}: Keine Gradienten! Überspringe.")
        model.zero_grad(set_to_none=True)
        continue
        
    # =======================================================
    # --- STEP & CLIPPING ---
    # =======================================================
    scaler.unscale_(optimizer)
    '''
    for tag, module in [('Backbone',model.backbone),('FPN',model.fpn_neck),
                        ('Stereo',model.stereo_head),('Seg',model.seg_head),
                        ('Yolo',model.yolo_head),('Normals',model.normals_head)]:
        grad_norm = get_grad_norm(module.parameters())
        step_logs[f'Grad_Norm_Pre/{tag}'] = grad_norm
        clip_key = tag.lower() + ('_head' if tag not in ['Backbone','FPN'] else ('_neck' if tag=='FPN' else ''))
        max_norm = CLIP_NORMS.get(clip_key, 5.0) if 'CLIP_NORMS' in globals() else 5.0
        torch.nn.utils.clip_grad_norm_(module.parameters(), max_norm=max_norm)

    torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=10.0)
    '''
    # 1. Module übersichtlich definieren, damit wir sie zweimal durchlaufen können
    modules_to_track = [
        ('Backbone', model.backbone),
        ('FPN', model.fpn_neck),
        ('Stereo', model.stereo_head),
        ('Seg', model.seg_head),
        ('Yolo', model.yolo_head),
        ('Normals', model.normals_head)
    ]

    # ==========================================================
    # PHASE 1: PRE-LOGGING & INDIVIDUELLES CLIPPING
    # ==========================================================
    for tag, module in modules_to_track:
        # 1a. Pre-Norm berechnen und loggen
        grad_norm_pre = get_grad_norm(module.parameters())
        step_logs[f'Grad_Norm_Pre/{tag}'] = grad_norm_pre
        
        # 1b. Individuelles Limit holen
        clip_key = tag.lower() + ('_head' if tag not in ['Backbone','FPN'] else ('_neck' if tag=='FPN' else ''))
        max_norm = CLIP_NORMS.get(clip_key, 5.0) if 'CLIP_NORMS' in globals() else 5.0
        
        # 1c. Individuell clippen
        torch.nn.utils.clip_grad_norm_(module.parameters(), max_norm=max_norm)


    # ==========================================================
    # PHASE 2: GLOBALES CLIPPING & PRE-GLOBAL LOGGING
    # ==========================================================
    # Wichtig: clip_grad_norm_ gibt als Rückgabewert immer den Norm VOR dem eigenen Eingriff zurück!
    global_norm_pre = torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=35.0) # (Hier ggf. auf 35 erhöhen!)
    step_logs['Grad_Norm_Pre/Global'] = global_norm_pre


    # ==========================================================
    # PHASE 3: POST-LOGGING (Das Ergebnis der Firewall)
    # ==========================================================
    for tag, module in modules_to_track:
        # Jetzt lesen wir die Gradienten erneut, nachdem beide Firewalls drüber gelaufen sind
        grad_norm_post = get_grad_norm(module.parameters())
        step_logs[f'Grad_Norm_Post/{tag}'] = grad_norm_post

    # Und noch den tatsächlichen finalen Gesamt-Norm des Modells
    step_logs['Grad_Norm_Post/Global'] = get_grad_norm(model.parameters())


    # ==========================================================
    # PHASE 4: OPTIMIZER STEP
    # ==========================================================

    scaler.step(optimizer)
    scaler.update()

    # =======================================================
    # --- 🚨 ADAPTIVE SCHEDULER STEP ---
    # =======================================================
    raw_loss = sum(step_logs.get(f'Loss_Raw/{k}', 0) for k in ['stereo', 'yolo', 'normals', 'seg_ce'])
    # ✅ NEU: NaN-Guard
    if math.isnan(raw_loss) or math.isinf(raw_loss):
        print(f"⚠️ NaN in raw_loss at step {global_step}, skipping EMA update")
        global_step += 1
        pbar.update(1)
        continue
    if smoothed_loss is None: smoothed_loss = raw_loss
    else: smoothed_loss = ema_alpha * smoothed_loss + (1 - ema_alpha) * raw_loss
      

    # 1. Losses glätten (EMA), damit Ausreißer die Geduld nicht fälschlich resetten
    if smoothed_losses is None:
        smoothed_losses = {k: v for k, v in step_logs.items() if 'Loss_Raw' in k}
    else:
        for k in smoothed_losses:
            if k in step_logs:
                # ✅ NEU: NaN-Guard pro Key
                v = step_logs[k]
                if not (math.isnan(v) or math.isinf(v)):
                    smoothed_losses[k] = smoothed_losses[k] * 0.95 + v * 0.05

    # 2. Scheduler-Update mit dem Dictionary der Teil-Losses
    # Wir filtern nur die relevanten Köpfe heraus
    monitor_dict = {
        'stereo': smoothed_losses.get('Loss_Raw/stereo', 0),
        'yolo': smoothed_losses.get('Loss_Raw/yolo', 0),
        'normals': smoothed_losses.get('Loss_Raw/normals', 0),
        'seg': smoothed_losses.get('Loss_Raw/seg_ce', 0)
    }

    lr_mult = scheduler.step(head_losses_dict=monitor_dict)

    # =======================================================
    # --- TENSORBOARD LOGGING ---
    # =======================================================
    if global_step % 50 == 0:
        writer.add_scalar('Loss/Total_Weighted', total_step_loss, global_step)
        writer.add_scalar('Scheduler/Smoothed_Raw_Loss', smoothed_loss, global_step)
        writer.add_scalar('Scheduler/Patience_Counter', scheduler.steps_without_improvement, global_step)
        # 🆕 Multi-Head Monitor Dict zu TensorBoard hinzufügen
        # Wir loggen sie unter einem eigenen Tree 'Scheduler_Heads/', 
        # damit sie in TensorBoard schön gruppiert sind
        for head_name, loss_val in monitor_dict.items():
            writer.add_scalar(f'Scheduler_Heads/{head_name}', loss_val, global_step)
            
            # Optional: Logge auch den Abstand zum bisherigen Bestwert in Prozent
            # Das hilft zu sehen, wie weit ein Head vom Threshold (1.5%) entfernt ist
            if head_name in scheduler.best_losses:
                best = scheduler.best_losses[head_name]
                # Verhältnis zum Bestwert (1.0 = exakt gleich, < 1.0 = besser)
                ratio = loss_val / (best + 1e-8)
                writer.add_scalar(f'Scheduler_Ratios/{head_name}', ratio, global_step)
            
        for i, pg in enumerate(optimizer.param_groups):
            writer.add_scalar(f'LR/{pg.get("name", f"G{i}")}', pg['lr'], global_step)
            
        for k, v in step_logs.items():
            if k.startswith('Grad_Norm') or '/' in k:
                writer.add_scalar(k, v, global_step)
            elif k not in ['yolo_num_targets']: 
                writer.add_scalar(f'Loss_Raw/{k}', v, global_step)

    # =======================================================
    # --- VISUALIZATION & BEST SAVING ---
    # =======================================================
    tsl = global_step - last_viz_step
    sig_drop = True if best_viz_loss==float('inf') else (best_viz_loss-smoothed_loss)/(best_viz_loss+1e-8)>LOSS_DROP_THRESH
    
    if global_step==0 or (tsl>=MIN_VIZ_STEPS and sig_drop) or tsl>=MAX_VIZ_STEPS:
        print(f"\n📸 Snapshot step {global_step} | Loss: {smoothed_loss:.4f} | LR-Mult: {lr_mult:.3f}")
        visualize_v29(step=global_step, writer=writer)
        writer.flush(); torch.cuda.empty_cache()
        model.train(); model.backbone.eval()
        best_viz_loss = min(best_viz_loss, smoothed_loss)
        last_viz_step = global_step

    # Best-Modell Logik (auf Raw Loss)
    if global_step % 100 == 0: # Nur alle 100 Steps auf Best-Wert prüfen
        if smoothed_loss < best_raw_loss:
            best_raw_loss = smoothed_loss
            save_checkpoint(model=model, optimizer=optimizer, 
                    scheduler=scheduler, scaler=scaler, step=global_step, loss=best_raw_loss,
                    filename="checkpoint_v5_0_best.pth")

    # Regelmäßiges Backup jede Epoche
    if global_step % (steps_per_epoch * 1) == 0:
        save_checkpoint(model=model, optimizer=optimizer,
                        scheduler=scheduler, scaler=scaler, step=global_step, loss=total_step_loss,
                        filename=f"checkpoint_v5_0_step_{global_step}.pth")
        print(f"\n📸 Snapshot step {global_step} | Loss: {smoothed_loss:.4f} | LR-Mult: {lr_mult:.3f}")
        visualize_v29(step=global_step, writer=writer)
        writer.flush(); torch.cuda.empty_cache()
        model.train(); model.backbone.eval()
        best_viz_loss = min(best_viz_loss, smoothed_loss)
        last_viz_step = global_step

    # =======================================================
    # --- PROGRESS BAR UPDATE ---
    # =======================================================
    radar_str = f"{(smoothed_loss/(best_viz_loss+1e-8))*100:.1f}%" if best_viz_loss != float('inf') else "---"
    
    # Die Logik für die Zustandsanzeige verfeinern:
    if global_step < scheduler.warmup_steps:
        mode = f"WARMUP:{lr_mult*100:.0f}%"
    elif not scheduler.decay_triggered:
        mode = "HOLD"
    else:
        mode = f"DECAY:{lr_mult:.3f}"

    pbar.set_description(f"V5.0 Step {global_step} [{mode}]")
    
    # Werte extrahieren
    s = step_logs.get('Loss_Raw/stereo', 0)
    c = step_logs.get('Loss_Raw/seg_ce', 0)
    y = step_logs.get('Loss_Raw/yolo', 0)
    n = step_logs.get('Loss_Raw/normals', 0)
    
    pbar.set_description(f"V5.0 Step {global_step} [{mode}]")
    pbar.set_postfix_str(f"P:{scheduler.steps_without_improvement}/{scheduler.patience} R:{radar_str} S:{s:.1f} C:{c:.2f} Y:{y:.1f} N:{n:.2f}")
    pbar.update(1)

    # --- ABBRUCH-BEDINGUNG ---
    if scheduler.decay_triggered and lr_mult < 0.005:
        print(f"🏁 Training beendet! Minimum LR erreicht bei Step {global_step}.")
        break

    global_step += 1


# In[ ]:





# In[ ]:





# In[ ]:




