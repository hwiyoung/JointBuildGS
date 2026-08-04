#!/usr/bin/env python3
"""Render exact C3 checkpoints with gsplat and publish RGB/semantic/depth panels."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import torch
from torch import nn

from scripts.p2.c3_utarget199_postprocess_v1.contract import load_config, validate_config
from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render, render_semantic


SEMANTIC_COLORS = np.asarray(
    [[35, 35, 35], [213, 94, 0], [0, 114, 178], [0, 158, 115]],
    dtype=np.uint8,
)


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def _record(path: Path, root: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def model_from_checkpoint(path: Path, device: str) -> GaussianModel2D:
    payload = torch.load(path, map_location="cpu", weights_only=True)
    state = payload["state_dict"]
    required = {"means", "quats", "log_scales", "opacities_raw", "sh0", "shN", "sem_logits"}
    if not required.issubset(state):
        raise RuntimeError("checkpoint state is incomplete")
    model = GaussianModel2D.__new__(GaussianModel2D)
    nn.Module.__init__(model)
    model.sh_degree = 3
    model.max_sh_degree = 3
    model.active_sh_degree = 3
    model.num_classes = 4
    for name in sorted(required):
        setattr(model, name, nn.Parameter(state[name].to(device=device), requires_grad=False))
    model.surface_seed_mask = torch.zeros(len(state["means"]), dtype=torch.bool, device=device)
    model.eval()
    return model


def _visible_views(config: Mapping[str, Any]) -> list[str]:
    manifest = json.loads(
        (Path(config["inputs"]["exact_view_manifest_git_path"])).read_text(encoding="utf-8")
    )
    names = [str(row["basename"]) for row in manifest["rows"]]
    if len(names) != int(config["inputs"]["exact_view_count"]):
        raise RuntimeError("exact view manifest count differs")
    return names


def _save_panel(
    path: Path,
    *,
    source: np.ndarray,
    rgb: np.ndarray,
    semantic: np.ndarray,
    depth: np.ndarray,
    title: str,
) -> None:
    figure, axes = plt.subplots(1, 4, figsize=(16, 4), dpi=130, constrained_layout=True)
    for axis, image, label in zip(
        axes,
        (source, rgb, SEMANTIC_COLORS[semantic], depth),
        ("current RGB", "GS RGB", "GS semantic", "GS depth"),
    ):
        if label == "GS depth":
            finite = np.isfinite(image) & (image > 0)
            shown = np.where(finite, image, np.nan)
            axis.imshow(shown, cmap="turbo")
        else:
            axis.imshow(image)
        axis.set_title(label, fontsize=10)
        axis.axis("off")
    figure.suptitle(title, fontsize=12)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, metadata={"Software": "JointBuildGS C3 U_target postprocess"})
    plt.close(figure)


def render_condition(
    *,
    output_root: Path,
    artifact_root: Path,
    checkpoint: Path,
    condition_id: str,
    device: str,
) -> dict[str, Any]:
    control = output_root / f"control/{condition_id}_gs_render_complete_v1.json"
    if control.is_file():
        return {**json.loads(control.read_text(encoding="utf-8")), "fast_path": True}
    config = load_config()
    validate_config(config)
    spec = next(row for row in config["conditions"] if row["condition_id"] == condition_id)
    if checkpoint.stat().st_size != int(spec["expected_bytes"]):
        raise RuntimeError("render checkpoint bytes differ")
    names = _visible_views(config)
    data_root = artifact_root / config["inputs"]["data_root_relative_path"]
    downscale = float(config["intermediate_exports"]["actual_gs_render_downscale"])
    dataset = ColmapDataset(
        data_root,
        downscale=downscale,
        load_depth=False,
        load_normal=False,
        load_semantic=False,
        visible_views=names,
    )
    count = int(config["intermediate_exports"]["actual_gs_render_view_count"])
    indices = np.rint(np.linspace(0, len(dataset) - 1, count)).astype(int).tolist()
    model = model_from_checkpoint(checkpoint, device)
    torch.cuda.reset_peak_memory_stats()
    records = []
    with torch.no_grad():
        for order, index in enumerate(indices):
            batch = dataset[index]
            width, height = int(batch["width"]), int(batch["height"])
            output = render(
                model,
                batch["w2c"].to(device),
                batch["K"].to(device),
                width,
                height,
                sh_degree=3,
                render_mode="RGB+ED",
                bg_color=torch.ones(3, device=device),
            )
            logits = render_semantic(
                model,
                batch["w2c"].to(device),
                batch["K"].to(device),
                width,
                height,
            )
            source = np.asarray(Image.open(dataset.frames[index].image_path).convert("RGB").resize((width, height)))
            rgb = np.rint(output["rgb"].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
            semantic = torch.argmax(logits, dim=-1).cpu().numpy().astype(np.uint8)
            depth = output["depth"].cpu().numpy()
            panel = output_root / f"conditions/{condition_id}/renders/view_{order:02d}_rgb_semantic_depth.png"
            _save_panel(
                panel,
                source=source,
                rgb=rgb,
                semantic=semantic,
                depth=depth,
                title=f"{condition_id} | exact common-base view {index}: {batch['name']}",
            )
            records.append({"view_index": index, "image_name": batch["name"], **_record(panel, output_root)})
    peak_mib = int(torch.cuda.max_memory_allocated() / (1024 * 1024))
    if peak_mib > int(config["caps"]["gpu_peak_memory_mib"]):
        raise RuntimeError(f"GS render GPU cap exceeded: {peak_mib} MiB")
    body = {
        "schema": "jointbuildgs.c3_utarget199_gs_render_condition.v1",
        "status": "COMPLETE",
        "condition_id": condition_id,
        "checkpoint_path": checkpoint.as_posix(),
        "view_count": len(records),
        "downscale": downscale,
        "peak_gpu_memory_mib": peak_mib,
        "records": records,
        "scientific_verdict": None,
    }
    _write_new(control, (json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
    return body


def finalize_render(output_root: Path) -> dict[str, Any]:
    config = load_config()
    rows = []
    for condition in config["conditions"]:
        path = output_root / f"control/{condition['condition_id']}_gs_render_complete_v1.json"
        body = json.loads(path.read_text(encoding="utf-8"))
        if body.get("status") != "COMPLETE":
            raise RuntimeError("condition GS render is incomplete")
        rows.append(body)
    body = {
        "schema": "jointbuildgs.c3_utarget199_gs_render_complete.v1",
        "status": "COMPLETE",
        "condition_count": 2,
        "render_panel_count": sum(row["view_count"] for row in rows),
        "maximum_peak_gpu_memory_mib": max(row["peak_gpu_memory_mib"] for row in rows),
        "scientific_verdict": None,
    }
    path = output_root / "control/gs_render_complete_v1.json"
    _write_new(path, (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode())
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    condition = sub.add_parser("condition")
    condition.add_argument("--output-root", type=Path, required=True)
    condition.add_argument("--artifact-root", type=Path, required=True)
    condition.add_argument("--checkpoint", type=Path, required=True)
    condition.add_argument("--condition-id", required=True)
    condition.add_argument("--device", default="cuda")
    final = sub.add_parser("finalize")
    final.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "condition":
        result = render_condition(
            output_root=args.output_root,
            artifact_root=args.artifact_root,
            checkpoint=args.checkpoint,
            condition_id=args.condition_id,
            device=args.device,
        )
    else:
        result = finalize_render(args.output_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
