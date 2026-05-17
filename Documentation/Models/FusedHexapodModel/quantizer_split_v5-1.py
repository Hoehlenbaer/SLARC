"""
quantizer_split_v5.py — Quantisiert und kompiliert 3 Split-ONNX-Modelle
zu jeweils einem HEF für den Hailo-8.

HEF A: Backbone    (input_layer1 [1,1,480,640] → f_s4, f_s8, f_s16, f_s32)
HEF B: Geometry    (f_s4_l/r, f_s8_l/r → disp_s4, normals_s4, disp_s8)
HEF C: Detection   (f_s4_l, f_s8_l, f_s16_l, f_s32_l, normals_s4 → seg, yolo_*)

Channel-Dimensionen (stereo_focused Alignment):
    s4 = 64, s8 = 128, s16 = 128, s32 = 256

Usage:
    python quantizer_split_v5.py              # Alle 3 HEFs
    python quantizer_split_v5.py backbone     # Nur Backbone
    python quantizer_split_v5.py geometry     # Nur Geometry
    python quantizer_split_v5.py detection    # Nur Detection
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
N_CALIB  = 1024

# ── Optimierungslevel ─────────────────────────────────────────────────
# 0 = schneller Compile, kein Tuning  (erster Lauf / Smoke-Test)
# 2 = volle Optimierung               (finaler HEF für den Pi)
OPTIMIZATION_LEVEL = 0

# Normalisierung (identisch zum Training: mean=0.449, std=0.226, in [0,255])
NORM_MEAN = 0.449 * 255.0   # = 114.495
NORM_STD  = 0.226 * 255.0   # =  57.630

# Channel-Dimensionen nach stereo_focused ChannelAligner
CH_S4  = 64
CH_S8  = 128
CH_S16 = 128
CH_S32 = 256

# ── Modell-Definitionen ──────────────────────────────────────────────
MODELS = {
    'backbone': {
        'onnx':   f'{ONNX_DIR}/hexapod_v5_backbone_simplified.onnx',
        'har':    f'{ONNX_DIR}/hexapod_v5_backbone.har',
        'hef':    f'{ONNX_DIR}/hexapod_v5_backbone.hef',
        'alls':   f'{ONNX_DIR}/backbone_v5_script.alls',
        'name':   'hexapod_v5_backbone_simplified',
        'inputs': {
            'input_layer1': [1, 1, 480, 640],
        },
        'outputs':     ['f_s4', 'f_s8', 'f_s16', 'f_s32'],
        'needs_norm':  True,             # Normalisierung auf NPU
        'norm_inputs': ['input_layer1'], # Rohbild-Input
    },
    'geometry': {
        'onnx':   f'{ONNX_DIR}/hexapod_v5_geometry_simplified.onnx',
        'har':    f'{ONNX_DIR}/hexapod_v5_geometry.har',
        'hef':    f'{ONNX_DIR}/hexapod_v5_geometry.hef',
        'alls':   f'{ONNX_DIR}/geometry_v5_script.alls',
        'name':   'hexapod_v5_geometry_simplified',
        'inputs': {
            'f_s4_l': [1, CH_S4,  120, 160],
            'f_s8_l': [1, CH_S8,   60,  80],
            'f_s4_r': [1, CH_S4,  120, 160],
            'f_s8_r': [1, CH_S8,   60,  80],
        },
        'outputs':     ['disp_s4', 'normals_s4', 'disp_s8'],
        'needs_norm':  False,  # Keine Rohbilder mehr (img_l entfernt in V5)
        'norm_inputs': [],
    },
    'detection': {
        'onnx':   f'{ONNX_DIR}/hexapod_v5_detection_simplified.onnx',
        'har':    f'{ONNX_DIR}/hexapod_v5_detection.har',
        'hef':    f'{ONNX_DIR}/hexapod_v5_detection.hef',
        'alls':   f'{ONNX_DIR}/detection_v5_script.alls',
        'name':   'hexapod_v5_detection_simplified',
        'inputs': {
            'f_s4_l':     [1, CH_S4,  120, 160],
            'f_s8_l':     [1, CH_S8,   60,  80],
            'f_s16_l':    [1, CH_S16,  30,  40],
            'f_s32_l':    [1, CH_S32,  15,  20],
            'normals_s4': [1, 4,       120, 160],   #V5.1 deployment -> channel padding to 4
        },
        'outputs':     ['seg', 'yolo_s8', 'yolo_s16', 'yolo_s32'],
        'needs_norm':  False,  # Nur Zwischen-Features, keine Rohbilder
        'norm_inputs': [],
    },
}


# =====================================================================
# HILFSFUNKTIONEN
# =====================================================================

def profile_model(model_cfg):
    """Profiling für ein einzelnes Sub-Modell."""
    har_path = model_cfg['har']
    name     = model_cfg['name']
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
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        if isinstance(report, dict) and 'stats' in report:
            md = report['stats'].get('model_details', {})
            print(f"   Weights: {md.get('weights', 0)/1e6:.1f}M")
            print(f"   OPs:     {md.get('total_ops_per_frame', 0)/1e9:.2f} GOPS")
            print(f"   Inputs:  {md.get('input_shapes', '?')}")
            print(f"   Outputs: {md.get('output_shapes', '?')}")
        print(f"   ✅ Report: {report_path}")
    except Exception:
        print("   ⚠️  Profiling fehlgeschlagen (nicht kritisch):")
        traceback.print_exc()


def write_model_script(model_cfg):
    """
    Schreibt das .alls Model-Script.
    OPTIMIZATION_LEVEL wird aus der globalen Konstante gezogen —
    für den ersten Lauf auf 0 lassen, für den finalen Compile auf 2 setzen.
    """
    alls_path = model_cfg['alls']
    name      = model_cfg['name']

    runner = ClientRunner(har=model_cfg['har'], hw_arch='hailo8')
    hn         = runner.get_hn_dict()
    all_layers = list(hn.get('layers', {}).keys())

    avgpool_layers = sorted([
        lname for lname, data in hn['layers'].items()
        if isinstance(data.get('type', ''), str)
        and 'pool' in data['type'].lower()
        and 'avg'  in data['type'].lower()
    ])

    pools_60x80 = [n for n in avgpool_layers
                   if hn['layers'][n]['params']['kernel_shape'][1] == 60]
    pools_30x40 = [n for n in avgpool_layers
                   if hn['layers'][n]['params']['kernel_shape'][1] == 30]
    pools_15x20 = [n for n in avgpool_layers
                   if hn['layers'][n]['params']['kernel_shape'][1] == 15]

    if avgpool_layers:
        print(f"   AvgPool 60×80: {len(pools_60x80)} Layer")
        print(f"   AvgPool 30×40: {len(pools_30x40)} Layer")
        print(f"   AvgPool 15×20: {len(pools_15x20)} Layer")

    with open(alls_path, 'w', encoding='utf-8') as f:
        f.write(f"model_optimization_flavor("
                f"optimization_level={OPTIMIZATION_LEVEL}, "
                f"compression_level=0, batch_size=4)\n")
        f.write("performance_param(compiler_optimization_level=max)\n")

        # Normalisierung (nur für Backbone — Input ist ein Rohbild)
        if model_cfg['needs_norm']:
            expected_inputs = list(model_cfg['inputs'].keys())
            har_inputs = sorted([l for l in all_layers if 'input_layer' in l.lower()])
            for norm_inp in model_cfg['norm_inputs']:
                if norm_inp in expected_inputs:
                    idx = expected_inputs.index(norm_inp)
                    if idx < len(har_inputs):
                        har_layer = har_inputs[idx]
                        f.write(f"norm_{idx} = normalization("
                                f"[{NORM_MEAN:.3f}], [{NORM_STD:.3f}], {har_layer})\n")
                    else:
                        print(f"   ⚠️  Kein HAR-Input für Normalisierung von '{norm_inp}'!")

        # AvgPool-Optimierung
        if pools_60x80:
            f.write(f"pre_quantization_optimization(global_avgpool_reduction, "
                    f"layers=[{','.join(pools_60x80)}], division_factors=[6,8])\n")
        if pools_30x40:
            f.write(f"pre_quantization_optimization(global_avgpool_reduction, "
                    f"layers=[{','.join(pools_30x40)}], division_factors=[6,8])\n")
        if pools_15x20:
            f.write(f"pre_quantization_optimization(global_avgpool_reduction, "
                    f"layers=[{','.join(pools_15x20)}], division_factors=[3,4])\n")

    print(f"   📝 Model-Script ({name}):  optimization_level={OPTIMIZATION_LEVEL}")
    print(f"      Pfad: {alls_path}")
    return alls_path


def _har_input_map(model_cfg):
    """
    Gibt ein Dict {onnx_input_name → har_layer_name} zurück.
    Der DFC benennt ONNX-Inputs zu input_layer1/2/... um — wir matchen
    per Reihenfolge (index in expected_inputs).
    """
    runner     = ClientRunner(har=model_cfg['har'], hw_arch='hailo8')
    hn         = runner.get_hn_dict()
    all_layers = list(hn.get('layers', {}).keys())
    har_inputs = sorted([l for l in all_layers if 'input_layer' in l.lower()])

    expected   = list(model_cfg['inputs'].keys())
    mapping    = {}
    for i, inp_name in enumerate(expected):
        if i < len(har_inputs):
            mapping[inp_name] = har_inputs[i]
        else:
            print(f"   ⚠️  Kein HAR-Input für '{inp_name}' (Index {i})!")
    return mapping


def _to_nhwc(arr):
    """NCHW → NHWC, float32."""
    return arr.transpose(0, 2, 3, 1).astype(np.float32)


def _fill_random(calib_data, har_input_map, model_cfg, n, calib_l):
    """Füllt calib_data mit passend skalierten Random-NHWC-Tensoren."""
    for inp_name, har_layer in har_input_map.items():
        shape = model_cfg['inputs'][inp_name]   # [1, C, H, W]
        nhwc  = (n, shape[2], shape[3], shape[1])
        if 'input_layer' in inp_name or 'img' in inp_name:
            calib_data[har_layer] = _to_nhwc(calib_l[:n])
        elif 'normals' in inp_name:
            calib_data[har_layer] = np.random.randn(*nhwc).astype(np.float32) * 0.5
        else:
            calib_data[har_layer] = np.random.randn(*nhwc).astype(np.float32) * 0.5


def generate_calib_data(model_key, model_cfg):
    """
    Erzeugt Kalibrierungsdaten (NHWC, float32) für ein Sub-Modell.

    Backbone:  Rohbilder aus calib_left.npy
    Geometry:  Backbone-Outputs (echte Features via HAR-Inferenz)
    Detection: Backbone-Outputs + Random-Normals
    """
    print(f"\n📊 Erzeuge Kalibrierungsdaten für {model_key}...")

    calib_l = np.load('calib_left.npy')   # [N, 1, H, W], Wertebereich 0–255
    calib_r = np.load('calib_right.npy')
    n = min(N_CALIB, calib_l.shape[0], calib_r.shape[0])

    har_map = _har_input_map(model_cfg)
    print(f"   HAR-Input-Mapping: {har_map}")

    calib_data = {}

    # ── Backbone ──────────────────────────────────────────────────────
    if model_key == 'backbone':
        har_layer = har_map.get('input_layer1')
        if har_layer:
            calib_data[har_layer] = _to_nhwc(calib_l[:n])
        else:
            print("   ⚠️  'input_layer1' nicht im HAR-Input-Mapping!")

    # ── Geometry ──────────────────────────────────────────────────────
    elif model_key == 'geometry':
        bb_har  = MODELS['backbone']['har']
        bb_alls = MODELS['backbone']['alls']

        if os.path.exists(bb_har) and os.path.exists(bb_alls):
            print("   🔄 Generiere Features via Backbone-HAR (links + rechts)...")
            bb_runner = ClientRunner(har=bb_har, hw_arch='hailo8')
            bb_runner.load_model_script(bb_alls)
            bb_hn     = bb_runner.get_hn_dict()
            bb_all    = list(bb_hn.get('layers', {}).keys())
            bb_input  = sorted([l for l in bb_all if 'input_layer' in l.lower()])[0]

            def run_backbone(images_nchw, batch_size=256):
                outputs = {k: [] for k in ['f_s4', 'f_s8']}
                with bb_runner.infer_context(InferenceContext.SDK_NATIVE) as ctx:
                    for i in range(0, len(images_nchw), batch_size):
                        batch = _to_nhwc(images_nchw[i:i+batch_size])
                        res   = bb_runner.infer(ctx, {bb_input: batch})
                        for k in outputs:
                            matching = [rk for rk in res if k in rk]
                            if matching:
                                outputs[k].append(res[matching[0]])
                return {k: np.concatenate(v, axis=0) for k, v in outputs.items() if v}

            try:
                print("       → Backbone(left)...")
                feat_l = run_backbone(calib_l[:n])
                print("       → Backbone(right)...")
                feat_r = run_backbone(calib_r[:n])
                print(f"   ✅ {n} Feature-Paare (L+R) generiert")

                # Erwartete NHWC-Shapes als Fallback
                fallback_s4 = (n, 120, 160, CH_S4)
                fallback_s8 = (n,  60,  80, CH_S8)

                for inp_name, har_layer in har_map.items():
                    if inp_name == 'f_s4_l':
                        calib_data[har_layer] = feat_l.get('f_s4',
                            np.random.randn(*fallback_s4).astype(np.float32) * 0.5)
                    elif inp_name == 'f_s8_l':
                        calib_data[har_layer] = feat_l.get('f_s8',
                            np.random.randn(*fallback_s8).astype(np.float32) * 0.5)
                    elif inp_name == 'f_s4_r':
                        calib_data[har_layer] = feat_r.get('f_s4',
                            np.random.randn(*fallback_s4).astype(np.float32) * 0.5)
                    elif inp_name == 'f_s8_r':
                        calib_data[har_layer] = feat_r.get('f_s8',
                            np.random.randn(*fallback_s8).astype(np.float32) * 0.5)

            except Exception as e:
                print(f"   ⚠️  Backbone-Inferenz fehlgeschlagen: {e}")
                print("       → Verwende Random-Features (Kalibrierung ggf. suboptimal)")
                _fill_random(calib_data, har_map, model_cfg, n, calib_l)
        else:
            print("   ⚠️  Backbone-HAR / .alls nicht gefunden → Random-Features")
            _fill_random(calib_data, har_map, model_cfg, n, calib_l)

    # ── Detection ─────────────────────────────────────────────────────
    elif model_key == 'detection':
        bb_har  = MODELS['backbone']['har']
        bb_alls = MODELS['backbone']['alls']
        geo_har  = MODELS['geometry']['har']
        geo_alls = MODELS['geometry']['alls']

        if os.path.exists(bb_har) and os.path.exists(bb_alls):
            print("   🔄 Generiere Backbone-Features für Detection...")
            bb_runner = ClientRunner(har=bb_har, hw_arch='hailo8')
            bb_runner.load_model_script(bb_alls)
            bb_hn     = bb_runner.get_hn_dict()
            bb_all    = list(bb_hn.get('layers', {}).keys())
            bb_input  = sorted([l for l in bb_all if 'input_layer' in l.lower()])[0]

            shape_to_key = {
                (120, 160): 'f_s4',
                (60, 80):   'f_s8',
                (30, 40):   'f_s16',
                (15, 20):   'f_s32',
            }

            try:
                batch_size = 256
                # --- Backbone-Inferenz (Links) ---
                all_bb_results = []
                with bb_runner.infer_context(InferenceContext.SDK_NATIVE) as ctx:
                    for i in range(0, n, batch_size):
                        batch = _to_nhwc(calib_l[i:i+batch_size])
                        res = bb_runner.infer(ctx, {bb_input: batch})
                        if isinstance(res, list):
                            res = {f'output_{j}': r for j, r in enumerate(res)}
                        all_bb_results.append(res)
                
                feat_l = {}
                first_res = all_bb_results[0]
                for res_key, res_val in first_res.items():
                    h, w = res_val.shape[1], res_val.shape[2]
                    feat_key = shape_to_key.get((h, w))
                    if feat_key:
                        feat_l[feat_key] = np.concatenate([r[res_key] for r in all_bb_results], axis=0)
                        print(f"         {feat_key}: {feat_l[feat_key].shape}")

                # --- Backbone-Inferenz (Rechts, für Geometry) ---
                print("       → Backbone(right) für Geometry-Normals...")
                all_bb_r_results = []
                with bb_runner.infer_context(InferenceContext.SDK_NATIVE) as ctx:
                    for i in range(0, n, batch_size):
                        batch = _to_nhwc(calib_r[i:i+batch_size])
                        res = bb_runner.infer(ctx, {bb_input: batch})
                        if isinstance(res, list):
                            res = {f'output_{j}': r for j, r in enumerate(res)}
                        all_bb_r_results.append(res)
                
                feat_r = {}
                first_res = all_bb_r_results[0]
                for res_key, res_val in first_res.items():
                    h, w = res_val.shape[1], res_val.shape[2]
                    feat_key = shape_to_key.get((h, w))
                    if feat_key:
                        feat_r[feat_key] = np.concatenate([r[res_key] for r in all_bb_r_results], axis=0)

                # --- Geometry-Inferenz → echte Normals ---
                normals_data = None
                if os.path.exists(geo_har) and os.path.exists(geo_alls):
                    print("       → Geometry-Inferenz für echte Normals...")
                    geo_runner = ClientRunner(har=geo_har, hw_arch='hailo8')
                    geo_runner.load_model_script(geo_alls)
                    geo_hn = geo_runner.get_hn_dict()
                    geo_all = list(geo_hn.get('layers', {}).keys())
                    geo_inputs = sorted([l for l in geo_all if 'input_layer' in l.lower()])
                    
                    # Geometry Input-Mapping per Shape
                    geo_input_shapes = {}
                    for gl in geo_inputs:
                        layer_info = geo_hn['layers'][gl]
                        shapes = layer_info.get('output_shapes', layer_info.get('input_shapes', []))
                        if shapes:
                            geo_input_shapes[gl] = shapes[0]
                    
                    all_normals = []
                    with geo_runner.infer_context(InferenceContext.SDK_NATIVE) as ctx:
                        for i in range(0, n, batch_size):
                            bs = min(batch_size, n - i)
                            # Geo-Feed zusammenbauen (f_s4_l, f_s8_l, f_s4_r, f_s8_r)
                            geo_feed = {}
                            feed_data = {
                                'f_s4': (feat_l['f_s4'][i:i+bs], feat_r['f_s4'][i:i+bs]),
                                'f_s8': (feat_l['f_s8'][i:i+bs], feat_r['f_s8'][i:i+bs]),
                            }
                            # Zuordnung per Shape
                            assigned = set()
                            for gl in geo_inputs:
                                info = geo_hn['layers'][gl]
                                shapes = info.get('input_shapes', [])
                                if shapes:
                                    h, w, c = shapes[0][1], shapes[0][2], shapes[0][3]
                                    fk = shape_to_key.get((h, w))
                                    if fk and fk in feed_data:
                                        # Erste Zuweisung = links, zweite = rechts
                                        idx = 0 if gl not in assigned else 1
                                        if gl + '_used' not in assigned:
                                            geo_feed[gl] = feed_data[fk][0]
                                            assigned.add(gl + '_used')
                                        else:
                                            geo_feed[gl] = feed_data[fk][1]
                            
                            res = geo_runner.infer(ctx, geo_feed)
                            if isinstance(res, list):
                                res = {f'output_{j}': r for j, r in enumerate(res)}
                            # Normals finden (3 Channels, 120x160)
                            for rk, rv in res.items():
                                if rv.shape[-1] == 3 and rv.shape[1] == 120:
                                    all_normals.append(rv)
                                    break
                    
                    if all_normals:
                        normals_data = np.concatenate(all_normals, axis=0)
                        print(f"         normals: {normals_data.shape}, range=[{normals_data.min():.2f}, {normals_data.max():.2f}]")
                    else:
                        print("   ⚠️ Keine Normals aus Geometry extrahiert")

                # --- Detection Feed zusammenbauen ---
                for inp_name, har_layer in har_map.items():
                    if inp_name == 'normals_s4':
                        if normals_data is not None:
                            calib_data[har_layer] = normals_data[:n]
                        else:
                            # Fallback: L2-normalisierte Random-Vektoren (nicht randn*0.5!)
                            rand_n = np.random.randn(n, 120, 160, 3).astype(np.float32)
                            norm = np.sqrt((rand_n**2).sum(axis=-1, keepdims=True)) + 1e-6
                            calib_data[har_layer] = (rand_n / norm).astype(np.float32)
                    else:
                        bb_key = inp_name.replace('_l', '')
                        shape = model_cfg['inputs'][inp_name]
                        fallback = (n, shape[2], shape[3], shape[1])
                        calib_data[har_layer] = feat_l.get(
                            bb_key, np.random.randn(*fallback).astype(np.float32) * 0.5)

                print(f"   ✅ {n} Feature-Sets + {'echte' if normals_data is not None else 'Random'}-Normals generiert")

            except Exception as e:
                print(f"   ⚠️  Backbone-Inferenz fehlgeschlagen: {e}")
                _fill_random(calib_data, har_map, model_cfg, n, calib_l)
        else:
            print("   ℹ️  Backbone-HAR nicht gefunden → Random-Features")
            _fill_random(calib_data, har_map, model_cfg, n, calib_l)

    # Shapes loggen
    for k, v in calib_data.items():
        print(f"   {k}: shape={v.shape}, range=[{v.min():.2f}, {v.max():.2f}]")

    return calib_data


# =====================================================================
# HAUPTLOGIK: Translate → Profile → Script → Calib → Optimize → Compile
# =====================================================================

def process_model(model_key, force_translate=False):
    """Verarbeitet ein einzelnes Sub-Modell komplett."""
    cfg  = MODELS[model_key]
    name = cfg['name']

    print("\n" + "=" * 60)
    print(f"🚀 Verarbeite: {model_key.upper()} ({name})")
    print(f"   optimization_level = {OPTIMIZATION_LEVEL}")
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
    print(f"\n🔍 Lade HAR + Model-Script...")
    runner = ClientRunner(har=cfg['har'], hw_arch='hailo8')
    runner.load_model_script(cfg['alls'])

    # FP32-Referenz (einzelnes Sample)
    test_feed = {k: v[0:1] for k, v in calib_data.items()}

    # SDK_NATIVE kennt das Model-Script nicht — normalization() aus dem .alls
    # ist dort nicht aktiv. Damit native und quantized auf demselben Eingangs-
    # bereich arbeiten, normalisieren wir den Rohbild-Input manuell vor.
    # Geometry/Detection haben needs_norm=False und brauchen das nicht.
    if cfg["needs_norm"]:
        har_map = _har_input_map(cfg)
        test_feed_native = {}
        for inp_name, har_layer in har_map.items():
            if inp_name in cfg["norm_inputs"] and har_layer in test_feed:
                raw = test_feed[har_layer].astype(np.float32)
                test_feed_native[har_layer] = (raw - NORM_MEAN) / NORM_STD
            else:
                test_feed_native[har_layer] = test_feed.get(har_layer)
    else:
        test_feed_native = test_feed

    try:
        print(f"\n🚀 Starte Quantisierung ({model_key}, level={OPTIMIZATION_LEVEL})...")
        runner.optimize(calib_data)

        print(f"\n⚡ Kompiliere HEF ({model_key})...")
        hef_buf = runner.compile()
        with open(cfg['hef'], 'wb') as f:
            f.write(hef_buf)
        size_kb = os.path.getsize(cfg['hef']) / 1024
        print(f"🎉 ERFOLG! HEF geschrieben: {cfg['hef']}  ({size_kb:.0f} KB)")
        return True

    except Exception:
        print(f"\n💥 Fehler bei {model_key}:")
        traceback.print_exc()
        return False
# =====================================================================
# MAIN
# =====================================================================
if __name__ == '__main__':
    targets = sys.argv[1:] if len(sys.argv) > 1 else ['backbone', 'geometry', 'detection']

    for t in targets:
        if t not in MODELS:
            print(f"❌ Unbekanntes Modell: {t}")
            print(f"   Verfügbar: {list(MODELS.keys())}")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  V5.0 Quantizer  —  optimization_level={OPTIMIZATION_LEVEL}")
    print(f"  Ziel-HEFs: {targets}")
    print(f"{'='*60}")

    results = {}

    # Reihenfolge einhalten: Backbone zuerst (liefert Features für Geometry/Detection)
    for model_key in ['backbone', 'geometry', 'detection']:
        if model_key in targets:
            results[model_key] = process_model(model_key)

    # Zusammenfassung
    print("\n" + "=" * 60)
    print(f"  ZUSAMMENFASSUNG  (optimization_level={OPTIMIZATION_LEVEL})")
    print("=" * 60)
    for k, success in results.items():
        status = "✅ HEF erstellt" if success else "❌ Fehlgeschlagen"
        hef    = MODELS[k]['hef']
        size   = f"  ({os.path.getsize(hef)/1024:.0f} KB)" if success and os.path.exists(hef) else ""
        print(f"   {k:12} → {status}{size}")

    if all(results.values()):
        print(f"\n🎉 Alle {len(results)} HEFs erfolgreich erstellt!")
        print("\nPipeline auf dem Pi 5:")
        print("   1. Backbone(left)  → f_s4, f_s8, f_s16, f_s32")
        print("   2. Backbone(right) → f_s4_r, f_s8_r  (gleicher HEF, anderer Input)")
        print("   3. Geometry(f_s4_l/r, f_s8_l/r) → disp_s4, normals_s4, disp_s8")
        print("   4. Detection(f_s4_l, f_s8_l, f_s16_l, f_s32_l, normals_s4) → seg, yolo_*")
    elif any(results.values()):
        print("\n⚠️  Teilweise erfolgreich. Einzeln debuggen:")
        for k, s in results.items():
            if not s:
                print(f"   python quantizer_split_v5.py {k}")
