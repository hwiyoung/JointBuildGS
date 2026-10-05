# Actual matched case figures after evaluation

Run `case_figures.py` only after `summarize.py` has completed and sealed its
evaluation-array and table identities. The helper validates candidate/configuration
hashes, all promoted summary files, and each consumed evaluated NPZ/JSON/photo/render
before use. It never opens raw UAS or recomputes geometry/depth/evaluation scores.

Sections are fixed-width bands of the existing evaluated surface/source samples,
not triangle-plane intersection curves. The interactive viewer can separately
show every evaluator-clipped triangle without simplification; see
[display provenance](DISPLAY_CONTRACT.md). That display export never enters scoring.

Inside the isolated CPU Docker runtime, without a `/reference` or broad artifact
mount:

```bash
python /audit/case_figures.py --task /task --viewer-manifest-v2 \
  --runtime-layout /task/contracts/runtime_layout_allocator_v2.json \
  --repeat-contract /task/contracts/supplemental_repeat_v1.json \
  --resource-contract /task/contracts/extraction_resource_v3.json
```

The new output owner is `task/evaluation/cases_v1/`; any existing target is rejected.
The effective figure configuration, package versions, script/dependency hashes and
every actual input hash are recorded. Failures preserve their partial output and a
failure receipt. A prior completed output is never edited on a rejected rerun.

Each selected case produces two aligned section rows, X and Y, through the frozen
case XY center. Width is0.5m and horizontal extent is5m, clipped to the regional
prism; all columns retain the full fixed regional Z range and identical axes.
Under resource_v3, `sections.png` has four columns: supplied ALS-prior surface
samples, original MVS point samples, native final1024 and changed final1024 surface
samples. Separate `sections_anchor_refinement512.png` has five columns: the same
prior/MVS sources, the shared exact anchor8000 extracted at512, native final512 and
changed final512. Both figures overlay the exact same observed reference samples.
Cases remain selected by the frozen main1024 raw-distance rule;512 results do not
rerank cases. Legacy exports without resource_v3 retain the original five-column
anchor/native/changed comparison. No point resampling or candidate-derived axis
selection occurs. Pointsets and surface
samples are labelled distinctly. Reference-absent sections and absent reconstructions
remain explicit; an empty0.5m selection cell is distinguished from any reference
samples that exist in the wider5m figure window.

The optical comparison projects the fixed5m XY × full-regional-Z case prism into
every frozen evaluation camera and selects the largest image-clipped bbox area,
breaking ties by source image name. This selection uses calibration and the fixed
case window; it does not score images, use prediction alpha or assume visibility.
The selected camera list, areas, pose identity and identical integer bbox are saved.
The original photograph and native/changed saved RGB renders use exactly that crop,
without exposure fitting, masks or resizing. Black prediction pixels remain. If no
evaluation camera intersects the prism, optical comparison is explicitly unavailable.

Outputs include `sections.png`, resource_v3 `sections_anchor_refinement512.png`,
`photo_render_crop.png`, individual original-pixel
crops, per-case `metadata.json`, and `index.json` with paths/status/provenance.
Optional `evaluation/viewer/manifest_v2.json` adds their links while retaining
`manifest.json` byte-for-byte. Browser rendering and scientific case interpretation
still require review of actual regional outputs. Nine synthetic Docker tests cover
the sealed end-to-end path, common axes/reference membership, selection/crop rules,
missing reference, empty reconstruction, changed bytes and mismatched poses.

`scientific_verdict: null`
