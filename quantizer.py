import os
import numpy as np
import traceback
from hailo_sdk_client import ClientRunner
from hailo_sdk_client import ProfilerLevel
from hailo_sdk_client import InferenceContext

# =====================================================================
# KONFIGURATION
# =====================================================================
onnx_path       = 'hexapod_v3_1_simplified.onnx'
har_path        = 'hexapod_v3_1_simplified.har'
alls_path       = 'model_script.alls'
hef_output_path = 'hexapod_v3_1.hef'
model_name      = 'hexapod_v3_1_simplified'
N_CALIB         = 1024

# Normalisierungsparameter (identisch zum Training)
# Entspricht: (pixel/255 - 0.449) / 0.226
NORM_MEAN = 0.449 * 255.0   # = 114.495
NORM_STD  = 0.226 * 255.0   # =  57.630


def profile_model():
    print(f"📊 Starte Profiling für {har_path}...")
    runner = ClientRunner(har=har_path)
    # Level 1 ist schnell, Level 2 zeigt detaillierte SRAM/DDR-Bandbreite
    report = runner.profile(level=ProfilerLevel.LEVEL_2)
    
    with open(f"{model_name}_profile.html", "w") as f:
        f.write(report)
    print(f"✅ Profiling-Report erstellt: {model_name}_profile.html")

# =====================================================================
# SCHRITT 1: ONNX → HAR (Translate)
# =====================================================================
def translate(force=False):
    if os.path.exists(har_path) and not force:
        print(f"⏭️  HAR bereits vorhanden: {har_path} (force=True zum Neu-Erstellen)")
        return

    print(f"🔄 Übersetze ONNX → HAR...")
    runner = ClientRunner(hw_arch='hailo8')
    runner.translate_onnx_model(
        onnx_path,
        model_name,
        start_node_names=['input_layer1', 'input_layer2'],
        end_node_names=['disp_final', 'seg', 'disp_s8', 'normals',
                        'yolo_s8', 'yolo_s16', 'yolo_s32'],
        net_input_shapes={
            'input_layer1': [1, 1, 480, 640],
            'input_layer2': [1, 1, 480, 640],
        }
    )
    runner.save_har(har_path)
    print(f"✅ HAR gespeichert: {har_path}")

