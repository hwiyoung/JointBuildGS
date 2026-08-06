# Roofer O/X human-review lock v1

- Criterion ID: `P2-ROOFER-HUMAN-OX-v1`
- Status: `USER APPROVED FROZEN — 2026-08-06`
- Scope: non-confirmatory technical-development visual review
- Human reviewer: 김휘영
- Scientific verdict: `null`

## Frozen rule

The review unit is one `building × condition` Roofer output. The web reviewer exposes
the frozen point evidence, footprint, Roofer result and technical missingness, and the
human reviewer records exactly one of:

- blank: not reviewed;
- `O`: the displayed Roofer result is accepted for this technical-development review;
- `X`: the displayed Roofer result is rejected. Missing Roofer output is reviewed as `X`.

No mandatory defect taxonomy or numerical human score is used. A free-text note is
optional. Roofer existence, val3dity and point counts remain advisory provenance and do
not automatically write the human O/X field.

Each condition is judged independently before paired transitions are derived. When C3
is available, `C2=X → C3=O` is a GS rescue and `C2=O → C3=X` is a GS regression. Both
directions and the unchanged cells are retained. C1 is an upper-baseline branch, not a
ground-truth label.

This O/X screen does not replace G0–G4, does not define numerical G3/G4 thresholds and
does not populate official `PASS_usable`. All 199 population rows, including missing
outputs, remain visible in later census reporting.

The machine-readable authority is
`configs/p2/c1_c2_shared_footprint_199_v3/roofer_ox_review_v1.json`.
