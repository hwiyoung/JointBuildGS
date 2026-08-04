# C1/C2 oracle + C3 extraction issue log v1

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