# =====================================================================
# SCHRITT 2: HAR → HEF (Optimize + Compile)
# =====================================================================
def quantize():
    print("🔍 Analysiere Modell-Struktur...")
    runner = ClientRunner(har=har_path, hw_arch='hailo8')
    hn = runner.get_hn_dict()
    all_layers = list(hn.get("layers", {}).keys())

    input_layers = sorted([n for n in all_layers if 'input_layer' in n.lower()])
    avgpool_layers = sorted([
        name for name, data in hn["layers"].items()
        if isinstance(data.get("type", ""), str)
        and "pool" in data["type"].lower()
        and "avg"  in data["type"].lower()
    ])

    # ── SCOPE-DIAGNOSE ────────────────────────────────────────────────
    print("\n📋 Scope-Analyse:")
    known_scopes      = {n.split("/")[0] for n in all_layers}
    root_scope_layers = [n for n in all_layers if n.split("/")[0] == model_name]
    print(f"   Scopes: {sorted(known_scopes)}")
    if root_scope_layers:
        print(f"   ⚠️  {len(root_scope_layers)} Root-Scope-Layer gefunden:")
        for l in root_scope_layers:
            print(f"      → {l}")
    else:
        print("   ✅ Keine Root-Scope-Layer.")
    print(f"   Input-Layer: {input_layers}")
    print()
    # ── ENDE DIAGNOSE ─────────────────────────────────────────────────
    pools_60x80 = [n for n in avgpool_layers if hn["layers"][n]['params']['kernel_shape'][1] == 60]
    print("pools_60x80:",pools_60x80)
    pools_30x40 = [n for n in avgpool_layers if hn["layers"][n]['params']['kernel_shape'][1] == 30]
    print("pools_30x40:",pools_30x40)
    pools_15x20 = [n for n in avgpool_layers if hn["layers"][n]['params']['kernel_shape'][1] == 15]
    print("pools_15x20:",pools_15x20)
    # 1) Model-Script schreiben
    with open(alls_path, 'w', encoding='utf-8') as f:
        
        f.write("model_optimization_flavor(optimization_level=2, compression_level=0, batch_size=4)\n")

        # Normalisierung auf den NPU verlagern (Input: float32 0-255)
        #f.write(f"normalization([{NORM_MEAN:.3f},{NORM_MEAN:.3f}], [{NORM_STD:.3f},{NORM_STD:.3f}])\n")
        #f.write(f"normalization([{NORM_MEAN:.3f}], [{NORM_STD:.3f}])\n")
        f.write(f"norm_left = normalization([{NORM_MEAN:.3f}], [{NORM_STD:.3f}], input_layer1)\n")
        f.write(f"norm_right = normalization([{NORM_MEAN:.3f}], [{NORM_STD:.3f}], input_layer2)\n")
        #f.write(f"pre_quantization_optimization(hexapod_v3_1_simplified/avgpool1, equalization=True)\n")

        ## AvgPool-Optimierung
        #if avgpool_layers:
        #    f.write(f"pre_quantization_optimization(global_avgpool_reduction, "
        #            f"layers=[{','.join(avgpool_layers)}], division_factors=[5,5])\n")
        if pools_60x80:
            f.write(f"pre_quantization_optimization(global_avgpool_reduction, "f"layers=[{','.join(pools_60x80)}], division_factors=[6,8])\n")
        if pools_30x40:
            f.write(f"pre_quantization_optimization(global_avgpool_reduction, "f"layers=[{','.join(pools_30x40)}], division_factors=[6,8])\n")
        if pools_15x20:
            f.write(f"pre_quantization_optimization(global_avgpool_reduction, "f"layers=[{','.join(pools_15x20)}], division_factors=[3,4])\n")
        
        f.write("performance_param(compiler_optimization_level=0)\n")

    print(f"📝 Model-Script geschrieben: {alls_path}")
    

    # 2) Kalibrierungsdaten laden (rohe Graustufenwerte 0-255, kein Normalisieren!)
    print(f"📊 Lade Kalibrierungsdaten ({N_CALIB} Samples)...")
    calib_l = np.load('calib_left.npy')
    calib_r = np.load('calib_right.npy')

    def prepare_calib(arr):
        # arr: [N, 1, H, W] float32, Wertebereich 0-255 → Hailo erwartet NHWC
        return arr.transpose(0, 2, 3, 1).astype(np.float32)

    n = min(N_CALIB, calib_l.shape[0], calib_r.shape[0])
    calib_data = {
        input_layers[0]: prepare_calib(calib_l[:n]),
        input_layers[1]: prepare_calib(calib_r[:n]),
    }
    print(f"   {n} Paare, Shape: {calib_data[input_layers[0]].shape}, "
          f"Range: [{calib_l[:n].min():.1f}, {calib_l[:n].max():.1f}]")

    # =====================================================================
    # NATIVE (Absoluter Rohzustand vom ONNX)
    # =====================================================================
    print("🧪 Generiere FP32-Referenzwerte (Native SDK)...")
    test_feed = {k: v[0:1] for k, v in calib_data.items()}
    with runner.infer_context(InferenceContext.SDK_NATIVE) as ctx:
        res_fp32 = runner.infer(ctx, test_feed)

    # =====================================================================
    # FP_OPTIMIZE (Nach Laden des Model-Scripts, vor Quantisierung)
    # =====================================================================
    print(f"📝 Lade Model-Script: {alls_path}")
    runner.load_model_script(alls_path)
    print("🧪 Schritt 2: Generiere FP_OPTIMIZED Referenz (Nach Fusionen/Equalization)...")
    with runner.infer_context(InferenceContext.SDK_NATIVE) as ctx:
        res_fp_opt = runner.infer(ctx, test_feed)

    # 3) Optimierung + Compile
    try:
        print(f"\n🚀 Starte Quantisierung (Optimization)...")
        runner.optimize(calib_data)

        # =====================================================================
        # QUANTIZED (Nach der 8-Bit Quantisierung)
        # =====================================================================
        print("🎮 Schritt 3: Generiere QUANTIZED Werte (Emulator)...")
        with runner.infer_context(InferenceContext.EMULATOR) as ctx:
            res_quant = runner.infer(ctx, test_feed)
    except Exception:
        print("\n💥 Fehler:")
        traceback.print_exc()
    
    # =====================================================================
    # 📊 DETAILLIERTE STATISTIK-AUSWERTUNG
    # =====================================================================
    nodes = ['disp_final', 'seg', 'disp_s8', 'normals', 'yolo_s8', 'yolo_s16', 'yolo_s32']
    
    print("\n" + "="*85)
    print(f"{'Output Node':15} | {'FP-Opt vs Native':20} | {'Quant vs FP-Opt':20} | {'Gesamt-SNR'}")
    print(f"{'':15} | {'(Struktur-Delta)':20} | {'(Quant-Rauschen)':20} | {'(End-Qualität)'}")
    print("-" * 85)

    for node in nodes:
        # Daten holen
        d_native = res_native[node]
        d_fp_opt = res_fp_opt[node]
        d_quant  = res_quant[node]

        def get_snr(ref, target):
            noise = np.var(ref - target)
            signal = np.var(ref)
            return 10 * np.log10(signal / noise) if noise > 1e-10 else 99.9

        # SNR 1: Hat das Model-Script (Equalization) die Werte verändert?
        snr_struct = get_snr(d_native, d_fp_opt)
        
        # SNR 2: Wieviel Präzision kostet die 8-Bit Wandlung?
        snr_quant  = get_snr(d_fp_opt, d_quant)
        
        # SNR Gesamt
        snr_total  = get_snr(d_native, d_quant)

        status = "✅" if snr_total > 30 else ("⚠️" if snr_total > 20 else "❌")
        
        print(f"{node:15} | {snr_struct:18.2f} dB | {snr_quant:18.2f} dB | {snr_total:10.2f} dB {status}")
    print("="*85 + "\n")    


        # ── POST-OPTIMIZE SCOPE-FIX ──────────────────────────────────
        # QAFT kann Layer im Root-Scope erzeugen → vor compile() patchen
        #print("🔧 Prüfe Scope-Zuweisung nach QAFT...")
        #hn_post = runner.get_hn_dict()
        #fixed = 0
        #for layer_name in list(hn_post.get("layers", {}).keys()):
        #    if layer_name.startswith(f"{model_name}/"):
        #        new_name = layer_name.replace(
        #            f"{model_name}/",
        #            f"{model_name}_scope1/", 1
        #        )
        #        hn_post["layers"][new_name] = hn_post["layers"].pop(layer_name)
        #        fixed += 1
        #if fixed:
        #    print(f"   ✅ {fixed} Root-Scope-Layer nach scope1 verschoben.")
        #    runner.update_hn_dict(hn_post)
        #else:
        #    print("   ✅ Kein Scope-Fix nötig.")
        # ── ENDE SCOPE-FIX ───────────────────────────────────────────

    try:
        print("⚡ Kompiliere HEF...")
        hef_buf = runner.compile()
        with open(hef_output_path, 'wb') as out:
            out.write(hef_buf)
        print(f"\n🎉 ERFOLG! HEF geschrieben: {hef_output_path}")
    except Exception:
        print("\n💥 Fehler:")
        traceback.print_exc()


# =====================================================================
# MAIN
# =====================================================================
if __name__ == "__main__":
    translate(force=False)  # force=True um HAR neu zu erstellen
    profile_model()
    quantize()
