"""Evaluate frozen photo cases against preserved UAS IDs; never set scores/weights.

The reference is mounted only in this subsequent CPU evaluator. Sparse UAS samples
are compared on their actual projected rays, not converted to a filled GT raster.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import sys
import time

import numpy as np


SOURCES = ("prior", "da3", "mvs")
MODES = ("raw", "plane")
SIZES = (9, 17, 33, 65)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def sample_valid4(depth, mask, uv):
    """Bilinear camera-Z; all four corners must exist and be source-valid."""
    h, w = depth.shape
    q = np.nan_to_num(uv, nan=-2., posinf=-2., neginf=-2.)
    inside = (np.isfinite(uv).all(1) & (q[:, 0] >= 0) & (q[:, 1] >= 0)
              & (q[:, 0] < w - 1) & (q[:, 1] < h - 1))
    x = np.floor(np.clip(q[:, 0], 0, w - 2)).astype(int)
    y = np.floor(np.clip(q[:, 1], 0, h - 2)).astype(int)
    corners = np.stack([depth[y, x], depth[y, x+1], depth[y+1, x], depth[y+1, x+1]], 1)
    valid = (inside & np.isfinite(corners).all(1) & (corners > 0).all(1)
             & mask[y, x] & mask[y, x+1] & mask[y+1, x] & mask[y+1, x+1])
    dx, dy = q[:, 0]-x, q[:, 1]-y
    coefficients = np.stack([(1-dx)*(1-dy), dx*(1-dy), (1-dx)*dy, dx*dy], 1)
    result = np.sum(coefficients * corners, axis=1)
    return np.where(valid, result, np.nan), valid


def statistics(error):
    error = np.asarray(error)
    require(np.isfinite(error).all(), "Nonfinite error reached summary")
    if not len(error):
        return dict(count=0, median_abs_error_m=None, mean_abs_error_m=None,
                    median_signed_error_m=None, p90_abs_error_m=None)
    return dict(count=int(len(error)), median_abs_error_m=float(np.median(np.abs(error))),
                mean_abs_error_m=float(np.mean(np.abs(error))),
                median_signed_error_m=float(np.median(error)),
                p90_abs_error_m=float(np.quantile(np.abs(error), .9)))


def error_rank(first, second, n):
    if not n:
        return "UNAVAILABLE_NO_COMMON_REFERENCE"
    a, b = first["median_abs_error_m"], second["median_abs_error_m"]
    if abs(a-b) <= 1e-9:
        return "NUMERIC_TIE"
    return "prior" if a < b else "image"


def self_checks():
    yy, xx = np.mgrid[:5, :6]
    d = 10. + xx * 2. + yy * 3.
    uv = np.array([[1.25, 2.5], [5., 2.], [-1., 2.]])
    z, m = sample_valid4(d, np.ones_like(d, bool), uv)
    require(m.tolist() == [True, False, False], "Bilinear boundary fixture failed")
    require(z[0] == 20., "Affine plane interpolation fixture failed")
    hole = np.ones_like(d, bool); hole[2, 1] = False
    require(not sample_valid4(d, hole, uv[:1])[1][0], "Invalid corner was filled")
    near, far = statistics(np.array([-.1, .2])), statistics(np.array([1., -2.]))
    require(error_rank(near, far, 2) == "prior", "Error ranking fixture failed")
    require(error_rank(near, near, 2) == "NUMERIC_TIE", "Tie fixture failed")
    require(statistics([])["median_abs_error_m"] is None, "Missing reference fixture failed")
    return ["affine_plane_valid4", "unfilled_invalid_corner", "boundary_exclusion",
            "paired_absolute_error_rank", "numeric_tie", "no_reference_is_null"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("attempt", "paired", "output"):
        ap.add_argument("--"+name, type=Path, required=True)
    ap.add_argument("--config", type=Path)
    ap.add_argument("--photo-preferences", type=Path,
                    help="Optional JSON rows: case_id, patch_size, pair, mode, preference (prior/image/tie/uncertain).")
    args = ap.parse_args()
    require(Path("/.dockerenv").exists(), "Project evaluation requires Docker")
    args.output.mkdir(parents=True, exist_ok=True)
    require(not any(args.output.iterdir()), "Refuse to overwrite nonempty evaluation output")
    started = time.time(); inputs = {}; cases = []; attempt_seals = {}

    def bind(path):
        path = Path(path)
        value = digest(path)
        if path.is_relative_to(args.attempt) and str(path.relative_to(args.attempt)) in attempt_seals:
            require(value == attempt_seals[str(path.relative_to(args.attempt))], "Frozen photo artifact hash mismatch: "+str(path))
        inputs[str(path)] = dict(path=str(path), sha256=value, bytes=path.stat().st_size)
        return path

    try:
        checks = self_checks(); bind(Path(__file__))
        cfg_path = args.config
        if cfg_path is None:
            available = [p for p in (args.attempt/"normal_photometry_v3_7.json", args.attempt/"config.json") if p.exists()]
            require(len(available) == 1, "Supply exact frozen --config")
            cfg_path = available[0]
        cfg = json.loads(bind(cfg_path).read_text())
        require(cfg["scientific_verdict"] is None and cfg["gt_input"] is False, "Photo config GT boundary differs")
        require(cfg["patch_sizes"] == [9, 17, 33], "Fixed photo patch sizes differ")
        require(cfg["weights_computed"] is False, "This diagnostic must not contain weights")
        frozen = json.loads(bind(args.attempt/"receipt.json").read_text())
        require(frozen.get("scientific_verdict") is None and frozen["status"] == "PASS_INTERNAL_FIT_DIAGNOSTIC", "Photo receipt not passed")
        attempt_seals = {row["path"]: row["sha256"] for row in frozen["outputs"]}
        bind(cfg_path)
        paired_receipt = json.loads(bind(args.paired/"receipt.json").read_text())
        shutil.copy2(Path(__file__), args.output/Path(__file__).name)
        shutil.copy2(cfg_path, args.output/"frozen_photo_config.json")
        preferences = {}
        if args.photo_preferences:
            rows = json.loads(bind(args.photo_preferences).read_text())
            if isinstance(rows, dict):
                rows = rows["rows"]
            for row in rows:
                key = (row["case_id"], int(row["patch_size"]), row["pair"], row["mode"])
                require(key not in preferences, "Duplicate photo preference key")
                require(row["preference"] in ("prior", "image", "tie", "uncertain", "unavailable"), "Unknown photo preference")
                preferences[key] = row
        case_paths = sorted(args.attempt.glob("cases/*/case.json"))
        require(len(case_paths) == 8, "Expected exactly eight frozen cases")
        refs = {}
        for cp in case_paths:
            c = json.loads(bind(cp).read_text()); cid = c["case_id"]; region = c["region"]
            require(region in ("P1", "P2"), "Unexpected region")
            if region not in refs:
                p = bind(args.paired/(region+".paired.npz"))
                require(inputs[str(p)]["sha256"] == paired_receipt["outputs"][region+".paired.npz"]["sha256"], "Paired reference seal mismatch")
                with np.load(p, allow_pickle=False) as a:
                    refs[region] = {k: a[k] for k in ("reference_points", "reference_original_indices",
                                   "strict_per_view_camera_z_error", "selected_view_names")}
            a = refs[region]; pts = a["reference_points"]; ids = a["reference_original_indices"]
            require(len(np.unique(ids)) == len(ids) == len(pts), "Reference IDs differ/duplicate")
            cam = c["reference_camera_model"]; K = np.array(cam["K"]); R = np.array(cam["R"]); t = np.array(cam["t"])
            require(np.allclose(R.T@R, np.eye(3), atol=1e-8), "Invalid camera rotation")
            vi = a["selected_view_names"].tolist().index(c["ref_camera"])
            strict = np.isfinite(a["strict_per_view_camera_z_error"][vi])
            xyz = pts.astype(float)@R.T+t; z = xyz[:, 2]
            with np.errstate(divide="ignore", invalid="ignore"):
                uv = (xyz@K.T)[:, :2] / z[:, None]
            center = np.array(c["center_uv"]); finite = np.isfinite(uv).all(1) & (z > 0)
            delta = np.abs(uv-center)
            in_context = finite & (delta < 65/2).all(1)
            indices = np.flatnonzero(in_context)
            selected_uv, selected_z = uv[indices], z[indices]
            rays = np.c_[selected_uv, np.ones(len(indices))] @ np.linalg.inv(K).T
            require(np.allclose((rays*selected_z[:, None]-t)@R, pts[indices], atol=1e-7), "Ray inversion mismatch")
            stored = dict(original_reference_ids=ids[indices], paired_indices=indices,
                          reference_points=pts[indices], reference_uv=selected_uv,
                          reference_camera_z=selected_z, inherited_strict_mask=strict[indices])
            files = sorted(cp.parent.glob("neighbor_*/numeric_arrays.npz"))
            require(files, "Missing source reference arrays for "+cid)
            keys = ["reference_uv"]+[f"{s}_{m}_{kind}" for s in SOURCES for m in MODES for kind in ("depth", "valid")]
            first = None
            for path in files:
                with np.load(bind(path), allow_pickle=False) as ar:
                    loaded = {key: ar[key] for key in keys}
                if first is None:
                    first = loaded
                else:
                    for key in keys:
                        require(np.array_equal(first[key], loaded[key], equal_nan=True), "Neighbor-dependent reference-side array: "+key)
            grid = first["reference_uv"]
            require(grid.ndim == 3 and grid.shape[-1] == 2, "Invalid reference UV grid")
            gh, gw = grid.shape[:2]; gy, gx = np.mgrid[:gh, :gw]
            require(np.allclose(grid, grid[0,0]+np.stack([gx, gy], -1), atol=1e-12), "Noncanonical source sampling grid")
            require(gh >= 65 and gw >= 65, "Evaluation context requires source 65x65 arrays")
            local_uv = selected_uv-grid[0,0]
            sampled = {}; supported = {}
            for s in SOURCES:
                for mode in MODES:
                    prefix = s+"_"+mode
                    d = first[prefix+"_depth"]; mask = first[prefix+"_valid"]
                    require(d.shape == mask.shape == (gh, gw), "Source depth/mask shape differs")
                    dep, good = sample_valid4(d, mask.astype(bool), local_uv)
                    sampled[prefix] = dep-selected_z; supported[prefix] = good
                    stored[prefix+"_depth"] = dep; stored[prefix+"_valid"] = good
                    stored[prefix+"_camera_z_error"] = sampled[prefix]
                    stored[prefix+"_world_z_error"] = sampled[prefix]*(rays@R)[:, 2]
            coverage = []; comparisons = []
            for size in SIZES:
                footprint = finite & (delta < size/2).all(1)
                inside = (np.abs(selected_uv-center) < size/2).all(1)
                eligible = inside & strict[indices]
                stored[f"patch_{size}_footprint_mask"] = inside
                coverage.append(dict(patch_size=size, all_reference_count=int(footprint.sum()),
                                     inherited_strict_count=int((footprint & strict).sum()),
                                     source_statistics={k: statistics(sampled[k][eligible & supported[k]]) for k in sampled}))
                if size == 65:
                    continue
                for image in ("da3", "mvs"):
                    pair = "prior_"+image
                    common = eligible.copy()
                    for s in ("prior", image):
                        for mode in MODES:
                            common &= supported[s+"_"+mode]
                    stored[f"patch_{size}_{pair}_all_four_common_mask"] = common
                    n = int(common.sum())
                    for mode in MODES:
                        ps = statistics(sampled["prior_"+mode][common]); ims = statistics(sampled[image+"_"+mode][common])
                        rank = error_rank(ps, ims, n)
                        row = dict(patch_size=size, pair=pair, mode=mode, common_reference_count=n,
                                   prior=ps, image=ims, image_source=image, reference_error_rank=rank,
                                   low_count_descriptive_only=(n < 10), low_count_threshold_role="Display flag only; no accuracy claim",
                                   all_four_raw_plane_sources_share_exact_ids=True,
                                   original_reference_ids_sha256=hashlib.sha256(ids[indices][common].tobytes()).hexdigest())
                        pref = preferences.get((cid, size, pair, mode))
                        if pref is None and "summary" in c:
                            photo = c["summary"][pair][str(size)][mode]
                            reading = photo["reading"]
                            state = {"PHOTO_COST_PREFERS_PRIOR": "prior", "PHOTO_COST_PREFERS_IMAGE": "image",
                                     "PHOTO_COST_CLOSE": "tie", "INSUFFICIENT_SUPPORT": "unavailable",
                                     "VIEW_DEPENDENT_OR_CLOSE": "uncertain"}.get(reading)
                            require(state is not None, "Unknown frozen photo reading: "+reading)
                            pref = dict(preference=state, **photo)
                        row["photo_preference"] = pref
                        if pref is None:
                            match = "UNAVAILABLE_NO_FROZEN_PHOTO_PREFERENCE"
                        elif not n:
                            match = "UNAVAILABLE_NO_COMMON_REFERENCE"
                        elif pref["preference"] not in ("prior", "image") or rank not in ("prior", "image"):
                            match = "UNRESOLVED_TIE_OR_UNCERTAIN"
                        else:
                            match = "DESCRIPTIVE_AGREEMENT" if pref["preference"] == rank else "DESCRIPTIVE_DISAGREEMENT"
                        row["photo_reference_comparison"] = match
                        comparisons.append(row)
            np.savez_compressed(args.output/(cid+"_reference_points.npz"), **stored)
            result = dict(case_id=cid, region=region, center_uv=center.tolist(), ref_camera=c["ref_camera"],
                          reference_status="OBSERVED_LOCAL_SUPPORT" if in_context.any() else "NO_REGIONAL_REFERENCE_IN_CONTEXT",
                          coverage=coverage, comparisons=comparisons, scientific_verdict=None)
            write(args.output/(cid+"_evaluation.json"), result); cases.append(result)
        for row in inputs.values():
            require(digest(row["path"]) == row["sha256"], "Input changed during evaluation: "+row["path"])
        outputs = {p.name: dict(sha256=digest(p), bytes=p.stat().st_size) for p in sorted(args.output.iterdir()) if p.is_file()}
        receipt = dict(schema="jbgs.normal_photometry.reference_evaluation.v3.7", status="PASS_TECHNICAL_REFERENCE_EVALUATION",
                       scientific_verdict=None, cases=cases, inputs=list(inputs.values()), outputs=outputs,
                       created_utc=datetime.now(timezone.utc).isoformat(), command=sys.argv, self_checks=checks,
                       gt_use="Subsequent evaluation only; no costs, case centers, normals, thresholds, or weights modified",
                       support_definition="Existing paired UAS strict mask: top envelope, near-nadir, regional 2px z-buffer with 0.2m tolerance, all 3x3 cells covered and <=0.5m range. Also inherits valid DA3 input requirement, no residual-magnitude conditioning.",
                       interpolation="Continuous projected UAS ray, bilinear positive source camera-Z on all four valid canonical samples; no nearest GT point assigned to an integer pixel, no GT raster filling",
                       comparison_support="Each pair/patch uses exact same original UAS IDs across both sources and raw/plane variants",
                       limitations=["Sparse regional UAS support is not certified physical visibility; external occluders absent.",
                                    "UAS header EPSG:32632 versus working EPSG:25832 and inherited datum/registration uncertainty remain uncorrected. Numerical reference discrepancy, not calibrated absolute accuracy.",
                                    "Reference sampling and source bilinear interpolation can mix surfaces near discontinuities.",
                                    "Plane interpolation evaluates local plane hypothesis; it is not new reconstructed geometry or GS outcome.",
                                    "These fixed development examples are not a population sample; no tuning or reproducibility claim.",
                                    "A lower photo cost is not automatically a reliable preference; optional comparison retains the frozen photo decision state."],
                       wall_seconds=time.time()-started, peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                       runtime=dict(python=platform.python_version(), numpy=np.__version__, image_id=os.environ.get("JBGS_RUNTIME_IMAGE_ID")))
        write(args.output/"receipt.json", receipt)
        print(json.dumps(dict(status=receipt["status"], cases=len(cases), context_supported_cases=sum(c["reference_status"]=="OBSERVED_LOCAL_SUPPORT" for c in cases), scientific_verdict=None)))
    except Exception as exc:
        write(args.output/"failure.json", dict(status="FAIL", error=repr(exc), inputs=list(inputs.values()),
                                               scientific_verdict=None, wall_seconds=time.time()-started))
        raise


if __name__ == "__main__":
    main()
