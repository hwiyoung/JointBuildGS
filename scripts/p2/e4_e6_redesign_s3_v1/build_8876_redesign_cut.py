#!/usr/bin/env python3
"""Versioned 8876 qualitative cut: v16 viewer app with E4/E5 slots re-bound.

Creates P2-E1-E6-VIEWER-REDESIGN-v1 next to the sealed v16 viewer: app files
are symlinked unchanged; the manifest's E4/E5 condition entries are replaced
with the redesign arms' per-building assets (roofer-input points + roofer OBJ,
S3 r0p25 lineage). E3/E6 stay legacy and a banner states the slot mapping.
Also writes an 8876 umbrella root offering the legacy and redesign versions.
"""
from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ART = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts")
OX = ART / "phase-payloads/p2/e1_e6_roofer_ox_review_v1"
V16 = OX / "P2-E1-E6-ROOFER-OX-REVIEW-v16-G3G4-DEV0P1"
S3 = ART / "phase-payloads/p2/e4_e6_redesign_s3_v1/P2-E4-E6-REDESIGN-S3-v1"
CUT = OX / "P2-E1-E6-VIEWER-REDESIGN-v1"
UMBRELLA = OX / "viewer_8876_root"
TECHDEV_VIEWER = ART / "phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1/viewer"
ARMS = {"E4": "E4_V2_STATIC", "E5": "E5_V2_F1"}
STATUS_MAP = {"TECHNICAL_VALID_LOD22": "TECHNICAL_LOD22_PRESENT", "FAILED": "NO_LOD22"}


def relink(target: Path, source: Path) -> None:
    if target.is_symlink() or target.exists():
        return
    target.symlink_to(os.path.relpath(source, target.parent))


def main() -> None:
    CUT.mkdir(parents=True, exist_ok=True)
    for name in ("app.js", "assets", "overview", "overview.html",
                 "development_g3_g4_building_condition_v0.csv", "development_g3_g4_summary_v0.json"):
        if (V16 / name).exists():
            relink(CUT / name, V16 / name)
    relink(CUT / "assets_redesign", S3 / "viewer_assets")

    counts = {}
    for row in json.loads((S3 / "viewer_assets/assets_receipt.json").read_text())["rows"]:
        counts[(row["arm"], row["stable_id"])] = row
    status = {}
    for line in (S3 / "results/building_method_results_v1.jsonl").read_text().splitlines():
        d = json.loads(line)
        status[(d["condition_id"], d["stable_id"])] = d

    manifest = json.loads((V16 / "viewer_manifest.json").read_text())
    for b in manifest["buildings"]:
        sid = b["stable_id"]
        idx = int(b["population_index"])
        for slot, arm in ARMS.items():
            spec = copy.deepcopy((b.get("conditions") or {}).get(slot) or {})
            asset = counts.get((arm, sid), {})
            st = status.get((arm, sid), {})
            base = f"assets_redesign/{arm}/B{idx:03d}_{sid}"
            spec.update({
                "points": base + ".points.ply",
                "point_count": int(asset.get("points", 0)),
                "roofer": (base + ".roofer.obj") if int(asset.get("triangles", 0)) > 0 else None,
                "roofer_triangles": int(asset.get("triangles", 0)),
                "technical_status": STATUS_MAP.get(str(st.get("status")), str(st.get("status") or "NO_LOD22")),
                "reason": str(st.get("reason") or "redesign_s3_r0p25"),
                "lineage_label": "REDESIGN_S2_R0P25_LOSS_ONLY_PRIOR",
                "metrics": None,
                "development_g3_g4": None,
                "automatic_candidate": None,
            })
            b.setdefault("conditions", {})[slot] = spec
    manifest["task_id"] = "P2-E1-E6-VIEWER-REDESIGN-v1"
    manifest["slot_binding_note"] = "E4/E5 slots re-bound to redesign arms (S3 r0p25); E3/E6 remain legacy; judgments live on 8880"
    (CUT / "viewer_manifest.json").write_text(json.dumps(manifest, separators=(",", ":")))

    index = (V16 / "index.html").read_text()
    banner = ('<div style="background:#173a5e;color:#cfe4ff;padding:6px 12px;font:12px system-ui">'
              '재설계 컷: <b>E4/E5 슬롯 = 재설계(v2) 산출</b> · E3/E6 = 레거시 · 점군 = roofer 입력(전량) · '
              '지표/판정은 <a href="http://localhost:8880/" style="color:#8fc1ff">8880</a> 기준 · scientific_verdict: null</div>')
    for marker in ("<body>", "</head>"):
        if marker in index:
            index = index.replace(marker, marker + banner, 1)
            break
    (CUT / "index.html").write_text(index)

    UMBRELLA.mkdir(exist_ok=True)
    relink(UMBRELLA / "legacy", TECHDEV_VIEWER)
    relink(UMBRELLA / "redesign_v1", CUT)
    (UMBRELLA / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>E1-E6 정성 뷰어 — 버전 선택</title>'
        '<body style="font:15px system-ui;padding:28px;background:#F6F7F8">'
        '<h2>E1–E6 정성 뷰어</h2><ul style="line-height:2">'
        '<li><a href="redesign_v1/">redesign_v1</a> — E4/E5 슬롯 = 재설계(v2), 점군 = roofer 입력 전량</li>'
        '<li><a href="legacy/">legacy</a> — 기존 techdev 뷰어 (봉인 원본)</li>'
        '</ul><p style="color:#8B95A0;font-size:12px">판정·지표는 8880 대시보드가 기준입니다.</p>'
        f'<p style="color:#8B95A0;font-size:11px">generated {datetime.now(timezone.utc).isoformat()}</p>')
    print(json.dumps({"cut": str(CUT), "umbrella": str(UMBRELLA)}))


if __name__ == "__main__":
    main()
