# Frozen review evidence

This directory owns version-separated visual review packages. Packages are not merged: each keeps its original figures and frozen manifest boundary.

- [`evidence_cards_v1/`](evidence_cards_v1/README.md) — historical v1 cards
- [`evidence_cards_v2/`](evidence_cards_v2/README.md) — historical v2 cards
- [`evidence_cards_v3/`](evidence_cards_v3/README.md) — v3 cards and frozen manifest
- [`judgment_kit_v4/`](judgment_kit_v4/README.md) — v4 judgment kit and frozen manifest

Exact old/new paths and hashes are recorded in [`../catalog/migrations/EVIDENCE_PACKAGE_PATHS.csv`](../catalog/migrations/EVIDENCE_PACKAGE_PATHS.csv). The package payload files were moved byte-for-byte.
