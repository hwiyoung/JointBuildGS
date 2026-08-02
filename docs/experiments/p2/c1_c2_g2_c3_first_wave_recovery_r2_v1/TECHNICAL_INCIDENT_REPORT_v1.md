# R2 technical incident — pinned val3dity CLI tokenization

- status: `BLOCKED_BEFORE_GEOMETRY_VALIDATION`
- scientific_verdict: `null`

The pinned command used `--overlap_tol=-1.0`, `--planarity_d2p_tol=0.01`,
`--planarity_n_tol=20.0`, and `--snap_tol=0.001`. The pinned val3dity 2.6.0 image
accepts these only as separate option/value tokens. It therefore printed CLI usage
and exited before consuming the streamed CityJSONSeq as a validation job.

A synthetic CityJSONSeq check with separate tokens emitted the expected `1st-line`
and feature verdict lines. This isolates tokenization as the cause without another
scientific payload read.

Counters: first C2 unit R2 read/hash 1; completed G2 validations 0; remaining C2
reads 0; reconstruction/Roofer 0/0; raw dense 0; semantic RGB/inference 0/0; C3
optimizer updates 0; validation/held-out access 0/0.
