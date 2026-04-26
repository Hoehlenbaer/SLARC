"""
quantizer_split.py — Quantisiert und kompiliert 3 Split-ONNX-Modelle
zu jeweils einem HEF für den Hailo-8.
 
HEF A: Backbone    (gray_img → f_s4, f_s8, f_s16, f_s32)
HEF B: Geometry    (features + img → disp, normals)
HEF C: Detection   (features + normals → seg, yolo)
 
Usage:
    python quantizer_split.py              # Alle 3 HEFs
    python quantizer_split.py backbone     # Nur Backbone
    python quantizer_split.py geometry     # Nur Geometry
    python quantizer_split.py detection    # Nur Detection
"""
 
import os
import sys
import numpy as np
import traceback
import json
from hailo_sdk_client import ClientRunner
from hailo_sdk_client import InferenceContext
 
# =====================================================================
# KONFIGURATION
# =====================================================================
ONNX_DIR = 'onnx_split'
N_CALIB = 1024
BATCH_SIZE = 8 # Kleinerer Batch für die Dataloader-Inferenz (schont RAM)
 
# Normalisierung (identisch zum Training)
NORM_MEAN = 0.449 * 255.0   # = 114.495
NORM_STD  = 0.226 * 255.0   # =  57.630
 
# ── Modell-Definitionen ──────────────────────────────────────────────
MODELS = {
    'single': {
        'onnx': f'{ONNX_DIR}/hexapod_v4_0_simplified.onnx',
        'har': f'{ONNX_DIR}/hexapod_single.har',
        'hef': f'{ONNX_DIR}/hexapod_single.hef',
        'alls': f'{ONNX_DIR}/backbone_script.alls',
        'name': 'hexapod_single_simplified',
        'inputs': {
            'input_layer1': [1, 1, 480, 640],
            'input_layer2': [1, 1, 480, 640],
        },
        'outputs': ['disp_final','seg','disp_s8','normals_s1','yolo_s8', 'yolo_s16', 'yolo_s32'],
        'needs_norm': True,    # Normalisierung auf NPU
        'norm_inputs': ['gray_img'],
    },
    'backbone': {
        'onnx': f'{ONNX_DIR}/hexapod_backbone_simplified.onnx',
        'har': f'{ONNX_DIR}/hexapod_backbone.har',
        'hef': f'{ONNX_DIR}/hexapod_backbone.hef',
        'alls': f'{ONNX_DIR}/backbone_script.alls',
        'name': 'hexapod_backbone_simplified',
        'inputs': {
            'gray_img': [1, 1, 480, 640],
        },
        'outputs': ['f_s4', 'f_s8', 'f_s16', 'f_s32'],
        'needs_norm': True,    # Normalisierung auf NPU
        'norm_inputs': ['gray_img'],
    },
    'geometry': {
        'onnx': f'{ONNX_DIR}/hexapod_geometry_simplified.onnx',
        'har': f'{ONNX_DIR}/hexapod_geometry.har',
        'hef': f'{ONNX_DIR}/hexapod_geometry.hef',
        'alls': f'{ONNX_DIR}/geometry_script.alls',
        'name': 'hexapod_geometry_simplified',
        'inputs': {
            'f_s4_l':  [1, 32, 120, 160],
            'f_s8_l':  [1, 48, 60, 80],
            'f_s4_r':  [1, 43, 120, 160],
            'f_s8_r':  [1, 48, 60, 80],
        },
        'outputs': ['disp_final', 'normals_s4', 'disp_s8'],
        'needs_norm': True,    # img_l braucht Normalisierung
        'norm_inputs': ['img_l'],
    },
    'detection': {
        'onnx': f'{ONNX_DIR}/hexapod_detection_simplified.onnx',
        'har': f'{ONNX_DIR}/hexapod_detection.har',
        'hef': f'{ONNX_DIR}/hexapod_detection.hef',
        'alls': f'{ONNX_DIR}/detection_script.alls',
        'name': 'hexapod_detection_simplified',
        'inputs': {
            'f_s4_l':    [1, 32, 120, 160],
            'f_s8_l':    [1, 48, 60, 80],
            'f_s16_l':   [1, 136, 30, 40],
            'f_s32_l':   [1, 448, 15, 20],
            'normals_s4': [1, 3, 120, 160],
        },
        'outputs': ['seg', 'yolo_s8', 'yolo_s16', 'yolo_s32'],
        'needs_norm': False,   # Bekommt nur Zwischen-Features, keine Rohbilder
        'norm_inputs': [],
    },
    'combined': {
        'onnx': f'{ONNX_DIR}/hexapod_geo_det_combined_simplified.onnx',
        'har': f'{ONNX_DIR}/hexapod_combined.har',
        'hef': f'{ONNX_DIR}/hexapod_combined.hef',
        'alls': f'{ONNX_DIR}/combined_script.alls',
        'name': 'hexapod_geo_det_combined_simplified',
        'inputs': {
            'f_s4_l':  [1, 32, 120, 160],
            'f_s8_l':  [1, 48, 60, 80],
            'f_s4_r':  [1, 32, 120, 160],
            'f_s8_r':  [1, 48, 60, 80],
            'f_s16_l': [1, 136, 30, 40],
            'f_s32_l': [1, 448, 15, 20],
        },
        'outputs': ['disp_final', 'normals_s4', 'disp_s8', 'seg',
                     'yolo_s8', 'yolo_s16', 'yolo_s32'],
        'needs_norm': True,
        'norm_inputs': ['img_l'],
    },
}

