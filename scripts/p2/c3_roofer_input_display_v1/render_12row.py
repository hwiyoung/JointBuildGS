#!/usr/bin/env python3
"""Compose one 12-stage C3 comparison sheet per building without recomputation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import (
    canonical_json_bytes,
    file_record,
    resolve_artifact,
    write_new,
)
from scripts.p2.c3_tsdf_roof_diagnostic_v1.render import VIEWS


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c3_roofer_input_display_v1/render_12row_v4.json"
CONDITIONS = ("C3_1_SEM", "C3_2_SEM_DEPTH")


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c3_twelve_row_comparison_display.v4":
        raise RuntimeError("unexpected 12-row display schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_EXPERIMENT_HOST_EXECUTION":
        raise RuntimeError("12-row display is not activated")
    if tuple(config["scope"]["condition_ids"]) != CONDITIONS:
        raise RuntimeError("condition order drifted")
    if len(config["scope"]["building_ids"]) != 3:
        raise RuntimeError("building membership drifted")
    if config["scope"].get("c4_c5_access_allowed") is not False:
        raise RuntimeError("C4/C5 access is prohibited")
    if any(int(value) != 0 for value in config["execution_counters"].values()):
        raise RuntimeError("12-row display counters must be zero")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific verdict must remain null")


def _paths(root: Path, pattern: str) -> list[Path]:
    paths = [root / pattern.format(view=view.lower()) for view in VIEWS]
    for path in paths:
        if not path.is_file():
            raise RuntimeError(f"required inherited panel missing: {path}")
    return paths


def _paired(c3_1: Sequence[Path], c3_2: Sequence[Path]) -> list[Path]:
    if len(c3_1) != 4 or len(c3_2) != 4:
        raise RuntimeError("paired comparison row requires four views per condition")
    return list(c3_1) + list(c3_2)


def _put_lines(canvas: np.ndarray, lines: Sequence[str], x: int, y: int, *, scale: float, color: tuple[int, int, int], thickness: int = 1, gap: int = 28) -> None:
    for index, line in enumerate(lines):
        cv2.putText(canvas, line, (x, y + index * gap), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def _sheet(path: Path, stable_id: str, rows: Sequence[tuple[str, str, Sequence[Path]]]) -> None:
    cell_w, cell_h = 960, 720
    label_w, header_h = 500, 160
    width = label_w + 8 * cell_w
    height = header_h + len(rows) * cell_h
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.rectangle(canvas, (0, 0), (width - 1, header_h - 1), (242, 244, 247), -1)
    cv2.putText(canvas, stable_id, (24, 46), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(canvas, "12-stage C3 comparison | sealed results rearranged only | scientific_verdict=null", (24, 88), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (55, 55, 55), 1, cv2.LINE_AA)
    cv2.putText(canvas, "C3-1 SEMANTIC", (label_w + 24, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.84, (26, 77, 142), 2, cv2.LINE_AA)
    cv2.putText(canvas, "C3-2 SEMANTIC + DEPTH", (label_w + 4 * cell_w + 24, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.84, (126, 55, 138), 2, cv2.LINE_AA)
    for group in range(2):
        for index, view in enumerate(VIEWS):
            x = label_w + (group * 4 + index) * cell_w + 24
            cv2.putText(canvas, view, (x, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (30, 30, 30), 2, cv2.LINE_AA)
    for row_index, (stage, label, paths) in enumerate(rows):
        if len(paths) != 8:
            raise RuntimeError(f"row {stage} does not have eight panels")
        y0 = header_h + row_index * cell_h
        shade = (250, 247, 242) if 6 <= row_index <= 7 else ((244, 248, 252) if 8 <= row_index <= 10 else (250, 250, 250))
        cv2.rectangle(canvas, (0, y0), (label_w - 1, y0 + cell_h - 1), shade, -1)
        cv2.putText(canvas, stage, (22, y0 + 54), cv2.FONT_HERSHEY_SIMPLEX, 0.82, (25, 25, 25), 2, cv2.LINE_AA)
        _put_lines(canvas, label.split("\n"), 22, y0 + 108, scale=0.61, color=(45, 45, 45), gap=31)
        if row_index == 6:
            cv2.putText(canvas, "MAIN STAGE-3 ROOFER BRANCH", (22, y0 + cell_h - 34), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (142, 72, 20), 1, cv2.LINE_AA)
        if row_index == 8:
            cv2.putText(canvas, "PARALLEL MESH DIAGNOSTIC BRANCH", (22, y0 + cell_h - 34), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (115, 73, 142), 1, cv2.LINE_AA)
        for column, panel_path in enumerate(paths):
            image = cv2.imread(str(panel_path), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"failed to load panel: {panel_path}")
            resized = cv2.resize(image, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
            x0 = label_w + column * cell_w
            canvas[y0:y0 + cell_h, x0:x0 + cell_w] = resized
        cv2.line(canvas, (0, y0), (width, y0), (218, 218, 218), 1)
    cv2.line(canvas, (label_w + 4 * cell_w, 0), (label_w + 4 * cell_w, height), (45, 45, 45), 5)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 5]):
        raise RuntimeError(f"failed to write sheet: {path}")


def run(output_root: Path, artifact_root: Path) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    diagnostic = resolve_artifact(artifact_root, config["source"]["diagnostic_relative_root"], "diagnostic source")
    roofer_input = resolve_artifact(artifact_root, config["source"]["roofer_input_display_relative_root"], "Roofer-input source")
    complete = resolve_artifact(artifact_root, config["source"]["complete_lineage_relative_root"], "Gaussian attribute source")
    v13 = resolve_artifact(artifact_root, config["source"]["v13_relative_root"], "v13 source")
    records = []
    for stable_id in config["scope"]["building_ids"]:
        raw = [v13 / f"qualitative/c3/comparison/{stable_id}/panels/01_rgb_roofline_{index}.png" for index in range(1, 5)]
        lod2_panels = diagnostic / f"qualitative/roof_first/{stable_id}/panels"
        lod2 = _paths(lod2_panels, "lod2_context_{view}.png")
        rows: list[tuple[str, str, list[Path]]] = [
            ("01", "2024 RGB + 2022 roofline\nprojection context", _paired(raw, raw)),
        ]
        paired_by_stage: dict[str, dict[str, list[Path]]] = {}
        for condition in CONDITIONS:
            v13_panels = v13 / f"qualitative/c3/support/{condition}/{stable_id}/panels"
            diagnostic_panels = diagnostic / f"qualitative/roof_first/{stable_id}/panels"
            complete_panels = complete / f"qualitative/complete_lineage/{stable_id}/panels"
            roofer_input_panels = roofer_input / f"qualitative/roof_first_with_roofer_input/{stable_id}/panels"
            paired_by_stage[condition] = {
                "rgb": _paths(v13_panels, "1_{view}.png"),
                "semantic": _paths(v13_panels, "2_{view}.png"),
                "height": _paths(complete_panels, f"{condition}_gaussian_height_{{view}}.png"),
                "normal": _paths(complete_panels, f"{condition}_gaussian_normal_{{view}}.png"),
                "fusion": _paths(v13_panels, "4_{view}.png"),
                "roofer_input": _paths(roofer_input_panels, f"{condition}_inherited_roofer_input_{{view}}.png"),
                "roofer": _paths(diagnostic_panels, f"{condition}_roofer_{{view}}.png"),
                "consensus": _paths(diagnostic_panels, f"{condition}_roof_consensus_{{view}}.png"),
                "poisson": _paths(diagnostic_panels, f"{condition}_poisson_{{view}}.png"),
                "tsdf": _paths(diagnostic_panels, f"{condition}_tsdf_{{view}}.png"),
            }
        for number, key, label in (
            ("02", "rgb", "GS 3D Gaussian RGB\noriented ellipses"),
            ("03", "semantic", "GS 3D Gaussian semantic\nroof / wall / terrain"),
            ("04", "height", "GS 3D Gaussian height\nworld-Z depth proxy"),
            ("05", "normal", "GS 3D Gaussian normal\nabsolute plane normal RGB"),
            ("06", "fusion", "Rendered-depth direct fusion\n3D surface point cloud"),
            ("07", "roofer_input", "Actual C3 Roofer input LAS\nclass6 roof + class2 terrain"),
            ("08", "roofer", "C3 Roofer output\nGT-footprint oracle diagnostic"),
            ("09", "consensus", "24-view roof-only consensus\nPoisson / TSDF input only"),
            ("10", "poisson", "Roof-only Poisson mesh\nparallel diagnostic"),
            ("11", "tsdf", "Roof-only TSDF mesh\nparallel diagnostic"),
        ):
            rows.append((number, label, _paired(paired_by_stage[CONDITIONS[0]][key], paired_by_stage[CONDITIONS[1]][key])))
        rows.append(("12", "2022 LoD2 context\nnot training or verdict input", _paired(lod2, lod2)))
        if len(rows) != 12:
            raise RuntimeError(f"12-row contract drifted for {stable_id}")
        sheet = output_root / f"qualitative/12row/{stable_id}/case_sheet_c3_12row_v4.png"
        _sheet(sheet, stable_id, rows)
        records.append({"stable_id": stable_id, "case_sheet": file_record(sheet, output_root), "row_count": 12, "column_count": 8, "visible_cell_count": 96})
    body = {
        "schema": "jointbuildgs.c3_twelve_row_comparison_display.v4",
        "status": "COMPLETE_SEALED_RESULTS_REARRANGED_ONLY",
        "case_sheet_count": len(records),
        "rows_per_sheet": 12,
        "columns_per_sheet": 8,
        "visible_cell_count": sum(row["visible_cell_count"] for row in records),
        "case_sheets": records,
        "roofer_result_lineage": "FOUR_PREVIOUSLY_COMPLETED_C3_ROOFER_OPERATIONS_INHERITED_EXACTLY_IN_V13; 4907177 TWO CONDITIONS NOT_RUN_INSUFFICIENT_EVIDENCE",
        "mesh_diagnostic_lineage": "24_VIEW_MINIMUM_2_VIEW_ROOF_CONSENSUS_PARALLEL_BRANCH_NOT_ROOFER_INPUT",
        "execution_counters": config["execution_counters"],
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "qualitative/index_v4.json", canonical_json_bytes(body))
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
