# Automated checks

Repository-wide tests are grouped by the implementation or workstream they protect. Reusable Stage 2/3
contracts live under `stage2/` and `stage3_readout/`; E5/C001, pilot, and Fusion contracts live under
`e5_c001/`, `pilot_1wave/`, and `fusion_w1/`; repository structure checks live under `repository/`.

Run checks in the repository containers; do not install host dependencies to satisfy a test.