# =====================================================================
# DATALOADER KLASSE
# =====================================================================

class HailoCalibrationDataloader:
    """
    Ein generischer Dataloader für die Hailo-Optimierung.
    Erzeugt Batches im Format { input_layer_name: data_array }.
    """
    def __init__(self, data_dict):
        """
        data_dict: Dictionary mit { 'har_layer_name': numpy_array }
        """
        self.data_dict = data_dict
        self.num_samples = len(next(iter(data_dict.values())))
        self.input_names = list(data_dict.keys())

    def __iter__(self):
        """ Iteriert über die Daten für die SDK optimize() Funktion. """
        for i in range(self.num_samples):
            # Hailo erwartet pro Iteration ein Dict mit einem Sample (Shape: 1, H, W, C)
            yield {name: self.data_dict[name][i:i+1] for name in self.input_names}

    def __len__(self):
        return self.num_samples 
 
# =====================================================================
# HILFSFUNKTIONEN
# =====================================================================
def profile_model(model_cfg):
    """Profiling für ein einzelnes Sub-Modell."""
    har_path = model_cfg['har']
    name = model_cfg['name']
    print(f"\n📊 Profiling: {name}...")
    try:
        runner = ClientRunner(har=har_path, hw_arch='hailo8')
        try:
            from hailo_sdk_client.profiler.profiler import ProfilingLevel
            report = runner.profile(profiling_level=ProfilingLevel.FULL)
        except ImportError:
            try:
                report = runner.profile(level=2)
            except TypeError:
                report = runner.profile()
        
        report_path = f"{ONNX_DIR}/{name}_profile.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        
        # Kurze Zusammenfassung
        if isinstance(report, dict) and 'stats' in report:
            md = report['stats'].get('model_details', {})
            print(f"   Weights: {md.get('weights', 0)/1e6:.1f}M")
            print(f"   OPs:     {md.get('total_ops_per_frame', 0)/1e9:.2f} GOPS")
            print(f"   Inputs:  {md.get('input_shapes', '?')}")
            print(f"   Outputs: {md.get('output_shapes', '?')}")
        print(f"   ✅ Report: {report_path}")
    except Exception:
        print(f"   ⚠️  Profiling fehlgeschlagen (nicht kritisch):")
        traceback.print_exc()
 
 
