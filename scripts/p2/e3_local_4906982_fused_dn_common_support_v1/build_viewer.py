#!/usr/bin/env python3
"""Publish an add-only viewer comparing fixed and common fused-normal support."""
from pathlib import Path


source = Path("/workspace/JointBuildGS/scripts/p2/e3_local_4906982_fused_surface_normal_v1/build_viewer.py")
text = source.read_text()
old_arms = '''ARMS = {
    "FUSED_VIS_CONF": (ROOT, "Depth only: fused depth + MVC/NC"),
    "FUSED_VIS_CONF_MVS_NORMAL": (RAW_ROOT, "+ raw COLMAP normal"),
    "FUSED_VIS_CONF_FUSED_NORMAL": (ROOT, "+ fused mesh surface normal"),
}'''
new_arms = '''ARMS = {
    "FUSED_VIS_CONF": (ROOT, "Depth only: fused depth + MVC/NC"),
    "__FIXED_ARM__": (RAW_ROOT, "+ fused normal on raw-valid mask"),
    "__COMMON_ARM__": (ROOT, "+ fused normal on common support"),
}'''
if old_arms not in text:
    raise RuntimeError("viewer arm contract drift")
text = text.replace(old_arms, new_arms)
old_raw = 'RAW_ROOT = AR / "phase-payloads/p2/e3_local_4906982_mvs_normal_ablation_v1/P2-E3-LOCAL-4906982-MVS-NORMAL-ABLATION-v1"'
new_raw = 'RAW_ROOT = Path("__FIXED_ROOT__")'
if old_raw not in text:
    raise RuntimeError("viewer comparator contract drift")
text = text.replace(old_raw, new_raw)
for old, new in (
    ("P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1", "P2-E3-LOCAL-4906982-FUSED-DN-COMMON-SUPPORT-v1"),
    ("e3_local_4906982_fused_surface_normal_v1", "e3_local_4906982_fused_dn_common_support_v1"),
    ("FUSED_VIS_CONF_FUSED_NORMAL", "FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT"),
    ("configs/p2/e3_local_4906982_fused_surface_normal_v1/viewer.yaml", "configs/p2/e3_local_4906982_fused_dn_common_support_v1/viewer.yaml"),
    ("55-view fused-surface-normal comparison", "55-view fused depth/normal common-support comparison"),
    ("DEBY_LOD2_4906982 · fused depth/normal", "DEBY_LOD2_4906982 · fused D/N common support"),
    ("Raw / native / fused 입력 비교", "Fused D/N support 입력 비교"),
    ("raw_native_fused", "raw_native_fused"),
):
    text = text.replace(old, new)
text = text.replace("__FIXED_ARM__", "FUSED_VIS_CONF_FUSED_NORMAL")
text = text.replace("__COMMON_ARM__", "FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT")
text = text.replace("__FIXED_ROOT__", "/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1")
text = text.replace("Raw → native filtered → fused 비교", "Fused depth/normal common-support 비교")
exec(compile(text, str(source), "exec"), {"__name__": "__main__", "__file__": __file__})
