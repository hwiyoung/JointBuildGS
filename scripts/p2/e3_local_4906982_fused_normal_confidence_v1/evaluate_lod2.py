#!/usr/bin/env python3
"""Run the frozen evaluation-only LoD2 evaluator in this namespace."""
from pathlib import Path

source = Path("/workspace/JointBuildGS/scripts/p2/e3_local_4906982_fused_surface_normal_v1/evaluate_lod2.py")
text = source.read_text()
for old, new in (
    ("e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1", "e3_local_4906982_fused_normal_confidence_v1/P2-E3-LOCAL-4906982-FUSED-NORMAL-CONFIDENCE-v1"),
    ("FUSED_VIS_CONF_FUSED_NORMAL", "FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE"),
    ("e3_local_4906982_fused_surface_normal_v1", "e3_local_4906982_fused_normal_confidence_v1"),
):
    text = text.replace(old, new)
exec(compile(text, str(source), "exec"), {"__name__": "__main__", "__file__": __file__})
