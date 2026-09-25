# Original Graph Cities algorithm provenance

`atlas/` preserves the original MIT-licensed fixed-point edge peeling source at
commit `9b805eff7a2d160f366117ee2a754ba1479bb600`. Its license and unchanged source
hashes are included. The application implements the same repeated maximum-core
edge peeling with igraph in `app/pipeline/fixed_points.py`; no compiler or sibling
checkout is required to run that implementation.

Wave/fragment behavior is checked against the original Graph Cities
`ewave_next` executable from upstream commit
`483c6cbf426511abc86aa950c30b3e8693b6cf6d`. That checkout distributes executables
but omits the C++ source for this stage. We do not misrepresent the Python port
as copied C++ source or substitute Leiden for its output. The original
wave-decomposition license is preserved as `GRAPH_CITIES_LICENSE.md`.

`tests/fixtures/graph_cities/original.json` contains original outputs and binary
SHA-256 fingerprints for 31 graphs. Tests compare edge peel, wave, fragment,
and connected wave partitions. Fixture generation is available through
`scripts/generate_graph_cities_reference.py --reference-root <original-wave-decomposition> --output tests/fixtures/graph_cities/original.json`.
Only that development command needs an original checkout and Docker. Normal
application execution and tests use files inside this repository exclusively.

The port repeatedly removes edges whose endpoints belong to the current maximum
core. Within each resulting edge layer, a wave starts at the remaining minimum
degree; its successive fragments remove vertices that fall strictly below that
threshold. Connected fixed-point edge components define buildings, with vertex
memberships permitted to overlap across layers. Input self-loops and repeated or
reversed undirected edges are discarded; isolated input vertices are retained
separately.

These are core algorithm parity checks, not a claim that integration, geometry,
or 100k end-to-end application verification is complete.
