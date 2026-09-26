"""Regenerate development-only parity fixtures using original Linux executables.

The application and test suite consume the saved JSON and never need this
checkout, Docker execution, or access to upstream repositories.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import itertools
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile


def cases():
    yield "edge", 2, [(0, 1)]
    yield "path", 9, [(i, i + 1) for i in range(8)]
    yield "star", 9, [(0, i) for i in range(1, 9)]
    yield "cycle", 8, [(i, (i + 1) % 8) for i in range(8)]
    yield "clique", 6, list(itertools.combinations(range(6), 2))
    yield "triangles_pendant", 7, [(0, 1), (0, 2), (1, 2), (2, 3), (3, 4), (3, 5), (4, 5), (5, 6)]
    yield "overlapping_layers", 6, [*itertools.combinations(range(4), 2), (3, 4), (4, 5), (3, 5)]
    yield "disconnected", 9, [*itertools.combinations(range(4), 2), (4, 5), (5, 6), (6, 7), (7, 8)]
    for seed in range(24):
        rng = random.Random(seed)
        n = 6 + seed
        p = (0.15, 0.35, 0.7)[seed % 3]
        edges = [(u, v) for u, v in itertools.combinations(range(n), 2) if rng.random() < p]
        if edges:
            yield f"random_{seed}", n, edges


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", default="pgvector/pgvector:pg16")
    args = parser.parse_args()
    binaries = ("preproc", "buffkcore", "ewave_next")
    checksums = {name: hashlib.sha256((args.reference_root / name).read_bytes()).hexdigest() for name in binaries}
    wave_map_source = args.reference_root / 'scripts/freqUsed/bucket_loop_int.py'
    module = ast.parse(wave_map_source.read_text())
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'getWaveMap')
    formula = next(node for node in function.body if isinstance(node, ast.For) and ast.unparse(node.iter) == 'wsizes.items()')
    formula_code = compile(ast.Module(body=[formula], type_ignores=[]), str(wave_map_source), 'exec')
    results = []
    with tempfile.TemporaryDirectory(prefix="graph-city-oracle-") as directory:
        root = Path(directory)
        for name in binaries:
            shutil.copyfile(args.reference_root / name, root / name)
            (root / name).chmod(0o755)

        def run(*command):
            subprocess.run(
                ["docker", "run", "--rm", "--ulimit", "core=0", "--network", "none",
                 "-v", f"{root}:/work", "-w", "/work", "--entrypoint", "/bin/bash",
                 args.image, "-c", 'exec "$@"', "oracle", *map(str, command)],
                check=True, capture_output=True, timeout=60,
            )

        for name, n, input_edges in cases():
            path = root / name
            (path / f"{name}_layers").mkdir(parents=True)
            (path / f"{name}_waves").mkdir()
            edges = sorted({tuple(sorted(edge)) for edge in input_edges})
            (path / f"{name}.txt").write_text("".join(f"{u}\t{v}\n" for u, v in edges))
            run("./preproc", f"{name}/{name}.txt", len(edges), "true", len(edges) * 2, 100000)
            vertices = (path / f"{name}.cc").stat().st_size // 8
            max_vertex = max(max(edge) for edge in edges)
            run("./buffkcore", f"{name}/{name}.bin", len(edges) * 2, vertices, f"{name}/{name}.cc", max_vertex, 100000)
            layers = json.loads((path / f"{name}-layer-info.json").read_text())
            labels = {}
            wave_labels = {}
            profiles = []
            source_levels = {}
            for file in sorted((path / f"{name}_layers").glob("*.csv")):
                for row in file.read_text().splitlines():
                    u, v, peel = map(int, row.split(","))
                    if u < v:
                        labels[(u, v)] = peel
            for peel, info in layers.items():
                if int(peel) == 0:
                    continue
                suffix = info["file_suffix"]
                files = list((path / f"{name}_layers").glob(f"*-{suffix}.csv"))
                if not files:
                    files = [path / f"{name}_layers" / f"layer-{suffix}.csv"]
                layer_file = files[0].relative_to(root)
                run("./ewave_next", f"{name}/{name}_layers", layer_file, peel,
                    info["edges"] * 2, info["vertices"], max_vertex, 100000)
                for row in (path / f"{name}_waves" / f"layer-{peel}-waves.csv").read_text().splitlines():
                    u, v, wave, component, fragment = map(int, row.split(","))
                    if u < v:
                        wave_labels[(u, v)] = [wave, component, fragment]
                source_levels[int(peel)] = {v: (w, f) for v, w, f in
                    (map(int, row.split(',')) for row in (path / f'{name}_waves' / f'layer-{peel}-wave-sources.csv').read_text().splitlines())}
            # Inputs come from original executable edge/source labels. Evaluate
            # the original numerical loop; never import the application port.
            for peel in sorted(set(labels.values())):
                adj = {}
                for (u, v), layer in labels.items():
                    if layer == peel:
                        adj.setdefault(u, set()).add(v)
                        adj.setdefault(v, set()).add(u)
                unseen = set(adj)
                while unseen:
                    members = {min(unseen)}
                    pending = list(members)
                    unseen.difference_update(members)
                    while pending:
                        vertex = pending.pop()
                        neighbors = adj[vertex] & unseen
                        unseen.difference_update(neighbors)
                        members.update(neighbors)
                        pending.extend(neighbors)
                    owned = [(u,v) for (u,v), layer in labels.items() if layer == peel and u in members]
                    wsizes = {}
                    counts = {}
                    levels = source_levels[peel]
                    for wave in sorted({wave_labels[edge][0] for edge in owned}):
                        wave_edges = [edge for edge in owned if wave_labels[edge][0] == wave]
                        vertices = {v for edge in wave_edges for v in edge}
                        wsizes[wave] = {'s': sum(levels[v] == (wave,0) for v in members),
                                        'ss': sum(levels[v][0] == wave for v in members),
                                        'v': len(vertices), 'e': len(wave_edges)}
                    for u,v in owned:
                        key = tuple(sorted((levels[u][0], levels[v][0])))
                        counts[key] = counts.get(key,0) + 2
                    namespace = {'wsizes': wsizes, 'counts': counts, 'data': {}}
                    exec(formula_code, namespace)
                    profiles.append({'peel': peel, 'vertices': sorted(members), 'waves': namespace['data']})
            results.append({"name": name, "vertex_count": n, "edges": edges,
                            "labels": [[u, v, labels[(u, v)], *wave_labels[(u, v)]] for u, v in edges], 'wave_profiles': profiles})
            print(f"{name}: {n} vertices, {len(edges)} edges", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"binary_sha256": checksums, 'wave_map_sha256': hashlib.sha256(wave_map_source.read_bytes()).hexdigest(), "cases": results}, indent=2) + "\n")


if __name__ == "__main__":
    main()
