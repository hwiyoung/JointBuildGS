#!/usr/bin/env python3
"""Publish the four-arm 3D/Roofer viewer while retaining mask overlays."""
from pathlib import Path
import json


source = Path("/workspace/JointBuildGS/scripts/p2/e3_local_4906982_fused_surface_normal_v1/build_viewer.py")
text = source.read_text()
old_arms = '''ARMS = {
    "FUSED_VIS_CONF": (ROOT, "Depth only: fused depth + MVC/NC"),
    "FUSED_VIS_CONF_MVS_NORMAL": (RAW_ROOT, "+ raw COLMAP normal"),
    "FUSED_VIS_CONF_FUSED_NORMAL": (ROOT, "+ fused mesh surface normal"),
}'''
new_arms = '''COMMON_ROOT = AR / "phase-payloads/p2/e3_local_4906982_fused_dn_common_support_v1/P2-E3-LOCAL-4906982-FUSED-DN-COMMON-SUPPORT-v1"
ARMS = {
    "FUSED_VIS_CONF": (ROOT, "Depth only"),
    "FUSED_VIS_CONF_FUSED_NORMAL": (RAW_ROOT, "Fused N · previous mask"),
    "FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT": (COMMON_ROOT, "Fused N · common depth mask"),
    "FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE": (ROOT, "Fused N · confidence mask"),
}'''
if old_arms not in text:
    raise RuntimeError("viewer arm template drift")
text = text.replace(old_arms, new_arms)
old_raw = 'RAW_ROOT = AR / "phase-payloads/p2/e3_local_4906982_mvs_normal_ablation_v1/P2-E3-LOCAL-4906982-MVS-NORMAL-ABLATION-v1"'
new_raw = 'RAW_ROOT = AR / "phase-payloads/p2/__FIXED_NAMESPACE__/__FIXED_TASK__"'
text = text.replace(old_raw, new_raw)
for old, new in (
    ("P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1", "P2-E3-LOCAL-4906982-FUSED-NORMAL-CONFIDENCE-v1"),
    ("e3_local_4906982_fused_surface_normal_v1", "e3_local_4906982_fused_normal_confidence_v1"),
    ('"default": {"arm": "FUSED_VIS_CONF_FUSED_NORMAL", "step": 20000}', '"default": {"arm": "FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE", "step": 20000}'),
    ("55-view fused-surface-normal comparison", "55-view fused-normal confidence comparison"),
    ("DEBY_LOD2_4906982 · fused depth/normal", "DEBY_LOD2_4906982 · fused normal mask comparison"),
    ("Raw / native / fused 입력 비교", "Depth / normal mask overlay"),
    ("plt.subplots(1, 3, figsize=(18, 7))", "plt.subplots(1, 4, figsize=(24, 7))"),
    ("roofer_3arm_20k_top.png", "roofer_4arm_20k_top.png"),
):
    if old not in text:
        raise RuntimeError(f"viewer template drift: {old}")
    text = text.replace(old, new)
text = text.replace("__FIXED_NAMESPACE__", "e3_local_4906982_fused_surface_normal_v1")
text = text.replace("__FIXED_TASK__", "P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1")

root = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_fused_normal_confidence_v1/P2-E3-LOCAL-4906982-FUSED-NORMAL-CONFIDENCE-v1")
slot = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_review_v1/P2-E3-LOCAL-4906982-INPUT-REVIEW-v3/viewer/e3-fused-normal-confidence-v1")
interactive = (slot / "inputs.html").read_text()
manifest_path = slot / "manifest.json"
if not manifest_path.is_file():
    manifest_path.write_text(json.dumps({"task_id": "P2-E3-LOCAL-4906982-FUSED-NORMAL-CONFIDENCE-v1", "scientific_verdict": None}) + "\n")
exec(compile(text, str(source), "exec"), {"__name__": "__main__", "__file__": __file__})
(slot / "inputs.html").write_text(interactive)

def sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

receipt_path = root / "viewer_slot.json"
receipt = json.loads(receipt_path.read_text())
receipt["files"] = {str(path.relative_to(slot)): sha256(path) for path in sorted(slot.rglob("*")) if path.is_file()}
receipt["input_comparison_url"] = "e3-fused-normal-confidence-v1/inputs.html"
receipt["scientific_verdict"] = None
receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
