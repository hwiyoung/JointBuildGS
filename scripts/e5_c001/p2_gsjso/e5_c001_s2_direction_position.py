#!/usr/bin/env python3
"""E5 C001 S2 direction-position experiment harness.

Task-scoped orchestration for the 2026-07-10 S2 order:
Track A zero-training checks, S2 arm config generation, short loss gates,
dense training fingerprints, readout/evaluation redirection, and report tables.

Canonical S0/S1/corrected artifacts are read-only inputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
PYDEPS_BOOT = REPO / "results/tum_transfer/e5_s1_full_factor/C001/python_deps/timm_0_4_12"
if PYDEPS_BOOT.exists() and str(PYDEPS_BOOT) not in sys.path:
    sys.path.insert(0, str(PYDEPS_BOOT))

import e5_c001_8way as eight  # noqa: E402
import e5_c001_pipeline_strips as strips  # noqa: E402
import e5_c001_readout_ablation as ab  # noqa: E402
import e5_c001_s1_full_factor as s1fac  # noqa: E402
from e5_pilot_gate_tools import C001_IDS, DEV_IMAGE, P0_RUNS, sha256_file  # noqa: E402

ORIGINAL_AB_SOURCE_FOR = ab.source_for

RUN_ID = "20260710_e5_c001_s2_direction_position"
P2_RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
P0_RUN_ID = "e5p_s2_direction_position_20260710_C001"
P0_RUN_DIR = P0_RUNS / P0_RUN_ID
REPAIR_RUN_ID = "e5p_s2_405_repair_20260710_C001"
REPAIRED_P0_RUN_DIR = P0_RUNS / REPAIR_RUN_ID / P0_RUN_ID

CONFIG_DIR = REPO / "configs/tum_mob/e5_s2_direction_position"
RESULTS_ROOT = REPO / "results/tum_transfer/e5_s2_direction_position/C001/readout"
CKPT_ROOT = REPO / "results/tum_transfer/e5_s2_direction_position/C001/runs"
TRAIN_LOG_ROOT = REPO / "results/tum_transfer/e5_s2_direction_position/C001/train_logs"
TORCH_EXTENSIONS = "results/tum_transfer/e5_s2_direction_position/C001/torch_extensions"
MONO_ROOT = REPO / "results/tum_transfer/e5_s2_direction_position/C001/mono_priors"
MONO_NORMAL_DIR = MONO_ROOT / "normal_omnidata_world_npy"
MONO_DEPTH_DIR = MONO_ROOT / "depth_metric_npy"
TORCH_HOME = REPO / "results/tum_transfer/e5_s1_full_factor/C001/torch_hub"
PYDEPS = REPO / "results/tum_transfer/e5_s1_full_factor/C001/python_deps/timm_0_4_12"

DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
DATA_ROOT_WS = "/workspace/JointBuildGS/results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
BASE_CONFIG = REPO / "configs/e5_c001/e5_s1_full_factor/gs_e5_C001_s1fac_w100_p005_dense_r1.yaml"
SHIFT_UTM = np.array([690953.0, 5336071.0, 604.0], dtype=np.float64)
ELLIP_TO_REF_SHIFT_M = float(eight.ELLIP_TO_REF_SHIFT_M)
FOOTPRINTS_GEOJSON = REPO / "phases/p0-audit/data/work/footprints/lod2_ground_plan.geojson"

FIG_DIR = REPO / "docs/figs/e5_c001_s2"
REPORT_PATH = REPO / "docs/experiments/joint-optimization/e5_c001_s2/reports/W_E5_C001_S2_방향자리.md"
CHECKPOINT_REPORT = REPO / "docs/archive/e5_c001_s2/temporary/reports/W_E5_C001_S2_checkpoint_20260710.md"

CSV_MONODEPTH = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_monodepth_precheck.csv"
CSV_MONODEPTH_BUILDING = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_monodepth_precheck_building.csv"
CSV_MONODEPTH_RESOLUTION = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_monodepth_resolution.csv"
CSV_SHEET = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_sheet_identity_alt.csv"
CSV_IMPL = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_implementation_check.csv"
CSV_NORMAL_RECHECK = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_normal_recheck.csv"
CSV_A5_PREP = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_a5_metric_prep.csv"
CSV_GRAD_SHARE = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_grad_share.csv"
CSV_TIMELINE = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_timeline_roofcrop.csv"
CSV_ARM_CELLS = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_arm_cells.csv"
CSV_405_REPAIR = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_405_rescore.csv"
CSV_405_BUILDING = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_405_rescore_building.csv"
CSV_GLOBAL_Z = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_global_z_hist.csv"
CSV_REND_DIST = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_rend_dist.csv"
CSV_PIPELINE_STRIPS = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_pipeline_strips.csv"
CSV_INVENTORY = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_inventory.csv"
CSV_ISSUES = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_issues.csv"

GOOD6 = ["4907184", "4907185", "4907198", "4907202", "4908168", "4908178"]
GS_FAIL5 = ["60098", "4907186", "4907188", "4907194", "4907195"]
TEXTURELESS_OBS3 = ["4907199", "8568391", "8568392"]
TIMELINE_IDS = ["4907202", "4908168", "4908178", "4907184"]
NORMAL_RECHECK_IDS = ["60098", "4907186", "4907188", "4907194", "4907195"]


@dataclass(frozen=True)
class Arm:
    key: str
    order: int
    label: str
    w_distort: float
    depth_floor: float | None
    use_mono_depth: bool


ARMS = [
    Arm("arm1", 1, "base + mono normal", 100.0, None, False),
    Arm("arm2", 2, "arm1 + depth floor 0.15", 100.0, 0.15, False),
    Arm("arm0", 3, "arm1 with surface gathering off", 0.0, None, False),
    Arm("arm3", 4, "arm2 + mono depth outside MVS pixels", 100.0, 0.15, True),
]


def rel(path: Path | str | None) -> str:
    if path is None:
        return ""
    p = Path(path)
    for root in (REPO, Path("/workspace/JointBuildGS")):
        try:
            return str(p.relative_to(root))
        except ValueError:
            pass
    text = str(p)
    prefix = "/workspace/JointBuildGS/"
    return text[len(prefix) :] if text.startswith(prefix) else text


def ws(path: Path) -> str:
    return f"/workspace/JointBuildGS/{rel(path)}"


def full_id(short: str) -> str:
    return short if short.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{short}"


def short_id(bid: str) -> str:
    return bid.replace("DEBY_LOD2_", "")


def num(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na"}:
        return None
    try:
        out = float(text)
    except ValueError:
        return None
    return out if math.isfinite(out) else None


def tf(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        v = float(value)
        return f"{v:.{digits}f}" if math.isfinite(v) else ""
    return str(value)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        if not fields:
            fh.write("")
            return
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def append_issue(part: str, severity: str, message: str, path: Path | str | None = None) -> None:
    rows = read_csv(CSV_ISSUES)
    rows.append(
        {
            "part": part,
            "severity": severity,
            "message": message,
            "path": rel(path),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    write_csv(CSV_ISSUES, rows)
    issue_md = REPO / "phases/p2-gsjso/docs/issues.md"
    line = f"- 2026-07-10 S2 {part}: {severity} - {message}"
    if path:
        line += f" ({rel(path)})"
    if issue_md.exists():
        text = issue_md.read_text(encoding="utf-8")
        if line not in text:
            with issue_md.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


def capture(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        return f"not_available:{exc.filename}"
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def run(cmd: list[str], log_path: Path | None = None, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    print("+ " + " ".join(cmd[:10]) + (" ..." if len(cmd) > 10 else ""), flush=True)
    proc = subprocess.run(cmd, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log_path:
        log_path.write_text("+ " + " ".join(cmd) + "\n" + (proc.stdout or ""), encoding="utf-8")
    if proc.stdout and not quiet:
        print(proc.stdout, end="", flush=True)
    if check:
        proc.check_returncode()
    return proc


def yaml_load(path: Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def yaml_dump(path: Path, payload: dict[str, Any]) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def docker_base(gpu: str = "0", extra_env: dict[str, str] | None = None) -> list[str]:
    cmd = [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--gpus",
        "all",
        "-e",
        "HOME=/tmp",
        "-e",
        f"CUDA_VISIBLE_DEVICES={gpu}",
        "-e",
        f"TORCH_EXTENSIONS_DIR=/workspace/JointBuildGS/{TORCH_EXTENSIONS}",
        "-e",
        f"TORCH_HOME=/workspace/JointBuildGS/{rel(TORCH_HOME)}",
        "-v",
        f"{REPO}:/workspace/JointBuildGS",
        "-w",
        "/workspace/JointBuildGS",
    ]
    for key, value in (extra_env or {}).items():
        cmd.extend(["-e", f"{key}={value}"])
    cmd.append(DEV_IMAGE)
    return cmd


def run_name(arm_key: str, rep: int) -> str:
    return f"gs_e5_C001_s2_{arm_key}_dense_r{rep}"


def gate_run_name(kind: str, weight: float) -> str:
    suffix = str(weight).replace(".", "p")
    return f"gs_e5_C001_s2_gate_{kind}_w{suffix}_dense_r1"


def arm_by_key(key: str) -> Arm:
    for arm in ARMS:
        if arm.key == key:
            return arm
    raise KeyError(key)


def _fit_scale_shift(raw: np.ndarray, target: np.ndarray, mask: np.ndarray) -> tuple[float, float, np.ndarray]:
    valid = mask & np.isfinite(raw) & np.isfinite(target)
    if np.count_nonzero(valid) < 64:
        return float("nan"), float("nan"), np.full_like(raw, np.nan, dtype=np.float32)
    x = raw[valid].reshape(-1).astype(np.float64)
    y = target[valid].reshape(-1).astype(np.float64)
    a, b = np.linalg.lstsq(np.column_stack([x, np.ones_like(x)]), y, rcond=None)[0]
    aligned = (float(a) * raw.astype(np.float32) + float(b)).astype(np.float32)
    return float(a), float(b), aligned


def _polyfit_amp(residual: np.ndarray, mask: np.ndarray, order: int) -> float | None:
    ys, xs = np.where(mask & np.isfinite(residual))
    if len(xs) < (3 if order == 1 else 6):
        return None
    h, w = residual.shape
    xn = (xs.astype(np.float64) / max(1, w - 1)) * 2.0 - 1.0
    yn = (ys.astype(np.float64) / max(1, h - 1)) * 2.0 - 1.0
    cols = [np.ones_like(xn), xn, yn]
    if order >= 2:
        cols.extend([xn * xn, xn * yn, yn * yn])
    coef = np.linalg.lstsq(np.column_stack(cols), residual[ys, xs].astype(np.float64), rcond=None)[0]
    pred = np.column_stack(cols) @ coef
    return float(np.percentile(pred, 95) - np.percentile(pred, 5))


def _depth_anything_model(device: Any) -> tuple[Any, str] | None:
    repo_dir = MONO_ROOT / "Depth-Anything-V2"
    if not repo_dir.exists():
        proc = subprocess.run(
            ["git", "clone", "--depth", "1", "https://github.com/DepthAnything/Depth-Anything-V2.git", str(repo_dir)],
            cwd=REPO,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if proc.returncode != 0:
            append_issue("A-1", "warn", f"Depth Anything V2 git clone failed: {proc.stdout[-300:]}")
            return None
    sys.path.insert(0, str(repo_dir))
    try:
        import torch
        from depth_anything_v2.dpt import DepthAnythingV2

        model = DepthAnythingV2(encoder="vits", features=64, out_channels=[48, 96, 192, 384])
        ckpt = MONO_ROOT / "depth_anything_v2_vits.pth"
        if not ckpt.exists():
            url = "https://huggingface.co/depth-anything/Depth-Anything-V2-Small/resolve/main/depth_anything_v2_vits.pth"
            state = torch.hub.load_state_dict_from_url(url, model_dir=str(MONO_ROOT), file_name=ckpt.name, map_location="cpu")
        else:
            state = torch.load(ckpt, map_location="cpu")
        model.load_state_dict(state)
        model.to(device).eval()
        return model, "Depth Anything V2 Small vits"
    except Exception as exc:  # noqa: BLE001
        append_issue("A-1", "warn", f"Depth Anything V2 runtime failed; falling back to Omnidata depth: {exc}")
        return None


def _omnidata_model(task: str, device: Any) -> tuple[Any, Any]:
    if str(PYDEPS) not in sys.path:
        sys.path.insert(0, str(PYDEPS))
    os.environ.setdefault("TORCH_HOME", str(TORCH_HOME))
    import torch

    name = "surface_normal_dpt_hybrid_384" if task == "normal" else "depth_dpt_hybrid_384"
    model = torch.hub.load("alexsax/omnidata_models", name, pretrained=True, trust_repo=True)
    model.to(device).eval()
    return model, torch


def _infer_priors_container(args: argparse.Namespace) -> None:
    import cv2
    import torch
    import torch.nn.functional as F
    from PIL import Image
    from torchvision import transforms

    from src.stage2.dataloader import ColmapDataset

    device = torch.device(args.device if args.device == "cpu" or torch.cuda.is_available() else "cpu")
    MONO_ROOT.mkdir(parents=True, exist_ok=True)
    MONO_NORMAL_DIR.mkdir(parents=True, exist_ok=True)
    MONO_DEPTH_DIR.mkdir(parents=True, exist_ok=True)
    (FIG_DIR / "monodepth_precheck").mkdir(parents=True, exist_ok=True)

    runtime_rows: list[dict[str, Any]] = []
    da_model = _depth_anything_model(device)
    if da_model is None:
        depth_model, torch_mod = _omnidata_model("depth", device)
        depth_backend = "Omnidata DPT-Hybrid depth"
    else:
        depth_model, depth_backend = da_model
        torch_mod = torch
    normal_model, _ = _omnidata_model("normal", device)
    runtime_rows.append(
        {
            "component": "mono_depth",
            "backend": depth_backend,
            "torch": torch.__version__,
            "device": str(device),
            "depth_anything_repo": rel(MONO_ROOT / "Depth-Anything-V2"),
        }
    )
    runtime_rows.append(
        {
            "component": "mono_normal",
            "backend": "Omnidata DPT-Hybrid surface normal",
            "torch": torch.__version__,
            "device": str(device),
            "torch_home": rel(TORCH_HOME),
        }
    )

    trans_depth = transforms.Compose(
        [
            transforms.Resize((384, 384), interpolation=Image.BILINEAR),
            transforms.ToTensor(),
            transforms.Normalize(mean=0.5, std=0.5),
        ]
    )
    trans_normal = transforms.Compose(
        [
            transforms.Resize((384, 384), interpolation=Image.BILINEAR),
            transforms.ToTensor(),
        ]
    )
    ds = ColmapDataset(root=str(DATA_ROOT), downscale=1.0, load_depth=True, load_normal=False, load_semantic=False)
    rows: list[dict[str, Any]] = []
    residual_gallery: list[tuple[str, np.ndarray]] = []
    for idx in range(len(ds)):
        batch = ds[idx]
        stem = Path(str(batch["name"])).stem
        img_path = DATA_ROOT / "images" / str(batch["name"])
        image_bgr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            append_issue("A-1", "warn", "image read failed", img_path)
            continue
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        h, w = image_rgb.shape[:2]
        pil = Image.fromarray(image_rgb)
        with torch.no_grad():
            if depth_backend.startswith("Depth Anything"):
                raw = depth_model.infer_image(image_bgr)
                raw = cv2.resize(raw.astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
            else:
                inp = trans_depth(pil)[:3].unsqueeze(0).to(device)
                out = depth_model(inp).float()
                if out.ndim == 3:
                    out = out.unsqueeze(1)
                out = F.interpolate(out, size=(h, w), mode="bicubic", align_corners=False)[0, 0]
                raw = (1.0 - out.clamp(0, 1)).detach().cpu().numpy().astype(np.float32)

            ninp = trans_normal(pil)[:3].unsqueeze(0).to(device)
            nout = normal_model(ninp).clamp(0, 1)
            nout = F.interpolate(nout, size=(h, w), mode="bilinear", align_corners=False)[0].permute(1, 2, 0)
            n_cam = (nout.detach().cpu().numpy().astype(np.float32) * 2.0) - 1.0
            n_cam = n_cam / np.maximum(np.linalg.norm(n_cam, axis=-1, keepdims=True), 1e-6)

        r = batch["w2c"].numpy()[:3, :3]
        n_world = n_cam.reshape(-1, 3) @ r
        n_world = n_world.reshape(h, w, 3)
        n_world = n_world / np.maximum(np.linalg.norm(n_world, axis=-1, keepdims=True), 1e-6)
        np.save(MONO_NORMAL_DIR / f"{stem}.npy", n_world.astype(np.float32))

        mvs = batch["depth"].numpy().astype(np.float32)
        mvs_mask = batch["depth_mask"].numpy().astype(bool)
        a, b, aligned = _fit_scale_shift(raw, mvs, mvs_mask)
        residual = aligned - mvs
        valid = mvs_mask & np.isfinite(residual)
        np.save(MONO_DEPTH_DIR / f"{stem}.npy", np.where(np.isfinite(aligned) & (aligned > 0), aligned, 0).astype(np.float32))
        med = float(np.median(np.abs(residual[valid]))) if np.any(valid) else None
        p90 = float(np.percentile(np.abs(residual[valid]), 90)) if np.any(valid) else None
        rows.append(
            {
                "image_idx": idx,
                "image_name": str(batch["name"]),
                "backend": depth_backend,
                "align_a": fmt(a, 8),
                "align_b": fmt(b, 8),
                "mvs_valid_pixels": int(np.count_nonzero(mvs_mask)),
                "residual_abs_median_m": fmt(med),
                "residual_abs_p90_m": fmt(p90),
                "warp_amp_plane_m": fmt(_polyfit_amp(residual, valid, 1)),
                "warp_amp_quadratic_m": fmt(_polyfit_amp(residual, valid, 2)),
                "metric_depth": rel(MONO_DEPTH_DIR / f"{stem}.npy"),
                "mono_normal_world": rel(MONO_NORMAL_DIR / f"{stem}.npy"),
            }
        )
        if len(residual_gallery) < 8 and np.any(valid):
            vis = np.zeros_like(residual, dtype=np.float32)
            lo, hi = np.percentile(residual[valid], [2, 98])
            vis[valid] = np.clip((residual[valid] - lo) / max(hi - lo, 1e-6), 0, 1)
            residual_gallery.append((stem, vis))
        if (idx + 1) % 50 == 0:
            print(json.dumps({"stage": "A-1-priors", "done": idx + 1, "total": len(ds)}, ensure_ascii=False), flush=True)

    write_csv(CSV_MONODEPTH, rows)
    write_csv(REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_mono_runtime.csv", runtime_rows)
    if residual_gallery:
        fig, axes = plt.subplots(2, 4, figsize=(12, 6))
        for ax, (stem, vis) in zip(axes.ravel(), residual_gallery):
            ax.imshow(vis, cmap="coolwarm")
            ax.set_title(stem[-16:], fontsize=8)
            ax.axis("off")
        fig.tight_layout()
        fig.savefig(FIG_DIR / "monodepth_precheck/alignment_residual_gallery.png", dpi=160)
        plt.close(fig)
    monodepth_building_score(args)
    print(json.dumps({"monodepth_precheck": rel(CSV_MONODEPTH), "rows": len(rows)}, ensure_ascii=False))


def infer_priors(args: argparse.Namespace) -> None:
    if os.environ.get("E5_S2_PRIOR_CONTAINER") == "1":
        _infer_priors_container(args)
        return
    cmd = docker_base(args.gpu, {"E5_S2_PRIOR_CONTAINER": "1", "MPLCONFIGDIR": "/tmp/matplotlib"}) + [
        "python",
        "scripts/e5_c001/p2_gsjso/e5_c001_s2_direction_position.py",
        "infer-priors",
        "--device",
        "cuda:0",
    ]
    run(cmd, P2_RUN_DIR / "infer_priors_container.log", check=True, quiet=False)


def _project_local(points_local: np.ndarray, w2c: np.ndarray, K: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    hom = np.concatenate([points_local, np.ones((len(points_local), 1), dtype=np.float64)], axis=1)
    cam = (w2c @ hom.T).T[:, :3]
    z = cam[:, 2]
    uvw = (K @ cam.T).T
    uv = uvw[:, :2] / np.maximum(uvw[:, 2:3], 1e-9)
    return uv, z


def camera_depth_to_world(uv: np.ndarray, depth: np.ndarray, w2c: np.ndarray, K: np.ndarray) -> np.ndarray:
    if len(uv) == 0:
        return np.zeros((0, 3), dtype=np.float64)
    Kinv = np.linalg.inv(K)
    uv1 = np.column_stack([uv[:, 0], uv[:, 1], np.ones(len(uv), dtype=np.float64)])
    rays = (Kinv @ uv1.T).T
    pts_cam = rays * depth.reshape(-1, 1)
    R = w2c[:3, :3]
    t = w2c[:3, 3]
    return (R.T @ (pts_cam - t).T).T + SHIFT_UTM


def roof_normal_world(surface: eight.RoofSurface) -> np.ndarray:
    n = np.asarray([-surface.ax, -surface.by, 1.0], dtype=np.float64)
    n = n / max(np.linalg.norm(n), 1e-9)
    if n[2] < 0:
        n = -n
    return n


def square_crop(crop: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = crop
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    side = max(x1 - x0, y1 - y0, 128)
    x0 = int(round(cx - side / 2.0))
    y0 = int(round(cy - side / 2.0))
    x1 = x0 + int(side)
    y1 = y0 + int(side)
    if x0 < 0:
        x1 -= x0
        x0 = 0
    if y0 < 0:
        y1 -= y0
        y0 = 0
    if x1 > width:
        x0 -= x1 - width
        x1 = width
    if y1 > height:
        y0 -= y1 - height
        y1 = height
    return max(0, x0), max(0, y0), min(width, x1), min(height, y1)


def normal_mode_count(normals_world: np.ndarray) -> int:
    if len(normals_world) < 64:
        return 0
    n = normals_world.copy()
    n[n[:, 2] < 0] *= -1
    tilt = np.degrees(np.arccos(np.clip(n[:, 2], -1.0, 1.0)))
    sloped = tilt > 10.0
    if np.count_nonzero(sloped) < 40:
        return 0
    az = (np.degrees(np.arctan2(n[sloped, 1], n[sloped, 0])) + 360.0) % 180.0
    hist, _ = np.histogram(az, bins=np.linspace(0.0, 180.0, 19))
    threshold = max(8, 0.25 * float(hist.max()))
    peaks = 0
    for i, val in enumerate(hist):
        if val >= threshold and val >= hist[(i - 1) % len(hist)] and val >= hist[(i + 1) % len(hist)]:
            peaks += 1
    return peaks


def classify_angle(angle: float | None) -> str:
    if angle is None:
        return "not_measured"
    if angle < 15.0:
        return "good_lt15"
    if angle <= 30.0:
        return "borderline_15_30"
    return "bad_gt30"


def monodepth_building_score(_args: argparse.Namespace) -> None:
    from src.stage2.dataloader import ColmapDataset

    target_ids = GOOD6 + TEXTURELESS_OBS3 + GS_FAIL5
    refs_by_id = eight.parse_lod2_roofs(eight.LOD2_DIR, {full_id(x) for x in target_ids})
    fps = strips.load_footprints(target_ids)
    ds = ColmapDataset(root=str(DATA_ROOT), downscale=1.0, load_depth=True, load_normal=False, load_semantic=False)
    rows: list[dict[str, Any]] = []
    res_rows: list[dict[str, Any]] = []
    for sid in target_ids:
        bid = full_id(sid)
        refs = refs_by_id.get(bid, [])
        fp = fps.get(bid)
        if not refs or fp is None:
            append_issue("A-1", "warn", "reference roof or footprint missing for mono-depth direct score", bid)
            continue
        view_idx, crop = strips.select_view(ds, fp, refs)
        batch = ds[view_idx]
        stem = Path(str(batch["name"])).stem
        depth_path = MONO_DEPTH_DIR / f"{stem}.npy"
        if not depth_path.exists():
            continue
        mono = np.load(depth_path)
        samples: list[np.ndarray] = []
        for surf in refs:
            pts_xy = eight.sample_polygon_points(surf.polygon, spacing=0.75, limit=250)
            if len(pts_xy):
                z = surf.z_at(pts_xy[:, 0], pts_xy[:, 1])
                samples.append(np.column_stack([pts_xy[:, 0], pts_xy[:, 1], z]))
        if not samples:
            continue
        pts_utm = np.vstack(samples)
        uv, roof_depth = _project_local(pts_utm - SHIFT_UTM, batch["w2c"].numpy(), batch["K"].numpy())
        h, w = mono.shape
        u = np.rint(uv[:, 0]).astype(int)
        v = np.rint(uv[:, 1]).astype(int)
        inside = (roof_depth > 0) & (u >= 0) & (u < w) & (v >= 0) & (v < h)
        mono_at_roof = mono[v[inside], u[inside]] if np.any(inside) else np.asarray([])
        depth_err = mono_at_roof - roof_depth[inside] if np.any(inside) else np.asarray([])
        mono_world = camera_depth_to_world(uv[inside], mono_at_roof, batch["w2c"].numpy(), batch["K"].numpy()) if np.any(inside) else np.zeros((0, 3), dtype=np.float64)
        mono_ref_z = mono_world[:, 2] + ELLIP_TO_REF_SHIFT_M if len(mono_world) else np.asarray([])
        height_err = mono_ref_z - pts_utm[inside, 2] if len(mono_ref_z) else np.asarray([])
        z_vals = np.concatenate([surf.z_at(np.asarray([(fp["bbox"][0] + fp["bbox"][2]) / 2.0]), np.asarray([(fp["bbox"][1] + fp["bbox"][3]) / 2.0])) for surf in refs])
        crop_depth = mono[crop[1] : crop[3], crop[0] : crop[2]]
        crop_valid = crop_depth[np.isfinite(crop_depth) & (crop_depth > 0)]
        rows.append(
            {
                "building_id": bid,
                "group_new": group_label(sid),
                "view_idx": view_idx,
                "image_name": str(batch["name"]),
                "projected_roof_samples": int(np.count_nonzero(inside)),
                "roof_height_error_abs_median_m": fmt(float(np.median(np.abs(height_err))) if height_err.size else None),
                "roof_height_error_abs_p90_m": fmt(float(np.percentile(np.abs(height_err), 90)) if height_err.size else None),
                "signed_height_error_median_m": fmt(float(np.median(height_err)) if height_err.size else None),
                "roof_depth_error_abs_median_m": fmt(float(np.median(np.abs(depth_err))) if depth_err.size else None),
                "roof_depth_error_abs_p90_m": fmt(float(np.percentile(np.abs(depth_err), 90)) if depth_err.size else None),
                "signed_depth_error_median_m": fmt(float(np.median(depth_err)) if depth_err.size else None),
                "ellip_to_reference_shift_m": fmt(ELLIP_TO_REF_SHIFT_M),
                "reference_roof_z_median_m": fmt(float(np.median(z_vals)) if len(z_vals) else None),
                "mono_ref_z_p50_m": fmt(float(np.median(mono_ref_z)) if len(mono_ref_z) else None),
                "crop_mono_depth_p10": fmt(float(np.percentile(crop_valid, 10)) if len(crop_valid) else None),
                "crop_mono_depth_p90": fmt(float(np.percentile(crop_valid, 90)) if len(crop_valid) else None),
            }
        )
        if len(crop_valid):
            res_rows.append(
                {
                    "building_id": bid,
                    "mono_crop_depth_step_p90_p10_m": fmt(float(np.percentile(crop_valid, 90) - np.percentile(crop_valid, 10))),
                    "ref_roof_z_span_m": fmt(float(max([s.z_at(np.asarray([(fp['bbox'][0] + fp['bbox'][2]) / 2.0]), np.asarray([(fp['bbox'][1] + fp['bbox'][3]) / 2.0]))[0] for s in refs]) - min([s.z_at(np.asarray([(fp['bbox'][0] + fp['bbox'][2]) / 2.0]), np.asarray([(fp['bbox'][1] + fp['bbox'][3]) / 2.0]))[0] for s in refs]))),
                }
            )
    write_csv(CSV_MONODEPTH_BUILDING, rows)
    write_csv(CSV_MONODEPTH_RESOLUTION, res_rows)
    decide_monodepth_branch(rows)


def group_label(sid: str) -> str:
    if sid in GOOD6:
        return "양쪽 성공 6동"
    if sid in GS_FAIL5:
        return "GS만 실패 5동"
    if sid in TEXTURELESS_OBS3:
        return "입력 한계 5동/무늬없음·관측됨 3"
    return "other"


def decide_monodepth_branch(rows: list[dict[str, Any]]) -> None:
    vals = [num(r.get("roof_height_error_abs_median_m")) for r in rows]
    if not any(v is not None for v in vals):
        vals = [num(r.get("roof_depth_error_abs_median_m")) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        decision = "exclude_arm3"
        reason = "no finite roof direct-score values"
    else:
        med = float(np.median(vals))
        if med <= 3.0:
            decision = "arm3_default_under_provisional_threshold"
            reason = f"roof height direct-score median {med:.3f} m <= 3 m"
        elif med <= 8.0:
            decision = "needs_human_mitigation_choice_before_arm3"
            reason = f"roof height direct-score median {med:.3f} m in 3-8 m band"
        else:
            decision = "exclude_arm3"
            reason = f"roof height direct-score median {med:.3f} m > 8 m"
    payload = {"decision": decision, "reason": reason, "created_utc": datetime.now(timezone.utc).isoformat()}
    (P2_RUN_DIR / "monodepth_decision.json").parent.mkdir(parents=True, exist_ok=True)
    (P2_RUN_DIR / "monodepth_decision.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if decision == "exclude_arm3":
        append_issue("A-1", "warn", "Arm 3 excluded by mono-depth precheck", P2_RUN_DIR / "monodepth_decision.json")


def load_footprints(ids: list[str]) -> dict[str, dict[str, Any]]:
    return strips.load_footprints(ids)


def sheet_identity_alt(_args: argparse.Namespace) -> None:
    import torch
    from src.stage2.dataloader import ColmapDataset

    specs = [
        ("corrected_recheck", "dense", REPO / "results/tum_transfer/e5_corrected_s1_recheck/C001/runs/gs_e5_C001_corrected_s1_preprune_dense_r1/ckpt/final.pt"),
        ("corrected_recheck", "sparse", REPO / "results/tum_transfer/e5_corrected_s1_recheck/C001/runs/gs_e5_C001_corrected_s1_preprune_sparse_r1/ckpt/final.pt"),
        ("s1_full_factor", "w100_p005", REPO / "results/tum_transfer/e5_s1_full_factor/C001/runs/gs_e5_C001_s1fac_w100_p005_dense_r1/ckpt/final.pt"),
        ("s1_full_factor", "w240_p005", REPO / "results/tum_transfer/e5_s1_full_factor/C001/runs/gs_e5_C001_s1fac_w240_p005_dense_r1/ckpt/final.pt"),
        ("s1_full_factor", "w240_p050", REPO / "results/tum_transfer/e5_s1_full_factor/C001/runs/gs_e5_C001_s1fac_w240_p050_dense_r1/ckpt/final.pt"),
    ]
    ds = ColmapDataset(root=str(DATA_ROOT), downscale=1.0, load_depth=False, load_normal=False, load_semantic=False)
    camera_z = []
    for fr in ds.frames:
        c = -fr.R.T @ fr.t
        camera_z.append(float(c[2] + SHIFT_UTM[2]))
    cam_p = {q: float(np.percentile(camera_z, q)) for q in [5, 50, 95]}
    rows: list[dict[str, Any]] = []
    slice_points: list[tuple[str, np.ndarray, np.ndarray]] = []
    for family, label, ckpt in specs:
        if not ckpt.exists():
            append_issue("A-2", "warn", "checkpoint missing for sheet identity", ckpt)
            continue
        payload = torch.load(ckpt, map_location="cpu", weights_only=False)
        state = payload["state_dict"]
        means = state["means"].detach().cpu().numpy().astype(np.float64) + SHIFT_UTM
        op = torch.sigmoid(state["opacities_raw"].detach().cpu().float()).numpy()
        z = means[:, 2]
        for band, lo, hi in [("sheet_595_615", 595.0, 615.0), ("high_sheet_655_670", 655.0, 670.0)]:
            m = (z >= lo) & (z <= hi)
            pts = means[m]
            opa = op[m]
            rows.append(
                {
                    "family": family,
                    "label": label,
                    "band": band,
                    "z_min": lo,
                    "z_max": hi,
                    "n_gaussians": int(m.sum()),
                    "z_p50": fmt(float(np.quantile(pts[:, 2], 0.5)) if len(pts) else None),
                    "opacity_p50": fmt(float(np.quantile(opa, 0.5)) if len(opa) else None),
                    "camera_z_p05": fmt(cam_p[5]),
                    "camera_z_p50": fmt(cam_p[50]),
                    "camera_z_p95": fmt(cam_p[95]),
                    "sheet_vs_camera_p50_m": fmt((float(np.quantile(pts[:, 2], 0.5)) - cam_p[50]) if len(pts) else None),
                    "ckpt": rel(ckpt),
                }
            )
            if len(pts):
                slice_points.append((f"{family}:{label}:{band}", pts[:, :2], opa))
        hist, edges = np.histogram(z, bins=np.arange(520, 701, 2))
        for i, count in enumerate(hist):
            rows.append({"family": family, "label": label, "band": "z_hist_2m", "z_min": edges[i], "z_max": edges[i + 1], "n_gaussians": int(count), "ckpt": rel(ckpt)})
    write_csv(CSV_SHEET, rows)
    plot_sheet_alt(rows, slice_points, camera_z)
    print(json.dumps({"sheet_identity_alt": rel(CSV_SHEET), "rows": len(rows)}, ensure_ascii=False))


def plot_sheet_alt(rows: list[dict[str, Any]], slice_points: list[tuple[str, np.ndarray, np.ndarray]], camera_z: list[float]) -> None:
    out_dir = FIG_DIR / "sheet_identity"
    out_dir.mkdir(parents=True, exist_ok=True)
    hist_rows = [r for r in rows if r.get("band") == "z_hist_2m"]
    fig, axes = plt.subplots(1, 3, figsize=(15.0, 4.2))
    for family, label in sorted({(r["family"], r["label"]) for r in hist_rows}):
        g = sorted([r for r in hist_rows if r["family"] == family and r["label"] == label], key=lambda x: float(x["z_min"]))
        x = [(float(r["z_min"]) + float(r["z_max"])) / 2.0 for r in g]
        y = [int(r["n_gaussians"]) for r in g]
        axes[0].plot(x, y, label=f"{family}:{label}", linewidth=1.1)
    axes[0].axvspan(595, 615, color="#f94144", alpha=0.12)
    axes[0].axvspan(655, 670, color="#f8961e", alpha=0.10)
    axes[0].hist(camera_z, bins=20, color="black", alpha=0.15, label="camera z")
    axes[0].set_xlabel("z m")
    axes[0].set_ylabel("count / 2m bin")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=6)
    for label, xy, op in slice_points[:8]:
        if len(xy) > 25000:
            rng = np.random.default_rng(20260710)
            idx = rng.choice(np.arange(len(xy)), size=25000, replace=False)
            xy = xy[idx]
            op = op[idx]
        axes[1].scatter(xy[:, 0], xy[:, 1], s=1, alpha=0.18, c=op, cmap="viridis", vmin=0, vmax=1, label=label[:22])
    axes[1].set_aspect("equal", adjustable="box")
    axes[1].set_title("sheet horizontal slices")
    axes[1].legend(fontsize=5)
    axes[2].hist(camera_z, bins=30, color="#577590", alpha=0.8)
    axes[2].set_title("camera flight altitude z")
    axes[2].set_xlabel("z m")
    fig.tight_layout()
    fig.savefig(out_dir / "sheet_identity_alt.png", dpi=170)
    plt.close(fig)


def implementation_check(_args: argparse.Namespace) -> None:
    cfg = yaml_load(BASE_CONFIG)
    rows = [
        {
            "item": "elongation_filter_config",
            "status": "checked",
            "value": f"enabled={cfg.get('elongation_filter')}; axis_ratio_threshold={cfg.get('elongation_axis_ratio_threshold')}; active in densification strategy before grow/prune",
            "source": rel(BASE_CONFIG),
        },
        {
            "item": "mono_normal_loss_path",
            "status": "checked",
            "value": "src.stage2.renderer.render normal_render -> src.stage2.loss.data_fitting.l_normal absdot; S2 overrides normal_dir with Omnidata world npy maps",
            "source": "src/stage2/train.py; src/stage2/dataloader.py",
        },
        {
            "item": "depth_floor_path",
            "status": "checked",
            "value": "w_depth_eff=max(scheduled_weight, depth_weight_floor) when depth_weight_floor is set; Arm2/Arm3 use 0.15",
            "source": "src/stage2/train.py",
        },
        {
            "item": "pointcloud_stage_units",
            "status": "checked",
            "value": "pre/minobs/sor are occupied 0.5m footprint-grid cells from stage_coverage.csv; fp pts is final classified roof/wall point count inside footprint from Roofer prep metrics",
            "source": "scripts/e5_c001/p2_gsjso/e5_c001_readout_extract_ablation.py; e5_c001_pipeline_strips.py",
        },
    ]
    write_csv(CSV_IMPL, rows)
    print(json.dumps({"implementation_check": rel(CSV_IMPL), "rows": len(rows)}, ensure_ascii=False))


def normal_recheck(args: argparse.Namespace) -> None:
    from src.stage2.dataloader import ColmapDataset

    before_rows = read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_s1_full/tables/e5_c001_s1_full_normal_precheck.csv")
    before_by = {short_id(r.get("building_id", "")): r for r in before_rows}
    if not before_rows:
        append_issue("A-4", "warn", "S1 normal precheck CSV missing; before/after table limited", REPO / "docs/experiments/joint-optimization/e5_c001_s1_full/tables/e5_c001_s1_full_normal_precheck.csv")
    refs_by_id = eight.parse_lod2_roofs(eight.LOD2_DIR, {full_id(x) for x in NORMAL_RECHECK_IDS})
    footprints = strips.load_footprints(NORMAL_RECHECK_IDS)
    ds = ColmapDataset(root=str(DATA_ROOT), downscale=1.0, load_depth=False, load_normal=False, load_semantic=False)
    out_dir = FIG_DIR / "normal_recheck"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for sid in NORMAL_RECHECK_IDS:
        prev = before_by.get(sid, {})
        bid = full_id(sid)
        fp = footprints.get(bid)
        refs = refs_by_id.get(bid, [])
        after: dict[str, Any] = {
            "view_idx": "",
            "image_name": "",
            "crop_xyxy": "",
            "angle50": None,
            "angle75": None,
            "quality": "not_measured",
            "mode_count": "",
            "pair_png": "",
            "normal_path": "",
            "note": "",
        }
        if fp is None or not refs:
            append_issue("A-4", "warn", "footprint or reference roof missing for normal recheck", bid)
            after["note"] = "footprint/reference missing"
        else:
            view_idx, crop0 = strips.select_view(ds, fp, refs)
            batch = ds[view_idx]
            h = int(batch["height"])
            w = int(batch["width"])
            crop = square_crop(crop0, w, h)
            stem = Path(str(batch["name"])).stem
            normal_path = MONO_NORMAL_DIR / f"{stem}.npy"
            after.update({"view_idx": view_idx, "image_name": str(batch["name"]), "crop_xyxy": ",".join(str(v) for v in crop), "normal_path": rel(normal_path)})
            if not normal_path.exists():
                append_issue("A-4", "warn", "S2 mono normal prior missing; run infer-priors before final A-4 recheck", normal_path)
                after["note"] = "mono normal prior missing; before value retained only for comparison"
            else:
                n_world = np.load(normal_path).astype(np.float32)
                if n_world.shape[:2] != (h, w):
                    append_issue("A-4", "warn", f"mono normal shape mismatch {n_world.shape[:2]} vs {(h, w)}", normal_path)
                    after["note"] = "mono normal shape mismatch"
                else:
                    x0, y0, x1, y1 = crop
                    crop_n = n_world[y0:y1, x0:x1]
                    norm = np.linalg.norm(crop_n, axis=-1)
                    margin_y = max(1, int(crop_n.shape[0] * 0.18))
                    margin_x = max(1, int(crop_n.shape[1] * 0.18))
                    mask = np.zeros(crop_n.shape[:2], dtype=bool)
                    mask[margin_y : crop_n.shape[0] - margin_y, margin_x : crop_n.shape[1] - margin_x] = True
                    mask &= norm > 0.5
                    sample_world = crop_n[mask]
                    if len(sample_world):
                        sample_world = sample_world / np.maximum(np.linalg.norm(sample_world, axis=1, keepdims=True), 1e-6)
                    ref_world = np.vstack([roof_normal_world(s) for s in refs])
                    dots = np.abs(sample_world @ ref_world.T) if len(sample_world) else np.empty((0, len(ref_world)))
                    angles = np.degrees(np.arccos(np.clip(np.max(dots, axis=1), -1.0, 1.0))) if len(sample_world) else np.asarray([])
                    angle50 = float(np.median(angles)) if len(angles) else None
                    angle75 = float(np.percentile(angles, 75)) if len(angles) else None
                    pair_png = out_dir / f"{sid}_normal_recheck_pair.png"
                    rgb = batch["rgb"].numpy()
                    crop_rgb = rgb[y0:y1, x0:x1]
                    crop_vis = np.clip((crop_n + 1.0) * 0.5, 0.0, 1.0)
                    fig, axes = plt.subplots(1, 2, figsize=(6.0, 3.0))
                    axes[0].imshow(crop_rgb)
                    axes[0].set_title("reselected crop")
                    axes[1].imshow(crop_vis)
                    axes[1].set_title("S2 mono normal")
                    for ax in axes:
                        ax.axis("off")
                    fig.suptitle(f"{sid} angle50={angle50:.1f}" if angle50 is not None else sid, fontsize=10)
                    fig.tight_layout()
                    fig.savefig(pair_png, dpi=160)
                    plt.close(fig)
                    after.update(
                        {
                            "angle50": angle50,
                            "angle75": angle75,
                            "quality": classify_angle(angle50),
                            "mode_count": normal_mode_count(sample_world),
                            "pair_png": rel(pair_png),
                            "note": "after recomputed from S2 full-image Omnidata world-normal prior on reselected central-footprint view",
                        }
                    )
        rows.append(
            {
                "building_id": bid,
                "group_new": "GS만 실패 5동",
                "before_view_idx": prev.get("view_idx", ""),
                "before_image_name": prev.get("image_name", ""),
                "before_angle_error_median_deg_absdot": prev.get("angle_error_median_deg_absdot", ""),
                "before_quality_bin_locked": prev.get("quality_bin_locked", ""),
                "after_view_idx": after["view_idx"],
                "after_image_name": after["image_name"],
                "after_crop_xyxy": after["crop_xyxy"],
                "after_angle_error_median_deg_absdot": fmt(after["angle50"]),
                "after_angle_error_p75_deg_absdot": fmt(after["angle75"]),
                "after_quality_bin_locked": after["quality"],
                "after_normal_mode_count": after["mode_count"],
                "after_pair_png": after["pair_png"],
                "after_normal_path": after["normal_path"],
                "note": after["note"],
            }
        )
    write_csv(CSV_NORMAL_RECHECK, rows)
    print(json.dumps({"normal_recheck": rel(CSV_NORMAL_RECHECK), "rows": len(rows)}, ensure_ascii=False))


def a5_metric_prep(_args: argparse.Namespace) -> None:
    rows = [
        {
            "metric": "rend_dist_mean",
            "status": "implemented",
            "producer": "render_dist_summary",
            "definition": "mean render_dist over alpha>0.5 pixels for selected representative views; linear metre scale inherited from 20260709 recheck",
            "csv": rel(CSV_REND_DIST),
        },
        {
            "metric": "final_gaussian_count",
            "status": "implemented",
            "producer": "fingerprint_training/build_arm_cells",
            "definition": "state['n_prim'] from ckpt/final.pt and S0 ratio in arm cell table",
            "csv": rel(CSV_ARM_CELLS),
        },
        {
            "metric": "global_z_hist",
            "status": "implemented",
            "producer": "global_z_hist",
            "definition": "all Gaussian centers shifted to EPSG:25832 z; 2 m bins with opacity summaries",
            "csv": rel(CSV_GLOBAL_Z),
        },
    ]
    write_csv(CSV_A5_PREP, rows)
    print(json.dumps({"a5_metric_prep": rel(CSV_A5_PREP), "rows": len(rows)}, ensure_ascii=False))


def monodepth_allows_arm3() -> bool:
    path = P2_RUN_DIR / "monodepth_decision.json"
    if not path.exists():
        return False
    decision = json.loads(path.read_text(encoding="utf-8")).get("decision", "")
    return decision == "arm3_default_under_provisional_threshold"


def active_arms(include_arm3: bool | None = None) -> list[Arm]:
    if include_arm3 is None:
        include_arm3 = monodepth_allows_arm3()
    return [arm for arm in ARMS if arm.key != "arm3" or include_arm3]


def write_config(run_name_value: str, arm: Arm, *, max_iter: int, gate: bool, normal_weight: float = 0.05, mono_depth_weight: float = 0.05) -> Path:
    cfg = yaml_load(BASE_CONFIG)
    cfg["w_distort"] = float(arm.w_distort)
    cfg["w_normal"] = float(normal_weight)
    cfg["normal_warmup"] = 0
    cfg["normal_schedule"] = "constant"
    cfg["normal_ramp_steps"] = 0
    cfg["normal_dir"] = ws(MONO_NORMAL_DIR)
    cfg["load_normal"] = True
    cfg["prune_opa"] = 0.005
    cfg["final_prune_opa"] = 0.0
    cfg["seed_protect"] = True
    cfg["seed_protect_until_iter"] = 5000
    cfg["depth_schedule"] = "exp_decay"
    cfg["depth_ramp_steps"] = 30000
    cfg["depth_final_weight"] = 0.05
    if arm.depth_floor is None:
        cfg.pop("depth_weight_floor", None)
    else:
        cfg["depth_weight_floor"] = float(arm.depth_floor)
    if arm.use_mono_depth:
        cfg["mono_depth_dir"] = ws(MONO_DEPTH_DIR)
        cfg["w_mono_depth"] = float(mono_depth_weight)
        cfg["mono_depth_schedule"] = "constant"
        cfg["mono_depth_warmup"] = 0
    else:
        cfg.pop("mono_depth_dir", None)
        cfg["w_mono_depth"] = 0.0
    cfg["max_iter"] = int(max_iter)
    cfg["ckpt_every"] = 500 if gate else 5000
    cfg["eval_every"] = 999999 if gate else 2000
    cfg["loss_grad_audit_every"] = 50 if gate else 500
    cfg["loss_grad_audit_params"] = "geometry"
    cfg["out_dir"] = ws(CKPT_ROOT / run_name_value)
    path = CONFIG_DIR / f"{run_name_value}.yaml"
    yaml_dump(path, cfg)
    return path


def generate_configs(args: argparse.Namespace) -> None:
    P2_RUN_DIR.mkdir(parents=True, exist_ok=True)
    include_arm3 = args.include_arm3 or monodepth_allows_arm3()
    paths: list[Path] = []
    # B-0: normal gate and optional mono-depth gate.
    paths.append(write_config(gate_run_name("normal", 0.05), arm_by_key("arm1"), max_iter=1000, gate=True, normal_weight=0.05))
    paths.append(write_config(gate_run_name("normal", 0.025), arm_by_key("arm1"), max_iter=1000, gate=True, normal_weight=0.025))
    if include_arm3:
        paths.append(write_config(gate_run_name("mono_depth", 0.05), arm_by_key("arm3"), max_iter=1000, gate=True, normal_weight=0.05, mono_depth_weight=0.05))
        paths.append(write_config(gate_run_name("mono_depth", 0.025), arm_by_key("arm3"), max_iter=1000, gate=True, normal_weight=0.05, mono_depth_weight=0.025))
    for arm in active_arms(include_arm3):
        for rep in [1, 2]:
            paths.append(write_config(run_name(arm.key, rep), arm, max_iter=30000, gate=False))
    rows = []
    for path in sorted(set(paths)):
        cfg = yaml_load(path)
        rows.append(
            {
                "config": rel(path),
                "run_name": path.stem,
                "arm": next((a.key for a in ARMS if f"_{a.key}_" in path.stem), "gate"),
                "max_iter": cfg.get("max_iter", ""),
                "w_normal": cfg.get("w_normal", ""),
                "w_distort": cfg.get("w_distort", ""),
                "depth_weight_floor": cfg.get("depth_weight_floor", ""),
                "w_mono_depth": cfg.get("w_mono_depth", ""),
                "normal_dir": cfg.get("normal_dir", ""),
                "mono_depth_dir": cfg.get("mono_depth_dir", ""),
                "out_dir": cfg.get("out_dir", ""),
                "sha256": sha256_file(path),
            }
        )
    write_csv(CSV_INVENTORY, rows)
    print(json.dumps({"configs": len(rows), "inventory": rel(CSV_INVENTORY), "include_arm3": include_arm3}, ensure_ascii=False))


def docker_train(config: Path, gpu: str, log_path: Path) -> int:
    cmd = docker_base(gpu) + ["python", "-m", "src.stage2.train", "--config", rel(config)]
    start = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(cmd, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    end = datetime.now(timezone.utc).isoformat()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f"START_UTC={start}\nHOST_GPU={gpu}\nCONFIG={rel(config)}\nCOMMAND={' '.join(cmd)}\n"
        + (proc.stdout or "")
        + f"\nEND_UTC={end}\nRETURN_CODE={proc.returncode}\n",
        encoding="utf-8",
    )
    print(proc.stdout or "", end="", flush=True)
    print(json.dumps({"config": rel(config), "gpu": gpu, "return_code": proc.returncode, "log": rel(log_path)}, ensure_ascii=False), flush=True)
    return int(proc.returncode)


def train_one(args: argparse.Namespace) -> None:
    config = CONFIG_DIR / f"{args.run_name}.yaml"
    if not config.exists():
        raise FileNotFoundError(config)
    rc = docker_train(config, args.gpu, TRAIN_LOG_ROOT / f"{args.run_name}.log")
    if rc != 0 and args.check:
        raise SystemExit(rc)


def parse_train_log(path: Path) -> dict[str, str]:
    out = {"start_utc": "", "end_utc": "", "host_gpu": "", "return_code": "", "elapsed_min": ""}
    if not path.exists():
        run_name_value = path.stem
        final_ckpt = CKPT_ROOT / run_name_value / "ckpt/final.pt"
        if final_ckpt.exists():
            out["return_code"] = "final_ckpt_present_log_missing"
            out["end_utc"] = datetime.fromtimestamp(final_ckpt.stat().st_mtime, timezone.utc).isoformat()
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("START_UTC="):
            out["start_utc"] = line.split("=", 1)[1].strip()
        elif line.startswith("END_UTC="):
            out["end_utc"] = line.split("=", 1)[1].strip()
        elif line.startswith("HOST_GPU="):
            out["host_gpu"] = line.split("=", 1)[1].strip()
        elif line.startswith("RETURN_CODE="):
            out["return_code"] = line.split("=", 1)[1].strip()
        elif "[done]" in line and " iter in " in line:
            out["elapsed_min"] = line.split(" iter in ", 1)[1].split(" min", 1)[0].strip()
    return out


def audit_csv_for(run_name_value: str) -> Path:
    return CKPT_ROOT / run_name_value / "audit/loss_grad_norms.csv"


def summarize_audit(run_name_value: str, component: str) -> dict[str, Any]:
    rows = read_csv(audit_csv_for(run_name_value))
    part = [r for r in rows if r.get("component") == component]
    total_rows = [r for r in rows if r.get("component") == "photo"]
    vals_total = [num(r.get("total_loss")) for r in total_rows]
    vals_loss = [num(r.get("weighted_loss_share")) for r in part]
    vals_grad = [num(r.get("grad_norm_share")) for r in part]
    return {
        "run_name": run_name_value,
        "component": component,
        "audit_csv": rel(audit_csv_for(run_name_value)) if audit_csv_for(run_name_value).exists() else "",
        "audit_rows": len(rows),
        "all_total_loss_finite": str(all(v is not None and math.isfinite(v) for v in vals_total)).lower(),
        "weighted_loss_share_max": max([v for v in vals_loss if v is not None], default=None),
        "grad_norm_share_max": max([v for v in vals_grad if v is not None], default=None),
        "weighted_loss_share_last": vals_loss[-1] if vals_loss else None,
        "grad_norm_share_last": vals_grad[-1] if vals_grad else None,
    }


def summarize_gates(_args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    decisions: dict[str, dict[str, Any]] = {}
    for kind, component in [("normal", "normal"), ("mono_depth", "mono_depth")]:
        base_rn = gate_run_name(kind, 0.05)
        if not (CONFIG_DIR / f"{base_rn}.yaml").exists():
            continue
        for weight in [0.05, 0.025]:
            rn = gate_run_name(kind, weight)
            if not (CONFIG_DIR / f"{rn}.yaml").exists():
                continue
            info = parse_train_log(TRAIN_LOG_ROOT / f"{rn}.log")
            s = summarize_audit(rn, component)
            final_ckpt = CKPT_ROOT / rn / "ckpt/final.pt"
            return_ok = info.get("return_code") == "0"
            finite_ok = s["all_total_loss_finite"] == "true"
            grad_ok = (s["grad_norm_share_max"] is not None and float(s["grad_norm_share_max"]) <= 0.40)
            gate_ok = return_ok and finite_ok and grad_ok and final_ckpt.exists()
            rows.append(
                {
                    "gate_kind": kind,
                    "component": component,
                    "weight": weight,
                    "run_name": rn,
                    "return_code": info.get("return_code", ""),
                    "final_ckpt_exists": str(final_ckpt.exists()).lower(),
                    "gate_finite_ok": str(finite_ok).lower(),
                    "gate_grad_share_le_040": str(grad_ok).lower(),
                    "gate_ok": str(gate_ok).lower(),
                    **{k: fmt(v) for k, v in s.items() if k not in {"run_name", "audit_csv", "component", "all_total_loss_finite"}},
                    "audit_csv": s["audit_csv"],
                    "log": rel(TRAIN_LOG_ROOT / f"{rn}.log"),
                }
            )
            if kind not in decisions and gate_ok:
                decisions[kind] = {"selected_weight": weight, "reason": f"{kind} gate passed at {weight}"}
                break
        if kind not in decisions and (CONFIG_DIR / f"{base_rn}.yaml").exists():
            append_issue("B-0", "error", f"{kind} gate failed at 0.05 and 0.025", CSV_GRAD_SHARE)
            decisions[kind] = {"selected_weight": None, "reason": f"{kind} gate failed"}
    (P2_RUN_DIR / "gate_decisions.json").write_text(json.dumps(decisions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        d = decisions.get(row["gate_kind"], {})
        row["selected_weight"] = d.get("selected_weight")
        row["selection_reason"] = d.get("reason", "")
    write_csv(CSV_GRAD_SHARE, rows)
    print(json.dumps({"grad_share": rel(CSV_GRAD_SHARE), "decisions": decisions}, ensure_ascii=False))


def configure_ablation_module(include_arm3: bool | None = None) -> list[Arm]:
    arms = active_arms(include_arm3)
    ab.RUN_ID = RUN_ID
    ab.P2_RUN_DIR = P2_RUN_DIR
    ab.P0_RUN_ID = P0_RUN_ID
    ab.P0_RUN_DIR = P0_RUN_DIR
    ab.RESULTS_ROOT = RESULTS_ROOT
    ab.CKPT_ROOT = CKPT_ROOT
    ab.TRAIN_RUN_DIR = P2_RUN_DIR
    ab.CANON_GATE_DIR = REPO / "phases/p0-audit/runs/e5p_gate_20260707_C001"
    ab.DATA_ROOT = rel(DATA_ROOT)
    ab.TORCH_EXTENSIONS = TORCH_EXTENSIONS
    ab.FIG_DIR = FIG_DIR / "readout"
    ab.REPORT_PATH = P2_RUN_DIR / "readout_tmp.md"
    ab.COVERAGE_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_coverage.csv"
    ab.FILTER_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_filter_contrib.csv"
    ab.METRICS_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_405_rescore_building.csv"
    ab.SUMMARY_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_summary.csv"
    ab.TRADEOFF_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_tradeoff.csv"
    ab.CASE_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_representative_buildings.csv"
    ab.INVENTORY_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_readout_inventory.csv"
    ab.ISSUES_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_readout_issues.csv"
    ab.RENDER_COVERAGE = REPO / "docs/e5_c001_s2_render_readout_coverage.csv"
    ab.SETTINGS = [ab.Setting("base", "S2 canonical readout", min_obs=3, voxel=0.05, sor="on", sor_std=2.0)]

    def selected_run_names(args: argparse.Namespace) -> list[str]:
        names = [run_name(arm.key, rep) for arm in arms for rep in [1, 2]]
        selected = getattr(args, "runs", None)
        if not selected:
            return names
        missing = sorted(set(selected) - set(names))
        if missing:
            raise RuntimeError(f"unknown S2 run names: {missing}")
        selected_set = set(selected)
        return [name for name in names if name in selected_set]

    def source_for(setting: ab.Setting, run_name_value: str) -> Any:
        src = ORIGINAL_AB_SOURCE_FOR(setting, run_name_value)
        repaired_root = REPAIRED_P0_RUN_DIR / setting.key
        repaired_status = repaired_root / "status" / f"{run_name_value}_run_1.csv"
        repaired_cityjson = repaired_root / "cityjson" / f"{run_name_value}_run_1.city.json"
        if repaired_status.exists() and repaired_cityjson.exists():
            src.status_path = repaired_status
            src.cityjson_path = repaired_cityjson
            src.source_badge = f"{setting.key}_405repair"
            src.readout = src.readout + "; 405 winding repair overlay"
        return src

    def write_readout_report(*_args: Any, **_kwargs: Any) -> None:
        ab.REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ab.REPORT_PATH.write_text("# S2 readout tmp\n\nGenerated by redirected C001 readout harness.\n", encoding="utf-8")

    ab.selected_run_names = selected_run_names
    ab.source_for = source_for
    ab.write_report = write_readout_report
    return arms


def evaluate_or_container(args: argparse.Namespace) -> None:
    configure_ablation_module(args.include_arm3)
    if os.environ.get("E5_S2_EVAL_CONTAINER") == "1":
        ab.evaluate(args)
        return
    try:
        ab.load_eight_module()
    except ModuleNotFoundError:
        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-e",
            "E5_S2_EVAL_CONTAINER=1",
            "-e",
            "MPLCONFIGDIR=/tmp/matplotlib",
            "-v",
            f"{REPO}:/workspace/JointBuildGS",
            "-w",
            "/workspace/JointBuildGS",
            "jointbuildgs-p0-tools:t0",
            "python3",
            "scripts/e5_c001/p2_gsjso/e5_c001_s2_direction_position.py",
            "evaluate",
        ]
        if args.include_arm3:
            cmd.append("--include-arm3")
        if args.force:
            cmd.append("--force")
        ab.run(cmd, log_path=P2_RUN_DIR / "evaluate_container.log", check=True, quiet=False)
        return
    ab.evaluate(args)


def readout_like(args: argparse.Namespace) -> None:
    configure_ablation_module(args.include_arm3)
    if args.cmd in {"readout", "all"}:
        ab.run_readout(args)
    if args.cmd in {"assemble", "all"}:
        ab.run_assemble(args)
    if args.cmd in {"evaluate", "all"}:
        evaluate_or_container(args)


def checkpoint_path(run_name_value: str, step: int | str) -> Path:
    if step == "final" or step == 30000:
        return CKPT_ROOT / run_name_value / "ckpt/final.pt"
    return CKPT_ROOT / run_name_value / "ckpt" / f"step_{int(step):06d}.pt"


def gaussian_stats_for_ckpt(ckpt: Path, footprints: dict[str, dict[str, Any]], target_ids: list[str]) -> list[dict[str, Any]]:
    import torch

    if not ckpt.exists():
        return []
    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    state = payload["state_dict"]
    means = state["means"].detach().cpu().numpy().astype(np.float64) + SHIFT_UTM
    opa = torch.sigmoid(state["opacities_raw"].detach().cpu().float()).numpy()
    rows: list[dict[str, Any]] = []
    for sid in target_ids:
        bid = full_id(sid)
        fp = footprints.get(bid)
        if fp is None:
            continue
        x0, y0, x1, y1 = fp["bbox"]
        m = (means[:, 0] >= x0 - 2.0) & (means[:, 0] <= x1 + 2.0) & (means[:, 1] >= y0 - 2.0) & (means[:, 1] <= y1 + 2.0)
        idx = np.array([], dtype=np.int64)
        if np.any(m):
            cand = means[m]
            inside = np.zeros(cand.shape[0], dtype=bool)
            for path in fp["paths"]:
                inside |= path.contains_points(cand[:, :2])
            idx = np.where(m)[0][inside]
        z = means[idx, 2] if idx.size else np.array([], dtype=float)
        op = opa[idx] if idx.size else np.array([], dtype=float)
        rows.append(
            {
                "building_id": bid,
                "n_gaussians_in_footprint": int(idx.size),
                "z_p50": float(np.quantile(z, 0.50)) if z.size else None,
                "z_std": float(np.std(z)) if z.size else None,
                "opacity_p50": float(np.quantile(op, 0.50)) if op.size else None,
            }
        )
    return rows


def timeline_roofcrop(args: argparse.Namespace) -> None:
    arms = active_arms(args.include_arm3)
    fps = load_footprints(TIMELINE_IDS)
    rows: list[dict[str, Any]] = []
    for arm in arms:
        for rep in [1, 2]:
            rn = run_name(arm.key, rep)
            for step in [5000, 10000, 15000, 20000, 25000, "final"]:
                ckpt = checkpoint_path(rn, step)
                for item in gaussian_stats_for_ckpt(ckpt, fps, TIMELINE_IDS):
                    rows.append(
                        {
                            "arm": arm.key,
                            "replicate": f"r{rep}",
                            "run_name": rn,
                            "step": 30000 if step == "final" else step,
                            "ckpt": rel(ckpt),
                            **{k: fmt(v) for k, v in item.items()},
                        }
                    )
    write_csv(CSV_TIMELINE, rows)
    plot_timeline(rows)
    print(json.dumps({"timeline": rel(CSV_TIMELINE), "rows": len(rows)}, ensure_ascii=False))


def plot_timeline(rows: list[dict[str, Any]]) -> None:
    out_dir = FIG_DIR / "timeline"
    out_dir.mkdir(parents=True, exist_ok=True)
    for sid in TIMELINE_IDS:
        bid = full_id(sid)
        part = [r for r in rows if r.get("building_id") == bid]
        if not part:
            continue
        fig, axes = plt.subplots(1, 3, figsize=(11.0, 3.5))
        for arm_rep in sorted({(r["arm"], r["replicate"]) for r in part}):
            arm, rep = arm_rep
            g = sorted([r for r in part if r["arm"] == arm and r["replicate"] == rep], key=lambda x: int(x["step"]))
            x = [int(r["step"]) / 1000 for r in g]
            label = f"{arm}:{rep}"
            axes[0].plot(x, [num(r["n_gaussians_in_footprint"]) or 0 for r in g], marker="o", label=label)
            axes[1].plot(x, [num(r["z_p50"]) or np.nan for r in g], marker="o", label=label)
            axes[2].plot(x, [num(r["opacity_p50"]) or np.nan for r in g], marker="o", label=label)
        axes[0].set_ylabel("count")
        axes[1].set_ylabel("z p50")
        axes[2].set_ylabel("opacity p50")
        for ax in axes:
            ax.set_xlabel("k iter")
            ax.grid(alpha=0.25)
        axes[0].legend(fontsize=6)
        fig.suptitle(f"S2 roofcrop timeline {sid}", fontsize=11)
        fig.tight_layout()
        fig.savefig(out_dir / f"timeline_{sid}.png", dpi=180)
        plt.close(fig)


def global_z_hist(args: argparse.Namespace) -> None:
    import torch

    rows: list[dict[str, Any]] = []
    for arm in active_arms(args.include_arm3):
        for rep in [1, 2]:
            rn = run_name(arm.key, rep)
            ckpt = checkpoint_path(rn, "final")
            if not ckpt.exists():
                continue
            state = torch.load(ckpt, map_location="cpu", weights_only=False)["state_dict"]
            z = state["means"].detach().cpu().numpy()[:, 2].astype(np.float64) + SHIFT_UTM[2]
            op = torch.sigmoid(state["opacities_raw"].detach().cpu().float()).numpy()
            hist, edges = np.histogram(z, bins=np.arange(520, 701, 2))
            for i, count in enumerate(hist):
                m = (z >= edges[i]) & (z < edges[i + 1])
                rows.append(
                    {
                        "arm": arm.key,
                        "replicate": f"r{rep}",
                        "run_name": rn,
                        "z_min": edges[i],
                        "z_max": edges[i + 1],
                        "n_gaussians": int(count),
                        "opacity_p50": fmt(float(np.quantile(op[m], 0.5)) if np.any(m) else None),
                        "ckpt": rel(ckpt),
                    }
                )
    write_csv(CSV_GLOBAL_Z, rows)
    print(json.dumps({"global_z_hist": rel(CSV_GLOBAL_Z), "rows": len(rows)}, ensure_ascii=False))


def fingerprint_training(args: argparse.Namespace) -> None:
    import torch

    rows: list[dict[str, Any]] = []
    for arm in active_arms(args.include_arm3):
        for rep in [1, 2]:
            rn = run_name(arm.key, rep)
            cfg = CONFIG_DIR / f"{rn}.yaml"
            eff = CKPT_ROOT / rn / "effective_config.json"
            ckpt = checkpoint_path(rn, "final")
            log = TRAIN_LOG_ROOT / f"{rn}.log"
            info = parse_train_log(log)
            state = torch.load(ckpt, map_location="cpu", weights_only=False) if ckpt.exists() else {}
            effective = json.loads(eff.read_text(encoding="utf-8")) if eff.exists() else {}
            rows.append(
                {
                    "arm": arm.key,
                    "replicate": f"r{rep}",
                    "run_name": rn,
                    "seed": 2001,
                    "config": rel(cfg),
                    "config_sha256": sha256_file(cfg) if cfg.exists() else "",
                    "effective_config": rel(eff),
                    "effective_config_sha256": sha256_file(eff) if eff.exists() else "",
                    "ckpt": rel(ckpt),
                    "ckpt_sha256": sha256_file(ckpt) if ckpt.exists() else "",
                    "return_code": info.get("return_code", ""),
                    "elapsed_min": info.get("elapsed_min", ""),
                    "host_gpu": info.get("host_gpu", ""),
                    "max_iter": state.get("it", "") if state else "",
                    "final_n_gaussians": state.get("n_prim", "") if state else "",
                    "depth_weight_floor": effective.get("depth_weight_floor", ""),
                    "normal_dir": effective.get("normal_dir", ""),
                    "mono_depth_dir": effective.get("mono_depth_dir", ""),
                    "audit_csv": rel(audit_csv_for(rn)) if audit_csv_for(rn).exists() else "",
                }
            )
    write_csv(P2_RUN_DIR / "train_fingerprints.csv", rows)
    print(json.dumps({"train_fingerprints": rel(P2_RUN_DIR / "train_fingerprints.csv"), "rows": len(rows)}, ensure_ascii=False))


def repair_405(args: argparse.Namespace) -> None:
    import e5_c001_405_repair as repair

    repair.RUN_ID = REPAIR_RUN_ID
    repair.REPAIR_ROOT = P0_RUNS / REPAIR_RUN_ID
    repair.CSV_SUMMARY = CSV_405_REPAIR
    repair.CSV_BUILDING = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_405_repair_status_building.csv"
    repair.CSV_ISSUES = REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_405_repair_issues.csv"
    repair_args = argparse.Namespace(
        source_run_id=[P0_RUN_ID],
        settings=["base"],
        include_factor=False,
        append=False,
        force=args.force,
    )
    repair.process(repair_args)
    print(json.dumps({"repair_405": rel(CSV_405_REPAIR)}, ensure_ascii=False))


def pipeline_strips(args: argparse.Namespace) -> None:
    from src.stage2.dataloader import ColmapDataset

    os.environ.setdefault("TORCH_HOME", "/tmp/torch")
    arms = configure_ablation_module(args.include_arm3)
    reps = [1, 2] if args.rep == "all" else [int(args.rep)]
    conditions = [
        strips.StripCondition(
            key=f"{arm.key}_r{rep}",
            label=f"{arm.key} {arm.label} r{rep}",
            run_name=run_name(arm.key, rep),
            ckpt=checkpoint_path(run_name(arm.key, rep), "final"),
            coverage_csv=ab.COVERAGE_CSV,
            metrics_csv=ab.METRICS_CSV,
            p0_run_id=P0_RUN_ID,
        )
        for arm in arms
        for rep in reps
    ]
    strips.REPAIR_ROOT = P0_RUNS / REPAIR_RUN_ID
    ids = list(TIMELINE_IDS)
    footprints = strips.load_footprints(ids)
    refs_by_id = eight.parse_lod2_roofs(eight.LOD2_DIR, {full_id(x) for x in ids})
    ds = ColmapDataset(root=str(DATA_ROOT), downscale=args.downscale, load_depth=True, load_normal=False, load_semantic=False)
    strips.render_crop.dataset = ds
    render_cache: dict[tuple[str, int], dict[str, np.ndarray]] = {}
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    out_dir = FIG_DIR / "pipeline_strips"
    for condition in conditions:
        if not condition.ckpt.exists():
            append_issue("B-2", "warn", "checkpoint missing for S2 pipeline strip", condition.ckpt)
            issues.append({"condition": condition.key, "building_id": "", "message": "checkpoint missing", "path": rel(condition.ckpt)})
            continue
        gauss = strips.load_gaussians(condition.ckpt)
        pred_by_id = eight.parse_cityjson_roofs(strips.cityjson_path(condition), {full_id(x) for x in ids})
        pred_by_id = {bid: eight.shift_surface_z(surfs, condition.z_shift_to_reference_m) for bid, surfs in pred_by_id.items()}
        for sid in ids:
            bid = full_id(sid)
            fp = footprints.get(bid)
            refs = refs_by_id.get(bid, [])
            if fp is None or not refs:
                append_issue("B-2", "warn", "footprint or reference missing for S2 pipeline strip", bid)
                issues.append({"condition": condition.key, "building_id": bid, "message": "footprint or reference missing", "path": ""})
                continue
            view_idx, crop = strips.select_view(ds, fp, refs)
            rendered = None
            try:
                rendered = strips.render_crop(condition, view_idx, crop, args.device, render_cache)
            except Exception as exc:  # noqa: BLE001
                append_issue("B-2", "warn", f"S2 pipeline strip render failed: {type(exc).__name__}: {exc}", condition.ckpt)
                issues.append({"condition": condition.key, "building_id": bid, "message": f"render failed: {type(exc).__name__}: {exc}", "path": rel(condition.ckpt)})
            counts = strips.coverage_counts(condition, bid)
            status = strips.status_for(condition, bid)
            out = out_dir / f"{sid}_{condition.key}.png"
            strips.plot_strip(condition, bid, fp, refs, pred_by_id.get(bid, []), gauss, rendered, counts, status, out)
            stats = strips.gaussian_stats(gauss["means"], gauss["opacity"], fp)
            replicate = condition.key.rsplit("_", 1)[-1]
            rows.append(
                {
                    "condition": condition.key,
                    "arm": condition.key.rsplit("_", 1)[0],
                    "replicate": replicate,
                    "run_name": condition.run_name,
                    "building_id": bid,
                    "figure": rel(out),
                    "view_idx": view_idx,
                    "crop_xyxy": ",".join(str(v) for v in crop),
                    "ckpt": rel(condition.ckpt),
                    "cityjson": rel(strips.cityjson_path(condition)),
                    "status_reason": status.get("reason", ""),
                    "has_lod22": status.get("has_lod22", ""),
                    "val3dity_valid": status.get("val3dity_valid", ""),
                    **{k: "" if v is None else v for k, v in stats.items()},
                    **{f"readout_{k}": v for k, v in counts.items()},
                }
            )
            print(json.dumps({"strip": rel(out), "condition": condition.key, "building_id": bid}, ensure_ascii=False), flush=True)
    write_csv(CSV_PIPELINE_STRIPS, rows)
    write_csv(
        REPO / "docs/experiments/joint-optimization/e5_c001_s2/tables/e5_c001_s2_pipeline_strips_issues.csv",
        issues,
        ["condition", "building_id", "message", "path"],
    )
    print(json.dumps({"pipeline_strips": rel(CSV_PIPELINE_STRIPS), "rows": len(rows), "issues": len(issues)}, ensure_ascii=False))


def s0_dense_count() -> int:
    rows = read_csv(REPO / "phases/p2-gsjso/runs/e5_c001/e5p_train_20260707_C001/train_fingerprints.csv")
    for row in rows:
        if row.get("run_name") == "gs_e5_C001_dense_r1":
            try:
                return int(float(row.get("final_n") or row.get("final_n_gaussians") or 0))
            except ValueError:
                pass
    return 575318


def rend_dist_summary(args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    for arm in active_arms(args.include_arm3):
        for rep in [1, 2]:
            rn = run_name(arm.key, rep)
            audit = read_csv(audit_csv_for(rn))
            eff_path = CKPT_ROOT / rn / "effective_config.json"
            denom = 1.0
            if eff_path.exists():
                denom = float(json.loads(eff_path.read_text(encoding="utf-8")).get("distort_norm_denominator", 1.0) or 1.0)
            dist_rows = [r for r in audit if r.get("component") == "distort"]
            tail = dist_rows[-10:]
            vals = [num(r.get("raw_loss")) for r in tail]
            vals = [v * denom for v in vals if v is not None]
            rows.append(
                {
                    "arm": arm.key,
                    "replicate": f"r{rep}",
                    "run_name": rn,
                    "rend_dist_mean_tail_m": fmt(float(np.mean(vals)) if vals else None),
                    "rend_dist_p50_tail_m": fmt(float(np.median(vals)) if vals else None),
                    "audit_rows_tail": len(tail),
                    "denominator": fmt(denom),
                    "audit_csv": rel(audit_csv_for(rn)),
                    "note": "tail audit reconstruction: loss_dist raw_loss * distort_norm_denominator",
                }
            )
    write_csv(CSV_REND_DIST, rows)
    print(json.dumps({"rend_dist": rel(CSV_REND_DIST), "rows": len(rows)}, ensure_ascii=False))


def summarize_source(metrics: list[dict[str, str]], run_name_value: str) -> dict[str, Any]:
    part = [r for r in metrics if r.get("setting") == "base" and r.get("run_name") == run_name_value]
    rms_vals = [num(r.get("ref_rms_m")) for r in part]
    rms_vals = [v for v in rms_vals if v is not None]
    return {
        "n": len(part),
        "has_lod22": sum(tf(r.get("has_lod22")) for r in part),
        "valid_assembled": sum(tf(r.get("has_lod22")) and tf(r.get("val3dity_valid")) for r in part),
        "invalid_assembled": sum(tf(r.get("has_lod22")) and not tf(r.get("val3dity_valid")) for r in part),
        "median_ref_rms_m": float(np.median(rms_vals)) if rms_vals else None,
    }


def coverage_mean(run_name_value: str) -> float | None:
    rows = read_csv(ab.COVERAGE_CSV)
    vals = [
        num(r.get("coverage_frac"))
        for r in rows
        if r.get("setting") == "base" and r.get("run_name") == run_name_value and r.get("stage") == "sor_post_clean"
    ]
    vals = [v for v in vals if v is not None]
    return float(np.mean(vals)) if vals else None


def build_arm_cells(args: argparse.Namespace) -> None:
    arms = configure_ablation_module(args.include_arm3)
    metrics = read_csv(ab.METRICS_CSV)
    raw = read_csv(REPO / "docs/experiments/evaluation/e5_c001_8way/tables/e5_c001_8way_metrics.csv")
    s1 = read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_3b_s1/tables/e5_c001_3b_s1_metrics.csv")
    train_fp = read_csv(P2_RUN_DIR / "train_fingerprints.csv")
    rend = read_csv(CSV_REND_DIST)
    raw_by = {(r.get("source_run", ""), r.get("building_id", "")): r for r in raw}
    s1_by = {(r.get("source_run", ""), r.get("building_id", "")): r for r in s1}
    metric_by = {(r.get("run_name", ""), r.get("building_id", "")): r for r in metrics if r.get("setting") == "base"}
    train_by = {r.get("run_name", ""): r for r in train_fp}
    rend_by = {r.get("run_name", ""): r for r in rend}
    s0x2 = s0_dense_count() * 2
    rows: list[dict[str, Any]] = []
    for arm in arms:
        for rep in [1, 2]:
            rn = run_name(arm.key, rep)
            sm = summarize_source(metrics, rn)
            normal_eval = []
            for sid in GOOD6:
                bid = full_id(sid)
                row = metric_by.get((rn, bid), {})
                raw_row = raw_by.get(("raw_dense", bid), {})
                s1_row = s1_by.get(("base__gs_e5_C001_s1_dense_r1", bid), {})
                rms = num(row.get("ref_rms_m"))
                raw_rms = num(raw_row.get("ref_rms_m"))
                s1_rms = num(s1_row.get("ref_rms_m"))
                normal_eval.append(
                    {
                        "built": tf(row.get("has_lod22")),
                        "raw_anchor_ok": rms is not None and raw_rms is not None and rms <= raw_rms + 0.5,
                        "delta_vs_s1": None if rms is None or s1_rms is None else rms - s1_rms,
                    }
                )
            deltas = [x["delta_vs_s1"] for x in normal_eval if x["delta_vs_s1"] is not None]
            final_n = num(train_by.get(rn, {}).get("final_n_gaussians"))
            rend_tail = num(rend_by.get(rn, {}).get("rend_dist_mean_tail_m"))
            guard = all(x["built"] for x in normal_eval) and sum(bool(x["raw_anchor_ok"]) for x in normal_eval) >= 5
            accuracy = bool(deltas) and float(np.median(deltas)) <= 0.3 and not any(d > 1.5 for d in deltas)
            cleaning = final_n is not None and final_n <= s0x2 and rend_tail is not None and rend_tail <= 0.5
            validity = sm["valid_assembled"] >= 10
            rows.append(
                {
                    "arm": arm.key,
                    "replicate": f"r{rep}",
                    "run_name": rn,
                    "configuration": arm.label,
                    "has_lod22": sm["has_lod22"],
                    "valid_assembled": sm["valid_assembled"],
                    "invalid_assembled": sm["invalid_assembled"],
                    "median_ref_rms_m": fmt(sm["median_ref_rms_m"]),
                    "mean_coverage_post_sor": fmt(coverage_mean(rn)),
                    "good6_all_built": str(all(x["built"] for x in normal_eval)).lower(),
                    "good6_raw_anchor_count": sum(bool(x["raw_anchor_ok"]) for x in normal_eval),
                    "good6_median_delta_vs_s1_m": fmt(float(np.median(deltas)) if deltas else None),
                    "good6_max_delta_vs_s1_m": fmt(max(deltas) if deltas else None),
                    "final_n_gaussians": fmt(final_n),
                    "s0_dense_x2_threshold": s0x2,
                    "rend_dist_mean_tail_m": fmt(rend_tail),
                    "pareto_guardrail": str(guard).lower(),
                    "pareto_accuracy_nonregression": str(accuracy).lower(),
                    "pareto_cleaning": str(cleaning).lower(),
                    "pareto_validity_nonregression": str(validity).lower(),
                    "pareto_all4": str(guard and accuracy and cleaning and validity).lower(),
                    "ckpt": train_by.get(rn, {}).get("ckpt", rel(checkpoint_path(rn, "final"))),
                    "readout": "gssem; minobs3; voxel0.05; SORstd2; 405 repair overlay when available",
                }
            )
    write_csv(CSV_ARM_CELLS, rows)
    plot_arm_cells(rows)
    print(json.dumps({"arm_cells": rel(CSV_ARM_CELLS), "rows": len(rows)}, ensure_ascii=False))


def plot_arm_cells(rows: list[dict[str, Any]]) -> None:
    out_dir = FIG_DIR / "summary"
    out_dir.mkdir(parents=True, exist_ok=True)
    labels = [f"{r['arm']}:{r['replicate']}" for r in rows]
    x = np.arange(len(labels))
    fig, axes = plt.subplots(1, 3, figsize=(13.0, 3.8))
    axes[0].bar(x, [int(r["good6_raw_anchor_count"]) for r in rows], color="#577590")
    axes[1].bar(x, [num(r["median_ref_rms_m"]) or 0 for r in rows], color="#f3722c")
    axes[2].bar(x, [num(r["rend_dist_mean_tail_m"]) or 0 for r in rows], color="#43aa8b")
    for ax in axes:
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=8)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_title("good6 raw anchors")
    axes[1].set_title("median RMS")
    axes[2].set_title("rend_dist tail")
    fig.tight_layout()
    fig.savefig(out_dir / "s2_arm_cell_summary.png", dpi=180)
    plt.close(fig)


def md_table(rows: list[dict[str, Any]], columns: list[str], max_rows: int = 20) -> str:
    use = rows[:max_rows]
    out = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in use:
        out.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    if len(rows) > max_rows:
        out.append("| ... | " + f"{len(rows) - max_rows} rows omitted |" + " | ".join("" for _ in columns[2:]) + " |")
    return "\n".join(out)


def versions(_args: argparse.Namespace) -> None:
    P2_RUN_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {RUN_ID}",
        f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}",
        f"git_head: {capture(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {capture(['git', 'branch', '--show-current'])}",
        "canonical_changed: no",
        "mode: S2 direction-position; observation material; no human verdict",
        f"monodepth_decision: {rel(P2_RUN_DIR / 'monodepth_decision.json')}",
        f"gate_decisions: {rel(P2_RUN_DIR / 'gate_decisions.json')}",
        f"train_fingerprints: {rel(P2_RUN_DIR / 'train_fingerprints.csv')}",
        f"readout_fingerprints: {rel(P2_RUN_DIR / 'readout_fingerprints.csv')}",
        f"arm_cells_csv: {rel(CSV_ARM_CELLS)}",
        f"issues_csv: {rel(CSV_ISSUES)}",
        f"issues_md: phases/p2-gsjso/docs/issues.md",
    ]
    (P2_RUN_DIR / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"versions": rel(P2_RUN_DIR / "versions.txt")}, ensure_ascii=False))


def checkpoint_report(_args: argparse.Namespace) -> None:
    mono = read_csv(CSV_MONODEPTH_BUILDING)
    gate = read_csv(CSV_GRAD_SHARE)
    timeline = read_csv(CSV_TIMELINE)
    impl = read_csv(CSV_IMPL)
    decision = {}
    if (P2_RUN_DIR / "monodepth_decision.json").exists():
        decision = json.loads((P2_RUN_DIR / "monodepth_decision.json").read_text(encoding="utf-8"))
    lines = [
        "# E5 C001 S2 중간 체크포인트",
        "",
        "> 관찰 자료. 승인 대기 없이 다음 작업을 계속한다.",
        "",
        f"- git head: `{capture(['git', 'rev-parse', '--short', 'HEAD'])}`",
        f"- A-1 decision: `{decision.get('decision', '')}` — {decision.get('reason', '')}",
        f"- CSV: `{rel(CSV_MONODEPTH_BUILDING)}`, `{rel(CSV_GRAD_SHARE)}`, `{rel(CSV_TIMELINE)}`",
        "",
        "## A-1 Roof Direct Score",
        "",
        md_table(mono, ["building_id", "group_new", "roof_height_error_abs_median_m", "roof_height_error_abs_p90_m", "view_idx"], 18) if mono else "_pending_",
        "",
        "## B-0 Gates",
        "",
        md_table(gate, ["gate_kind", "weight", "return_code", "gate_grad_share_le_040", "gate_ok", "selected_weight"], 8) if gate else "_pending_",
        "",
        "## Completed Timelines",
        "",
        md_table([r for r in timeline if r.get("building_id") == "DEBY_LOD2_4907202"], ["arm", "replicate", "step", "n_gaussians_in_footprint", "z_p50", "opacity_p50"], 24) if timeline else "_pending_",
        "",
        "## A-3 Implementation Check",
        "",
        md_table(impl, ["item", "status", "value"], 8) if impl else "_pending_",
        "",
    ]
    CHECKPOINT_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"checkpoint_report": rel(CHECKPOINT_REPORT)}, ensure_ascii=False))


def report(_args: argparse.Namespace) -> None:
    arm = read_csv(CSV_ARM_CELLS)
    gate = read_csv(CSV_GRAD_SHARE)
    mono = read_csv(CSV_MONODEPTH_BUILDING)
    sheet = read_csv(CSV_SHEET)
    normal = read_csv(CSV_NORMAL_RECHECK)
    timeline = read_csv(CSV_TIMELINE)
    issues = read_csv(CSV_ISSUES)
    predictions = [
        {"prediction": "P-A Arm 0", "observation": summarize_arm_obs(arm, "arm0")},
        {"prediction": "P-B Arm 1", "observation": summarize_arm_obs(arm, "arm1")},
        {"prediction": "P-C Arm 2", "observation": summarize_arm_obs(arm, "arm2")},
        {"prediction": "P-D/P-E Arm 3", "observation": summarize_arm_obs(arm, "arm3")},
    ]
    lines = [
        "# W_E5_C001 S2 방향·자리",
        "",
        "> 관찰 자료. 판정 0. C001 dense 18동, seed 2001, 30k, 2런 기본. 정본 S0/S1/corrected 산출물은 덮어쓰지 않았다.",
        "",
        "## B-0 Gate",
        "",
        md_table(gate, ["gate_kind", "component", "weight", "return_code", "gate_grad_share_le_040", "gate_ok", "selected_weight"], 12) if gate else "_not generated_",
        "",
        "## Pareto 4항 v2.2",
        "",
        md_table(
            arm,
            [
                "arm",
                "replicate",
                "good6_all_built",
                "good6_raw_anchor_count",
                "good6_median_delta_vs_s1_m",
                "final_n_gaussians",
                "rend_dist_mean_tail_m",
                "valid_assembled",
                "pareto_all4",
            ],
            12,
        )
        if arm
        else "_not generated_",
        "",
        "## Prediction Contrast",
        "",
        md_table(predictions, ["prediction", "observation"], 8),
        "",
        "## A-1 Mono Depth",
        "",
        md_table(mono, ["building_id", "group_new", "roof_height_error_abs_median_m", "roof_height_error_abs_p90_m", "view_idx"], 18) if mono else "_not generated_",
        "",
        "## A-2 Sheet Identity",
        "",
        md_table([r for r in sheet if r.get("band") in {"sheet_595_615", "high_sheet_655_670"}], ["family", "label", "band", "n_gaussians", "z_p50", "opacity_p50", "sheet_vs_camera_p50_m"], 20) if sheet else "_not generated_",
        "",
        "## A-4 Normal Recheck",
        "",
        md_table(normal, ["building_id", "before_angle_error_median_deg_absdot", "after_angle_error_median_deg_absdot", "after_quality_bin_locked"], 10) if normal else "_not generated_",
        "",
        "## Timeline 4907202",
        "",
        md_table([r for r in timeline if r.get("building_id") == "DEBY_LOD2_4907202"], ["arm", "replicate", "step", "n_gaussians_in_footprint", "z_p50", "opacity_p50"], 30) if timeline else "_not generated_",
        "",
        "## Issues",
        "",
        md_table(issues, ["part", "severity", "message", "path"], 30) if issues else "_recorded issues 없음_",
        "",
        "## Outputs",
        "",
        f"- CSV: `{rel(CSV_ARM_CELLS)}`, `{rel(CSV_TIMELINE)}`, `{rel(CSV_MONODEPTH)}`, `{rel(CSV_SHEET)}`, `{rel(CSV_GRAD_SHARE)}`, `{rel(CSV_405_BUILDING)}`, `{rel(CSV_NORMAL_RECHECK)}`, `{rel(CSV_GLOBAL_Z)}`.",
        f"- figures: `{rel(FIG_DIR)}/`.",
        f"- versions: `{rel(P2_RUN_DIR / 'versions.txt')}`.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"report": rel(REPORT_PATH)}, ensure_ascii=False))


def summarize_arm_obs(rows: list[dict[str, str]], arm_key: str) -> str:
    part = [r for r in rows if r.get("arm") == arm_key]
    if not part:
        return "not run or excluded"
    pass_count = sum(tf(r.get("pareto_all4")) for r in part)
    guard = "/".join(r.get("good6_raw_anchor_count", "") for r in part)
    valid = "/".join(r.get("valid_assembled", "") for r in part)
    z = "/".join(r.get("rend_dist_mean_tail_m", "") for r in part)
    return f"pareto_all4 {pass_count}/{len(part)}; good6 anchors {guard}; valid {valid}; rend_dist {z}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_prior = sub.add_parser("infer-priors")
    p_prior.add_argument("--gpu", default="0")
    p_prior.add_argument("--device", default="cuda:0")
    sub.add_parser("score-monodepth")
    sub.add_parser("sheet-identity-alt")
    sub.add_parser("implementation-check")
    p_norm = sub.add_parser("normal-recheck")
    p_norm.add_argument("--force-normal-recheck", action="store_true")
    sub.add_parser("a5-metric-prep")
    p_cfg = sub.add_parser("generate-configs")
    p_cfg.add_argument("--include-arm3", action="store_true")
    p_train = sub.add_parser("train-one")
    p_train.add_argument("--run-name", required=True)
    p_train.add_argument("--gpu", default="0")
    p_train.add_argument("--check", action="store_true")
    sub.add_parser("summarize-gates")
    for name in ["readout", "assemble", "evaluate", "all"]:
        p = sub.add_parser(name)
        p.add_argument("--settings", nargs="*", default=None)
        p.add_argument("--runs", nargs="*", default=None)
        p.add_argument("--force", action="store_true")
        p.add_argument("--data-root", default=rel(DATA_ROOT))
        p.add_argument("--torch-extensions", default=TORCH_EXTENSIONS)
        p.add_argument("--gpu", default="0")
        p.add_argument("--buffer-m", type=float, default=20.0)
        p.add_argument("--include-arm3", action="store_true")
    p_repair = sub.add_parser("repair-405")
    p_repair.add_argument("--force", action="store_true")
    p_timeline = sub.add_parser("timeline-roofcrop")
    p_timeline.add_argument("--include-arm3", action="store_true")
    p_z = sub.add_parser("global-z-hist")
    p_z.add_argument("--include-arm3", action="store_true")
    p_rd = sub.add_parser("rend-dist-summary")
    p_rd.add_argument("--include-arm3", action="store_true")
    p_fp = sub.add_parser("fingerprint-training")
    p_fp.add_argument("--include-arm3", action="store_true")
    p_cells = sub.add_parser("arm-cells")
    p_cells.add_argument("--include-arm3", action="store_true")
    p_strips = sub.add_parser("pipeline-strips")
    p_strips.add_argument("--include-arm3", action="store_true")
    p_strips.add_argument("--rep", choices=["1", "2", "all"], default="1")
    p_strips.add_argument("--device", default="cuda:0")
    p_strips.add_argument("--downscale", type=float, default=0.35)
    sub.add_parser("versions")
    sub.add_parser("checkpoint-report")
    sub.add_parser("report")
    return parser


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    args = build_parser().parse_args()
    if args.cmd == "infer-priors":
        infer_priors(args)
    elif args.cmd == "score-monodepth":
        monodepth_building_score(args)
    elif args.cmd == "sheet-identity-alt":
        sheet_identity_alt(args)
    elif args.cmd == "implementation-check":
        implementation_check(args)
    elif args.cmd == "normal-recheck":
        normal_recheck(args)
    elif args.cmd == "a5-metric-prep":
        a5_metric_prep(args)
    elif args.cmd == "generate-configs":
        generate_configs(args)
    elif args.cmd == "train-one":
        train_one(args)
    elif args.cmd == "summarize-gates":
        summarize_gates(args)
    elif args.cmd in {"readout", "assemble", "evaluate", "all"}:
        readout_like(args)
    elif args.cmd == "repair-405":
        repair_405(args)
    elif args.cmd == "timeline-roofcrop":
        timeline_roofcrop(args)
    elif args.cmd == "global-z-hist":
        global_z_hist(args)
    elif args.cmd == "rend-dist-summary":
        rend_dist_summary(args)
    elif args.cmd == "fingerprint-training":
        fingerprint_training(args)
    elif args.cmd == "arm-cells":
        build_arm_cells(args)
    elif args.cmd == "pipeline-strips":
        pipeline_strips(args)
    elif args.cmd == "versions":
        versions(args)
    elif args.cmd == "checkpoint-report":
        checkpoint_report(args)
    elif args.cmd == "report":
        report(args)


if __name__ == "__main__":
    main()
