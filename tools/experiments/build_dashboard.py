"""Build experiment viewer dashboard.

Scans results/ for completed experiments and builds per-experiment 4-way viewers:
  - Phase × Step × Stage (2 GS / 3 CityGML) directories
  - Each directory has index.html + assets/ (ksplat for Stage 2, PLY for Stage 3)
  - Root index.html lists all experiments with status and links

Experiment registry is hard-coded in EXPERIMENTS below — map Phase/Step to
each condition's result directory + ckpt/stage3 output paths.

Usage:
    python tools/experiments/build_dashboard.py [--only phase2_2/stage2]

Hooked into run_ablation.sh + run_post_training.sh to auto-rebuild after
training or Stage 3 completes.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]  # JointBuildGS/
TOOLS = ROOT / "tools"
EXP_DIR = TOOLS / "experiments"
SHARED = EXP_DIR / "_shared"
TEMPLATE_GS_4WAY = SHARED / "gs_4way_template.html"
TEMPLATE_GS_6PANEL = SHARED / "gs_6panel_template.html"
TEMPLATE_CITYGML = SHARED / "citygml_6panel_template.html"

CONDITIONS = ["baseline", "mutual", "structure", "both"]

# Experiment registry. Each entry: (exp_key, label, per-condition ckpt path relative to ROOT)
EXPERIMENTS = {
    "phase1/stage2": {
        "label": "Phase 1 / Step 1-6 / Stage 2 GS (4-way)",
        "kind": "gs",
        "template": "4way",  # Phase 1 (MatrixCity) has no GT mesh
        "ckpts": {
            "baseline":  "results/phase1_semantic/run/ckpt/final.pt",
            "mutual":    "results/phase1_mutual/run/ckpt/final.pt",
            "structure": "results/phase1_structure/run/ckpt/final.pt",
            "both":      "results/phase1_ablation/run/ckpt/final.pt",
        },
    },
    "phase2_2/stage2": {
        "label": "Phase 2 Step 2-2 / Stage 2 GS (GT + 4 conds + minimap)",
        "kind": "gs",
        "template": "6panel",  # Phase 2 has GT scene.obj
        "ckpts": {
            "baseline":  "results/phase2_ablation_citygml/baseline/ckpt/final.pt",
            "mutual":    "results/phase2_ablation_citygml/mutual/ckpt/final.pt",
            "structure": "results/phase2_ablation_citygml/structure/ckpt/final.pt",
            "both":      "results/phase2_ablation_citygml/both/ckpt/final.pt",
        },
    },
    "phase2_2/stage3": {
        "label": "Phase 2 Step 2-2 / Stage 3 CityGML (GT + 4 conds + minimap)",
        "kind": "citygml",
        "plys": {
            # Stage 3 outputs a colored PLY at stage3/building_{bid:02d}/lod2.ply per building.
            # We aggregate into a single per-condition LOD2 PLY (or use the first building's).
            # For now, point to stage3/ dir; template will scan on load.
            "baseline":  "results/phase2_ablation_citygml/baseline/stage3",
            "mutual":    "results/phase2_ablation_citygml/mutual/stage3",
            "structure": "results/phase2_ablation_citygml/structure/stage3",
            "both":      "results/phase2_ablation_citygml/both/stage3",
        },
    },
}


def _export_ksplat(ckpt: Path, out: Path, mode: str, max_count: int = 400_000) -> bool:
    """Export a ckpt to .ksplat via scripts/stage2/export_2dgs_ksplat.py.

    max_count=400k gives ~17MB per file (vs 52MB at 1.2M) — 3x faster download
    with minimal visual quality loss for aerial GS viewing.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python", str(ROOT / "scripts/stage2/export_2dgs_ksplat.py"),
        "--ckpt", str(ckpt),
        "--out", str(out),
        "--color-mode", mode,
        "--max-count", str(max_count),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            print(f"  [ksplat export {mode} FAIL] {r.stderr[:400]}")
            return False
        return True
    except Exception as e:
        print(f"  [ksplat export {mode} EXCEPTION] {e}")
        return False


