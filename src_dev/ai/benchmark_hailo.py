"""
benchmark_hailo.py — Benchmark der 3-HEF-Pipeline auf dem Hailo-8 (Pi 5)

Misst Latenz pro HEF und Gesamt-Pipeline.
Kopiere die 3 HEF-Dateien in den gleichen Ordner.

Usage:
    python benchmark_hailo.py                    # Vollständiger Pipeline-Benchmark
    python benchmark_hailo.py --hef backbone     # Nur ein HEF testen
    python benchmark_hailo.py --frames 100       # 100 Frames messen
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

# Input/Output-Shapes (NHWC, Batch=1)
SHAPES = {
    'backbone': {
        'inputs':  {'gray_img': (1, 480, 640, 1)},
        'outputs': ['f_s4', 'f_s8', 'f_s16', 'f_s32'],
    },
    'geometry': {
        'inputs': {
            'f_s4_l':  (1, 120, 160, 24),
            'f_s8_l':  (1, 60, 80, 40),
            'f_s4_r':  (1, 120, 160, 24),
            'f_s8_r':  (1, 60, 80, 40),
            'img_l':   (1, 480, 640, 1),
        },
        'outputs': ['disp_final', 'normals_s1', 'normals_s4', 'disp_s8'],
    },
    'detection': {
        'inputs': {
            'f_s4_l':     (1, 120, 160, 24),
            'f_s8_l':     (1, 60, 80, 40),
            'f_s16_l':    (1, 30, 40, 112),
            'f_s32_l':    (1, 15, 20, 960),
            'normals_s4': (1, 120, 160, 3),
        },
        'outputs': ['seg', 'yolo_s8', 'yolo_s16', 'yolo_s32'],
    },
}


# =====================================================================
# HILFSFUNKTIONEN
# =====================================================================
def create_random_input(shape_dict):
    """Erzeugt zufällige Eingabedaten im UINT8-Format."""
    return {name: np.random.randint(0, 256, size=shape, dtype=np.uint8)
            for name, shape in shape_dict.items()}


def benchmark_single_hef(hef_path, n_frames=50, warmup=5):
    """Benchmarkt ein einzelnes HEF."""
    print(f"\n📊 Benchmark: {hef_path}")
    
    hef = HEF(hef_path)
    
    # VDevice erstellen
    params = VDevice.create_params()
    with VDevice(params) as vdevice:
        # Netzwerk konfigurieren
        configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
        network_group = vdevice.configure(hef, configure_params)[0]
        network_group_params = network_group.create_params()
        
        # Stream-Parameter
        input_vstream_params = InputVStreamParams.make(network_group, format_type=FormatType.UINT8)
        output_vstream_params = OutputVStreamParams.make(network_group, format_type=FormatType.FLOAT32)
        
        # Input-Shapes aus dem HEF auslesen
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
        
        with InferVStreams(network_group, input_vstream_params, output_vstream_params) as pipeline:
            # Warmup
            print(f"   🔥 Warmup ({warmup} Frames)...")
            for _ in range(warmup):
                pipeline.infer(input_data)
            
            # Benchmark
            print(f"   ⏱️  Messe {n_frames} Frames...")
            latencies = []
            for i in range(n_frames):
                t0 = time.perf_counter()
                results = pipeline.infer(input_data)
                t1 = time.perf_counter()
                latencies.append((t1 - t0) * 1000)  # ms
            
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
                'results': results,  # Letztes Ergebnis für Pipeline-Test
            }


def benchmark_pipeline(n_frames=50, warmup=5):
    """Benchmarkt die vollständige 3-HEF-Pipeline sequentiell."""
    print("\n" + "=" * 60)
    print("🚀 VOLLSTÄNDIGE PIPELINE BENCHMARK")
    print("=" * 60)
    
    # Alle 3 HEFs laden
    hefs = {name: HEF(path) for name, path in HEF_PATHS.items()}
    
    params = VDevice.create_params()
    with VDevice(params) as vdevice:
        # Alle Netzwerke konfigurieren
        networks = {}
        input_params = {}
        output_params = {}
        
        for name, hef in hefs.items():
            cfg = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
            ng = vdevice.configure(hef, cfg)[0]
            networks[name] = ng
            input_params[name] = InputVStreamParams.make(ng, format_type=FormatType.UINT8)
            output_params[name] = OutputVStreamParams.make(ng, format_type=FormatType.FLOAT32)
        
        # Dummy-Eingabebild
        img_left = np.random.randint(0, 256, size=(1, 480, 640, 1), dtype=np.uint8)
        img_right = np.random.randint(0, 256, size=(1, 480, 640, 1), dtype=np.uint8)
        
        # Input-Infos auslesen
        bb_inputs = hefs['backbone'].get_input_vstream_infos()
        bb_outputs = hefs['backbone'].get_output_vstream_infos()
        geo_inputs = hefs['geometry'].get_input_vstream_infos()
        det_inputs = hefs['detection'].get_input_vstream_infos()
        
        bb_input_name = bb_inputs[0].name
        
        print(f"\n   Backbone Input:  {bb_input_name}")
        print(f"   Backbone Outputs: {[o.name for o in bb_outputs]}")
        print(f"   Geometry Inputs:  {[i.name for i in geo_inputs]}")
        print(f"   Detection Inputs: {[i.name for i in det_inputs]}")
        
        # Pipeline-Funktion
        def run_pipeline():
            """Ein vollständiger Pipeline-Durchlauf."""
            timings = {}
            
            # 1. Backbone(left)
            t0 = time.perf_counter()
            with InferVStreams(networks['backbone'], input_params['backbone'], output_params['backbone']) as pipe:
                feat_l = pipe.infer({bb_input_name: img_left})
            t1 = time.perf_counter()
            timings['bb_left'] = (t1 - t0) * 1000
            
            # 2. Backbone(right)
            t0 = time.perf_counter()
            with InferVStreams(networks['backbone'], input_params['backbone'], output_params['backbone']) as pipe:
                feat_r = pipe.infer({bb_input_name: img_right})
            t1 = time.perf_counter()
            timings['bb_right'] = (t1 - t0) * 1000
            
            # 3. Geometry — Inputs aus Backbone-Outputs zusammenbauen
            geo_feed = {}
            geo_input_names = [i.name for i in geo_inputs]
            bb_output_names = [o.name for o in bb_outputs]
            
            # Mapping: Geometry erwartet f_s4_l, f_s8_l, f_s4_r, f_s8_r, img_l
            # Backbone gibt f_s4, f_s8, f_s16, f_s32 zurück
            # Die Zuordnung muss über die Reihenfolge oder Shape gehen
            for i, geo_inp in enumerate(geo_input_names):
                if i == 0:  # f_s4_l
                    geo_feed[geo_inp] = feat_l[bb_output_names[0]]
                elif i == 1:  # f_s8_l
                    geo_feed[geo_inp] = feat_l[bb_output_names[1]]
                elif i == 2:  # f_s4_r
                    geo_feed[geo_inp] = feat_r[bb_output_names[0]]
                elif i == 3:  # f_s8_r
                    geo_feed[geo_inp] = feat_r[bb_output_names[1]]
                elif i == 4:  # img_l
                    geo_feed[geo_inp] = img_left
            
            t0 = time.perf_counter()
            with InferVStreams(networks['geometry'], input_params['geometry'], output_params['geometry']) as pipe:
                geo_out = pipe.infer(geo_feed)
            t1 = time.perf_counter()
            timings['geometry'] = (t1 - t0) * 1000
            
            # 4. Detection — Backbone-Features + normals_s4
            det_feed = {}
            det_input_names = [i.name for i in det_inputs]
            geo_output_names = list(geo_out.keys())
            
            # Finde normals_s4 im Geometry-Output (3. Output, Shape 120x160x3)
            normals_s4_key = None
            for k, v in geo_out.items():
                if len(v.shape) >= 3 and v.shape[-1] == 3 and v.shape[-2] == 160:
                    normals_s4_key = k
                    break
            
            for i, det_inp in enumerate(det_input_names):
                if i == 0:  # f_s4_l
                    det_feed[det_inp] = feat_l[bb_output_names[0]]
                elif i == 1:  # f_s8_l
                    det_feed[det_inp] = feat_l[bb_output_names[1]]
                elif i == 2:  # f_s16_l
                    det_feed[det_inp] = feat_l[bb_output_names[2]]
                elif i == 3:  # f_s32_l
                    det_feed[det_inp] = feat_l[bb_output_names[3]]
                elif i == 4:  # normals_s4
                    det_feed[det_inp] = geo_out[normals_s4_key] if normals_s4_key else \
                        np.zeros((1, 120, 160, 3), dtype=np.float32)
            
            t0 = time.perf_counter()
            with InferVStreams(networks['detection'], input_params['detection'], output_params['detection']) as pipe:
                det_out = pipe.infer(det_feed)
            t1 = time.perf_counter()
            timings['detection'] = (t1 - t0) * 1000
            timings['total'] = sum(timings.values())
            
            return timings, geo_out, det_out
        
        # Warmup
        print(f"\n   🔥 Warmup ({warmup} Frames)...")
        for _ in range(warmup):
            run_pipeline()
        
        # Benchmark
        print(f"   ⏱️  Messe {n_frames} Frames...")
        all_timings = []
        for i in range(n_frames):
            timings, _, _ = run_pipeline()
            all_timings.append(timings)
            if (i + 1) % 10 == 0:
                print(f"      Frame {i+1}/{n_frames}: {timings['total']:.1f} ms")
        
        # Auswertung
        print("\n" + "=" * 60)
        print("📈 ERGEBNISSE")
        print("=" * 60)
        
        steps = ['bb_left', 'bb_right', 'geometry', 'detection', 'total']
        labels = {
            'bb_left': 'Backbone(L)',
            'bb_right': 'Backbone(R)',
            'geometry': 'Geometry',
            'detection': 'Detection',
            'total': 'TOTAL',
        }
        
        print(f"\n{'Schritt':15} | {'Median':>8} | {'Mean':>8} | {'Min':>8} | {'Max':>8}")
        print("-" * 60)
        for step in steps:
            vals = [t[step] for t in all_timings]
            med = np.median(vals)
            mean = np.mean(vals)
            mn = np.min(vals)
            mx = np.max(vals)
            sep = "=" if step == 'total' else " "
            if step == 'total':
                print("-" * 60)
            print(f"{labels[step]:15} | {med:7.2f}ms | {mean:7.2f}ms | {mn:7.2f}ms | {mx:7.2f}ms")
        
        total_median = np.median([t['total'] for t in all_timings])
        print(f"\n🎯 Pipeline FPS: {1000/total_median:.1f} FPS (Median)")
        print(f"   Ziel 30 FPS → max {33.3:.1f} ms/Frame → {'✅ ERREICHT' if total_median < 33.3 else '❌ ZU LANGSAM'}")


# =====================================================================
# MAIN
# =====================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Hailo-8 Pipeline Benchmark')
    parser.add_argument('--hef', choices=['backbone', 'geometry', 'detection'],
                        help='Nur ein einzelnes HEF benchmarken')
    parser.add_argument('--frames', type=int, default=50, help='Anzahl Frames (default: 50)')
    parser.add_argument('--warmup', type=int, default=5, help='Warmup Frames (default: 5)')
    args = parser.parse_args()
    
    if args.hef:
        benchmark_single_hef(HEF_PATHS[args.hef], n_frames=args.frames, warmup=args.warmup)
    else:
        # Einzelne HEFs zuerst
        for name in ['backbone', 'geometry', 'detection']:
            benchmark_single_hef(HEF_PATHS[name], n_frames=args.frames, warmup=args.warmup)
        # Dann Pipeline
        benchmark_pipeline(n_frames=args.frames, warmup=args.warmup)
