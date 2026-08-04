#!/usr/bin/env python3
"""Consolidate sealed C1/C2 and C3 qualitative results without recomputation."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c1_c2_c3_consolidated_results_v1/compose_v1.json"


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def resolve(artifact_root: Path, relative: str, role: str) -> Path:
    path = artifact_root / relative
    if not path.is_dir():
        raise RuntimeError(f"missing {role}: {path}")
    return path


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c1_c2_c3_consolidated_results.v1":
        raise RuntimeError("unexpected config schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_PRESENTATION_ONLY":
        raise RuntimeError("presentation config is not active")
    if len(config["building_ids"]) != 3 or len(config["condition_ids"]) != 2:
        raise RuntimeError("scope drifted")
    if len(config["views"]) != 4:
        raise RuntimeError("view contract drifted")
    if any(int(value) != 0 for value in config["execution_counters"].values()):
        raise RuntimeError("all execution counters must remain zero")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    if config.get("official_G3_G4_PASS_usable", "missing") is not None:
        raise RuntimeError("official gate fields must remain null")


def required(paths: Sequence[Path]) -> list[Path]:
    for path in paths:
        if not path.is_file():
            raise RuntimeError(f"required sealed panel missing: {path}")
    return list(paths)


def view_paths(root: Path, pattern: str, views: Sequence[str]) -> list[Path]:
    return required([root / pattern.format(view=view.lower()) for view in views])


def source_lineage(path: Path, artifact_root: Path, role: str, stable_id: str, condition_id: str | None, view: str) -> dict[str, Any]:
    item = record(path, artifact_root)
    item.update({"role": role, "stable_id": stable_id, "condition_id": condition_id, "view": view})
    return item


def put_lines(canvas: np.ndarray, lines: Sequence[str], x: int, y: int, *, scale: float = 0.64, gap: int = 34) -> None:
    for index, line in enumerate(lines):
        cv2.putText(canvas, line, (x, y + index * gap), cv2.FONT_HERSHEY_SIMPLEX, scale, (42, 42, 42), 1, cv2.LINE_AA)


def compose_c3_sheet(path: Path, stable_id: str, condition_id: str, condition_label: str, views: Sequence[str], rows: Sequence[tuple[str, str, Sequence[Path]]]) -> None:
    cell_w, cell_h = 960, 720
    label_w, header_h = 620, 180
    width = label_w + len(views) * cell_w
    height = header_h + len(rows) * cell_h
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.rectangle(canvas, (0, 0), (width - 1, header_h - 1), (242, 244, 247), -1)
    cv2.putText(canvas, stable_id, (24, 48), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(canvas, condition_label, (24, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.84, (38, 74, 128), 2, cv2.LINE_AA)
    cv2.putText(canvas, "sealed results rearranged only | scientific_verdict=null", (24, 137), cv2.FONT_HERSHEY_SIMPLEX, 0.54, (70, 70, 70), 1, cv2.LINE_AA)
    for column, view in enumerate(views):
        label = "SECTION" if view == "PRINCIPAL_SECTION" else view
        cv2.putText(canvas, label, (label_w + column * cell_w + 22, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.73, (30, 30, 30), 2, cv2.LINE_AA)
    for row_index, (number, label, panels) in enumerate(rows):
        if len(panels) != len(views):
            raise RuntimeError(f"row {number} has {len(panels)} panels")
        y0 = header_h + row_index * cell_h
        shade = (248, 248, 248)
        if row_index in (6, 7):
            shade = (250, 246, 239)
        elif row_index in (8, 9, 10, 11):
            shade = (244, 248, 252)
        cv2.rectangle(canvas, (0, y0), (label_w - 1, y0 + cell_h - 1), shade, -1)
        cv2.putText(canvas, number, (22, y0 + 55), cv2.FONT_HERSHEY_SIMPLEX, 0.82, (25, 25, 25), 2, cv2.LINE_AA)
        put_lines(canvas, label.split("\n"), 22, y0 + 110)
        if number == "07":
            cv2.putText(canvas, "MAIN C3 ROOFER INPUT", (22, y0 + cell_h - 35), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (142, 72, 20), 1, cv2.LINE_AA)
        if number == "09":
            cv2.putText(canvas, "C1 SENSOR-UPPER COMPARATOR", (22, y0 + cell_h - 35), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (32, 88, 132), 1, cv2.LINE_AA)
        for column, panel_path in enumerate(panels):
            image = cv2.imread(str(panel_path), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"unreadable panel: {panel_path}")
            resized = cv2.resize(image, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
            x0 = label_w + column * cell_w
            canvas[y0:y0 + cell_h, x0:x0 + cell_w] = resized
        cv2.line(canvas, (0, y0), (width, y0), (216, 216, 216), 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 5]):
        raise RuntimeError(f"failed to write sheet: {path}")


def build_pdf(page_paths: Sequence[Path], destination: Path) -> None:
    images: list[Image.Image] = []
    try:
        for path in page_paths:
            with Image.open(path) as source:
                images.append(source.convert("RGB"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        images[0].save(destination, "PDF", save_all=True, append_images=images[1:], resolution=150.0, quality=92, optimize=True)
    finally:
        for image in images:
            image.close()


def run(output_root: Path, artifact_root: Path, source_base_commit: str) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError(f"add-once output is not empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    sources = {key: resolve(artifact_root, value, key) for key, value in config["sources"].items()}
    finalized = json.loads((sources["c1_c2_relative_root"] / "control/finalized_v1.json").read_text(encoding="utf-8"))
    if finalized.get("case_count") != 3 or finalized.get("panel_count") != 60:
        raise RuntimeError("C1/C2 v6 source is not the sealed 3-case/60-panel result")
    texture_closed = json.loads((sources["texture_relative_root"] / "control/300-closed.local_v1.json").read_text(encoding="utf-8"))
    if not str(texture_closed.get("status", "")).startswith("300-CLOSED"):
        raise RuntimeError("texture source is not closed")

    views = tuple(config["views"])
    condition_labels = {"C3_1_SEM": "C3-1 | 2DGS + semantic", "C3_2_SEM_DEPTH": "C3-2 | 2DGS + semantic + depth"}
    page_records: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    page_paths: list[Path] = []
    page_number = 0
    for stable_id in config["building_ids"]:
        c1_c2_source = sources["c1_c2_relative_root"] / f"qualitative/{stable_id}/case_sheet.png"
        required([c1_c2_source])
        page_number += 1
        c1_c2_page = output_root / f"pages/{page_number:02d}_{stable_id}_C1_C2.png"
        c1_c2_page.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(c1_c2_source, c1_c2_page)
        page_paths.append(c1_c2_page)
        page_records.append({"page": page_number, "stable_id": stable_id, "section": "C1_C2_EXISTING", "output": record(c1_c2_page, output_root), "source": record(c1_c2_source, artifact_root), "exact_copy": sha256(c1_c2_page) == sha256(c1_c2_source)})

        for condition_id in config["condition_ids"]:
            texture_panels = sources["texture_relative_root"] / f"qualitative/{stable_id}/panels"
            support_panels = sources["v13_relative_root"] / f"qualitative/c3/support/{condition_id}/{stable_id}/panels"
            complete_panels = sources["complete_lineage_relative_root"] / f"qualitative/complete_lineage/{stable_id}/panels"
            diagnostic_panels = sources["diagnostic_relative_root"] / f"qualitative/roof_first/{stable_id}/panels"
            roofer_input_panels = sources["roofer_input_relative_root"] / f"qualitative/roof_first_with_roofer_input/{stable_id}/panels"
            row_specs = [
                ("01", "2024 RGB + 2022 roofline\nprojection context", view_paths(texture_panels, "context_{view}.png", views), "RGB_ROOFLINE"),
                ("02", "GS 3D Gaussian RGB\noriented ellipses", view_paths(support_panels, "1_{view}.png", views), "GS_3D_RGB"),
                ("03", "GS 3D world-Z depth proxy\nnot camera-depth raster", view_paths(complete_panels, f"{condition_id}_gaussian_height_{{view}}.png", views), "GS_3D_DEPTH_PROXY"),
                ("04", "GS 3D Gaussian normal\nabsolute plane-normal RGB", view_paths(complete_panels, f"{condition_id}_gaussian_normal_{{view}}.png", views), "GS_3D_NORMAL"),
                ("05", "GS 3D Gaussian semantic\nroof / wall / terrain", view_paths(support_panels, "2_{view}.png", views), "GS_3D_SEMANTIC"),
                ("06", "24-view roof-only consensus\nfused points; mesh branch", view_paths(diagnostic_panels, f"{condition_id}_roof_consensus_{{view}}.png", views), "ROOF_ONLY_FUSED_POINTS"),
                ("07", "Actual C3 Roofer input LAS\nclass 6 roof + class 2 terrain", view_paths(roofer_input_panels, f"{condition_id}_inherited_roofer_input_{{view}}.png", views), "C3_ROOFER_INPUT"),
                ("08", "GS Roofer output\nGT-footprint oracle diagnostic", view_paths(diagnostic_panels, f"{condition_id}_roofer_{{view}}.png", views), "C3_ROOFER_OUTPUT"),
                ("09", "C1 Roofer output\ncurrent UAS LiDAR source", view_paths(texture_panels, "c1_roofer_{view}.png", views), "C1_ROOFER_OUTPUT"),
                ("10", "Textured Poisson roof mesh\nparallel diagnostic", view_paths(texture_panels, f"poisson_texture_{condition_id}_{{view}}.png", views), "TEXTURED_POISSON"),
                ("11", "Textured TSDF roof mesh\nparallel diagnostic", view_paths(texture_panels, f"tsdf_texture_{condition_id}_{{view}}.png", views), "TEXTURED_TSDF"),
                ("12", "2022 LoD2 reference\nevaluation context only", view_paths(texture_panels, "lod2_reference_{view}.png", views), "LOD2_REFERENCE"),
            ]
            for _, _, panels, role in row_specs:
                for view, source in zip(views, panels):
                    lineage.append(source_lineage(source, artifact_root, role, stable_id, condition_id, view))
            page_number += 1
            c3_page = output_root / f"pages/{page_number:02d}_{stable_id}_{condition_id}.png"
            compose_c3_sheet(c3_page, stable_id, condition_id, condition_labels[condition_id], views, [(number, label, panels) for number, label, panels, _ in row_specs])
            page_paths.append(c3_page)
            page_records.append({"page": page_number, "stable_id": stable_id, "section": condition_id, "row_count": 12, "column_count": 4, "output": record(c3_page, output_root)})

    pdf_path = output_root / "reports/C1_C2_C3_qualitative_results_v1.pdf"
    build_pdf(page_paths, pdf_path)
    links = "".join(f'<section><h2>Page {item["page"]}: {html.escape(item["stable_id"])} — {html.escape(item["section"])}</h2><img src="../{html.escape(item["output"]["path"])}"></section>' for item in page_records)
    write_new(output_root / "reports/case_index.html", ("<!doctype html><meta charset=utf-8><title>C1/C2/C3 consolidated results</title><style>body{font-family:sans-serif;max-width:1800px;margin:auto}img{width:100%;margin-bottom:3rem}section{border-bottom:2px solid #aaa}</style><h1>C1/C2/C3 consolidated qualitative results</h1>" + links).encode("utf-8"))

    index = {
        "schema": "jointbuildgs.c1_c2_c3_consolidated_results_index.v1",
        "status": "COMPLETE_SEALED_RESULTS_REARRANGED_ONLY",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_base_commit": source_base_commit,
        "case_count": 3,
        "page_count": len(page_records),
        "c1_c2_page_count": sum(item["section"] == "C1_C2_EXISTING" for item in page_records),
        "c3_page_count": sum(item["section"] != "C1_C2_EXISTING" for item in page_records),
        "c3_rows": ["RGB_ROOFLINE", "GS_3D_RGB", "GS_3D_DEPTH_PROXY", "GS_3D_NORMAL", "GS_3D_SEMANTIC", "ROOF_ONLY_FUSED_POINTS", "C3_ROOFER_INPUT", "C3_ROOFER_OUTPUT", "C1_ROOFER_OUTPUT", "TEXTURED_POISSON", "TEXTURED_TSDF", "LOD2_REFERENCE"],
        "pages": page_records,
        "source_panel_lineage": lineage,
        "pdf": record(pdf_path, output_root),
        "execution_counters": config["execution_counters"],
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "qualitative/index_v1.json", canonical_json_bytes(index))
    report = """# C1/C2/C3 통합 정성 결과판 v1

