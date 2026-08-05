# MVS native textured mesh preflight issues

## P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v1

- State: technically failed before densification.
- Time: 2026-08-05T07:37:26Z to 2026-08-05T07:37:30Z.
- Failure: OpenMVS loaded all 937 camera poses, then could not read the first
  image because the sealed `scene.mvs` resolves images below
  `/workspace/data/work/mvs/colmap_dense/images`, which was not mounted in the
  isolated recovery container.
- Effect: no depth-map fusion, recovered dense PLY, dense MVS, mesh, refinement,
  or texture output was produced. The sealed source scene and retained dense PLY
  were mounted or accessed read-only and were not changed.
- Recovery: `P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2` adds the missing read-only
  `/workspace/data` mount without changing any DensifyPointCloud parameter.
- Scientific verdict: null.

## P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2

- State: technically complete; exact dense-PLY equality gate failed.
- Time: 2026-08-05T07:38:36Z to 2026-08-05T07:57:42Z.
- Inputs and controls: the sealed 937-camera `scene.mvs`, retained dense PLY,
  pinned OpenMVS image, and the original densification parameters were used.
- Recovered outputs: 924 depth maps fused into 43,926,567 points; the recovered
  dense MVS is 1,329,728,524 bytes and retains the point-view lineage required by
  OpenMVS mesh reconstruction.
- Equality result: the retained PLY has 43,942,554 points, so the recovered PLY
  has 15,987 fewer points (`-0.0363815903827529%`). The PLY SHA-256 values and
  order-independent point-hash summaries also differ. Point order is not stable:
  zero index-aligned XYZ rows match, so index-aligned distance values are not a
  valid geometry-equivalence measure.
- Distribution observations: all points are finite. Coordinate means differ by
  approximately `(+0.262, -0.034, -0.015)` in the scene coordinate system, while
  the extreme bounding-box tails also differ.
- Gate action: stopped before `ReconstructMesh`, `RefineMesh`, and `TextureMesh`.
  No geometry-equivalence or scientific verdict is asserted.
- Scientific verdict: null.
