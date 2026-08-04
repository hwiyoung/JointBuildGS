# C1/C2 oracle + C3 extraction issue log v1

## CLOSED — C3 extraction lazy CUDA cache path

Recovery v2 completed all four independent Roofer operations, then exported the full
C3-1 Gaussian PLY and stopped at the first surface render because gsplat attempted to
build its lazy CUDA extension under unwritable `/.cache`. No C3 surface or mesh was
produced, and GS training remained zero. Recovery v3 verifies and inherits the exact
C1/C2 inputs, footprints, terminals and CityJSONSeq outputs without another Roofer
invocation, then mounts a task-local writable Torch/CUDA cache for both C3 conditions.

## CLOSED — zero-class6 pre-Roofer statistic

Recovery v1 reached the expected `DEBY_LOD2_4907177/C2 class-6=0` condition but tried
to compute the minimum and maximum Z of that empty array. It stopped before writing
prepared records and before every Roofer/C3 extraction invocation. The preserved
Recovery-v1 partial is empty. Recovery v2 records both height extrema as null and
continues to the already-frozen `PRE_ROOFER_REFERENCE_ID_ALIGNMENT_FAILURE` path.

## CLOSED — local launcher precreated bind-mount root

The first direct Experiment Host invocation stopped before C1/C2 preparation because
`run_host.sh` precreated the `.partial` directory for a Docker bind mount while the
producer rejected any existing output path. The preserved partial is empty. Roofer,
C3 extraction, G2, GS training and metric invocation counts were all zero. Recovery v1
uses a fresh add-once namespace and permits only an existing empty bind-mount root;
any non-empty root still fails closed.

## OPEN — DEBY_LOD2_4907177 reference/ID alignment

Read-only raw-source preflight found only 25 deterministic 0.2 m C1 class-6 voxels and
0 C2 class-6 voxels inside the 2022 LoD2 `GroundSurface` XY. The other two buildings
have more than 134k class-6 voxels per condition. `4907177` is therefore fixed as two
`PRE_ROOFER_REFERENCE_ID_ALIGNMENT_FAILURE` records. Roofer is not invoked and no
other building's output is substituted. This is not a C1/C2 or Roofer execution failure.

Resolution requires an independently reviewed 2022↔2024 identity/epoch association;
it is outside this execution's authority.

## CLOSED — focused test runner mismatch

The pinned project image does not install `pytest`, so the first focused-test command
ended before test collection with `No module named pytest`. The new focused test was
converted to the repository-compatible `unittest` form. Five tests then passed in the
same pinned image. No project dependency was installed or changed.
