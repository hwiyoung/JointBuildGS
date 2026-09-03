# Source-decision evidence viewer v1 (stage-by-stage, port 8892)

This offline WebGL viewer shows the results of the source-decision method **stage by stage**
(design v2 §10.7): it is a qualitative diagnostic, not a decision tool.

| tab | what it shows | data |
|---|---|---|
| 장면 | the whole scene: both source clouds, the frozen one-pass M3C2 relation cores (the 3D-a sample), and the **"MVS empty, prior present" zones** — class-4 cores at least 3 m above the local ground, clustered; a list with "이동" buttons jumps the camera to each cluster. These are H_M candidate sites for a new prism, not a method input. | relation viewer assets + `hm_zones` computed at build time |
| 1 영역 | per prism: the 0.5 m XY-column pairs of the surface patches (pairing state, dz, rough) | T1 evidence bank cells (pairing fields) |
| 2 증거 T1 | per prism: 3D-a signed distance, 3D-b ray fractions, 2D-c texture, r | `PHD-EVIDENCE-BANK-*` |
| 2 증거 T2 | per prism: warp-NCC S_M / S_P, paired Δ and f(M>P) / f(P>M), power, pair counts, visibility, the 1 m vertical-shift control, 2D-b edges, r_t2; **guided review cases A–F** (expectation / channel / how to check, mirrored on H_M sites), warp chips on click, the current TOP image overlay | `PHD-WARP-NCC-*` |

Prisms are listed in the config (`prisms`), each pinned to its evidence-bank and warp-ncc
artifact manifest + validation receipt; the builder byte-verifies every upstream and the
chip digests, and the validator re-checks strides, hashes, chips, images and the H_M zone
assets. The rejected T0 region-unit layer was removed from the viewer (its artifact remains).

Build and validate in Docker:

```bash
scripts/phd/mvs_als_surface_patch_viewer_v1/build_host.sh
```

Serve on port 8892:

```bash
scripts/phd/mvs_als_surface_patch_viewer_v1/serve.sh
```

Nothing shown here decides temporal change, source correctness, source authority, or
scientific performance. `scientific_verdict` remains `null`.
