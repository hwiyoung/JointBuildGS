#!/usr/bin/env python3
"""Light S1 readout: held-out rendered depth vs fused target and ALS prior.

Decodes each arm's it020000 eval depth PNGs and reports, per arm and pooled
over the eval slots: |render - fused| MAE/RMSE on fused support, and
|render - ALS TIN| median on prior support. Roofer-level readout follows
separately; this table is the same-night first pass for D2/D7/D9.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

from src.stage2.dataloader import ColmapDataset

REPO = Path(__file__).resolve().parents[3]
COMMON = REPO / "configs/p2/e4_e6_redesign_s1_v1/s1_v1.yaml"
ARTIFACTS = Path("/artifacts/JointBuildGS")
STEP = 20000


def materialized_base(common):
    config = yaml.safe_load((REPO / common["base_training_config"]).read_text(encoding="utf-8"))
    config.update(yaml.safe_load((REPO / common["fused_arm_config"]).read_text(encoding="utf-8"))["overrides"])
    return config


def decode_depth(render_dir: Path, slot: int) -> tuple[int, np.ndarray]:
    meta = json.loads((render_dir / f"it{STEP:06d}_v{slot}_depth.json").read_text(encoding="utf-8"))
    code = np.asarray(Image.open(render_dir / meta["png"]), dtype=np.int64)
    depth = np.full(code.shape, np.nan, dtype=np.float64)
    valid = code != int(meta["invalid_code"])
    depth[valid] = float(meta["decode_offset_m"]) + (code[valid] - 1) * float(meta["decode_scale_m_per_code_step"])
    return int(meta["dataset_index"]), depth


def main() -> None:
    common = yaml.safe_load(COMMON.read_text(encoding="utf-8"))
    task_root = Path(common["output_root"])
    base = materialized_base(common)
    dataset = ColmapDataset(base["data_root"], downscale=1.0, load_depth=True, load_normal=False, load_semantic=False, visible_views=list(base["visible_views"]))

    prior_dir = task_root / "prior/E4_STATIC"
    arms = {"CONTROL": ARTIFACTS / common["source_run"]}
    for arm in common["arms"]:
        arms[arm] = task_root / "arms" / arm / "R1"

    rows = []
    for arm, root in arms.items():
        render_dir = root / "renders"
        if not (render_dir / f"it{STEP:06d}_v0_depth.json").is_file():
            rows.append({"arm": arm, "status": "MISSING_RENDERS"})
            continue
        fused_abs, als_abs, alpha_invalid = [], [], []
        slot = 0
        while (render_dir / f"it{STEP:06d}_v{slot}_depth.json").is_file():
            index, rendered = decode_depth(render_dir, slot)
            sample = dataset[index]
            fused = sample["depth"].numpy().astype(np.float64)
            fused_mask = sample["depth_mask"].numpy().astype(bool)
            support = fused_mask & np.isfinite(rendered)
            fused_abs.append(np.abs(rendered[support] - fused[support]))
            alpha_invalid.append(float((~np.isfinite(rendered)).mean()))
            stem = Path(dataset.frames[index].name).stem
            with np.load(prior_dir / f"{stem}.npz", allow_pickle=False) as prior:
                yy = prior["pixel_y"].astype(np.int64)
                xx = prior["pixel_x"].astype(np.int64)
                prior_depth = prior["depth"].astype(np.float64)
            rendered_at_prior = rendered[yy, xx]
            ok = np.isfinite(rendered_at_prior)
            als_abs.append(np.abs(rendered_at_prior[ok] - prior_depth[ok]))
            slot += 1
        fused_pool = np.concatenate(fused_abs)
        als_pool = np.concatenate(als_abs)
        rows.append({
            "arm": arm,
            "eval_slots": slot,
            "fused_mae_m": float(fused_pool.mean()),
            "fused_rmse_m": float(np.sqrt((fused_pool ** 2).mean())),
            "fused_p95_m": float(np.quantile(fused_pool, 0.95)),
            "als_abs_median_m": float(np.median(als_pool)),
            "als_gt1m_fraction": float((als_pool > 1.0).mean()),
            "rendered_invalid_fraction": float(np.mean(alpha_invalid)),
        })
        print(json.dumps(rows[-1]), flush=True)

    body = {
        "schema": "jointbuildgs.p2.e4_e6_redesign_s1_v1.light_readout.v1",
        "task_id": common["task_id"],
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "step": STEP,
        "note": "held-out eval slots only; roofer-level readout is a separate pass",
        "rows": rows,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    out = task_root / "control" / "s1_light_readout_v1.json"
    out.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(out)}))


if __name__ == "__main__":
    main()
