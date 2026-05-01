"""
benchmark_hailo_streaming.py — Latenz-optimierter Benchmark für 3 HEFs

Simuliert den echten Roboter-Betrieb: Ein Frame nach dem anderen,
aber minimiert den Python-Overhead durch statisches Tensor-Routing.

Usage:
    python benchmark_hailo_streaming.py
"""

import numpy as np
import time
import argparse
from hailo_platform import (
    HEF, VDevice, HailoStreamInterface,
    ConfigureParams, InferVStreams, InputVStreamParams, OutputVStreamParams,
    FormatType
)

# =====================================================================
# KONFIGURATION
# =====================================================================
HEF_PATHS = {
    'backbone':  'hexapod_backbone.hef',
    'geometry':  'hexapod_geometry.hef',
    'detection': 'hexapod_detection.hef',
}

# =====================================================================
# STATISCHES TENSOR ROUTING (Der Turbo-Boost)
# =====================================================================
def _build_routing_plan(hef_dest, dest_in_names, bb_feat_l, bb_feat_r):
    """
    Erstellt vor der Inferenz-Schleife einen festen Plan, welcher
    NPU-Output in welchen NPU-Input kopiert werden muss.
    Gibt eine Liste von (Destination_Key, Source_Type, Source_Key, Fallback_Shape) zurück.
    """
    plan = []
    hef_input_infos = {info.name: info for info in hef_dest.get_input_vstream_infos()}
    used_l = set()
    
    for dest_name in dest_in_names:
        shape = tuple(hef_input_infos[dest_name].shape) # (H, W, C)
        
        # 1. Ist es das Rohbild?
        if shape == (480, 640, 1):
            plan.append((dest_name, 'img_left', None, shape))
            continue
            
        # 2. Sind es die Normalen?
        if shape[-1] == 3 and shape[0] == 120:
            plan.append((dest_name, 'normals', None, shape))
            continue
            
        # 3. Ist es ein Feature vom linken Backbone?
        match_found = False
        for src_name, feat in bb_feat_l.items():
            if tuple(feat.shape[1:]) == shape and src_name not in used_l:
                used_l.add(src_name)
                plan.append((dest_name, 'feat_l', src_name, shape))
                match_found = True
                break
                
        if match_found: continue
                
        # 4. Ist es ein Feature vom rechten Backbone?
        if bb_feat_r is not None:
            for src_name, feat in bb_feat_r.items():
                if tuple(feat.shape[1:]) == shape:
                    plan.append((dest_name, 'feat_r', src_name, shape))
                    match_found = True
                    break
                    
        # 5. Notnagel (Sollte nie passieren)
        if not match_found:
            print(f"⚠️ Warnung: Kein Routing für {dest_name} (Shape {shape}) gefunden!")
            plan.append((dest_name, 'zeros', None, shape))
            
    return plan

def _assemble_feed_fast(plan, img_left, normals_data, feat_l, feat_r):
    """
    Die schnellste Möglichkeit in Python, das Input-Dictionary zusammenzubauen.
    Keine If-Elif-Ketten im Loop, keine Shape-Checks.
    """
    feed = {}
    for dest_key, src_type, src_key, shape in plan:
        if src_type == 'feat_l':
            feed[dest_key] = feat_l[src_key]
        elif src_type == 'feat_r':
            feed[dest_key] = feat_r[src_key]
        elif src_type == 'img_left':
            feed[dest_key] = img_left
        elif src_type == 'normals':
            feed[dest_key] = normals_data
        else: # 'zeros'
            feed[dest_key] = np.zeros((1,) + shape, dtype=np.float32)
    return feed

