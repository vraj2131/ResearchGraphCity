"""Capture numeric output from original spiral/frustum code without plotting.

Only the Matplotlib drawing expression is omitted from the spiral AST. Numeric
statements are executed unchanged; source hashes and input descriptors are saved.
"""
import argparse
import ast
from contextlib import redirect_stdout
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spiral_path = args.reference_root / "scripts/freqUsed/spiral_min.py"
    building_path = args.reference_root / "scripts/freqUsed/building.py"
    bucket_path = args.reference_root / "scripts/freqUsed/bucketingWithFP2_ve.py"
    bucket_text = bucket_path.read_text()
    snippet = bucket_text[bucket_text.index("cmpt_group_th ="):bucket_text.index("print('len(thresholds)")]
    inputs = [
        {"id": "B1", "peel": 4, "node_count": 12, "edge_count": 32, "max_wave_vertices": 10, "first_wave_sources": 4, "wave_count": 3},
        {"id": "B2", "peel": 2, "node_count": 9, "edge_count": 13, "max_wave_vertices": 8, "first_wave_sources": 3, "wave_count": 2},
        {"id": "B3", "peel": 1, "node_count": 3, "edge_count": 2, "max_wave_vertices": 3, "first_wave_sources": 2, "wave_count": 1},
        {"id": "B4", "peel": 2, "node_count": 6, "edge_count": 9, "max_wave_vertices": 6, "first_wave_sources": 4, "wave_count": 1},
    ]
    namespace = {"math": math, "data": {"vertices": 100}, "g_components": {item["id"]: {"links": item["edge_count"]} for item in inputs}}
    with redirect_stdout(io.StringIO()):
        exec(snippet, namespace)
    thresholds = namespace["thresholds"]
    datas = {}
    names = {}
    for index, item in enumerate(inputs):
        name = f"wavemap_{item['peel']}_{index}_{item['wave_count']}.json"
        names[name.removesuffix(".json")] = item["id"]
        bucket = int(np.searchsorted(thresholds, item["edge_count"], side="right"))
        datas.setdefault(bucket, {})[name] = {
            "peel": item["peel"], "verts": item["node_count"], "edges": item["edge_count"],
            "rad": item["max_wave_vertices"], "base": math.log2(item["first_wave_sources"] + 1),
            "fragNum": item["wave_count"], "fragNeg": 0, "fragPos": 0, "fragBucket": [1], "buckSize": 1, "duplicate": 1,
        }
    tree = ast.parse(spiral_path.read_text())
    start = next(i for i, statement in enumerate(tree.body) if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "max_rad" for t in statement.targets))
    tree.body = tree.body[start:]

    class OmitDrawing(ast.NodeTransformer):
        def visit_Expr(self, node):
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "add_patch":
                return None
            return node

    tree = ast.fix_missing_locations(OmitDrawing().visit(tree))
    namespace = {name: getattr(math, name) for name in ("log2", "sqrt", "cos", "sin", "pi")}
    namespace["datas"] = datas
    capture = io.StringIO()
    with redirect_stdout(capture):
        exec(compile(tree, str(spiral_path), "exec"), namespace)
    output = []
    for line in capture.getvalue().splitlines()[::2]:
        fields = line.split()
        output.append({"id": names[fields[0]], "x": float(fields[1]), "z": float(fields[2]), "rotation_degrees": float(fields[3]), "radius": float(fields[4])})
    tree = ast.parse(building_path.read_text())
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "frustumHeight"]
    namespace = {"pi": math.pi}
    exec(compile(tree, str(building_path), "exec"), namespace)
    frustums = [{"volume": v, "upper": u, "lower": l, "height": namespace["frustumHeight"](v, u, l)} for v, u, l in [(3, 0, math.log2(5)), (4, 2, 1), (1, 0, math.log2(3))]]
    args.output.write_text(json.dumps({"source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (spiral_path, bucket_path, building_path)}, "vertex_count": 100, "inputs": inputs, "thresholds": thresholds, "spiral": output, "frustums": frustums}, indent=2) + "\n")


if __name__ == "__main__":
    main()