def write_model_script(model_cfg):
    """Schreibt das .alls Model-Script für ein Sub-Modell."""
    alls_path = model_cfg['alls']
    name = model_cfg['name']
    
    # Analysiere HAR für AvgPool-Layer und Input-Layer
    runner = ClientRunner(har=model_cfg['har'], hw_arch='hailo8')
    hn = runner.get_hn_dict()
    all_layers = list(hn.get("layers", {}).keys())
    
    avgpool_layers = sorted([
        lname for lname, data in hn["layers"].items()
        if isinstance(data.get("type", ""), str)
        and "pool" in data["type"].lower()
        and "avg" in data["type"].lower()
    ])
    
    # AvgPools nach Kernel-Shape gruppieren (exakt wie im Original-Quantizer)
    pools_60x80 = [n for n in avgpool_layers if hn["layers"][n]['params']['kernel_shape'][1] == 60]
    pools_30x40 = [n for n in avgpool_layers if hn["layers"][n]['params']['kernel_shape'][1] == 30]
    pools_15x20 = [n for n in avgpool_layers if hn["layers"][n]['params']['kernel_shape'][1] == 15]
    
    if avgpool_layers:
        print(f"   AvgPool 60×80: {len(pools_60x80)} Layer")
        print(f"   AvgPool 30×40: {len(pools_30x40)} Layer")
        print(f"   AvgPool 15×20: {len(pools_15x20)} Layer")
    
    with open(alls_path, 'w', encoding='utf-8') as f:
        f.write("model_optimization_flavor(optimization_level=0, compression_level=0, batch_size=4)\n")
        f.write("performance_param(compiler_optimization_level=max)\n")
        
        # Normalisierung nur für Rohbild-Inputs
        # Der DFC benennt Inputs immer um zu input_layer1, input_layer2, etc.
        if model_cfg['needs_norm']:
            expected_inputs = list(model_cfg['inputs'].keys())
            har_inputs = sorted([l for l in all_layers if 'input_layer' in l.lower()])
            for norm_inp in model_cfg['norm_inputs']:
                if norm_inp in expected_inputs:
                    idx = expected_inputs.index(norm_inp)
                    if idx < len(har_inputs):
                        har_layer = har_inputs[idx]
                        f.write(f"norm_{idx} = normalization([{NORM_MEAN:.3f}], [{NORM_STD:.3f}], {har_layer})\n")
                    else:
                        print(f"   ⚠️  Kein HAR-Input für Normalisierung von '{norm_inp}'!")
        
        # AvgPool-Optimierung nach Größe gruppiert
        if pools_60x80:
            f.write(f"pre_quantization_optimization(global_avgpool_reduction, "
                    f"layers=[{','.join(pools_60x80)}], division_factors=[6,8])\n")
        if pools_30x40:
            f.write(f"pre_quantization_optimization(global_avgpool_reduction, "
                    f"layers=[{','.join(pools_30x40)}], division_factors=[6,8])\n")
        if pools_15x20:
            f.write(f"pre_quantization_optimization(global_avgpool_reduction, "
                    f"layers=[{','.join(pools_15x20)}], division_factors=[3,4])\n")
    
    print(f"   📝 Model-Script: {alls_path}")
    return alls_path
 
 
def get_har_input_mapping(runner, model_cfg):
    """Ermittelt das Mapping von Config-Inputs zu tatsächlichen HAR-Layern."""
    hn = runner.get_hn_dict()
    all_layers = list(hn.get("layers", {}).keys())
    har_inputs = sorted([l for l in all_layers if 'input_layer' in l.lower()])
    
    expected_inputs = list(model_cfg['inputs'].keys())
    mapping = {}
    for i, inp_name in enumerate(expected_inputs):
        if i < len(har_inputs):
            mapping[inp_name] = har_inputs[i]
    return mapping

def to_nhwc(arr):
    """Konvertiert NCHW (ONNX/PyTorch) zu NHWC (Hailo)."""
    if arr.ndim == 4 and arr.shape[1] in [1, 3, 32, 48, 136, 448]:
        return arr.transpose(0, 2, 3, 1).astype(np.float32)
    return arr.astype(np.float32)