# =====================================================================
# 3-HEF PIPELINE (STREAMING OPTIMIERT)
# =====================================================================
def benchmark_streaming(n_frames=50, warmup=5):
    print("\n" + "=" * 60)
    print("🚀 3-HEF STREAMING BENCHMARK (LOW-LATENCY ROUTING)")
    print("=" * 60)
    
    hef_bb = HEF(HEF_PATHS['backbone'])
    hef_geo = HEF(HEF_PATHS['geometry'])
    hef_det = HEF(HEF_PATHS['detection'])
    
    params = VDevice.create_params()
    with VDevice(params) as vdevice:
        # Konfigurieren der Netzwerke
        ng_bb = vdevice.configure(hef_bb, ConfigureParams.create_from_hef(hef_bb, interface=HailoStreamInterface.PCIe))[0]
        ng_geo = vdevice.configure(hef_geo, ConfigureParams.create_from_hef(hef_geo, interface=HailoStreamInterface.PCIe))[0]
        ng_det = vdevice.configure(hef_det, ConfigureParams.create_from_hef(hef_det, interface=HailoStreamInterface.PCIe))[0]
        
        bb_in_p = InputVStreamParams.make(ng_bb, format_type=FormatType.UINT8)
        bb_out_p = OutputVStreamParams.make(ng_bb, format_type=FormatType.FLOAT32)
        geo_in_p = InputVStreamParams.make(ng_geo, format_type=FormatType.FLOAT32)
        geo_out_p = OutputVStreamParams.make(ng_geo, format_type=FormatType.FLOAT32)
        det_in_p = InputVStreamParams.make(ng_det, format_type=FormatType.FLOAT32)
        det_out_p = OutputVStreamParams.make(ng_det, format_type=FormatType.FLOAT32)
        
        bb_in_name = hef_bb.get_input_vstream_infos()[0].name
        geo_in_names = [i.name for i in hef_geo.get_input_vstream_infos()]
        det_in_names = [i.name for i in hef_det.get_input_vstream_infos()]
        
        img_left = np.random.randint(0, 256, size=(1, 480, 640, 1), dtype=np.uint8).astype(np.float32)
        img_right = np.random.randint(0, 256, size=(1, 480, 640, 1), dtype=np.uint8).astype(np.float32)

        print("   🛠️ Generiere statische Routing-Pläne...")
        
        # 1. Dummy-Run Backbone um Shapes & Keys zu bekommen
        with ng_bb.activate(ng_bb.create_params()):
             with InferVStreams(ng_bb, bb_in_p, bb_out_p) as pipe_bb:
                dummy_feat_l = pipe_bb.infer({bb_in_name: img_left})
                dummy_feat_r = pipe_bb.infer({bb_in_name: img_right})
                
        # 2. Plan für Geometry bauen
        geo_plan = _build_routing_plan(hef_geo, geo_in_names, dummy_feat_l, dummy_feat_r)
        dummy_geo_feed = _assemble_feed_fast(geo_plan, img_left, None, dummy_feat_l, dummy_feat_r)
        
        # 3. Dummy-Run Geometry um Normals Key zu finden
        with ng_geo.activate(ng_geo.create_params()):
            with InferVStreams(ng_geo, geo_in_p, geo_out_p) as pipe_geo:
                dummy_geo_out = pipe_geo.infer(dummy_geo_feed)
                
        normals_key = next((k for k, v in dummy_geo_out.items() if v.shape[-1] == 3 and v.shape[-2] == 160), None)
        
        # 4. Plan für Detection bauen
        det_plan = _build_routing_plan(hef_det, det_in_names, dummy_feat_l, dummy_feat_r)

        print(f"      Geo-Plan Ops: {len(geo_plan)}")
        print(f"      Det-Plan Ops: {len(det_plan)}")
        print(f"      Normals Key:  {normals_key}")

        all_timings = []

        print(f"\n   🔥 Warmup ({warmup} Frames)...")
        print(f"   ⏱️  Start Streaming Messung ({n_frames} Frames)...")
        
        # WICHTIG: Das ist der einzige Weg auf dem Hailo-8. 
        # Wir MÜSSEN die Netzwerke in der Schleife aktivieren/deaktivieren, 
        # da der Chip nur ein Modell fassen kann.
        for i in range(n_frames + warmup):
            is_warmup = i < warmup
            timings = {}
            
            # --- 1. BACKBONE ---
            t_bb_start = time.perf_counter()
            with ng_bb.activate(ng_bb.create_params()):
                 with InferVStreams(ng_bb, bb_in_p, bb_out_p) as pipe_bb:
                    t0 = time.perf_counter()
                    feat_l = pipe_bb.infer({bb_in_name: img_left})
                    timings['bb_l_infer'] = (time.perf_counter() - t0) * 1000
                    
                    t1 = time.perf_counter()
                    feat_r = pipe_bb.infer({bb_in_name: img_right})
                    timings['bb_r_infer'] = (time.perf_counter() - t1) * 1000
            timings['bb_total_with_switch'] = (time.perf_counter() - t_bb_start) * 1000

            # --- 2. GEOMETRY ---
            geo_feed = _assemble_feed_fast(geo_plan, img_left, None, feat_l, feat_r)
            
            t_geo_start = time.perf_counter()
            with ng_geo.activate(ng_geo.create_params()):
                with InferVStreams(ng_geo, geo_in_p, geo_out_p) as pipe_geo:
                    t0 = time.perf_counter()
                    geo_out = pipe_geo.infer(geo_feed)
                    timings['geo_infer'] = (time.perf_counter() - t0) * 1000
            timings['geo_total_with_switch'] = (time.perf_counter() - t_geo_start) * 1000

            # --- 3. DETECTION ---
            normals_data = geo_out[normals_key] if normals_key else None
            det_feed = _assemble_feed_fast(det_plan, img_left, normals_data, feat_l, feat_r)
            
            t_det_start = time.perf_counter()
            with ng_det.activate(ng_det.create_params()):
                with InferVStreams(ng_det, det_in_p, det_out_p) as pipe_det:
                    t0 = time.perf_counter()
                    pipe_det.infer(det_feed)
                    timings['det_infer'] = (time.perf_counter() - t0) * 1000
            timings['det_total_with_switch'] = (time.perf_counter() - t_det_start) * 1000
            
            # --- GESAMT ---
            timings['total_pipeline'] = (time.perf_counter() - t_bb_start) * 1000
            
            if not is_warmup:
                all_timings.append(timings)
                if (i - warmup + 1) % 10 == 0:
                    print(f"      Frame {i - warmup + 1}/{n_frames}: {timings['total_pipeline']:.1f} ms")


        # --- AUSWERTUNG ---
        print(f"\n{'=' * 60}")
        print(f"📈 3-HEF STREAMING ERGEBNISSE (PYTHON ROUTING OPTIMIERT)")
        print(f"{'=' * 60}")
        print(f"{'Schritt':25} | {'Median':>8} | {'Mean':>8}")
        print("-" * 60)
        
        # Reine Inferenz (Die Zeit auf der NPU)
        print("Reine NPU-Inferenz (ohne Context Switch):")
        for step in ['bb_l_infer', 'bb_r_infer', 'geo_infer', 'det_infer']:
            vals = [t[step] for t in all_timings]
            print(f"  {step:23} | {np.median(vals):7.2f}ms | {np.mean(vals):7.2f}ms")
            
        print("-" * 60)
        # Gesamtdauer pro Stufe (inkl. Treiber/Speicher Umschalten)
        print("Stufen-Dauer inkl. Hardware Context-Switch:")
        for step in ['bb_total_with_switch', 'geo_total_with_switch', 'det_total_with_switch']:
            vals = [t[step] for t in all_timings]
            print(f"  {step:23} | {np.median(vals):7.2f}ms | {np.mean(vals):7.2f}ms")

        print("-" * 60)
        tot_vals = [t['total_pipeline'] for t in all_timings]
        print(f"{'TOTAL FRAME LATENCY':25} | {np.median(tot_vals):7.2f}ms | {np.mean(tot_vals):7.2f}ms")
        
        total_median = np.median(tot_vals)
        print(f"\n🎯 Reale Streaming FPS: {1000/total_median:.1f} FPS (Median)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Hailo Streaming Benchmark')
    parser.add_argument('--frames', type=int, default=50, help='Frames')
    parser.add_argument('--warmup', type=int, default=5, help='Warmup')
    args = parser.parse_args()
    
    benchmark_streaming(n_frames=args.frames, warmup=args.warmup)