봉인된 C1/C2 결과와 C3 진단·texture 결과만 다시 조합했다. 건물별 페이지 순서는 C1/C2 기존판, C3-1, C3-2이며 단일 PDF 9쪽이다. C3는 조건당 4열로 분리해 8열 초대형 판보다 글자와 시점을 읽기 쉽게 했다.

C3 행은 RGB+roofline, 3D Gaussian RGB, world-Z depth proxy, normal, semantic, roof-only consensus fused points, 실제 Roofer input LAS, GS Roofer output, C1 current-UAS-LiDAR Roofer output, textured Poisson roof mesh, textured TSDF roof mesh, 2022 LoD2 reference 순서다. 3행의 depth는 카메라 depth raster가 아니라 3D Gaussian의 world-Z 높이 proxy다. 6행 consensus는 Poisson/TSDF 진단 입력이며 7행 Roofer LAS와 동일하지 않다.

이번 작업은 표시판 조합과 PDF 작성만 수행했다. GS 학습, checkpoint extraction, Poisson, TSDF, Roofer, G2, metric 재계산, C4/C5 access는 모두 0회다. `scientific_verdict: null`이며 공식 G3/G4/`PASS_usable` 판정이 아니다.
"""
    write_new(output_root / "reports/technical_report_ko_v1.md", report.encode("utf-8"))

    checks = {
        "case_count_3": index["case_count"] == 3,
        "page_count_9": index["page_count"] == 9,
        "c1_c2_page_count_3": index["c1_c2_page_count"] == 3,
        "c3_page_count_6": index["c3_page_count"] == 6,
        "source_panel_lineage_count_288": len(lineage) == 288,
        "all_c1_c2_pages_exact_copies": all(item.get("exact_copy", True) for item in page_records),
        "all_execution_counters_zero": all(int(value) == 0 for value in config["execution_counters"].values()),
        "scientific_verdict_null": index["scientific_verdict"] is None,
    }
    if not all(checks.values()):
        raise RuntimeError(f"verification failed: {checks}")
    verified = {"schema": "jointbuildgs.local_technical_200_verified.v1", "status": "200-VERIFIED_LOCAL_SELF_CHECK", "checks": checks, "scientific_verdict": None}
    write_new(output_root / "control/200-verified.local_v1.json", canonical_json_bytes(verified))
    returned = {"schema": "jointbuildgs.local_technical_return.v1", "status": "RETURNED_LOCAL_CONSOLIDATED_RESULTS", "pdf": record(pdf_path, output_root), "page_count": 9, "execution_counters": config["execution_counters"], "scientific_verdict": None}
    write_new(output_root / "control/technical_return_v1.json", canonical_json_bytes(returned))
    material = [path for path in sorted(output_root.rglob("*")) if path.is_file() and path.name not in {"artifact_manifest_v1.json", "300-closed.local_v1.json"}]
    manifest = {"schema": "jointbuildgs.c1_c2_c3_consolidated_results_manifest.v1", "status": "COMPLETE_HASHED_MATERIAL_PAYLOAD", "records": [record(path, output_root) for path in material], "scientific_verdict": None}
    manifest["record_count"] = len(manifest["records"])
    write_new(output_root / "control/artifact_manifest_v1.json", canonical_json_bytes(manifest))
    closed = {"schema": "jointbuildgs.local_technical_300_closed.v1", "status": "300-CLOSED_LOCAL_CONSOLIDATED_RESULTS", "verified": record(output_root / "control/200-verified.local_v1.json", output_root), "technical_return": record(output_root / "control/technical_return_v1.json", output_root), "manifest": record(output_root / "control/artifact_manifest_v1.json", output_root), "scientific_verdict": None}
    write_new(output_root / "control/300-closed.local_v1.json", canonical_json_bytes(closed))
    return closed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--source-base-commit", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root, args.source_base_commit), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
