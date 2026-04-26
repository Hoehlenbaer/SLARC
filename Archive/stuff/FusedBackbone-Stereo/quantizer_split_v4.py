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

# Normalisierung (identisch zum Training)
NORM_MEAN = 0.449 * 255.0   # = 114.495
NORM_STD  = 0.226 * 255.0   # =  57.630

# ── Modell-Definitionen ──────────────────────────────────────────────
MODELS = {
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
                'f_s4_l': [1, 32, 120, 160], 
                'f_s8_l': [1, 48, 60, 80],   # 🚨 Hier auf 48 geändert!
                'f_s4_r': [1, 32, 120, 160], 
                'f_s8_r': [1, 48, 60, 80]
                # img_l wurde glorreich in den Ruhestand verabschiedet!
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
                'f_s4_l': [1, 32, 120, 160],
                'f_s8_l': [1, 48, 60, 80],
                'f_s16_l': [1, 136, 30, 40],
                'f_s32_l': [1, 448, 15, 20],
                'normals_s4': [1, 3, 120, 160]
            },
        'outputs': ['seg', 'yolo_s8', 'yolo_s16', 'yolo_s32'],
        'needs_norm': False,   # Bekommt nur Zwischen-Features, keine Rohbilder
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


def generate_calib_data(model_key, model_cfg):
    """
    Erzeugt Kalibrierungsdaten für ein Sub-Modell.
    
    Backbone:  Rohbilder (calib_left.npy)
    Geometry:  Backbone-Outputs + Rohbilder → braucht Backbone-Inferenz
    Detection: Backbone-Outputs + Normals → braucht Backbone + Geometry Inferenz
    
    Für den initialen Compile verwenden wir Random-Daten für die Feature-Inputs
    (Range passend zu typischen Backbone-Aktivierungen). Die exakte Kalibrierung
    kann nachträglich mit echten Pipeline-Daten verfeinert werden.
    """
    print(f"\n📊 Erzeuge Kalibrierungsdaten für {model_key}...")
    
    calib_l = np.load('calib_left.npy')  # [N, 1, H, W], 0-255
    calib_r = np.load('calib_right.npy')
    n = min(N_CALIB, calib_l.shape[0], calib_r.shape[0])
    
    def to_nhwc(arr):
        return arr.transpose(0, 2, 3, 1).astype(np.float32)
    
    # HAR-Layer-Namen ermitteln
    # WICHTIG: Der DFC benennt ONNX-Inputs IMMER um zu input_layer1, input_layer2, etc.
    # Wir matchen daher über die Input-Shapes, nicht über die Namen!
    runner = ClientRunner(har=model_cfg['har'], hw_arch='hailo8')
    hn = runner.get_hn_dict()
    all_layers = list(hn.get("layers", {}).keys())
    
    # Alle input_layer* im HAR finden und deren Shapes auslesen
    har_inputs = sorted([l for l in all_layers if 'input_layer' in l.lower()])
    print(f"   HAR-Input-Layer: {har_inputs}")
    
    # Shape-basiertes Mapping: ONNX-Input-Name → HAR-Layer-Name
    # Die Reihenfolge der input_layerN im HAR entspricht der Reihenfolge
    # der start_node_names beim translate_onnx_model Aufruf,
    # die wiederum der Reihenfolge in model_cfg['inputs'] entspricht.
    expected_inputs = list(model_cfg['inputs'].keys())
    har_input_map = {}
    for i, inp_name in enumerate(expected_inputs):
        if i < len(har_inputs):
            har_input_map[inp_name] = har_inputs[i]
        else:
            print(f"   ⚠️  Kein HAR-Input für '{inp_name}' (Index {i})!")
    
    print(f"   Input-Mapping: {har_input_map}")
    
    calib_data = {}
    
    if model_key == 'backbone':
        har_layer = har_input_map.get('gray_img')
        if har_layer:
            calib_data[har_layer] = to_nhwc(calib_l[:n])
        
    elif model_key == 'geometry':
        # Feature-Maps: Backbone auf die Kalibrierungsdaten laufen lassen
        bb_har = MODELS['backbone']['har']
        if os.path.exists(bb_har):
            print("   🔄 Generiere Features via Backbone-HAR...")
            print("       Links UND rechts werden durch den Backbone geschickt.")
            bb_runner = ClientRunner(har=bb_har, hw_arch='hailo8')
            bb_hn = bb_runner.get_hn_dict()
            bb_all = list(bb_hn.get("layers", {}).keys())
            bb_input = sorted([l for l in bb_all if 'input_layer' in l.lower()])[0]
            
            bb_runner.load_model_script(MODELS['backbone']['alls'])
            
            batch_size = 256
            
            def run_backbone(images_nchw):
                """Backbone-Inferenz auf einem Bilderstapel."""
                outputs = {k: [] for k in ['f_s4', 'f_s8', 'f_s16', 'f_s32']}
                with bb_runner.infer_context(InferenceContext.SDK_NATIVE) as ctx:
                    for i in range(0, len(images_nchw), batch_size):
                        batch = to_nhwc(images_nchw[i:i+batch_size])
                        res = bb_runner.infer(ctx, {bb_input: batch})
                        for k in outputs:
                            matching = [rk for rk in res if k in rk]
                            if matching:
                                outputs[k].append(res[matching[0]])
                return {k: np.concatenate(v, axis=0) for k, v in outputs.items() if v}
            
            try:
                # Linke Bilder → alle 4 Scales
                print("       → Backbone(left)...")
                features_l = run_backbone(calib_l[:n])
                
                # Rechte Bilder → nur s4, s8 (für Stereo Matching)
                print("       → Backbone(right)...")
                features_r_full = run_backbone(calib_r[:n])
                features_r = {k: features_r_full[k] for k in ['f_s4', 'f_s8'] if k in features_r_full}
                
                print(f"   ✅ {n} Feature-Paare (L+R) generiert")
                
                # Zuordnung per Name-Matching
                for inp_name, har_layer in har_input_map.items():
                    if 'img' in inp_name:
                        calib_data[har_layer] = to_nhwc(calib_l[:n])
                    elif inp_name == 'f_s4_r':
                        calib_data[har_layer] = features_r.get('f_s4',
                            np.random.randn(n, 120, 160, 24).astype(np.float32) * 0.5)
                    elif inp_name == 'f_s8_r':
                        calib_data[har_layer] = features_r.get('f_s8',
                            np.random.randn(n, 60, 80, 40).astype(np.float32) * 0.5)
                    elif inp_name == 'f_s4_l':
                        calib_data[har_layer] = features_l.get('f_s4',
                            np.random.randn(n, 120, 160, 24).astype(np.float32) * 0.5)
                    elif inp_name == 'f_s8_l':
                        calib_data[har_layer] = features_l.get('f_s8',
                            np.random.randn(n, 60, 80, 40).astype(np.float32) * 0.5)
                        
            except Exception as e:
                print(f"   ⚠️  Backbone-Inferenz fehlgeschlagen: {e}")
                print("   → Verwende Random-Features (Kalibrierung ggf. suboptimal)")
                _fill_random(calib_data, har_input_map, model_cfg, n, calib_l)
        else:
            print("   ⚠️  Backbone-HAR nicht gefunden → Random-Features")
            _fill_random(calib_data, har_input_map, model_cfg, n, calib_l)
            
    elif model_key == 'detection':
        # Detection: Backbone-Features + normals_s4
        # Am besten auch hier echte Features durchpropagieren
        bb_har = MODELS['backbone']['har']
        geo_har = MODELS['geometry']['har']
        
        if os.path.exists(bb_har):
            print("   🔄 Generiere Backbone-Features für Detection...")
            bb_runner = ClientRunner(har=bb_har, hw_arch='hailo8')
            bb_hn = bb_runner.get_hn_dict()
            bb_all = list(bb_hn.get("layers", {}).keys())
            bb_input = sorted([l for l in bb_all if 'input_layer' in l.lower()])[0]
            bb_runner.load_model_script(MODELS['backbone']['alls'])
            
            batch_size = 64
            outputs = {k: [] for k in ['f_s4', 'f_s8', 'f_s16', 'f_s32']}
            try:
                with bb_runner.infer_context(InferenceContext.SDK_NATIVE) as ctx:
                    for i in range(0, n, batch_size):
                        batch = to_nhwc(calib_l[i:i+batch_size])
                        res = bb_runner.infer(ctx, {bb_input: batch})
                        for k in outputs:
                            matching = [rk for rk in res if k in rk]
                            if matching:
                                outputs[k].append(res[matching[0]])
                features_l = {k: np.concatenate(v, axis=0) for k, v in outputs.items() if v}
                
                for inp_name, har_layer in har_input_map.items():
                    if inp_name == 'normals_s4':
                        # Normalen: Random N(0, 0.5), werden beim Stereo-Compile verfeinert
                        calib_data[har_layer] = np.random.randn(n, 120, 160, 3).astype(np.float32) * 0.5
                    else:
                        key = inp_name.replace('_l', '')
                        calib_data[har_layer] = features_l.get(key,
                            np.random.randn(n, *[model_cfg['inputs'][inp_name][i] 
                                for i in [2, 3, 1]]).astype(np.float32) * 0.5)
                
                print(f"   ✅ {n} Feature-Sets + Random-Normals generiert")
            except Exception as e:
                print(f"   ⚠️  Backbone-Inferenz fehlgeschlagen: {e}")
                _fill_random(calib_data, har_input_map, model_cfg, n, calib_l)
        else:
            print("   ℹ️  Verwende Random-Features für initialen Compile")
            _fill_random(calib_data, har_input_map, model_cfg, n, calib_l)
    
    # Shapes loggen
    for k, v in calib_data.items():
        print(f"   {k}: shape={v.shape}, range=[{v.min():.2f}, {v.max():.2f}]")
    
    return calib_data


def _fill_random(calib_data, har_input_map, model_cfg, n, calib_l):
    """Füllt mit passend skalierten Random-Daten."""
    for inp_name, har_layer in har_input_map.items():
        shape = model_cfg['inputs'][inp_name]
        # NHWC: [N, H, W, C]
        nhwc_shape = (n, shape[2], shape[3], shape[1])
        
        if 'img' in inp_name:
            calib_data[har_layer] = calib_l[:n].transpose(0, 2, 3, 1).astype(np.float32)
        elif 'normals' in inp_name:
            calib_data[har_layer] = np.random.randn(*nhwc_shape).astype(np.float32) * 0.5
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
    
    # ── 4. Kalibrierungsdaten ────────────────────────────────────────
    calib_data = generate_calib_data(model_key, cfg)
    
    # ── 5. Quantisierung + Compile ───────────────────────────────────
    print(f"\n🔍 Lade HAR und Model-Script...")
    runner = ClientRunner(har=cfg['har'], hw_arch='hailo8')
    runner.load_model_script(cfg['alls'])
    
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
    order = ['backbone', 'geometry', 'detection']
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
