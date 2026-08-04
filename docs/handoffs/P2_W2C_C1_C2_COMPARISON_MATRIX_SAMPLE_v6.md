# P2 C1/C2 comparison matrix sample v6 output-cap recovery — ACTIVE

- task_id: `P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v6`
- handoff_id: `P2-W2C-C1-C2-COMPARISON-MATRIX-SAMPLE-v6`
- source: exact sealed C1/C2 census and the v5 visual-correction renderer
- exact renderer source commit: `da0e106bd2d4b087f028febdd5ae508c01f9e245`
- activation basis: direct human instruction to continue without a separate Work Host visit
- scientific_verdict: `null`

v5 produced all expected visual files but stopped before finalization because the measured
378,580,147-byte payload exceeded its preregistered 250,000,000-byte cap. The v5 partial
is preserved without modification. v6 changes only the fresh namespace, raises the cap to
450,000,000 bytes using the observed payload as the engineering basis, and adds one
legible five-row by four-column PNG case sheet per selected building.

Current UAS LiDAR/RGB remain same-frame with zero vertical shift. The 45.7 m translation
is applied exactly once only to the evaluation-only 2022 LoD2 RoofSurface roofline.
Roofer, G2, GS training and metric recomputation remain zero in this reuse renderer;
official G3/G4/PASS and `scientific_verdict` remain null.
