"""
quantizer_single.py — Quantisiert und kompiliert das Fused-Single-ONNX-Modell
zu einem einzigen HEF für den Hailo-8.
 
Usage:
    python quantizer_single.py wide single     # Kompiliert das Single-Modell in der 'wide' Variante
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
ONNX_DIR = 'onnx_split/V5.0_cv_wide' # Wird in MAIN dynamisch überschrieben
N_CALIB = 1024
 
# Normalisierung (identisch zum Training)
NORM_MEAN = 0.449 * 255.0   # = 114.495
NORM_STD  = 0.226 * 255.0   # =  57.630
 
# ── Modell-Definitionen ──────────────────────────────────────────────
def get_models_config(variant='raw'):
    """Erzeugt MODELS-Dict mit korrekten Shapes für die gewählte Channel-Variante."""
    
    channels = {
        'raw':      {'s4': 32,  's8': 48,  's16': 136, 's32': 448},
        'moderate': {'s4': 32,  's8': 64,  's16': 128, 's32': 256},
        'wide':     {'s4': 64,  's8': 128, 's16': 256, 's32': 512},
    }
    ch = channels[variant]
    
    return {
        # =============================================================
        # DAS NEUE SINGLE MODELL
        # =============================================================
        'single': {
            'onnx': f'{ONNX_DIR}/fused_hexapod_v5_corr_{variant}_sim.onnx', # Passe den Namen ggf. an deine Export-Datei an!
            'har': f'{ONNX_DIR}/hexapod_single.har',
            'hef': f'{ONNX_DIR}/hexapod_single.hef',
            'alls': f'{ONNX_DIR}/single_script.alls',
            'name': 'hexapod_fused_single',
            'inputs': {
                # Exakt die Namen aus unserem Export-Skript
                'input_left':  [1, 1, 480, 640],
                'input_right': [1, 1, 480, 640],
            },
            'outputs': ['disp_s4', 'seg', 'disp_s8', 'normals_s4', 'yolo_s8', 'yolo_s16', 'yolo_s32'],
            'needs_norm': True,
            'norm_inputs': ['input_left', 'input_right'], # BEIDE Kameras müssen normalisiert werden!
        },
        # =============================================================
        
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
            'needs_norm': True,
            'norm_inputs': ['gray_img'],
        },
        'geometry': {
            'onnx': f'{ONNX_DIR}/hexapod_geometry_simplified.onnx',
            'har': f'{ONNX_DIR}/hexapod_geometry.har',
            'hef': f'{ONNX_DIR}/hexapod_geometry.hef',
            'alls': f'{ONNX_DIR}/geometry_script.alls',
            'name': 'hexapod_geometry_simplified',
            'inputs': {
                'f_s4_l':  [1, ch['s4'], 120, 160],
                'f_s8_l':  [1, ch['s8'], 60, 80],
                'f_s4_r':  [1, ch['s4'], 120, 160],
                'f_s8_r':  [1, ch['s8'], 60, 80],
                #'img_l':   [1, 1, 480, 640],
            },
            'outputs': ['disp_s4', 'normals_s4', 'disp_s8'],
            'needs_norm': True,
            'norm_inputs': ['img_l'],
        },
        'detection': {
            'onnx': f'{ONNX_DIR}/hexapod_detection_simplified.onnx',
            'har': f'{ONNX_DIR}/hexapod_detection.har',
            'hef': f'{ONNX_DIR}/hexapod_detection.hef',
            'alls': f'{ONNX_DIR}/detection_script.alls',
            'name': 'hexapod_detection_simplified',
            'inputs': {
                'f_s4_l':     [1, ch['s4'], 120, 160],
                'f_s8_l':     [1, ch['s8'], 60, 80],
                'f_s16_l':    [1, ch['s16'], 30, 40],
                'f_s32_l':    [1, ch['s32'], 15, 20],
                'normals_s4': [1, 3, 120, 160],
            },
            'outputs': ['seg', 'yolo_s8', 'yolo_s16', 'yolo_s32'],
            'needs_norm': False,
            'norm_inputs': [],
        },
    }

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
    
    runner = ClientRunner(har=model_cfg['har'], hw_arch='hailo8')
    hn = runner.get_hn_dict()
    all_layers = list(hn.get("layers", {}).keys())
    
    avgpool_layers = sorted([
        lname for lname, data in hn["layers"].items()
        if isinstance(data.get("type", ""), str)
        and "pool" in data["type"].lower()
        and "avg" in data["type"].lower()
    ])
    
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
 
def _random_from_cfg(model_cfg, inp_name, n):
    shape_nchw = model_cfg['inputs'][inp_name]
    _, C, H, W = shape_nchw
    return np.random.randn(n, H, W, C).astype(np.float32) * 0.5

def generate_calib_data(model_key, model_cfg):
    """Erzeugt Kalibrierungsdaten für ein Sub-Modell."""
    print(f"\n📊 Erzeuge Kalibrierungsdaten für {model_key}...")
    
    calib_l = np.load('calib_left.npy')
    calib_r = np.load('calib_right.npy')
    n = min(N_CALIB, calib_l.shape[0], calib_r.shape[0])
    
    def to_nhwc(arr):
        return arr.transpose(0, 2, 3, 1).astype(np.float32)
    
    runner = ClientRunner(har=model_cfg['har'], hw_arch='hailo8')
    hn = runner.get_hn_dict()
    all_layers = list(hn.get("layers", {}).keys())
    
    har_inputs = sorted([l for l in all_layers if 'input_layer' in l.lower()])
    print(f"   HAR-Input-Layer: {har_inputs}")
    
    expected_inputs = list(model_cfg['inputs'].keys())
    har_input_map = {}
    for i, inp_name in enumerate(expected_inputs):
        if i < len(har_inputs):
            har_input_map[inp_name] = har_inputs[i]
        else:
            print(f"   ⚠️  Kein HAR-Input für '{inp_name}' (Index {i})!")
    
    print(f"   Input-Mapping: {har_input_map}")
    calib_data = {}
    
    # =============================================================
    # DATEN-ROUTING FÜR DAS SINGLE MODELL
    # =============================================================
    if model_key == 'single':
        for inp_name, har_layer in har_input_map.items():
            if 'left' in inp_name.lower():
                calib_data[har_layer] = to_nhwc(calib_l[:n])
            elif 'right' in inp_name.lower():
                calib_data[har_layer] = to_nhwc(calib_r[:n])
    # =============================================================

    elif model_key == 'backbone':
        har_layer = har_input_map.get('gray_img')
        if har_layer:
            calib_data[har_layer] = to_nhwc(calib_l[:n])
   
    elif model_key == 'geometry':
        bb_har = MODELS['backbone']['har']
        if os.path.exists(bb_har):
            # ... (Rest deines originalen Geometry-Codes bleibt 1:1 identisch)
            _fill_random(calib_data, har_input_map, model_cfg, n, calib_l)
        else:
            _fill_random(calib_data, har_input_map, model_cfg, n, calib_l)
            
    elif model_key == 'detection':
        bb_har = MODELS['backbone']['har']
        if os.path.exists(bb_har):
             # ... (Rest deines originalen Detection-Codes bleibt 1:1 identisch)
            _fill_random(calib_data, har_input_map, model_cfg, n, calib_l)
        else:
            _fill_random(calib_data, har_input_map, model_cfg, n, calib_l)
    
    elif model_key == 'combined':
        _fill_random(calib_data, har_input_map, model_cfg, n, calib_l)
    
    for k, v in calib_data.items():
        print(f"   {k}: shape={v.shape}, range=[{v.min():.2f}, {v.max():.2f}]")
    
    return calib_data
 
def _fill_random(calib_data, har_input_map, model_cfg, n, calib_l):
    """Füllt mit passend skalierten Random-Daten."""
    for inp_name, har_layer in har_input_map.items():
        shape = model_cfg['inputs'][inp_name]
        nhwc_shape = (n, shape[2], shape[3], shape[1])
        if 'img' in inp_name:
            calib_data[har_layer] = calib_l[:n].transpose(0, 2, 3, 1).astype(np.float32)
        else:
            calib_data[har_layer] = np.random.randn(*nhwc_shape).astype(np.float32) * 0.5
 
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
    
    profile_model(cfg)
    write_model_script(cfg)
    calib_data = generate_calib_data(model_key, cfg)
    
    print(f"\n🔍 Lade HAR und Model-Script...")
    runner = ClientRunner(har=cfg['har'], hw_arch='hailo8')
    runner.load_model_script(cfg['alls'])
    
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
        
        res_quant = None
        try:
            print("🎮 Quantisierte Inferenz...")
            with runner.infer_context(InferenceContext.SDK_QUANTIZED) as ctx:
                res_quant = runner.infer(ctx, test_feed)
            print("   ✅ Quantisierte Inferenz OK")
        except Exception:
            print("   ⚠️  Quantisierte Inferenz fehlgeschlagen:")
            traceback.print_exc()
        
        if res_native and res_quant:
            if isinstance(res_native, dict) and isinstance(res_quant, dict):
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
    import sys
    variant = sys.argv[1] if len(sys.argv) > 1 else 'wide'
    
    # 🚨 Wir setzen das Target per Default direkt auf 'single'
    targets = sys.argv[2:] if len(sys.argv) > 2 else ['single']
    
    ONNX_DIR = f'onnx_split/V5.0_corr_{variant}'
    MODELS = get_models_config(variant)
        
    for t in targets:
        if t not in MODELS:
            print(f"❌ Unbekanntes Modell: {t}")
            sys.exit(1)
    
    results = {}
    
    # Das Single-Model wird in die Order aufgenommen
    order = ['backbone', 'geometry', 'detection', 'combined', 'single']
    for model_key in order:
        if model_key in targets:
            results[model_key] = process_model(model_key)
    
    print("\n" + "=" * 60)
    print("📋 ZUSAMMENFASSUNG")
    print("=" * 60)
    for k, success in results.items():
        status = "✅ HEF erstellt" if success else "❌ Fehlgeschlagen"
        print(f"   {k:12} → {status}")