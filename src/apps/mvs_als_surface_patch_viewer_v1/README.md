# MVS–Existing ALS surface-patch viewer v1

This offline WebGL viewer compares two representations of the same frozen
relation-core rows:

- **before** — the one-pass five-class M3C2/support relation label;
- **after** — the relation label aggregated only after source-separated,
  locally connected surface-patch generation.

It also exposes patch UID, source-family, patch-status, core/patch metadata,
and click-to-highlight inspection.  The source point clouds are byte-verified
copies of the already-built relation viewer display assets.  The patch
membership and summary are verified against the upstream patch artifact
manifest and validation receipt.

Build and validate in Docker:

```bash
scripts/phd/mvs_als_surface_patch_viewer_v1/build_host.sh
```

Serve the separate viewer on port 8892:

```bash
scripts/phd/mvs_als_surface_patch_viewer_v1/serve.sh
```

The display is a qualitative development diagnostic.  It does not recompute
M3C2 and does not decide temporal change, source correctness, source authority,
or scientific performance.  `scientific_verdict` remains `null`.
