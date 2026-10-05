"""Evaluate sealed native RGB renders against every fixed evaluation photograph.

The regional ROI is the image-clipped bounding rectangle of the fixed world prism
after clipping its edges to a positive camera-depth plane. It is computed solely
from frozen bounds/camera calibration, never prediction alpha, residual or UAS.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def projected_prism_bbox(bounds, R, t, K, width, height, near=1e-4):
    """Return half-open integer pixel bbox or None when the prism is invisible.

    Twelve box edges are intersected with z=near before perspective projection.
    This includes near-plane crossings and avoids projecting vertices behind the
    camera through negative depth. The rectangle intentionally contains pixels
    outside the projected convex prism; it is labelled a bbox, not a silhouette.
    """
    if isinstance(bounds, dict):
        bounds = [bounds[axis] for axis in "xyz"]
    bounds = np.asarray(bounds, dtype=float)
    R, t, K = np.asarray(R, dtype=float), np.asarray(t, dtype=float), np.asarray(K, dtype=float)
    if (bounds.shape != (3, 2) or R.shape != (3, 3) or t.shape != (3,) or K.shape != (3, 3)
            or not all(np.isfinite(value).all() for value in (bounds, R, t, K))
            or not np.all(bounds[:, 0] < bounds[:, 1]) or width <= 0 or height <= 0
            or not np.isfinite(near) or near <= 0):
        raise ValueError("Finite calibrated camera, positive image size/near and increasing prism bounds required")
    bits = list(itertools.product((0, 1), repeat=3))
    vertices = np.array([[bounds[axis, bit[axis]] for axis in range(3)] for bit in bits])
    camera = vertices @ R.T + t
    clipped = [point for point in camera if point[2] >= near]
    for i, first in enumerate(bits):
        for j in range(i + 1, len(bits)):
            if sum(a != b for a, b in zip(first, bits[j])) != 1:
                continue
            a, b = camera[i], camera[j]
            if (a[2] >= near) != (b[2] >= near):
                factor = (near-a[2]) / (b[2]-a[2])
                clipped.append(a + factor*(b-a))
    if not clipped:
        return None
    homogeneous = np.asarray(clipped) @ K.T
    pixels = homogeneous[:, :2] / homogeneous[:, 2:3]
    lower = np.maximum(pixels.min(axis=0), [0, 0])
    upper = np.minimum(pixels.max(axis=0), [width, height])
    if np.any(upper <= lower):
        return None
    return [int(np.floor(lower[0])), int(np.floor(lower[1])),
            int(np.ceil(upper[0])), int(np.ceil(upper[1]))]


def read_rgb(path):
    with Image.open(path) as opened:
        if opened.mode not in ("RGB", "RGBA"):
            raise ValueError(f"Expected saved 8-bit RGB/RGBA pixels, found {opened.mode}")
        # Dropping alpha matches upstream metrics.py's [:, :3] channel slice.
        return np.array(opened.convert("RGB"), dtype=np.uint8)


def _load_module(name, path, package=False):
    spec = importlib.util.spec_from_file_location(name, path,
                submodule_search_locations=[str(Path(path).parent)] if package else None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class NativeMetrics:
    """One cached official VGG criterion; no per-image weight loading/download.

    Native LPIPS keeps upstream GeoGS metrics.py's [0,1] inputs. Optional signed
    [-1,1] inputs are reported separately and never replace the native column.
    """
    def __init__(self, source_root, weight_root, device="cuda", signed_lpips=False):
        import torch
        self.torch = torch
        self.device = torch.device(device)
        self.signed_lpips = bool(signed_lpips)
        source_root, weight_root = Path(source_root), Path(weight_root)
        manifest = json.loads((weight_root / "manifest.json").read_text())
        for key in ("vgg16", "vgg_lpips"):
            record = manifest["weights"][key]
            path = weight_root / record["path"]
            if not path.is_file() or sha(path) != record["sha256"]:
                raise ValueError(f"Exact offline metric weight missing or changed: {key}")
        torch.hub.set_dir(str(weight_root / "torch/hub"))
        suffix = hashlib.sha256(str(source_root.resolve()).encode()).hexdigest()[:12]
        loss = _load_module(f"geogs_metric_loss_{suffix}", source_root / "utils/loss_utils.py")
        image = _load_module(f"geogs_metric_image_{suffix}", source_root / "utils/image_utils.py")
        lpips = _load_module(f"geogs_metric_lpips_{suffix}", source_root / "lpipsPyTorch/__init__.py", package=True)
        self.ssim, self.psnr = loss.ssim, image.psnr
        self.native_lpips_function = lpips.lpips
        self.lpips = lpips.LPIPS(net_type="vgg", version="0.1").to(self.device).eval()
        self.metadata = dict(implementation="official GeoGS metrics functions; VGG criterion cached once",
            lpips_native_input_range=[0, 1], lpips_signed_input_range=[-1, 1] if signed_lpips else None,
            lpips_version="0.1", lpips_backbone="VGG16_IMAGENET1K_V1", min_lpips_side=32,
            weight_manifest_sha256=sha(weight_root / "manifest.json"), device=str(self.device),
            source_files={str(path.relative_to(source_root)): sha(path) for path in
                [source_root / "metrics.py", source_root / "utils/loss_utils.py", source_root / "utils/image_utils.py",
                 *sorted((source_root / "lpipsPyTorch").rglob("*.py"))]})

    def score(self, photo, render):
        if photo.dtype != np.uint8 or render.dtype != np.uint8 or photo.shape != render.shape or photo.ndim != 3 or photo.shape[2] != 3:
            raise ValueError("Metric inputs must be equal-size uint8 RGB arrays")
        torch = self.torch
        def tensor(array):
            return torch.from_numpy(np.ascontiguousarray(array.transpose(2, 0, 1))).to(self.device).float().unsqueeze(0)/255.0
        with torch.inference_mode():
            reference, prediction = tensor(photo), tensor(render)
            psnr = float(self.psnr(prediction, reference).mean().item())
            result = dict(psnr_native_db=None if np.isposinf(psnr) else psnr,
                          psnr_positive_infinity=bool(np.isposinf(psnr)),
                          ssim_native=float(self.ssim(prediction, reference).item()),
                          lpips_vgg_native_01=None, lpips_vgg_signed_11=None)
            if min(photo.shape[:2]) < 32:
                result["lpips_status"] = "NOT_ASSESSED_DOMAIN_SIDE_LT_32"
            else:
                result["lpips_vgg_native_01"] = float(self.lpips(prediction, reference).item())
                result["lpips_status"] = "ASSESSED_NATIVE_RANGE_0_1"
                if self.signed_lpips:
                    result["lpips_vgg_signed_11"] = float(self.lpips(2*prediction-1, 2*reference-1).item())
            if any(isinstance(value, float) and not np.isfinite(value) for value in result.values()):
                raise ValueError("Native metric returned a nonfinite value beyond the explicit identical-image PSNR case")
            return result


def write_montage(photo, render, output, bbox=None):
    """Write real photo/render/fixed-scale mean absolute RGB error, all pixels."""
    if photo.shape != render.shape or photo.dtype != np.uint8 or render.dtype != np.uint8:
        raise ValueError("Montage arrays must have identical uint8 dimensions")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    error = np.mean(np.abs(photo.astype(np.float32)-render.astype(np.float32)), axis=2)
    error_rgb = np.repeat(np.round(error).astype(np.uint8)[..., None], 3, axis=2)
    height, width = photo.shape[:2]
    figure = Image.new("RGB", (width*3, height+30), "#202020")
    draw = ImageDraw.Draw(figure)
    for column, (array, title) in enumerate(((photo, "Actual evaluation photograph"), (render, "Native saved RGB render"),
                                            (error_rgb, "Mean absolute RGB error: fixed 0..255"))):
        figure.paste(Image.fromarray(array), (column*width, 30))
        draw.text((column*width+4, 8), title, fill="white")
        if bbox is not None:
            x0, y0, x1, y1 = bbox
            draw.rectangle((column*width+x0, y0+30, column*width+x1-1, y1+29), outline="#00ffff", width=2)
    figure.save(output, format="PNG")


def evaluate_render_set(split, render_records, bounds, photos_root, scorer, output,
                        region, condition, stage, seed, sealed_render_manifest_sha256, runtime_metadata=None):
    """Emit CSV/JSON and PNGs for all frozen evaluation views, including failures.

    Each render record requires name, evaluation_index, image_id, camera_id,
    render_path and render_sha256. The caller binds this mapping to a sealed
    renderer receipt; filename enumeration alone never establishes pose identity.
    """
    if not sealed_render_manifest_sha256 or len(sealed_render_manifest_sha256) != 64:
        raise ValueError("An exact sealed render-manifest SHA256 is required")
    runtime_metadata = {} if runtime_metadata is None else runtime_metadata
    if set(runtime_metadata)-{'runtime_layout_sha256', 'runtime_layout_revision', 'runtime_layout_path', 'runs_directory',
                              'repeat_contract_sha256', 'supplemental_repeat_id', 'supplemental_only',
                              'completion_contract_sha256', 'evaluation_scope', 'input_verification',
                              'resource_contract_sha256', 'resource_revision', 'resource_contract_path'}:
        raise ValueError('Only operational runtime layout metadata may extend the evaluation receipt')
    expected = sorted(split["evaluation"], key=lambda item: item["name"])
    if len({item["name"] for item in expected}) != len(expected):
        raise ValueError("Duplicate evaluation image names")
    if {item["name"] for item in expected} & {item["name"] for item in split["train"]}:
        raise ValueError("Train and evaluation image memberships overlap")
    mapping = {record["name"]: record for record in render_records}
    if len(mapping) != len(render_records) or set(mapping)-{item["name"] for item in expected}:
        raise ValueError("Duplicate or extra render mapping names")
    output, photos_root = Path(output), Path(photos_root)
    output.mkdir(parents=True, exist_ok=False)
    (output / "montages").mkdir()
    rows = []
    for index, view in enumerate(expected):
        bbox = projected_prism_bbox(bounds, view["R"], view["t"], view["K"], view["width"], view["height"])
        base = dict(region=region, condition=condition, stage=stage, seed=seed,
                    evaluation_index=index, image_id=view["image_id"], camera_id=view["camera_id"], name=view["name"],
                    photo_sha256=view["sha256"], render_sha256=None, status="ASSESSED", error=None)
        record = mapping.get(view["name"])
        photo = render = None
        try:
            if record is None or not Path(record["render_path"]).is_file():
                base["status"] = "RENDER_MISSING"
            elif any(record[key] != value for key, value in (("evaluation_index", index), ("image_id", view["image_id"]), ("camera_id", view["camera_id"]))):
                base["status"] = "RENDER_POSE_IDENTITY_MISMATCH"
            elif sha(record["render_path"]) != record["render_sha256"]:
                base["status"] = "RENDER_BYTES_IDENTITY_MISMATCH"
            else:
                path = photos_root / view["name"]
                if sha(path) != view["sha256"]:
                    base["status"] = "PHOTO_BYTES_IDENTITY_MISMATCH"
                else:
                    photo, render = read_rgb(path), read_rgb(record["render_path"])
                    base["render_sha256"] = record["render_sha256"]
                    if photo.shape != (view["height"], view["width"], 3) or render.shape != photo.shape:
                        base["status"] = "RGB_SHAPE_MISMATCH"
        except (OSError, KeyError, ValueError) as error:
            base.update(status="RGB_READ_OR_IDENTITY_FAILURE", error=str(error))
        for domain in ("full_frame", "fixed_prism_projected_bbox"):
            rectangle = [0, 0, view["width"], view["height"]] if domain == "full_frame" else bbox
            row = dict(base, domain=domain, roi_x0=None, roi_y0=None, roi_x1=None, roi_y1=None,
                       pixel_count=0, psnr_native_db=None, psnr_positive_infinity=False, ssim_native=None,
                       lpips_vgg_native_01=None, lpips_vgg_signed_11=None, lpips_status="NOT_ASSESSED", montage=None)
            if rectangle is not None:
                x0, y0, x1, y1 = rectangle
                row.update(roi_x0=x0, roi_y0=y0, roi_x1=x1, roi_y1=y1, pixel_count=(x1-x0)*(y1-y0))
            elif row["status"] == "ASSESSED":
                row["status"] = "PRISM_NOT_IN_CAMERA_DOMAIN"
            if row["status"] == "ASSESSED":
                try:
                    reference_crop, render_crop = photo[y0:y1, x0:x1], render[y0:y1, x0:x1]
                    row.update(scorer.score(reference_crop, render_crop))
                    montage = output / "montages" / f"{index:05d}_{domain}.png"
                    write_montage(reference_crop, render_crop, montage, bbox=bbox if domain == "full_frame" else None)
                    row["montage"] = str(montage.relative_to(output))
                except Exception as error:
                    row.update(status="METRIC_OR_MONTAGE_FAILURE", error=str(error))
            rows.append(row)
    with (output / "per_image_metrics.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ["name", "status"])
        writer.writeheader()
        writer.writerows(rows)
    receipt = dict(schema="jointbuildgs.geogs.render_quality.v1", scientific_verdict=None,
                   region=region, condition=condition, stage=stage, seed=seed, rows=rows,
                   **runtime_metadata,
                   expected_evaluation_views=len(expected), sealed_render_manifest_sha256=sealed_render_manifest_sha256,
                   scoring=dict(roi="camera-near-clipped fixed-prism projected bounding rectangle; integer half-open bbox",
                                near_m=1e-4, prediction_dependent_masks=False, alpha_mask=False,
                                include_black_prediction_pixels=True, image_resize=False, exposure_fit=False,
                                error_montage_scale="per-pixel RGB mean absolute difference; fixed uint8 0..255"),
                   metrics=scorer.metadata,
                   status="COMPLETE_WITH_RECORDED_FAILURES" if any(row["status"] not in ("ASSESSED", "PRISM_NOT_IN_CAMERA_DOMAIN") for row in rows) else "PASS_RENDER_QUALITY_EVALUATION")
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False)+"\n")
    return receipt
