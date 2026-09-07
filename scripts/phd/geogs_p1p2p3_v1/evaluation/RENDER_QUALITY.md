# Fixed-view native render evaluation

`render_quality.py` evaluates actual saved native RGB PNGs against all frozen
evaluation photographs. It requires a sealed renderer manifest mapping each source
photo name, evaluation index, image ID and camera ID to exact rendered-file bytes.
The caller must validate that manifest against the renderer receipt. Enumeration of
PNG filenames alone is insufficient to establish the rendered camera identity.

```python
scorer = NativeMetrics(official_source_root, offline_weight_root, device="cuda")
evaluate_render_set(split, render_records, bounds, photos_root, scorer, new_output,
                    region, condition, stage, seed, sealed_render_manifest_sha256)
```

`bounds` is a fixed world-coordinate rectangular prism, represented as three
increasing `[min, max]` pairs in x/y/z order or a dictionary with x/y/z keys. Its
coordinate frame must match the frozen camera's world-to-camera `R, t`. The ROI
projects the prism after clipping edges at positive camera depth 0.0001m, then uses
the image-clipped integer bounding rectangle. This is explicitly a **bbox** domain;
it includes pixels outside the actual projected prism silhouette. No UAS geometry,
prediction alpha, residual, exposure adjustment or output-dependent mask is used.
All pixels inside each scoring domain, including black prediction, contribute.

The module preserves original GeoGS PSNR and SSIM implementations and original
metrics.py VGG LPIPS inputs in [0,1] under `lpips_vgg_native_01`. Optional conventional
[-1,1] input results are a separate column. VGG weights are verified from the exact
offline weight manifest and loaded once. Domains smaller than32 pixels on either
side retain PSNR/SSIM but report LPIPS as not assessed. Identical-image infinite
PSNR has an explicit boolean marker and null numeric field for strict JSON.

Each expected evaluation photograph produces two rows: full frame and fixed-prism
projected bbox. Missing render, identity mismatch, shape mismatch and metric errors
remain explicit failures with null metrics. Real photo/render/absolute RGB error
montages use the same fixed0..255 error scale in PNGs. The full-frame montage marks
the frozen ROI rectangle. Per-image rows preserve source camera and image IDs.

Data-free verification in Docker passed12 tests, including exact agreement with
the original bundled VGG LPIPS function on cached weights, known PSNR, identical
images, small ROI, near-plane projection, black-pixel retention, missing render,
pose/shape mismatch and output preservation. Log:
`runtime/render_quality_tests_v1.log` under the external task root. These tests are
implementation checks; they are not regional render-quality results.

`scientific_verdict: null`