def _merge_plys(stage3_dir: Path, out_ply: Path) -> bool:
    """Concatenate per-building LOD2 PLYs into a single scene PLY."""
    ply_files = sorted(stage3_dir.glob("building_*/lod2.ply"))
    if not ply_files:
        return False
    all_verts = []
    all_faces = []
    vert_offset = 0
    for pf in ply_files:
        # Minimal PLY parser (ASCII)
        with open(pf) as f:
            lines = f.readlines()
        in_header = True
        n_vert = n_face = 0
        hdr_end = 0
        for i, ln in enumerate(lines):
            if ln.startswith("element vertex"): n_vert = int(ln.split()[-1])
            elif ln.startswith("element face"): n_face = int(ln.split()[-1])
            elif ln.strip() == "end_header": hdr_end = i + 1; break
        for i in range(hdr_end, hdr_end + n_vert):
            all_verts.append(lines[i].rstrip())
        for i in range(hdr_end + n_vert, hdr_end + n_vert + n_face):
            parts = lines[i].split()
            count = int(parts[0])
            idxs = [str(int(x) + vert_offset) for x in parts[1:1+count]]
            rest = parts[1+count:]
            all_faces.append(" ".join([str(count)] + idxs + rest))
        vert_offset += n_vert
    out_ply.parent.mkdir(parents=True, exist_ok=True)
    with open(out_ply, "w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(all_verts)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write(f"element face {len(all_faces)}\n")
        f.write("property list uchar int vertex_indices\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        f.write("end_header\n")
        for v in all_verts: f.write(v + "\n")
        for fa in all_faces: f.write(fa + "\n")
    return True


def _build_gs_viewer(exp_key: str, cfg: dict, entries: list) -> dict:
    out_dir = EXP_DIR / exp_key
    out_dir.mkdir(parents=True, exist_ok=True)

    status = {"key": exp_key, "label": cfg["label"], "kind": "gs", "url": f"{exp_key}/",
              "conditions": {}, "ready": False}
    ready_count = 0
    for cond, ckpt_rel in cfg["ckpts"].items():
        ckpt = ROOT / ckpt_rel
        if not ckpt.exists():
            status["conditions"][cond] = "missing"
            continue
        for mode in ("rgb", "normal", "semantic"):
            out_ksplat = out_dir / f"assets/ksplat_{mode}/{cond}.ksplat"
            if out_ksplat.exists():
                continue
            print(f"  {exp_key} {cond} {mode}: exporting…")
            if not _export_ksplat(ckpt, out_ksplat, mode):
                status["conditions"][cond] = f"export_fail({mode})"
                break
        else:
            status["conditions"][cond] = "ready"
            ready_count += 1
            continue
    status["ready"] = ready_count == 4

    # Copy template HTML + inject title (4-way vs 6-panel based on cfg.template)
    idx_html = out_dir / "index.html"
    tmpl_path = TEMPLATE_GS_6PANEL if cfg.get("template") == "6panel" else TEMPLATE_GS_4WAY
    tmpl = tmpl_path.read_text()
    tmpl = tmpl.replace("<title>JointBuildGS Phase 1 - 2DGS Splat Viewer</title>",
                         f"<title>{cfg['label']}</title>")
    tmpl = tmpl.replace("<!-- TITLE -->", cfg["label"])
    idx_html.write_text(tmpl)
    entries.append(status)
    return status


def _build_citygml_viewer(exp_key: str, cfg: dict, entries: list) -> dict:
    out_dir = EXP_DIR / exp_key
    out_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    status = {"key": exp_key, "label": cfg["label"], "kind": "citygml", "url": f"{exp_key}/",
              "conditions": {}, "ready": False}
    ready_count = 0
    for cond, stage3_rel in cfg["plys"].items():
        stage3_dir = ROOT / stage3_rel
        out_ply = assets_dir / f"{cond}.ply"
        if not stage3_dir.exists() or not any(stage3_dir.glob("building_*/lod2.ply")):
            status["conditions"][cond] = "missing"
            continue
        print(f"  {exp_key} {cond}: merging PLYs…")
        if _merge_plys(stage3_dir, out_ply):
            status["conditions"][cond] = "ready"
            ready_count += 1
        else:
            status["conditions"][cond] = "merge_fail"
    status["ready"] = ready_count == 4

    # Copy template
    idx_html = out_dir / "index.html"
    if TEMPLATE_CITYGML.exists():
        tmpl = TEMPLATE_CITYGML.read_text()
        tmpl = tmpl.replace("<!-- TITLE -->", cfg["label"])
        idx_html.write_text(tmpl)
    entries.append(status)
    return status


def _write_root_index(entries: list):
    STATUS_STYLE = {
        "ready": "color:#38a169; font-weight:600",
        "missing": "color:#a0aec0",
        "export_fail": "color:#e53e3e",
        "merge_fail": "color:#e53e3e",
    }
    html = ["""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>JointBuildGS — Experiments Dashboard</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       background: #0d1117; color: #e6edf3; padding: 24px; max-width: 1100px;
       margin: 0 auto; }
h1 { color: #f0f6fc; border-bottom: 1px solid #30363d; padding-bottom: 8px; }
.card { border: 1px solid #30363d; border-radius: 8px; padding: 16px 20px;
        margin-bottom: 14px; background: #161b22; }
.card h2 { margin: 0 0 4px; font-size: 18px; color: #58a6ff; }
.card .kind { font-size: 12px; color: #8b949e; margin-bottom: 8px; }
.conds { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 6px; font-size: 13px; font-family: monospace; }
.conds span { padding: 3px 10px; border-radius: 3px; background: #21262d; }
.actions { margin-top: 12px; }
.btn { display: inline-block; padding: 6px 14px; background: #238636; color: #fff;
       text-decoration: none; border-radius: 5px; font-size: 13px; font-weight: 500; }
.btn.disabled { background: #30363d; color: #6e7681; cursor: not-allowed; }
.btn + .btn { margin-left: 6px; }
.btn.sec { background: #30363d; color: #e6edf3; }
.kind-gs { color: #79c0ff; }
.kind-citygml { color: #ffa657; }
</style>
</head><body>
<h1>JointBuildGS — Experiments Dashboard</h1>
<p style="color:#8b949e">자동 생성. 각 실험의 Stage 2 (Gaussian Splats) / Stage 3 (CityGML) 를 4-way viewer 에서 확인.</p>
"""]
    for e in entries:
        cond_html = []
        for c in CONDITIONS:
            st = e["conditions"].get(c, "missing")
            style = STATUS_STYLE.get(st, "color:#a0aec0")
            cond_html.append(f'<span style="{style}">{c}: {st}</span>')
        btn_cls = "btn" if e["ready"] else "btn disabled"
        btn_label = "Open 4-way viewer" if e["ready"] else f"Waiting ({sum(1 for c in e['conditions'].values() if c == 'ready')}/4)"
        kind_cls = "kind-gs" if e["kind"] == "gs" else "kind-citygml"
        html.append(f"""<div class="card">
  <h2>{e['label']}</h2>
  <div class="kind {kind_cls}">{e['kind'].upper()} · {e['key']}</div>
  <div class="conds">{' '.join(cond_html)}</div>
  <div class="actions">
    <a href="./{e['url']}" class="{btn_cls}">{btn_label}</a>
  </div>
</div>""")
    html.append("</body></html>")
    (EXP_DIR / "index.html").write_text("\n".join(html))
    print(f"\n[index] wrote {EXP_DIR/'index.html'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="rebuild only one exp (e.g., phase2_2/stage2)")
    args = parser.parse_args()

    keys = [args.only] if args.only else list(EXPERIMENTS.keys())
    entries = []
    for key in keys:
        if key not in EXPERIMENTS:
            print(f"[skip] unknown {key}"); continue
        cfg = EXPERIMENTS[key]
        print(f"\n[build] {key} ({cfg['kind']})")
        if cfg["kind"] == "gs":
            _build_gs_viewer(key, cfg, entries)
        elif cfg["kind"] == "citygml":
            _build_citygml_viewer(key, cfg, entries)

    # Always write root index (covering all known experiments, not just built)
    # Re-collect status for all experiments for complete index
    if not args.only:
        _write_root_index(entries)
    print("[done]")


if __name__ == "__main__":
    main()
