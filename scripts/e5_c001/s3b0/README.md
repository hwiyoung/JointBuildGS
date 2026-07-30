# E5 C001 S3B0 drivers

This directory is the reusable-code entry point for the S3B0 alpha, seed, height-sweep, mono-reliability, semantic, and gate workflow. The seven Python modules and seven shell drivers move together because they share `e5_c001_s3b0_common.py`.

Tests live in `tests/experiments/e5_c001_s3b0/`. Dependencies whose exact phase path is locked by adjacent S3A′ or historical workflows remain in `phases/p2-gsjso/scripts/`.
