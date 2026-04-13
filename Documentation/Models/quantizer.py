import os
import numpy as np
import traceback
from hailo_sdk_client import ClientRunner

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
        f.write("performance_param(compiler_optimization_level=0)\n")
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

    print(f"📝 Model-Script geschrieben: {alls_path}")
    runner.load_model_script(alls_path)

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

    # 3) Optimierung + Compile
    try:
        print(f"\n🚀 Starte Optimierung...")
        runner.optimize(calib_data)

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
    quantize()
