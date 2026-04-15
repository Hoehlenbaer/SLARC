"""
benchmark_hailo.py — Benchmark der HEF-Pipeline auf dem Hailo-8 (Pi 5)

Usage:
    python benchmark_hailo.py                           # Beide Pipelines
    python benchmark_hailo.py --hef backbone             # Nur ein HEF
    python benchmark_hailo.py --pipeline 3hef            # Nur 3-HEF Pipeline
    python benchmark_hailo.py --pipeline 2hef            # Nur 2-HEF Pipeline
    python benchmark_hailo.py --frames 100               # 100 Frames messen
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
    'combined':  'hexapod_combined.hef',
}


# =====================================================================
# SHAPE-BASIERTES INPUT MATCHING
# =====================================================================
def _match_inputs_by_shape(input_names, input_infos_dict, hef, 
                            feat_l, feat_r, bb_out_names, img_left,
                            normals_data=None):
    """
    Mappt HEF-Inputs auf Backbone-Outputs anhand der Shapes.
    
    Bekannte Shapes:
      480x640x1  → img_l (Rohbild)
      120x160x24 → f_s4 (kommt 2x vor: links und rechts)
      60x80x40   → f_s8 (kommt 2x vor: links und rechts)
      30x40x112  → f_s16
      15x20x960  → f_s32
      120x160x3  → normals_s4
    """
    # Backbone-Outputs nach Shape indizieren
    bb_by_shape = {}
    for name in bb_out_names:
        shape = tuple(feat_l[name].shape[1:])  # ohne Batch
        if shape not in bb_by_shape:
            bb_by_shape[shape] = []
        bb_by_shape[shape].append(name)
    
    # Auch für rechte Features
    bb_r_by_shape = {}
    if feat_r is not None:
        for name in bb_out_names:
            if name in feat_r:
                shape = tuple(feat_r[name].shape[1:])
                if shape not in bb_r_by_shape:
                    bb_r_by_shape[shape] = []
                bb_r_by_shape[shape].append(name)
    
    # HEF-Input-Infos nach Name
    hef_input_infos = {info.name: info for info in hef.get_input_vstream_infos()}
    
    feed = {}
    used_l = set()  # Track welche L-Features schon verwendet
    
    for name in input_names:
        info = hef_input_infos[name]
        shape = tuple(info.shape)  # (H, W, C)
        
        # Rohbild: 480x640x1
        if shape == (480, 640, 1):
            feed[name] = img_left.astype(np.float32)
            continue
        
        # Normals: 120x160x3
        if shape[-1] == 3 and shape[0] == 120:
            if normals_data is not None:
                feed[name] = normals_data
            else:
                feed[name] = np.zeros((1,) + shape, dtype=np.float32)
            continue
        
        # Feature-Map: finde passendes Backbone-Output
        # Bei doppelten Shapes (s4, s8): erste Zuweisung → links, zweite → rechts
        bb_name = None
        for bn in bb_out_names:
            if bn in feat_l and tuple(feat_l[bn].shape[1:]) == shape:
                if bn not in used_l:
                    bb_name = bn
                    used_l.add(bn)
                    feed[name] = feat_l[bn]
                    break
        
        if bb_name is None and feat_r is not None:
            # Zweites Vorkommen → rechtes Bild
            for bn in bb_out_names:
                if bn in feat_r and tuple(feat_r[bn].shape[1:]) == shape:
                    feed[name] = feat_r[bn]
                    break
        
        if name not in feed:
            print(f"   ⚠️  Kein Match für {name} mit Shape {shape}")
            feed[name] = np.zeros((1,) + shape, dtype=np.float32)
    
    return feed


# =====================================================================
# EINZELNES HEF BENCHMARKEN
# =====================================================================
def benchmark_single_hef(hef_path, n_frames=50, warmup=5):
    print(f"\n📊 Benchmark: {hef_path}")
    
    hef = HEF(hef_path)
    params = VDevice.create_params()
    with VDevice(params) as vdevice:
        configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
        network_group = vdevice.configure(hef, configure_params)[0]
        
        input_vstream_params = InputVStreamParams.make(network_group, format_type=FormatType.UINT8)
        output_vstream_params = OutputVStreamParams.make(network_group, format_type=FormatType.FLOAT32)
        
        input_vstream_infos = hef.get_input_vstream_infos()
        output_vstream_infos = hef.get_output_vstream_infos()
        
        print(f"   Inputs:")
        input_data = {}
        for info in input_vstream_infos:
            shape = (1,) + tuple(info.shape)
            input_data[info.name] = np.random.randint(0, 256, size=shape, dtype=np.uint8)
            print(f"      {info.name}: {shape}")
        
        print(f"   Outputs:")
        for info in output_vstream_infos:
            print(f"      {info.name}: {info.shape}")
        
        with network_group.activate(network_group.create_params()):
            with InferVStreams(network_group, input_vstream_params, output_vstream_params) as pipeline:
                print(f"   🔥 Warmup ({warmup} Frames)...")
                for _ in range(warmup):
                    pipeline.infer(input_data)
                
                print(f"   ⏱️  Messe {n_frames} Frames...")
                latencies = []
                for i in range(n_frames):
                    t0 = time.perf_counter()
                    results = pipeline.infer(input_data)
                    t1 = time.perf_counter()
                    latencies.append((t1 - t0) * 1000)
                
                latencies = np.array(latencies)
                print(f"\n   📈 Ergebnisse ({n_frames} Frames):")
                print(f"      Median:  {np.median(latencies):.2f} ms")
                print(f"      Mean:    {np.mean(latencies):.2f} ms")
                print(f"      Min:     {np.min(latencies):.2f} ms")
                print(f"      Max:     {np.max(latencies):.2f} ms")
                print(f"      Std:     {np.std(latencies):.2f} ms")
                print(f"      → {1000/np.median(latencies):.1f} FPS (Median)")
                
                return {
                    'median': np.median(latencies),
                    'mean': np.mean(latencies),
                    'min': np.min(latencies),
                    'max': np.max(latencies),
                    'results': results,
                }


# =====================================================================
# 3-HEF PIPELINE
# =====================================================================
def benchmark_3hef_pipeline(n_frames=50, warmup=5):
    print("\n" + "=" * 60)
    print("🚀 3-HEF PIPELINE BENCHMARK")
    print("=" * 60)
    
    hef_bb = HEF(HEF_PATHS['backbone'])
    hef_geo = HEF(HEF_PATHS['geometry'])
    hef_det = HEF(HEF_PATHS['detection'])
    
    params = VDevice.create_params()
    with VDevice(params) as vdevice:
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
        bb_out_names = [o.name for o in hef_bb.get_output_vstream_infos()]
        geo_in_names = [i.name for i in hef_geo.get_input_vstream_infos()]
        det_in_names = [i.name for i in hef_det.get_input_vstream_infos()]
        
        print(f"   BB Input:   {bb_in_name}")
        print(f"   BB Outputs: {bb_out_names}")
        print(f"   Geo Inputs: {geo_in_names}")
        print(f"   Det Inputs: {det_in_names}")
        
        img_left = np.random.randint(0, 256, size=(1, 480, 640, 1), dtype=np.uint8)
        img_right = np.random.randint(0, 256, size=(1, 480, 640, 1), dtype=np.uint8)
        
        def run_pipeline():
            timings = {}
            
            # 1. Backbone(left)
            t0 = time.perf_counter()
            with ng_bb.activate(ng_bb.create_params()):
                with InferVStreams(ng_bb, bb_in_p, bb_out_p) as pipe:
                    feat_l = pipe.infer({bb_in_name: img_left})
            timings['bb_left'] = (time.perf_counter() - t0) * 1000
            
            # 2. Backbone(right)
            t0 = time.perf_counter()
            with ng_bb.activate(ng_bb.create_params()):
                with InferVStreams(ng_bb, bb_in_p, bb_out_p) as pipe:
                    feat_r = pipe.infer({bb_in_name: img_right})
            timings['bb_right'] = (time.perf_counter() - t0) * 1000
            
            # 3. Geometry — Shape-basiertes Mapping
            geo_feed = _match_inputs_by_shape(
                geo_in_names,
                {name: hef_geo.get_input_vstream_infos() for name in geo_in_names},
                hef_geo,
                feat_l, feat_r, bb_out_names, img_left
            )
            
            t0 = time.perf_counter()
            with ng_geo.activate(ng_geo.create_params()):
                with InferVStreams(ng_geo, geo_in_p, geo_out_p) as pipe:
                    geo_out = pipe.infer(geo_feed)
            timings['geometry'] = (time.perf_counter() - t0) * 1000
            
            # 4. Detection — Shape-basiertes Mapping
            # normals_s4 finden (Shape ...x160x3)
            normals_key = None
            for k, v in geo_out.items():
                if v.shape[-1] == 3 and v.shape[-2] == 160:
                    normals_key = k
                    break
            
            det_feed = _match_inputs_by_shape(
                det_in_names,
                {name: hef_det.get_input_vstream_infos() for name in det_in_names},
                hef_det,
                feat_l, feat_r, bb_out_names, img_left,
                normals_data=geo_out.get(normals_key) if normals_key else None
            )
            
            t0 = time.perf_counter()
            with ng_det.activate(ng_det.create_params()):
                with InferVStreams(ng_det, det_in_p, det_out_p) as pipe:
                    pipe.infer(det_feed)
            timings['detection'] = (time.perf_counter() - t0) * 1000
            timings['total'] = sum(timings.values())
            return timings
        
        _run_and_print("3-HEF PIPELINE", run_pipeline, n_frames, warmup,
                       ['bb_left', 'bb_right', 'geometry', 'detection', 'total'],
                       {'bb_left': 'Backbone(L)', 'bb_right': 'Backbone(R)',
                        'geometry': 'Geometry', 'detection': 'Detection', 'total': 'TOTAL'})


# =====================================================================
# 2-HEF PIPELINE
# =====================================================================
def benchmark_2hef_pipeline(n_frames=50, warmup=5):
    print("\n" + "=" * 60)
    print("🚀 2-HEF PIPELINE BENCHMARK")
    print("=" * 60)
    
    hef_bb = HEF(HEF_PATHS['backbone'])
    hef_comb = HEF(HEF_PATHS['combined'])
    
    params = VDevice.create_params()
    with VDevice(params) as vdevice:
        ng_bb = vdevice.configure(hef_bb, ConfigureParams.create_from_hef(hef_bb, interface=HailoStreamInterface.PCIe))[0]
        ng_comb = vdevice.configure(hef_comb, ConfigureParams.create_from_hef(hef_comb, interface=HailoStreamInterface.PCIe))[0]
        
        bb_in_p = InputVStreamParams.make(ng_bb, format_type=FormatType.UINT8)
        bb_out_p = OutputVStreamParams.make(ng_bb, format_type=FormatType.FLOAT32)
        comb_in_p = InputVStreamParams.make(ng_comb, format_type=FormatType.FLOAT32)
        comb_out_p = OutputVStreamParams.make(ng_comb, format_type=FormatType.FLOAT32)
        
        bb_in_name = hef_bb.get_input_vstream_infos()[0].name
        bb_out_names = [o.name for o in hef_bb.get_output_vstream_infos()]
        comb_in_names = [i.name for i in hef_comb.get_input_vstream_infos()]
        
        print(f"   BB Input:    {bb_in_name}")
        print(f"   BB Outputs:  {bb_out_names}")
        print(f"   Comb Inputs: {comb_in_names}")
        
        img_left = np.random.randint(0, 256, size=(1, 480, 640, 1), dtype=np.uint8)
        img_right = np.random.randint(0, 256, size=(1, 480, 640, 1), dtype=np.uint8)
        
        def run_pipeline():
            timings = {}
            
            # 1. Backbone(left)
            t0 = time.perf_counter()
            with ng_bb.activate(ng_bb.create_params()):
                with InferVStreams(ng_bb, bb_in_p, bb_out_p) as pipe:
                    feat_l = pipe.infer({bb_in_name: img_left})
            timings['bb_left'] = (time.perf_counter() - t0) * 1000
            
            # 2. Backbone(right)
            t0 = time.perf_counter()
            with ng_bb.activate(ng_bb.create_params()):
                with InferVStreams(ng_bb, bb_in_p, bb_out_p) as pipe:
                    feat_r = pipe.infer({bb_in_name: img_right})
            timings['bb_right'] = (time.perf_counter() - t0) * 1000
            
            # 3. Combined — Shape-basiertes Mapping
            comb_feed = _match_inputs_by_shape(
                comb_in_names,
                {name: hef_comb.get_input_vstream_infos() for name in comb_in_names},
                hef_comb,
                feat_l, feat_r, bb_out_names, img_left
            )
            
            t0 = time.perf_counter()
            with ng_comb.activate(ng_comb.create_params()):
                with InferVStreams(ng_comb, comb_in_p, comb_out_p) as pipe:
                    pipe.infer(comb_feed)
            timings['combined'] = (time.perf_counter() - t0) * 1000
            timings['total'] = sum(timings.values())
            return timings
        
        _run_and_print("2-HEF PIPELINE", run_pipeline, n_frames, warmup,
                       ['bb_left', 'bb_right', 'combined', 'total'],
                       {'bb_left': 'Backbone(L)', 'bb_right': 'Backbone(R)',
                        'combined': 'Combined', 'total': 'TOTAL'})


# =====================================================================
# HELPER
# =====================================================================
def _run_and_print(title, run_fn, n_frames, warmup, steps, labels):
    print(f"\n   🔥 Warmup ({warmup} Frames)...")
    for _ in range(warmup):
        run_fn()
    
    print(f"   ⏱️  Messe {n_frames} Frames...")
    all_timings = []
    for i in range(n_frames):
        timings = run_fn()
        all_timings.append(timings)
        if (i + 1) % 10 == 0:
            print(f"      Frame {i+1}/{n_frames}: {timings['total']:.1f} ms")
    
    print(f"\n{'=' * 60}")
    print(f"📈 {title} ERGEBNISSE")
    print(f"{'=' * 60}")
    print(f"\n{'Schritt':15} | {'Median':>8} | {'Mean':>8} | {'Min':>8} | {'Max':>8}")
    print("-" * 60)
    for step in steps:
        vals = [t[step] for t in all_timings]
        if step == 'total':
            print("-" * 60)
        print(f"{labels[step]:15} | {np.median(vals):7.2f}ms | {np.mean(vals):7.2f}ms | "
              f"{np.min(vals):7.2f}ms | {np.max(vals):7.2f}ms")
    
    total_median = np.median([t['total'] for t in all_timings])
    print(f"\n🎯 Pipeline FPS: {1000/total_median:.1f} FPS (Median)")
    print(f"   Ziel 30 FPS → max 33.3 ms/Frame → "
          f"{'✅ ERREICHT' if total_median < 33.3 else '❌ ZU LANGSAM'}")


# =====================================================================
# MAIN
# =====================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Hailo-8 Pipeline Benchmark')
    parser.add_argument('--hef', choices=['backbone', 'geometry', 'detection', 'combined'],
                        help='Nur ein einzelnes HEF benchmarken')
    parser.add_argument('--pipeline', choices=['3hef', '2hef', 'both'], default='both',
                        help='Welche Pipeline benchmarken (default: both)')
    parser.add_argument('--frames', type=int, default=50, help='Anzahl Frames (default: 50)')
    parser.add_argument('--warmup', type=int, default=5, help='Warmup Frames (default: 5)')
    args = parser.parse_args()
    
    if args.hef:
        benchmark_single_hef(HEF_PATHS[args.hef], n_frames=args.frames, warmup=args.warmup)
    else:
        benchmark_single_hef(HEF_PATHS['backbone'], n_frames=args.frames, warmup=args.warmup)
        
        if args.pipeline in ('3hef', 'both'):
            benchmark_3hef_pipeline(n_frames=args.frames, warmup=args.warmup)
        if args.pipeline in ('2hef', 'both'):
            benchmark_2hef_pipeline(n_frames=args.frames, warmup=args.warmup)
