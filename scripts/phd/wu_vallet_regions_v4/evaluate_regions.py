"""Reference-only, native-point before/after evaluation of frozen regional updates."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import time
import traceback

import laspy
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import cKDTree

from scripts.phd.wu_vallet_p3_v1.evaluate import header_crs_metadata


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def utc():
    return datetime.now(timezone.utc).isoformat()


def points(value):
    value = np.asarray(value, dtype=np.float64)
    if value.ndim != 2 or value.shape[1] != 3 or not np.isfinite(value).all():
        raise ValueError("Expected finite native Nx3 coordinates; invalid points cannot be discarded")
    return value


def membership(xyz, domain):
    return ((xyz >= np.asarray(domain["bbox_min"])) & (xyz < np.asarray(domain["bbox_max"]))).all(axis=1)


def summary(values, signed=False):
    values = np.asarray(values, dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite distances cannot be removed from metrics")
    if not len(values):
        return dict(count=0, mean_m=None, median_m=None, p90_m=None, p95_m=None, rmse_m=None, max_m=None)
    result = dict(count=len(values), mean_m=float(values.mean()), median_m=float(np.median(values)),
                  p90_m=float(np.quantile(values, .9)), p95_m=float(np.quantile(values, .95)),
                  rmse_m=float(np.sqrt(np.mean(values ** 2))), max_m=float(values.max()))
    if signed:
        result.update(min_m=float(values.min()), mae_m=float(np.mean(np.abs(values))))
    return result


def median_grid(xyz, domain, cell):
    xyz = points(xyz)
    low, high = np.asarray(domain["bbox_min"]), np.asarray(domain["bbox_max"])
    if not np.isfinite(cell) or cell <= 0 or (high <= low).any():
        raise ValueError("Invalid fixed grid")
    shape = np.ceil((high[:2] - low[:2]) / cell).astype(np.int64)
    if not membership(xyz, domain).all():
        raise ValueError("Metric input outside fixed half-open prism")
    count = np.zeros(int(np.prod(shape)), np.int64)
    height = np.full(len(count), np.nan)
    if len(xyz):
        ij = np.floor((xyz[:, :2] - low[:2]) / cell).astype(np.int64)
        ij = np.minimum(ij, shape - 1)
        ids = ij[:, 1] * shape[0] + ij[:, 0]
        order = np.argsort(ids, kind="stable")
        unique, starts, sizes = np.unique(ids[order], return_index=True, return_counts=True)
        count[unique] = sizes
        z = xyz[order, 2]
        for index, start, size in zip(unique, starts, sizes):
            height[index] = np.median(z[start:start + size])
    return height.reshape(shape[::-1]), count.reshape(shape[::-1])


def measure(xyz, reference, reference_tree, ref_height, ref_count, domain, cfg):
    xyz = points(xyz)
    height, count = median_grid(xyz, domain, cfg["xy_cell_m"])
    forward = reference_tree.query(xyz, workers=cfg["workers"])[0] if len(xyz) else np.empty(0)
    reverse = cKDTree(xyz).query(reference, workers=cfg["workers"])[0] if len(xyz) else np.empty(0)
    thresholds = cfg["distance_thresholds_m"]
    precision_n = [int((forward <= t).sum()) for t in thresholds]
    recall_n = [int((reverse <= t).sum()) for t in thresholds]
    precision = [n / len(xyz) if len(xyz) else 0. for n in precision_n]
    recall = [n / len(reference) if len(reference) else 0. for n in recall_n]
    fscore = [2 * p * r / (p + r) if p + r else 0. for p, r in zip(precision, recall)]
    shared = (count > 0) & (ref_count > 0)
    delta = np.full_like(height, np.nan)
    delta[shared] = height[shared] - ref_height[shared]
    result = dict(point_count=len(xyz), to_reference=summary(forward), reference_to=summary(reverse),
                  reference_distance_unavailable_count=0 if len(xyz) else len(reference),
                  coverage=dict(thresholds_m=thresholds, precision=precision, recall=recall, fscore=fscore,
                                precision_numerators=precision_n, recall_numerators=recall_n,
                                prediction_denominator=len(xyz), reference_denominator=len(reference),
                                empty_prediction_policy="precision/recall/fscore are zero; unavailable reverse distances are separately counted"),
                  xy_cells=dict(cell_m=cfg["xy_cell_m"], total_cells=int(count.size),
                                reference_cells=int((ref_count > 0).sum()), prediction_cells=int((count > 0).sum()),
                                missed_reference_cells=int(((ref_count > 0) & (count == 0)).sum()),
                                prediction_cells_without_reference=int(((ref_count == 0) & (count > 0)).sum()),
                                shared_cells=int(shared.sum()), median_z_signed=summary(delta[shared], signed=True)))
    return result, dict(height=height, count=count, delta=delta), forward


def validate_update(common, payload):
    old, new = points(common["old_xyz"]), points(common["new_xyz"])
    masks = {}
    for side, xyz in (("old", old), ("new", new)):
        mask = np.asarray(payload[f"{side}_keep_mask"])
        if mask.shape != (len(xyz),) or mask.dtype != bool:
            raise ValueError("Keep masks must be native-row boolean arrays")
        masks[side] = mask
    exact = np.concatenate([old[masks["old"]], new[masks["new"]]])
    if not np.array_equal(exact, payload["updated_points"]):
        raise ValueError("Updated XYZ does not replay source point decisions exactly")
    expected_source = np.r_[np.zeros(masks["old"].sum(), np.uint8), np.ones(masks["new"].sum(), np.uint8)]
    if not np.array_equal(expected_source, payload["updated_source"]):
        raise ValueError("Updated source membership mismatch")
    if "updated_pixel_id" in payload and not np.array_equal(
            payload["updated_pixel_id"][expected_source == 1], common["new_pixel_id"][masks["new"]]):
        raise ValueError("Updated native pixel membership mismatch")
    return exact


def verify_region(region):
    root = Path(region["update_root"])
    receipt_path = root / region["candidate_receipt"]
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("reference_accessed") is not False or receipt.get("scientific_verdict") is not None:
        raise ValueError("Candidate receipt does not establish a reference-free completed update")
    if "COMPLETE" not in str(receipt.get("status", "")):
        raise ValueError("Incomplete candidate receipt")
    hashes = {str(receipt_path): sha(receipt_path)}
    common_path = Path(region["common_npz"])
    hashes[str(common_path)] = sha(common_path)
    expected_common = receipt.get("outputs", {}).get("common.npz")
    if expected_common is None:
        origins = [value for name, value in receipt.get("input_hashes", {}).items() if name.endswith("/common.npz")]
        if len(set(origins)) == 1:
            expected_common = origins[0]
    if expected_common is None or hashes[str(common_path)] != expected_common:
        raise ValueError("Common source archive is not bound to the completed candidate receipt")
    common = np.load(common_path)
    for side in ("old", "new"):
        if not membership(points(common[f"{side}_xyz"]), region["domain"]).all():
            raise ValueError(f"{region['id']}: {side} source outside frozen prism")
    advertised = {row["name"]: row for row in receipt["arms"]}
    payloads = {}
    for arm_name in region["method_arms"].values():
        row = advertised[arm_name]
        for filename, expected in row["outputs"].items():
            file_path = root / arm_name / filename
            actual = sha(file_path)
            if actual != expected:
                raise ValueError(f"Candidate hash mismatch: {file_path}")
            hashes[str(file_path)] = actual
        path = root / arm_name / "updated_points.npz"
        data = np.load(path)
        validate_update(common, data)
        payloads[arm_name] = {k: data[k] for k in data.files}
    native_path = Path(region["native_npz"])
    hashes[str(native_path)] = sha(native_path)
    native_expected = receipt.get("input_hashes", {}).get(str(native_path))
    if native_expected is not None and hashes[str(native_path)] != native_expected:
        raise ValueError("Native context archive differs from update input receipt")
    with np.load(native_path) as native:
        mvs = points(native["mvs_xyz"])
        if not np.array_equal(native["als_xyz"], common["old_xyz"]):
            raise ValueError("Frozen ALS native and update inputs differ")
    if not membership(mvs, region["domain"]).all():
        raise ValueError("MVS context points outside fixed prism")
    view_path = Path(region["view_json"])
    hashes[str(view_path)] = sha(view_path)
    view_doc = json.loads(view_path.read_text())
    if region["view_json_kind"] == "selected_master":
        view = view_doc["view"]
    else:
        view = next(v for v in view_doc["views"] if v["image_id"] == region["image_id"])
    photo = {key: view[key] for key in ("path", "width", "height", "image_id", "sha256")}
    if sha(photo["path"]) != photo["sha256"]:
        raise ValueError("Selected current image hash mismatch")
    hashes[photo["path"]] = photo["sha256"]
    return dict(common={k: common[k] for k in common.files}, payloads=payloads, mvs=mvs, photo=photo,
                input_hashes=hashes, candidate_receipt=str(receipt_path), candidate_status=receipt["status"])


def stream_reference(cfg, regions):
    if not regions:
        provenance_config = cfg["frozen_reference_metadata"]
        sources = []
        for region in cfg["regions"]:
            provenance = provenance_config if "source_evaluation_json" in provenance_config else provenance_config[region["id"]]
            path = Path(provenance["source_evaluation_json"])
            if sha(path) != provenance["sha256"]:
                raise ValueError("Frozen reference provenance receipt hash mismatch")
            source = json.loads(path.read_text())
            if source["outputs"]["reference.npz"] != region["frozen_reference_sha256"]:
                raise ValueError("Reference copy hash not bound to source evaluation receipt")
            if source["domain"] != region["domain"]:
                raise ValueError("Frozen reference domain differs from requested prism")
            sources.append(dict(id=region.get("id"), source_evaluation_json=str(path),
                                source_evaluation_sha256=provenance["sha256"], header_crs=source["reference_crs_header"]))
        headers = {row["header_crs"] for row in sources}
        if len(headers) != 1:
            raise ValueError("Frozen reference CRS declarations differ")
        return {}, dict(mode="EXACT_EXISTING_REFERENCE_ONLY_NO_RAW_UAS_ACCESS", decompressed_passes=0,
                        regions_streamed=[], sources=sources,
                        header_crs=next(iter(headers)), raw_reference_accessed=False)
    spec = cfg["raw_reference"]
    path = Path(spec["path"])
    if path.stat().st_size != spec["bytes"] or sha(path) != spec["sha256"]:
        raise ValueError("Raw UAS bytes/hash mismatch")
    state = (path.stat().st_size, path.stat().st_mtime_ns)
    chunks = {r["id"]: [] for r in regions}
    rows = {r["id"]: [] for r in regions}
    offset = 0
    with laspy.open(path) as stream:
        header_count = int(stream.header.point_count)
        crs = header_crs_metadata(stream.header)
        if header_count != spec["point_count"]:
            raise ValueError("Raw UAS count differs from frozen source declaration")
        for chunk in stream.chunk_iterator(cfg["reference_chunk_points"]):
            xyz = points(np.column_stack([chunk.x, chunk.y, chunk.z])) - np.asarray(cfg["frame"]["world_shift_xyz_m"])
            for region in regions:
                keep = membership(xyz, region["domain"])
                if keep.any():
                    chunks[region["id"]].append(xyz[keep])
                    rows[region["id"]].append(np.flatnonzero(keep).astype(np.int64) + offset)
            offset += len(xyz)
    if offset != header_count or state != (path.stat().st_size, path.stat().st_mtime_ns):
        raise ValueError("Raw UAS stream count or file state changed")
    result = {}
    for region in regions:
        rid = region["id"]
        result[rid] = (np.concatenate(chunks[rid]) if chunks[rid] else np.empty((0, 3)),
                       np.concatenate(rows[rid]) if rows[rid] else np.empty(0, np.int64))
        if not len(result[rid][0]):
            raise ValueError(f"No reference points in fixed {rid} crop")
    return result, dict(path=str(path), sha256=spec["sha256"], raw_point_count=offset,
                        decompressed_passes=1, regions_streamed=[r["id"] for r in regions], **crs)


def figures(output, clouds, grids, domain, cfg, primary_payload, common):
    low, high = np.asarray(domain["bbox_min"]), np.asarray(domain["bbox_max"])
    names = ["ALS_before", "Image_before", "Naive_union", "Wu_area1", "Reference", "MVS_context"]
    extent = [low[0], high[0], low[1], high[1]]
    fig, axes = plt.subplots(2, 6, figsize=(24, 8), sharey=True)
    sections = {}
    for row, fixed_axis in enumerate((0, 1)):
        center = (low[fixed_axis] + high[fixed_axis]) / 2
        for col, name in enumerate(names):
            xyz = clouds[name]
            keep = (xyz[:, fixed_axis] >= center - cfg["section_half_width_m"]) & (xyz[:, fixed_axis] < center + cfg["section_half_width_m"])
            cut = xyz[keep]
            ax = axes[row, col]
            ax.scatter(cut[:, 1 - fixed_axis], cut[:, 2], s=.6, rasterized=True)
            ax.set(xlim=(low[1-fixed_axis], high[1-fixed_axis]), ylim=(low[2], high[2]),
                   title=f"{name}\nn={len(cut):,}", xlabel=f"{'Y' if fixed_axis == 0 else 'X'} (m)")
            ax.grid(alpha=.2)
            sections[f"axis{fixed_axis}_{name}"] = len(cut)
        axes[row, 0].set_ylabel(f"Z (m); {'X' if fixed_axis == 0 else 'Y'}={center:g}")
    fig.suptitle("Fixed half-open sections; all native section points; reference is evaluation only")
    fig.tight_layout(); fig.savefig(output / "cross_sections.png", dpi=120); plt.close(fig)
    for difference, filename in ((False, "median_heights.png"), (True, "median_height_differences.png")):
        fig, axes = plt.subplots(2, 3, figsize=(15, 10))
        for ax, name in zip(axes.flat, names):
            values = grids[name]["delta" if difference else "height"]
            image = ax.imshow(values, origin="lower", extent=extent, interpolation="nearest",
                              cmap="coolwarm" if difference else "viridis",
                              vmin=-2 if difference else low[2], vmax=2 if difference else high[2])
            ax.set(title=name, xlabel="X (m)", ylabel="Y (m)")
            fig.colorbar(image, ax=ax, fraction=.035)
        fig.suptitle("Median Z minus UAS, display clipped +/-2m; missing cells white; full errors in metrics"
                     if difference else "Fixed 0.5m cells, median of all native Z; missing cells white")
        fig.tight_layout(); fig.savefig(output / filename, dpi=140); plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(15, 12))
    display_counts = {}
    for ax, name in zip(axes.flat, names):
        xyz = clouds[name]
        step = max(1, int(np.ceil(len(xyz) / cfg["display_max_points"])))
        shown = xyz[::step]
        ax.scatter(shown[:, 0], shown[:, 1], c=shown[:, 2], cmap="viridis", vmin=low[2], vmax=high[2], s=.4, rasterized=True)
        ax.set(title=f"{name}; n={len(xyz):,}", xlim=(low[0], high[0]), ylim=(low[1], high[1]), xlabel="X (m)", ylabel="Y (m)")
        ax.set_aspect("equal")
        display_counts[name] = dict(native_points=len(xyz), displayed_points=len(shown), display_stride=step)
    fig.suptitle("Native point height maps; deterministic display sampling only; metrics use every point")
    fig.tight_layout(); fig.savefig(output / "source_maps.png", dpi=140); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    for ax, side in zip(axes, ("old", "new")):
        xyz, keep = common[f"{side}_xyz"], primary_payload[f"{side}_keep_mask"]
        for mask, color, label in ((~keep, "#c4c6cb", "removed/rejected"), (keep, "#e08324" if side == "new" else "#277fb8", "kept/admitted")):
            subset = xyz[mask]
            step = max(1, int(np.ceil(len(subset) / cfg["display_max_points"])))
            ax.scatter(subset[::step, 0], subset[::step, 1], s=.8, color=color, label=f"{label} {len(subset):,}", rasterized=True)
        ax.set(title=f"{side}: Wu area1", xlim=(low[0], high[0]), ylim=(low[1], high[1]), xlabel="X (m)", ylabel="Y (m)")
        ax.set_aspect("equal"); ax.legend(markerscale=5)
    fig.suptitle("Decision provenance, not ground-truth change labels")
    fig.tight_layout(); fig.savefig(output / "source_decisions.png", dpi=140); plt.close(fig)
    return dict(section_counts=sections, display_counts=display_counts)


def run(config_path, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker execution required")
    cfg = json.loads(config_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    write(output / "config.json", cfg)
    started = time.monotonic()
    try:
        prepared = {r["id"]: verify_region(r) for r in cfg["regions"]}
        seal = dict(status="ALL_REGIONAL_CANDIDATES_VERIFIED_BEFORE_REFERENCE", time_utc=utc(),
                    reference_accessed=False, scientific_verdict=None,
                    regions={rid: {k: v for k, v in data.items() if k in ("input_hashes", "candidate_receipt", "candidate_status")}
                             for rid, data in prepared.items()})
        write(output / "PRE_REFERENCE_CANDIDATE_SEAL.json", seal)
        first_reference_access = utc()
        streamed = [r for r in cfg["regions"] if "frozen_reference_npz" not in r]
        references, reference_meta = stream_reference(cfg, streamed)
        rows = []
        root_out = Path(cfg["output_artifact_root"])
        for region in cfg["regions"]:
            rid = region["id"]
            dest = output / rid; dest.mkdir()
            advertised_dest = root_out / rid
            data = prepared[rid]
            reference_path = dest / "reference.npz"
            if "frozen_reference_npz" in region:
                source = Path(region["frozen_reference_npz"])
                if sha(source) != region["frozen_reference_sha256"]:
                    raise ValueError("Frozen P3 reference hash mismatch")
                shutil.copy2(source, reference_path)
                with np.load(reference_path) as archive:
                    reference = points(archive["uas_xyz"])
                reference_identity = dict(source=str(source), sha256=sha(source), mode="EXACT_FROZEN_REFERENCE_COPY")
            else:
                reference, raw_rows = references[rid]
                np.savez_compressed(reference_path, uas_xyz=reference, uas_raw_rows=raw_rows)
                reference_identity = dict(source=cfg["raw_reference"]["path"], sha256=cfg["raw_reference"]["sha256"],
                                          mode="ONE_PASS_RAW_REFERENCE_CROP", raw_row_sha256=hashlib.sha256(raw_rows.tobytes()).hexdigest())
            if not membership(reference, region["domain"]).all() or not len(reference):
                raise ValueError("Reference outside exact frozen prism or empty")
            tree = cKDTree(reference)
            ref_height, ref_count = median_grid(reference, region["domain"], cfg["xy_cell_m"])
            common = data["common"]
            clouds = dict(ALS_before=points(common["old_xyz"]), Image_before=points(common["new_xyz"]),
                          Naive_union=np.concatenate([common["old_xyz"], common["new_xyz"]]), MVS_context=data["mvs"])
            for method, arm in region["method_arms"].items():
                clouds[method] = points(data["payloads"][arm]["updated_points"])
            metrics, grids, source_distances = {}, {}, {}
            for name, xyz in clouds.items():
                metrics[name], grids[name], forward = measure(xyz, reference, tree, ref_height, ref_count, region["domain"], cfg)
                if name in ("ALS_before", "Image_before"):
                    source_distances["old" if name == "ALS_before" else "new"] = forward
                print(json.dumps({"region": rid, "method": name, "points": len(xyz), "phase": "measured"}), flush=True)
            source_groups = {}
            for method, arm in region["method_arms"].items():
                payload = data["payloads"][arm]
                groups = {}
                for side, positive, negative in (("old", "old_kept", "old_removed"), ("new", "new_admitted", "new_rejected")):
                    mask = payload[f"{side}_keep_mask"]
                    for label, selected in ((positive, mask), (negative, ~mask)):
                        dist = source_distances[side][selected]
                        groups[label] = dict(point_count=int(selected.sum()), reference_distance=summary(dist),
                                             reference_distance_over_2m=int((dist > 2).sum()),
                                             reference_distance_over_2m_role="post-hoc diagnostic only")
                source_groups[method] = groups
            np.savez_compressed(dest / "source_distances.npz", old_reference_distance_m=source_distances["old"],
                                new_reference_distance_m=source_distances["new"], new_pixel_id=common["new_pixel_id"])
            np.savez_compressed(dest / "fixed_grids.npz", reference_count=ref_count, reference_height=ref_height,
                                **{f"{name}_{key}": array for name, fields in grids.items() for key, array in fields.items()})
            clouds["Reference"] = reference
            grids["Reference"] = dict(height=ref_height, count=ref_count, delta=np.where(ref_count > 0, 0., np.nan))
            plot_meta = figures(dest, clouds, grids, region["domain"], cfg, data["payloads"][region["primary_arm"]], common)
            mvs_path = dest / "context.npz"
            np.savez_compressed(mvs_path, mvs_xyz=data["mvs"])
            evaluation = dict(status="REGIONAL_NATIVE_REFERENCE_EVALUATION_COMPLETE", id=rid, methods=metrics,
                              source_groups=source_groups, reference_points=len(reference), reference_identity=reference_identity,
                              domain=region["domain"], frame=cfg["frame"], reference_crs_header=reference_meta["header_crs"],
                              reprojection_or_registration_performed=False, scientific_verdict=None,
                              interpretation=cfg["interpretation"], plotting=plot_meta,
                              input_hashes=data["input_hashes"], outputs={p.name: sha(p) for p in dest.iterdir() if p.is_file()})
            write(dest / "evaluation.json", evaluation)
            figure_rows = [dict(id=name, label=label, path=str(advertised_dest / filename), caption=caption)
                           for name, label, filename, caption in (
                               ("sections", "고정 단면", "cross_sections.png", "모든 native 단면점, 동일 축·폭. UAS는 평가 전용."),
                               ("sources", "갱신 전후 출처 지도", "source_maps.png", "표시만 균등 간격 sampling. 정량은 모든 원점을 사용."),
                               ("decisions", "유지·삭제·추가·제외", "source_decisions.png", "출처 판단 기록이며 실제 변화 정답 라벨이 아님."),
                               ("heights", "고정 격자 중앙 높이", "median_heights.png", "0.5m 고정 XY cell의 모든 Z 중앙값. 흰색은 결손."),
                               ("height_delta", "참조와 중앙 높이 차이", "median_height_differences.png", "표시 범위 ±2m. 전체 편차와 결손 분모는 정량에 보존."))]
            rows.append(dict(id=rid, label=region["label"], common_npz=region["common_npz"],
                             updated_npz=str(Path(region["update_root"]) / region["primary_arm"] / "updated_points.npz"),
                             reference_npz=str(advertised_dest / "reference.npz"), evaluation_json=str(advertised_dest / "evaluation.json"),
                             photo=data["photo"], context_npz=str(advertised_dest / "context.npz"), frame=cfg["frame"],
                             domain=region["domain"], primary_arm=region["primary_arm"], figures=figure_rows,
                             arms=[dict(name=arm, updated_npz=str(Path(region["update_root"]) / arm / "updated_points.npz"), evaluation_key=method)
                                   for method, arm in region["method_arms"].items()]))
        for rid, data in prepared.items():
            for path, expected in data["input_hashes"].items():
                if sha(path) != expected:
                    raise ValueError(f"Candidate changed during evaluation: {rid} {path}")
        receipt = dict(status="REGIONAL_WU_BEFORE_AFTER_REFERENCE_EVALUATION_COMPLETE", task_id=cfg["task_id"],
                       scientific_verdict=None, regions=rows, interpretation=cfg["interpretation"],
                       candidate_seal_sha256=sha(output / "PRE_REFERENCE_CANDIDATE_SEAL.json"),
                       reference_first_access_utc=first_reference_access, raw_reference=reference_meta,
                       source_git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"), container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
                       source_snapshot_manifest=os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"),
                       versions={k: importlib.metadata.version(k) for k in ("numpy", "scipy", "laspy", "matplotlib")},
                       elapsed_seconds=time.monotonic() - started)
        write(output / "receipt.json", receipt)
        print(json.dumps({"phase": "all_regions_complete", "regions": [r["id"] for r in rows], "elapsed_seconds": receipt["elapsed_seconds"]}), flush=True)
    except Exception as error:
        write(output / "FAILED.json", dict(error=repr(error), traceback=traceback.format_exc(), scientific_verdict=None))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.config, args.output)
