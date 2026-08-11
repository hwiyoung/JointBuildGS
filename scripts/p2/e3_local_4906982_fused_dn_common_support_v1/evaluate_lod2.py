#!/usr/bin/env python3
"""Run the existing evaluation-only LoD2 evaluator in the new namespace."""
from pathlib import Path

source = Path("/workspace/JointBuildGS/scripts/p2/e3_local_4906982_fused_surface_normal_v1/evaluate_lod2.py")
text = source.read_text()
for old, new in (
    ("e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1", "e3_local_4906982_fused_dn_common_support_v1/P2-E3-LOCAL-4906982-FUSED-DN-COMMON-SUPPORT-v1"),
    ("FUSED_VIS_CONF_FUSED_NORMAL", "FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT"),
    ("e3_local_4906982_fused_surface_normal_v1", "e3_local_4906982_fused_dn_common_support_v1"),
):
    text = text.replace(old, new)
exec(compile(text, str(source), "exec"), {"__name__": "__main__", "__file__": __file__})
