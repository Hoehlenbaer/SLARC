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
import threading
import queue
from hailo_platform import (
    HEF, VDevice, HailoStreamInterface,
    ConfigureParams, InferVStreams, InputVStreamParams, OutputVStreamParams,
    FormatType, HailoSchedulingAlgorithm  # <-- KORRIGIERT
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
    """
    bb_by_shape = {}
    for name in bb_out_names:
        shape = tuple(feat_l[name].shape[1:])  
        if shape not in bb_by_shape:
            bb_by_shape[shape] = []
        bb_by_shape[shape].append(name)
    
    bb_r_by_shape = {}
    if feat_r is not None:
        for name in bb_out_names:
            if name in feat_r:
                shape = tuple(feat_r[name].shape[1:])
                if shape not in bb_r_by_shape:
                    bb_r_by_shape[shape] = []
                bb_r_by_shape[shape].append(name)
    
    hef_input_infos = {info.name: info for info in hef.get_input_vstream_infos()}
    
    feed = {}
    used_l = set()
    
    for name in input_names:
        info = hef_input_infos[name]
        shape = tuple(info.shape)
        
        if shape == (480, 640, 1):
            feed[name] = img_left.astype(np.float32)
            continue
        
        if shape[-1] == 3 and shape[0] == 120:
            if normals_data is not None:
                feed[name] = normals_data
            else:
                feed[name] = np.zeros((1,) + shape, dtype=np.float32)
            continue
        
        bb_name = None
        for bn in bb_out_names:
            if bn in feat_l and tuple(feat_l[bn].shape[1:]) == shape:
                if bn not in used_l:
                    bb_name = bn
                    used_l.add(bn)
                    feed[name] = feat_l[bn]
                    break
        
        if bb_name is None and feat_r is not None:
            for bn in bb_out_names:
                if bn in feat_r and tuple(feat_r[bn].shape[1:]) == shape:
                    feed[name] = feat_r[bn]
                    break
        
        if name not in feed:
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
        
        input_data = {}
        for info in input_vstream_infos:
            shape = (1,) + tuple(info.shape)
            input_data[info.name] = np.random.randint(0, 256, size=shape, dtype=np.uint8)
        
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
                print(f"      → {1000/np.median(latencies):.1f} FPS (Median)")


# =====================================================================
# 3-HEF PIPELINE (ASYNC MIT THREADS)
# =====================================================================
def benchmark_3hef_pipeline(n_frames=50, warmup=5):
    print("\n" + "=" * 60)
    print("🚀 3-HEF PIPELINE BENCHMARK (ASYNC FLIESSBAND)")
    print("=" * 60)
    
    hef_bb = HEF(HEF_PATHS['backbone'])
    hef_geo = HEF(HEF_PATHS['geometry'])
    hef_det = HEF(HEF_PATHS['detection'])
    
    params = VDevice.create_params()
    # KORRIGIERT: HailoSchedulingAlgorithm
    params.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN 
    
    with VDevice(params) as vdevice:
        # 1. Alle Modelle auf den Device konfigurieren
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
        
        # Queues für den asynchronen Datentransfer zwischen den Modellen
        q_bb_to_geo = queue.Queue(maxsize=3)
        q_geo_to_det = queue.Queue(maxsize=3)
        
        total_runs = n_frames + warmup
        timings = []
        
        # --- WORKER THREADS ---
        
        def worker_backbone(pipe):
            """Stufe 1: Backbone für links und rechts"""
            for i in range(total_runs):
                img_left = np.random.randint(0, 256, size=(1, 480, 640, 1), dtype=np.uint8)
                img_right = np.random.randint(0, 256, size=(1, 480, 640, 1), dtype=np.uint8)
                
                t0 = time.perf_counter()
                feat_l = pipe.infer({bb_in_name: img_left})
                feat_r = pipe.infer({bb_in_name: img_right})
                
                # Sende Daten an Geometry-Stufe
                q_bb_to_geo.put((i, t0, img_left, feat_l, feat_r))

        def worker_geometry(pipe):
            """Stufe 2: Geometry"""
            geo_infos = {name: hef_geo.get_input_vstream_infos() for name in geo_in_names}
            for _ in range(total_runs):
                i, t0, img_l, feat_l, feat_r = q_bb_to_geo.get()
                
                feed = _match_inputs_by_shape(
                    geo_in_names, geo_infos, hef_geo,
                    feat_l, feat_r, bb_out_names, img_l
                )
                
                geo_out = pipe.infer(feed)
                q_geo_to_det.put((i, t0, img_l, feat_l, feat_r, geo_out))
                q_bb_to_geo.task_done()

        def worker_detection(pipe):
            """Stufe 3: Detection"""
            det_infos = {name: hef_det.get_input_vstream_infos() for name in det_in_names}
            for _ in range(total_runs):
                i, t0, img_l, feat_l, feat_r, geo_out = q_geo_to_det.get()
                
                # Normals finden
                normals_key = None
                for k, v in geo_out.items():
                    if v.shape[-1] == 3 and v.shape[-2] == 160:
                        normals_key = k
                        break
                
                feed = _match_inputs_by_shape(
                    det_in_names, det_infos, hef_det,
                    feat_l, feat_r, bb_out_names, img_l,
                    normals_data=geo_out.get(normals_key) if normals_key else None
                )
                
                pipe.infer(feed)
                t1 = time.perf_counter()
                
                latency = (t1 - t0) * 1000
                timings.append(latency)
                
                # Ausgabe nach dem Warmup
                if i >= warmup and (i + 1 - warmup) % 10 == 0:
                    print(f"      Frame {i+1-warmup}/{n_frames}: Durchlauf-Latenz {latency:.1f} ms")
                
                q_geo_to_det.task_done()

        # --- PIPELINE STARTEN ---
        print(f"   🔥 Warmup ({warmup} Frames) & Messe {n_frames} Frames...")
        
        # Alle Netze gleichzeitig auf dem Chip aktivieren (möglich durch ROUND_ROBIN)

            
        # Streaming-Pipelines aufbauen
        with InferVStreams(ng_bb, bb_in_p, bb_out_p) as pipe_bb, \
            InferVStreams(ng_geo, geo_in_p, geo_out_p) as pipe_geo, \
             InferVStreams(ng_det, det_in_p, det_out_p) as pipe_det:
                
            # Threads initialisieren
            t_bb = threading.Thread(target=worker_backbone, args=(pipe_bb,))
            t_geo = threading.Thread(target=worker_geometry, args=(pipe_geo,))
            t_det = threading.Thread(target=worker_detection, args=(pipe_det,))
                
            time_start = time.perf_counter()
                
            # Threads loslaufen lassen
            t_det.start()
            t_geo.start()
            t_bb.start()
                
            # Warten bis alles verarbeitet wurde
            t_bb.join()
            t_geo.join()
            t_det.join()
                
            time_end = time.perf_counter()

        # --- AUSWERTUNG ---
        valid_timings = timings[warmup:]
        total_duration_sec = time_end - time_start
        
        real_fps = total_runs / total_duration_sec
        median_latency = np.median(valid_timings)

        print(f"\n{'=' * 60}")
        print("📈 3-HEF ASYNC PIPELINE ERGEBNISSE")
        print(f"{'=' * 60}")
        print(f"   Latenz (Median):  {median_latency:.2f} ms (Zeit für 1 Bild von Anfang bis Ende)")
        print(f"   Latenz (Min/Max): {np.min(valid_timings):.2f} ms / {np.max(valid_timings):.2f} ms")
        print(f"\n🎯 Pipeline Durchsatz: {real_fps:.1f} FPS")
        
        if real_fps >= 30.0:
            print("   Ziel 30 FPS → ✅ ERREICHT! Der Pipeline-Overhead wurde besiegt.")
        else:
            print("   Ziel 30 FPS → ❌ ZU LANGSAM")


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
    # KORRIGIERT: HailoSchedulingAlgorithm
    params.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN
    
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
        
        img_left = np.random.randint(0, 256, size=(1, 480, 640, 1), dtype=np.uint8)
        img_right = np.random.randint(0, 256, size=(1, 480, 640, 1), dtype=np.uint8)
        
        def run_pipeline():
            timings = {}
            t0 = time.perf_counter()
            with ng_bb.activate(ng_bb.create_params()):
                with InferVStreams(ng_bb, bb_in_p, bb_out_p) as pipe:
                    feat_l = pipe.infer({bb_in_name: img_left})
                    t1 = time.perf_counter()
                    timings['bb_left'] = (t1 - t0) * 1000
                    t2 = time.perf_counter()
                    feat_r = pipe.infer({bb_in_name: img_right})
            timings['bb_right'] = (time.perf_counter() - t2) * 1000
            
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
        if args.pipeline in ('3hef', 'both'):
            benchmark_3hef_pipeline(n_frames=args.frames, warmup=args.warmup)
        if args.pipeline in ('2hef', 'both'):
            benchmark_2hef_pipeline(n_frames=args.frames, warmup=args.warmup)