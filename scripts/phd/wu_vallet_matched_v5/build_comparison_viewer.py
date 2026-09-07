"""Build a native-source, synchronized before/after/reference comparison.

The builder does not score or filter points. It validates native membership,
copies sealed evaluation evidence, and creates explicit DISPLAY_ONLY subsets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import time

import numpy as np


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def safe_name(value):
    value = str(value)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise ValueError(f"Unsafe native identifier: {value}")
    return value


def points(array, name):
    value = np.asarray(array, dtype=np.float64)
    if value.ndim != 2 or value.shape[1] != 3 or not np.isfinite(value).all():
        raise ValueError(f"Invalid native XYZ: {name}")
    return value


def evaluation_key(name):
    if name.startswith("changed_only_area"):
        return "Wu_changed_only_area" + name.split("changed_only_area", 1)[1]
    if name.startswith("corrected_area"):
        return "Wu_area" + name.split("corrected_area", 1)[1]
    return name


def main(config_path, output):
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Run project processing in Docker")
    started = time.monotonic()
    cfg = read(config_path)
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("A null scientific verdict is required")
    receipt_path = Path(cfg["comparison_root"]) / "receipt.json"
    receipt = read(receipt_path)
    if receipt.get("scientific_verdict", "missing") is not None or not receipt.get("regions"):
        raise ValueError("Sealed region comparison receipt required")
    gate = receipt.get("matched_protocol", {})
    if gate.get("status") != "PASS_MATCHED_THREE_REGION_PROTOCOL_BEFORE_REFERENCE":
        raise ValueError("Matched three-region protocol gate required")
    output.mkdir(parents=True, exist_ok=False)
    copied, derived, inputs = {}, {}, {}

    def copy(source, relative):
        source = Path(source)
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = sha(source)
        shutil.copy2(source, destination)
        if sha(destination) != digest:
            raise ValueError(f"Copied source hash mismatch: {source}")
        copied[relative] = {"source": str(source), "sha256": digest, "bytes": destination.stat().st_size}
        inputs[str(source)] = digest
        return relative

    def binary(array, relative, dtype):
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        value = np.asarray(array, dtype=dtype)
        with destination.open("xb") as handle:
            value.tofile(handle)
        derived[relative] = {"sha256": sha(destination), "bytes": destination.stat().st_size,
                             "dtype": np.dtype(dtype).str, "shape": list(value.shape),
                             "role": "DISPLAY_ONLY_no_scoring_no_classification_no_spatial_aggregation"}
        return relative

    cap = int(cfg["maximum_display_points_per_source"])
    if cap < 1:
        raise ValueError("Positive display cap required")
    repo = Path(__file__).resolve().parents[3]
    for name in ("index.html", "viewer.js", "style.css"):
        copy(repo / "src/apps/wu_vallet_matched_v5" / name, name)
    copy(repo / "src/apps/gs3d_4way_viewer/build/three.module.min.js", "three.module.min.js")
    copy(config_path, "receipts/viewer_config.json")
    copy(receipt_path, "receipts/comparison.json")
    copy(receipt["matched_protocol_path"], "receipts/matched_protocol.json")
    region_data = []
    for entry in receipt["regions"]:
        name = safe_name(entry["id"])
        common_path = Path(entry["common_npz"])
        common = np.load(common_path, allow_pickle=False)
        old = points(common["old_xyz"], name + "/ALS")
        new = points(common["new_xyz"], name + "/image")
        reference_path = Path(entry["reference_npz"])
        reference_payload = np.load(reference_path, allow_pickle=False)
        reference = points(reference_payload["uas_xyz"], name + "/reference")
        if not len(old) or not len(new) or not len(reference):
            raise ValueError(f"Empty before/reference input in {name}")
        domain = entry["domain"]
        bounds = {"min": list(domain["bbox_min"]), "max": list(domain["bbox_max"])}
        if len(bounds["min"]) != 3 or len(bounds["max"]) != 3 or np.any(np.array(bounds["max"]) <= bounds["min"]):
            raise ValueError(f"Invalid fixed region bounds: {name}")
        section_cfg = cfg.get("regions", {}).get(name, {})
        sections = {"x": float(section_cfg.get("section_x_m", (bounds["min"][0] + bounds["max"][0]) / 2)),
                    "y": float(section_cfg.get("section_y_m", (bounds["min"][1] + bounds["max"][1]) / 2)),
                    "width": float(cfg["section_full_width_m"])}
        if sections["width"] <= 0:
            raise ValueError("Positive section width required")

        def cloud(xyz, stem, source=None):
            ids = np.arange(len(xyz), dtype=np.int64)[::max(1, int(np.ceil(len(xyz) / cap)))]
            result = {"native_count": len(xyz), "display_count": len(ids),
                      "xyz": binary(xyz[ids], f"display/{name}/{stem}/xyz.bin", "<f4"),
                      "native_indices": binary(ids, f"display/{name}/{stem}/native_indices.bin", "<i8"),
                      "sections": {}}
            if source is not None:
                source = np.asarray(source, dtype=np.uint8)
                if source.shape != (len(xyz),) or not np.isin(source, [0, 1]).all():
                    raise ValueError("Invalid native source vector")
                result["source"] = binary(source[ids], f"display/{name}/{stem}/source.bin", "u1")
            for axis, dim in (("x", 0), ("y", 1)):
                selected = np.flatnonzero(np.abs(xyz[:, dim] - sections[axis]) <= sections["width"] / 2)
                section = {"native_count": len(selected),
                           "xyz": binary(xyz[selected], f"display/{name}/{stem}/section_{axis}_xyz.bin", "<f4"),
                           "native_indices": binary(selected, f"display/{name}/{stem}/section_{axis}_native_indices.bin", "<i8")}
                if source is not None:
                    section["source"] = binary(source[selected], f"display/{name}/{stem}/section_{axis}_source.bin", "u1")
                result["sections"][axis] = section
            return result

        methods = {"als": cloud(old, "als"), "image": cloud(new, "image"), "reference": cloud(reference, "reference")}
        downloads = [{"label": "갱신 전 ALS·영상 NPZ", "path": copy(common_path, f"downloads/{name}/common.npz")},
                     {"label": "평가 전용 UAS NPZ", "path": copy(reference_path, f"downloads/{name}/reference.npz")}]
        if entry.get("context_npz"):
            context_path = Path(entry["context_npz"])
            context_payload = np.load(context_path, allow_pickle=False)
            context_key = "fused_mvs_xyz" if "fused_mvs_xyz" in context_payload else "mvs_xyz"
            context = points(context_payload[context_key], name + "/MVS context")
            methods["mvs"] = cloud(context, "mvs_context")
            methods["mvs"]["source_npz_key"] = context_key
            downloads.append({"label": "기존 MVS 맥락 NPZ", "path": copy(context_path, f"downloads/{name}/mvs_context.npz")})
        epath = Path(entry["evaluation_json"])
        evaluation = read(epath)
        if evaluation.get("scientific_verdict", "missing") is not None:
            raise ValueError("Evaluation must retain a null scientific verdict")
        for method_name, value in evaluation["methods"].items():
            coverage = value["coverage"]
            n = len(coverage["thresholds_m"])
            if any(len(coverage[key]) != n for key in ("precision", "recall", "fscore")):
                raise ValueError(f"Mismatched coverage thresholds: {name}/{method_name}")
        expected_counts = {"ALS_before": len(old), "Image_before": len(new)}
        for method_name, expected in expected_counts.items():
            if evaluation["methods"][method_name]["point_count"] != expected:
                raise ValueError(f"Frozen metric denominator differs: {name}/{method_name}")
        ecopy = copy(epath, f"receipts/{name}/evaluation.json")
        arms = []
        for arm_entry in entry["arms"]:
            arm_name = safe_name(arm_entry["name"])
            path = Path(arm_entry["updated_npz"])
            payload = np.load(path, allow_pickle=False)
            keep_old = np.asarray(payload["old_keep_mask"], dtype=bool)
            keep_new = np.asarray(payload["new_keep_mask"], dtype=bool)
            if keep_old.shape != (len(old),) or keep_new.shape != (len(new),):
                raise ValueError(f"Full native membership length mismatch: {name}/{arm_name}")
            expected = np.concatenate([old[keep_old], new[keep_new]])
            actual = points(payload["updated_points"], name + "/" + arm_name)
            sources = np.r_[np.zeros(int(keep_old.sum()), np.uint8), np.ones(int(keep_new.sum()), np.uint8)]
            if actual.shape != expected.shape or not np.allclose(actual, expected, rtol=0, atol=1e-7):
                raise ValueError(f"Updated XYZ moved or changed order: {name}/{arm_name}")
            if not np.array_equal(payload["updated_source"], sources):
                raise ValueError(f"Updated source ordering mismatch: {name}/{arm_name}")
            metric_key = arm_entry.get("evaluation_key", evaluation_key(arm_name))
            if metric_key not in evaluation["methods"] or evaluation["methods"][metric_key]["point_count"] != len(actual):
                raise ValueError(f"Updated metric denominator differs: {name}/{arm_name}/{metric_key}")
            arm_downloads = [{"label": f"{arm_name} 갱신 NPZ", "path": copy(path, f"downloads/{name}/{arm_name}.npz")}]
            if path.with_suffix(".ply").is_file():
                arm_downloads.append({"label": f"{arm_name} 갱신 PLY", "path": copy(path.with_suffix(".ply"), f"downloads/{name}/{arm_name}.ply")})
            arms.append({"name": arm_name, "label": arm_entry.get("label", arm_name), "evaluation_key": metric_key,
                         "cloud": cloud(actual, arm_name + "/update", sources),
                         "removed_old": cloud(old[~keep_old], arm_name + "/removed_old"),
                         "added_new": cloud(new[keep_new], arm_name + "/added_new"),
                         "counts": {"retained_old": int(keep_old.sum()), "removed_old": int((~keep_old).sum()),
                                    "admitted_new": int(keep_new.sum()), "updated": len(actual)},
                         "downloads": arm_downloads, "membership_validation": "PASS_native_XYZ_source_membership_exact"})
        names = [arm["name"] for arm in arms]
        if len(names) != len(set(names)) or entry["primary_arm"] not in names:
            raise ValueError("Missing or duplicate primary update arm")
        photo = None
        if entry.get("photo"):
            photo = dict(entry["photo"])
            if sha(photo["path"]) != photo["sha256"]:
                raise ValueError(f"Frozen actual photo hash mismatch: {name}")
            from PIL import Image
            with Image.open(photo["path"]) as im:
                if list(im.size) != [photo["width"], photo["height"]]:
                    raise ValueError("Actual photo dimensions differ from receipt")
            photo["path"] = copy(photo["path"], f"photos/{name}/master.jpg")
            if name == "P3":
                photo["detail_url"] = cfg.get("p3_photo_detail_url")
        figures = []
        for item in entry.get("figures", []):
            figure = dict(item)
            figure["id"] = safe_name(figure["id"])
            figure["path"] = copy(figure["path"], f"figures/{name}/{figure['id']}{Path(figure['path']).suffix}")
            figures.append(figure)
        region_data.append({"id": name, "label": entry.get("label", name), "bounds": bounds, "sections": sections,
                            "note": entry.get("note"), "matched_protocol": entry["matched_protocol"],
                            "methods": methods, "arms": arms, "default_arm": entry["primary_arm"],
                            "evaluation": evaluation, "evaluation_path": ecopy, "downloads": downloads,
                            "photo": photo, "figures": figures, "frame": entry["frame"], "domain": domain,
                            "metric_labels": {"ALS_before": "과거 ALS", "Image_before": "현재 영상 기하", "Naive_union": "무가중 합집합", "MVS_context": "기존 전체 MVS · 맥락"},
                            "evaluation_note": "UAS는 평가 전용입니다. 참조 헤더 EPSG:32632 / 작업 표기 EPSG:25832. 재투영·정합 없이 기존 수치 좌표를 비교했으므로 절대 정확도 인증이 아닙니다. 모든 조건은 동일한 참조 원점과 공간 범위를 사용합니다.",
                            "scope_note": "Wu–Vallet 원문 기반 구현에서 소영역 제외 후 점을 다시 추가하던 경로를 수정한 조건입니다. single은 교차 미검출이며 가림·범위 부족 등을 포함합니다. ALS 위치는 추정 궤적이고 영상 기하는 COLMAP 깊이이며 PSMNet 입력과 다릅니다. 무작정 합치거나 참조로 점을 보정한 결과가 아닙니다.",
                            "input_paths": {k: entry[k] for k in ("common_npz", "updated_npz", "reference_npz", "evaluation_json")},
                            "source_hashes": {k: sha(entry[k]) for k in ("common_npz", "updated_npz", "reference_npz", "evaluation_json")},
                            "membership_validation": "PASS_all_arms_native_XYZ_source_membership_exact"})
    ids = [r["id"] for r in region_data]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate region identifiers")
    region_data.sort(key=lambda r: r["id"])
    default = cfg["default_region"]
    if default not in ids:
        raise ValueError("Configured default region is not available")
    data = {"schema": cfg["schema"], "task_id": cfg["task_id"], "scientific_verdict": None,
            "native_2026_reproduction": False, "regions": region_data, "default_region": default,
            "matched_protocol": gate, "display_cap": cap, "display_rule": "native_order_stride_ceil_N_over_cap_DISPLAY_ONLY"}
    write(output / "data.json", data)
    manifest = {"status": "SYNCHRONIZED_NATIVE_BEFORE_AFTER_REFERENCE_VIEWER_COMPLETE", "task_id": cfg["task_id"],
                "scientific_verdict": None, "native_2026_reproduction": False,
                "generated_utc": datetime.now(timezone.utc).isoformat(), "regions": ids,
                "all_region_native_membership_and_metric_denominators": "PASS",
                "matched_three_region_protocol": "PASS",
                "copied_assets": copied, "display_derivatives": derived, "input_hashes": inputs,
                "data_json": {"sha256": sha(output / "data.json"), "bytes": (output / "data.json").stat().st_size},
                "source_git_head": __import__("os").environ.get("JBGS_SOURCE_GIT_HEAD"),
                "container_image": __import__("os").environ.get("JBGS_CONTAINER_IMAGE_ID"),
                "runtime_seconds": time.monotonic() - started}
    write(output / "viewer_manifest.json", manifest)
    print(json.dumps({"status": manifest["status"], "regions": ids, "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        main(args.config, args.output)
    except Exception as exc:
        if args.output.exists() and not (args.output / "FAILED.json").exists():
            write(args.output / "FAILED.json", {"error": repr(exc), "scientific_verdict": None})
        raise
