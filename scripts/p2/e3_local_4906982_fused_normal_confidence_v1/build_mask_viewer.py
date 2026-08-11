#!/usr/bin/env python3
"""Publish the pre-training RGB mask overlays in an add-only 8878 slot."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import shutil

import yaml


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-FUSED-NORMAL-CONFIDENCE-v1"
ROOT = AR / "phase-payloads/p2/e3_local_4906982_fused_normal_confidence_v1" / TASK_ID
CONFIG = REPO / "configs/p2/e3_local_4906982_fused_normal_confidence_v1/viewer.yaml"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    os.replace(temporary, path)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> None:
    config = yaml.safe_load(CONFIG.read_text())
    viewer_root = Path(config["viewer_root"])
    slot = viewer_root / config["slot_dir"]
    precondition = ROOT / "control/viewer_root_precondition.json"
    fixed = {name: sha256(viewer_root / name) for name in config["root_files_must_remain_unchanged"]}
    if precondition.is_file():
        previous = json.loads(precondition.read_text())["fixed_file_sha256"]
        if previous != fixed:
            raise RuntimeError("protected viewer root changed before mask publication")
    else:
        atomic_json(precondition, {"viewer_root": str(viewer_root), "fixed_file_sha256": fixed, "scientific_verdict": None})
    rows = list(csv.DictReader((ROOT / "normal_confidence_mask_metrics.csv").open()))
    if len(rows) != 55:
        raise RuntimeError("mask viewer requires exactly 55 view rows")
    asset_root = slot / "mask-assets"
    asset_root.mkdir(parents=True, exist_ok=True)
    for row in rows:
        stem = Path(row["view"]).stem
        source = ROOT / "mask_overlay_views" / stem
        target = asset_root / stem
        target.mkdir(parents=True, exist_ok=True)
        for name in ("rgb.png", "depth.png", "previous.png", "confidence.png", "difference.png"):
            src = source / name; dst = target / name
            if dst.is_file() and sha256(dst) == sha256(src):
                continue
            temporary = dst.with_suffix(".tmp.png"); shutil.copy2(src, temporary); os.replace(temporary, dst)
    data = [{key: (float(value) if key == "new_fraction_of_depth" else int(value) if key not in {"view", "role"} else value) for key, value in row.items()} for row in rows]
    html = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fused normal confidence mask overlays</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#111;color:#eee}body{margin:0;padding:18px}main{max-width:1500px;margin:auto}.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin-bottom:12px}.control{display:grid;gap:4px}select,input,button{font:inherit}button{padding:7px 10px}.stage{position:relative;display:inline-block;max-width:100%;background:#000}.stage img{display:block;max-width:100%;height:auto}.stage #overlay{position:absolute;inset:0}.stats{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}.stat{background:#202020;padding:8px 10px;border-radius:6px}.legend{display:flex;flex-wrap:wrap;gap:12px;margin:10px 0;color:#ddd}.sw{display:inline-block;width:12px;height:12px;margin-right:5px;border-radius:2px}.note{color:#bbb}a{color:#8fd3ff}
</style></head><body><main>
<h2>Depth / previous normal / confidence normal mask overlay</h2>
<div class="controls"><label class="control">View<select id="view"></select></label><label class="control">Overlay<select id="layer"><option value="depth">Depth mask</option><option value="previous">Previous normal mask</option><option value="confidence" selected>New confidence normal mask</option><option value="difference">Difference categories</option></select></label><label class="control">Opacity <span id="opacity-value">70%</span><input id="opacity" type="range" min="0" max="100" value="70"></label></div>
<div class="stats" id="stats"></div>
<div class="legend"><span><i class="sw" style="background:rgb(20,210,235)"></i>depth</span><span><i class="sw" style="background:rgb(245,145,35)"></i>previous normal</span><span><i class="sw" style="background:rgb(220,65,210)"></i>new confidence normal</span><span class="note">Difference: blue depth-only · green retained · orange removed · magenta added</span></div>
<div class="stage"><img id="rgb" alt="RGB base"><img id="overlay" alt="selected mask overlay"></div>
<p class="note">LoD2 geometry was not used. Thresholds were frozen before these masks and before training.</p>
</main><script>const rows=__ROWS__;const view=document.getElementById('view'),layer=document.getElementById('layer'),opacity=document.getElementById('opacity'),opv=document.getElementById('opacity-value'),rgb=document.getElementById('rgb'),overlay=document.getElementById('overlay'),stats=document.getElementById('stats');for(const [i,r] of rows.entries()){const o=document.createElement('option');o.value=i;o.textContent=`${r.role} · ${r.view}`;view.appendChild(o)}function update(){const r=rows[+view.value||0],stem=r.view.replace(/\.[^.]+$/,'');rgb.src=`mask-assets/${stem}/rgb.png`;overlay.src=`mask-assets/${stem}/${layer.value}.png`;overlay.style.opacity=(+opacity.value/100);opv.textContent=opacity.value+'%';stats.innerHTML=`<span class="stat">depth ${r.depth_mask_pixels.toLocaleString()}</span><span class="stat">previous ${r.previous_normal_mask_pixels.toLocaleString()}</span><span class="stat">new ${r.new_normal_mask_pixels.toLocaleString()}</span><span class="stat">new/depth ${(100*r.new_fraction_of_depth).toFixed(1)}%</span><span class="stat">removed ${r.removed_from_previous.toLocaleString()}</span><span class="stat">added ${r.added_vs_previous.toLocaleString()}</span>`}view.onchange=layer.onchange=opacity.oninput=update;update();</script></body></html>'''.replace("__ROWS__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    atomic_text(slot / "inputs.html", html)
    receipt = {
        "schema": "jointbuildgs.viewer.fused_normal_confidence_mask_pretraining.v1", "task_id": TASK_ID,
        "slot": config["slot_dir"], "relative_url": f"{config['slot_dir']}/inputs.html",
        "published_before_training": not (ROOT / "arms/FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE/R1/ckpt").exists(),
        "view_count": len(rows), "protected_root_equal": fixed == json.loads(precondition.read_text())["fixed_file_sha256"],
        "inputs_html_sha256": sha256(slot / "inputs.html"), "scientific_verdict": None,
    }
    atomic_json(ROOT / "mask_viewer_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
