#!/usr/bin/env python3
"""Render the exact C4 final checkpoint as RGB/semantic/depth/normal panels."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import torch

from scripts.p2.c3_utarget199_postprocess_v1.render_gs import model_from_checkpoint
from scripts.p2.c4_utarget199_postprocess_v1.contract import CONDITION_ID, load_config, validate_config
from src.stage2.dataloader import ColmapDataset
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


def _visible_names(config: dict[str, Any]) -> list[str]:
    manifest = json.loads(Path(config["inputs"]["exact_view_manifest_git_path"]).read_text(encoding="utf-8"))
    names = [str(row["basename"]) for row in manifest["rows"]]
    if len(names) != int(config["inputs"]["exact_view_count"]):
        raise RuntimeError("exact common-base view count differs")
    return names


def _save_panel(
    path: Path,
    *,
    source: np.ndarray,
    rgb: np.ndarray,
    semantic: np.ndarray,
    depth: np.ndarray,
    normal: np.ndarray,
    title: str,
) -> None:
    figure, axes = plt.subplots(1, 5, figsize=(20, 4), dpi=130, constrained_layout=True)
    images = (source, rgb, SEMANTIC_COLORS[semantic], depth, np.clip(np.abs(normal), 0, 1))
    labels = ("current RGB", "C4 GS RGB", "C4 semantic", "C4 depth", "C4 |normal xyz|")
    for axis, image, label in zip(axes, images, labels):
        if label == "C4 depth":
            finite = np.isfinite(image) & (image > 0)
            axis.imshow(np.where(finite, image, np.nan), cmap="turbo")
        else:
            axis.imshow(image)
        axis.set_title(label, fontsize=10)
        axis.axis("off")
    figure.suptitle(title, fontsize=12)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, metadata={"Software": "JointBuildGS C4 U_target postprocess"})
    plt.close(figure)


def render_condition(
    *,
    output_root: Path,
    artifact_root: Path,
    checkpoint: Path,
    device: str,
) -> dict[str, Any]:
    control = output_root / "control/C4_EXISTING_ALS_gs_render_complete_v1.json"
    if control.is_file():
        return {**json.loads(control.read_text(encoding="utf-8")), "fast_path": True}
    config = load_config()
    validate_config(config)
    spec = config["condition"]
    data = checkpoint.read_bytes()
    if len(data) != int(spec["expected_bytes"]) or hashlib.sha256(data).hexdigest() != spec["expected_sha256"]:
        raise RuntimeError("C4 render checkpoint identity differs")
    names = _visible_names(config)
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
            normal = output["normal_render"].cpu().numpy()
            panel = output_root / f"conditions/{CONDITION_ID}/renders/view_{order:02d}_rgb_semantic_depth_normal.png"
            _save_panel(
                panel,
                source=source,
                rgb=rgb,
                semantic=semantic,
                depth=depth,
                normal=normal,
                title=f"{CONDITION_ID} | exact common-base view {index}: {batch['name']}",
            )
            records.append({"view_index": index, "image_name": batch["name"], **_record(panel, output_root)})
    peak_mib = int(torch.cuda.max_memory_allocated() / (1024 * 1024))
    if peak_mib > int(config["caps"]["gpu_peak_memory_mib"]):
        raise RuntimeError(f"C4 GS render GPU cap exceeded: {peak_mib} MiB")
    body = {
        "schema": "jointbuildgs.c4_utarget199_gs_render_condition.v1",
        "status": "COMPLETE",
        "condition_id": CONDITION_ID,
        "checkpoint_path": checkpoint.as_posix(),
        "view_count": len(records),
        "render_channels": config["intermediate_exports"]["actual_gs_render_channels"],
        "downscale": downscale,
        "peak_gpu_memory_mib": peak_mib,
        "records": records,
        "scientific_verdict": None,
    }
    _write_new(control, (json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
    summary = {
        "schema": "jointbuildgs.c4_utarget199_gs_render_complete.v1",
        "status": "COMPLETE",
        "condition_count": 1,
        "render_panel_count": len(records),
        "maximum_peak_gpu_memory_mib": peak_mib,
        "scientific_verdict": None,
    }
    _write_new(output_root / "control/gs_render_complete_v1.json", (json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n").encode())
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    print(json.dumps(render_condition(
        output_root=args.output_root,
        artifact_root=args.artifact_root,
        checkpoint=args.checkpoint,
        device=args.device,
    ), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
