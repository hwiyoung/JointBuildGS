#!/usr/bin/env python3
"""Reuse the audited raycaster and expand fused normals to the full frozen depth support."""
from pathlib import Path


REPO = Path("/workspace/JointBuildGS")
SOURCE = REPO / "scripts/p2/e3_local_4906982_fused_surface_normal_v1/prepare_targets.py"
text = SOURCE.read_text()
replacements = (
    ("P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1", "P2-E3-LOCAL-4906982-FUSED-DN-COMMON-SUPPORT-v1"),
    ("e3_local_4906982_fused_surface_normal_v1", "e3_local_4906982_fused_dn_common_support_v1"),
    ("data/fused_vis_conf_fused_normal_colmap_crop", "data/fused_dn_common_support_colmap_crop"),
    ("data/fused_surface_normal_world", "data/fused_surface_normal_common_support_world"),
    ("fused_surface_normal_target_definition.json", "fused_dn_common_support_target_definition.json"),
    ("raw_native_fused_metrics.csv", "fused_dn_common_support_metrics.csv"),
    ("target_ok = prior_raw_ok & fused_ok", "target_ok = support & fused_ok"),
    ('"normal_mask_exactly_matches_raw_normal_arm": target_count == prior_target_count,', '"normal_mask_exactly_matches_depth_support": target_count == support_count,'),
    ('"unit_normal_coverage_on_frozen_normal_mask": target_count / max(prior_target_count, 1) >= float(gate["minimum_same_normal_mask_fraction"]),', '"unit_normal_coverage_on_frozen_depth_support": target_count / max(support_count, 1) >= float(gate["minimum_same_normal_mask_fraction"]),'),
    ('"normal_mask": "exact prior FUSED_VIS_CONF_MVS_NORMAL nonzero target mask; only normal values change",', '"normal_mask": "exact frozen FUSED_VIS_CONF positive-finite depth support; fused depth and fused normal share one mask",'),
)
for old, new in replacements:
    if old not in text:
        raise RuntimeError(f"upstream prepare contract drift: {old}")
    text = text.replace(old, new)
text = text.replace(
    'NATIVE_NORMAL = ROOT / "native_dmap_normal"',
    'NATIVE_NORMAL = AR / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1/native_dmap_normal"',
)
text = text.replace(
    'extractor_binary = ROOT / "control/bin/extract_native_normal"',
    'extractor_binary = AR / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1/control/bin/extract_native_normal"',
)
exec(compile(text, str(SOURCE), "exec"), {"__name__": "__main__", "__file__": __file__})
