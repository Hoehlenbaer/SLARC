"""
remove_se_blocks.py — Entfernt Squeeze-and-Excite Blöcke aus einem ONNX-Modell.

Strategie: NUR die SE-Mul-Nodes bypassen (Output → Main-Input umleiten).
Die verwaisten SE-Nodes (Pool, FC, Sigmoid) werden von onnxsim entfernt.

Usage:
    python remove_se_blocks.py input.onnx output.onnx
"""

import onnx
import sys
import os
import subprocess


def find_se_multiply_nodes(graph):
    """
    Findet alle Mul-Nodes die das Ende eines SE-Blocks sind.
    Erkennung: Mul-Node wo ein Input über Sigmoid/HardSigmoid ← ... ← AvgPool kommt.
    """
    output_to_node = {}
    for node in graph.node:
        for out in node.output:
            output_to_node[out] = node

    def trace_has_pool(node, depth=8):
        if depth <= 0:
            return False
        if node.op_type in ('GlobalAveragePool', 'ReduceMean', 'AveragePool'):
            return True
        for inp in node.input:
            if inp in output_to_node:
                if trace_has_pool(output_to_node[inp], depth - 1):
                    return True
        return False

    se_muls = []
    for node in graph.node:
        if node.op_type != 'Mul':
            continue

        for i, inp in enumerate(node.input):
            if inp not in output_to_node:
                continue
            src = output_to_node[inp]
            # Sigmoid, HardSigmoid, oder Clip (HSigmoid-Variante)
            if src.op_type in ('Sigmoid', 'HardSigmoid', 'Clip', 'Div', 'Mul'):
                if trace_has_pool(src, depth=10):
                    se_muls.append({
                        'mul_node': node,
                        'main_input': node.input[1 - i],  # der andere Input
                        'se_input_idx': i,
                    })
                    break  # nur einmal pro Mul

    return se_muls


def remove_se_blocks(input_path, output_path):
    print(f"📥 Lade: {input_path}")
    model = onnx.load(input_path)
    graph = model.graph

    print(f"   Nodes vorher: {len(graph.node)}")

    # 1. Finde SE-Mul-Nodes
    se_muls = find_se_multiply_nodes(graph)
    print(f"   🔍 {len(se_muls)} SE-Blöcke gefunden:")

    for i, se in enumerate(se_muls):
        mul = se['mul_node']
        print(f"      SE {i+1}: Mul '{mul.name}' — bypass to: {se['main_input']}")

    if not se_muls:
        print("   ⚠️  Keine SE-Blöcke gefunden!")
        return

    # 2. NUR die Mul-Outputs umleiten — KEINE Nodes entfernen!
    #    Jeder Consumer des Mul-Outputs bekommt stattdessen den Main-Input
    for se in se_muls:
        mul_node = se['mul_node']
        mul_output = mul_node.output[0]
        main_input = se['main_input']

        # In allen nachfolgenden Nodes ersetzen
        for node in graph.node:
            if node == mul_node:
                continue
            for j, inp in enumerate(node.input):
                if inp == mul_output:
                    node.input[j] = main_input
                    print(f"         → {node.name}: input[{j}] umgeleitet")

        # Auch in Graph-Outputs prüfen
        for out in graph.output:
            if out.name == mul_output:
                out.name = main_input

    # 3. Entferne NUR die Mul-Nodes selbst (nicht den SE-Pfad!)
    mul_ids = {id(se['mul_node']) for se in se_muls}
    remaining = [n for n in graph.node if id(n) not in mul_ids]

    removed = len(graph.node) - len(remaining)
    del graph.node[:]
    graph.node.extend(remaining)
    print(f"\n   🗑️  {removed} Mul-Nodes entfernt")
    print(f"   Nodes nachher: {len(graph.node)} (vor onnxsim)")

    # 4. Speichern (mit toten SE-Nodes — onnxsim räumt auf)
    temp_path = output_path.replace('.onnx', '_raw.onnx')
    onnx.save(model, temp_path)
    print(f"   💾 Zwischenspeicher: {temp_path}")

    # 5. onnxsim entfernt die verwaisten SE-Nodes
    print(f"\n   🔧 Bereinige mit onnxsim...")
    try:
        result = subprocess.run(
            ['python', '-m', 'onnxsim', temp_path, output_path],
            check=True, capture_output=True, text=True
        )
        # Finales Modell laden und Stats anzeigen
        final = onnx.load(output_path)
        print(f"   ✅ Bereinigt: {len(final.graph.node)} Nodes")

        orig_size = os.path.getsize(input_path) / 1e6
        new_size = os.path.getsize(output_path) / 1e6
        print(f"\n   📊 Original: {orig_size:.1f} MB → Ohne SE: {new_size:.1f} MB")
        print(f"      Ersparnis: {orig_size - new_size:.1f} MB ({(1 - new_size / orig_size) * 100:.0f}%)")

        # Cleanup temp
        os.remove(temp_path)

    except subprocess.CalledProcessError as e:
        print(f"   ⚠️  onnxsim fehlgeschlagen: {e.stderr}")
        print(f"       Verwende unbereinigtes Modell: {temp_path}")
        # Fallback: temp als output umbenennen
        os.rename(temp_path, output_path)

    except FileNotFoundError:
        print("   ⚠️  onnxsim nicht installiert. pip install onnxsim")
        os.rename(temp_path, output_path)

    # 6. Validierung
    try:
        final_model = onnx.load(output_path)
        onnx.checker.check_model(final_model)
        print("   ✅ ONNX Validierung OK")
    except Exception as e:
        print(f"   ⚠️  Validierung: {e}")

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python remove_se_blocks.py input.onnx output.onnx")
        print("   z.B.: python remove_se_blocks.py onnx_split/hexapod_backbone_simplified.onnx onnx_split/hexapod_backbone_no_se.onnx")
        sys.exit(1)

    remove_se_blocks(sys.argv[1], sys.argv[2])