def generate_calib_dataloader(model_key, model_cfg):
    """
    Erzeugt den Dataloader für ein Modell. 
    Hier steckt die Logik, wie Features durchgereicht werden.
    """
    print(f"\n📦 Bereite Dataloader vor: {model_key}...")
    
    # Basis-Daten laden
    calib_l = np.load('calib_left.npy')
    calib_r = np.load('calib_right.npy')
    n = min(N_CALIB, calib_l.shape[0])
    
    runner = ClientRunner(har=model_cfg['har'], hw_arch='hailo8')
    har_map = get_har_input_mapping(runner, model_cfg)
    
    raw_data = {}

    # --- LOGIK: BACKBONE & SINGLE ---
    if model_key in ['backbone', 'single']:
        if model_key == 'backbone':
            raw_data[har_map['gray_img']] = to_nhwc(calib_l[:n])
        else: # single
            raw_data[har_map['input_layer1']] = to_nhwc(calib_l[:n])
            raw_data[har_map['input_layer2']] = to_nhwc(calib_r[:n])

    # --- LOGIK: GEOMETRY / DETECTION (mit Feature-Inferenz) ---
    else:
        bb_har = MODELS['backbone']['har']
        if not os.path.exists(bb_har):
            print("⚠️ Backbone HAR nicht gefunden! Nutze Random-Daten für Dataloader.")
            return _make_random_dataloader(model_cfg, har_map, n)

        print("🔄 Generiere Zwischen-Features für Dataloader via Backbone...")
        bb_runner = ClientRunner(har=bb_har, hw_arch='hailo8')
        bb_runner.load_model_script(MODELS['backbone']['alls'])
        
        # Inferenz-Helper
        def run_inference(images_nchw):
            feats = {k: [] for k in ['f_s4', 'f_s8', 'f_s16', 'f_s32']}
            with bb_runner.infer_context(InferenceContext.SDK_NATIVE) as ctx:
                for i in range(0, n, BATCH_SIZE):
                    batch = to_nhwc(images_nchw[i:i+BATCH_SIZE])
                    res = bb_runner.infer(ctx, batch)
                    for k in feats:
                        match = [rk for rk in res if k in rk]
                        if match: feats[k].append(res[match[0]])
            return {k: np.concatenate(v, axis=0) for k, v in feats.items() if v}

        f_left = run_inference(calib_l[:n])
        
        if model_key == 'geometry' or model_key == 'combined':
            f_right = run_inference(calib_r[:n])
            
            for inp_name, har_layer in har_map.items():
                if 'img' in inp_name: raw_data[har_layer] = to_nhwc(calib_l[:n])
                elif 'f_s4_l' in inp_name: raw_data[har_layer] = f_left['f_s4']
                elif 'f_s8_l' in inp_name: raw_data[har_layer] = f_left['f_s8']
                elif 'f_s4_r' in inp_name: raw_data[har_layer] = f_right['f_s4']
                elif 'f_s8_r' in inp_name: raw_data[har_layer] = f_right['f_s8']
                # Für Combined zusätzlich:
                elif 'f_s16_l' in inp_name: raw_data[har_layer] = f_left['f_s16']
                elif 'f_s32_l' in inp_name: raw_data[har_layer] = f_left['f_s32']

        elif model_key == 'detection':
            for inp_name, har_layer in har_map.items():
                if 'normals' in inp_name: 
                    raw_data[har_layer] = np.random.randn(n, 120, 160, 3).astype(np.float32) * 0.5
                else:
                    key = inp_name.replace('_l', '')
                    raw_data[har_layer] = f_left[key]

    return HailoCalibrationDataloader(raw_data)

def _make_random_dataloader(cfg, har_map, n):
    """Fallback für Random Daten."""
    data = {}
    for inp_name, har_layer in har_map.items():
        shape = cfg['inputs'][inp_name]
        data[har_layer] = np.random.randn(n, shape[2], shape[3], shape[1]).astype(np.float32)
    return HailoCalibrationDataloader(data)
 
