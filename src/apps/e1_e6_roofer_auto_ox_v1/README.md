# E1-E6 Roofer reference auto O/X viewer

This additive browser layer presents building-by-condition binary Roofer/LoD2
development labels computed from sealed E1-E6 outputs. It does not train a
model or run Roofer. The primary threshold is O50; O60/O70/O80 are sensitivity
views. `REVIEW` is not an outcome. `NA` is reserved for a missing independent
evaluation reference, while a missing prediction is `X`.

G3 first measures whole-roof support completeness/correctness/quality and then
requires one-to-one agreement of major roof-plane count, direction, and height.
This prevents a gable collapsed to a single slope from passing merely because
its footprint is covered.

`official_PASS_usable` and `scientific_verdict` remain null.