# =====================================================================
# HAUPTLOGIK: Translate → Optimize → Compile pro Sub-Modell
# =====================================================================
def process_model(model_key, force_translate=False):
    """Verarbeitet ein einzelnes Sub-Modell komplett."""
    cfg = MODELS[model_key]
    name = cfg['name']
    
    print("\n" + "=" * 60)
    print(f"🚀 Verarbeite: {model_key.upper()} ({name})")
    print("=" * 60)
    
    # ── 1. Translate ONNX → HAR ──────────────────────────────────────
    if not os.path.exists(cfg['har']) or force_translate:
        print(f"\n🔄 Übersetze ONNX → HAR...")
        runner = ClientRunner(hw_arch='hailo8')
        runner.translate_onnx_model(
            cfg['onnx'],
            cfg['name'],
            start_node_names=list(cfg['inputs'].keys()),
            end_node_names=cfg['outputs'],
            net_input_shapes=cfg['inputs'],
        )
        runner.save_har(cfg['har'])
        print(f"   ✅ HAR gespeichert: {cfg['har']}")
    else:
        print(f"   ⏭️  HAR vorhanden: {cfg['har']}")
    
    # ── 2. Profiling ─────────────────────────────────────────────────
    profile_model(cfg)
    
    # ── 3. Model-Script schreiben ────────────────────────────────────
    write_model_script(cfg)
    
    # 4. Dataloader statt festes Dict
    dataloader = generate_calib_dataloader(model_key, cfg)
    
    print(f"\n🚀 Starte Quantisierung ({model_key})...")
    runner = ClientRunner(har=cfg['har'], hw_arch='hailo8')
    runner.load_model_script(cfg['alls'])
    
    # Der entscheidende Part: optimize() nimmt den Dataloader-Iterator
    runner.optimize(dataloader)
    
    # FP32 Referenz
    test_feed = {k: v[0:1] for k, v in calib_data.items()}
    res_native = None
    try:
        print("🧪 FP32-Referenz...")
        with runner.infer_context(InferenceContext.SDK_NATIVE) as ctx:
            res_native = runner.infer(ctx, test_feed)
        print("   ✅ Native Inferenz OK")
    except Exception:
        print("   ⚠️  Native Inferenz fehlgeschlagen:")
        traceback.print_exc()
    
    try:
        print(f"\n🚀 Starte Quantisierung ({model_key})...")
        runner.optimize(calib_data)
        
        # Quantisierte Referenz
        res_quant = None
        try:
            print("🎮 Quantisierte Inferenz...")
            with runner.infer_context(InferenceContext.SDK_QUANTIZED) as ctx:
                res_quant = runner.infer(ctx, test_feed)
            print("   ✅ Quantisierte Inferenz OK")
        except Exception:
            print("   ⚠️  Quantisierte Inferenz fehlgeschlagen:")
            traceback.print_exc()
        
        # SNR
        if res_native and res_quant:
            # SDK gibt manchmal list statt dict zurück — SNR nur mit dict möglich
            if isinstance(res_native, dict) and isinstance(res_quant, dict):
                print(f"\n   Native Keys:  {list(res_native.keys())}")
                print(f"   Quant Keys:   {list(res_quant.keys())}")
                
                print(f"\n{'Output':20} | {'SNR (dB)':>10} | Status")
                print("-" * 50)
                for node in cfg['outputs']:
                    matching_native = [k for k in res_native if k == node or k.endswith('/' + node)]
                    matching_quant = [k for k in res_quant if k == node or k.endswith('/' + node)]
                    if matching_native and matching_quant:
                        ref = res_native[matching_native[0]].astype(np.float32)
                        tgt = res_quant[matching_quant[0]].astype(np.float32)
                        noise = np.var(ref - tgt)
                        signal = np.var(ref)
                        snr = 10 * np.log10(signal / noise) if noise > 1e-10 else 99.9
                        status = "✅" if snr > 30 else ("⚠️" if snr > 20 else "❌")
                        print(f"{node:20} | {snr:10.2f} | {status}")
                    else:
                        print(f"{node:20} | {'N/A':>10} | ⚠️  (no match)")
            else:
                print(f"\n   ⚠️  SNR-Vergleich übersprungen (SDK gab {type(res_native).__name__} zurück, nicht dict)")
        
        # Compile
        print(f"\n⚡ Kompiliere HEF ({model_key})...")
        hef_buf = runner.compile()
        with open(cfg['hef'], 'wb') as f:
            f.write(hef_buf)
        print(f"🎉 ERFOLG! HEF geschrieben: {cfg['hef']}")
        return True
        
    except Exception:
        print(f"\n💥 Fehler bei {model_key}:")
        traceback.print_exc()
        return False
 
 
# =====================================================================
# MAIN
# =====================================================================
if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ['backbone', 'geometry', 'detection']
    
    # Validierung
    for t in targets:
        if t not in MODELS:
            print(f"❌ Unbekanntes Modell: {t}")
            print(f"   Verfügbar: {list(MODELS.keys())}")
            sys.exit(1)
    
    results = {}
    
    # Reihenfolge ist wichtig! Backbone muss zuerst,
    # damit Geometry die Features für Kalibrierung bekommt
    order = ['backbone', 'geometry', 'detection', 'combined']
    for model_key in order:
        if model_key in targets:
            results[model_key] = process_model(model_key)
    
    # Zusammenfassung
    print("\n" + "=" * 60)
    print("📋 ZUSAMMENFASSUNG")
    print("=" * 60)
    for k, success in results.items():
        status = "✅ HEF erstellt" if success else "❌ Fehlgeschlagen"
        print(f"   {k:12} → {status}")
    
    if all(results.values()):
        print(f"\n🎉 Alle {len(results)} HEFs erfolgreich erstellt!")
        print("\nPipeline auf dem Pi 5:")
        print("   1. Backbone(left)  → f_s4, f_s8, f_s16, f_s32")
        print("   2. Backbone(right) → f_s4_r, f_s8_r")
        print("   3. Geometry(features + img) → disp, normals")
        print("   4. Detection(features + normals) → seg, yolo")
    elif any(results.values()):
        print("\n⚠️  Teilweise erfolgreich. Fehlgeschlagene Modelle einzeln debuggen:")
        for k, s in results.items():
            if not s:
                print(f"   python quantizer_split.py {k}")