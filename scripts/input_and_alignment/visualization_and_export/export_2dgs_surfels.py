"""Export 2DGS checkpoints to a compact binary surfel format for the web viewer.

The 4-way web viewer uses this format directly instead of converting 2DGS
surfel primitives into 3DGS `.ksplat` ellipsoids. Each primitive is stored as
one oriented 2D ellipse in world space.

Format:
  bytes 0..7   magic: b"JBSF2D1\0"
  uint32       primitive count
  uint32       floats per primitive (=16)
  float32[]    interleaved records:
               center.xyz,
               axis0.xyz, axis1.xyz, normal.xyz,
               rgb.xyz, alpha
"""
import argparse
from pathlib import Path

import numpy as np
import torch


SH_C0 = 0.28209479177387814
MAGIC = b"JBSF2D1\0"
FLOATS_PER_SURFEL = 16


def quat_axes_wxyz(quats: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return local X/Y/Z axes for unit quaternions in w,x,y,z layout."""
    w, x, y, z = quats[:, 0], quats[:, 1], quats[:, 2], quats[:, 3]

    axis0 = np.stack(
        [
            1.0 - 2.0 * (y * y + z * z),
            2.0 * (x * y + z * w),
            2.0 * (x * z - y * w),
        ],
        axis=1,
    )
    axis1 = np.stack(
        [
            2.0 * (x * y - z * w),
            1.0 - 2.0 * (x * x + z * z),
            2.0 * (y * z + x * w),
        ],
        axis=1,
    )
    normal = np.stack(
        [
            2.0 * (x * z + y * w),
            2.0 * (y * z - x * w),
            1.0 - 2.0 * (x * x + y * y),
        ],
        axis=1,
    )
    return axis0, axis1, normal


def select_indices(
    means: np.ndarray,
    alpha: np.ndarray,
    max_count: int,
    min_alpha: float,
    seed: int,
    grid_size: int,
) -> np.ndarray:
    valid = np.flatnonzero(alpha >= min_alpha)
    if max_count <= 0 or valid.size <= max_count:
        return valid

    rng = np.random.default_rng(seed)
    xy = means[valid, :2]
    xy_min = xy.min(axis=0)
    xy_max = xy.max(axis=0)
    span = np.maximum(xy_max - xy_min, 1e-6)
    ij = np.floor((xy - xy_min) / span * grid_size).astype(np.int32)
    ij = np.clip(ij, 0, grid_size - 1)
    cell_ids = ij[:, 0] + ij[:, 1] * grid_size

    order = np.argsort(cell_ids)
    sorted_valid = valid[order]
    sorted_cells = cell_ids[order]
    unique_cells, starts, counts = np.unique(sorted_cells, return_index=True, return_counts=True)

    # Allocate by sqrt(count): dense cells get more samples, sparse boundary
    # cells still remain represented in the primitive inspection viewer.
    weights = np.sqrt(counts.astype(np.float64))
    quotas = np.floor(weights / weights.sum() * max_count).astype(np.int32)
    quotas = np.maximum(quotas, 1)

    while quotas.sum() > max_count:
        candidates = np.flatnonzero(quotas > 1)
        if candidates.size == 0:
            break
        reduce_order = candidates[np.argsort(-quotas[candidates])]
        for qi in reduce_order[: quotas.sum() - max_count]:
            quotas[qi] -= 1
    while quotas.sum() < max_count:
        room = counts - quotas
        candidates = np.flatnonzero(room > 0)
        if candidates.size == 0:
            break
        add_order = candidates[np.argsort(-room[candidates])]
        for qi in add_order[: max_count - quotas.sum()]:
            quotas[qi] += 1

    chunks = []
    for start, count, quota in zip(starts, counts, quotas):
        cell_indices = sorted_valid[start : start + count]
        if quota >= count:
            chunks.append(cell_indices)
        else:
            chunks.append(rng.choice(cell_indices, size=int(quota), replace=False))
    selected = np.concatenate(chunks)
    selected.sort()
    return selected


def export_one(args: argparse.Namespace) -> None:
    ckpt = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    sd = ckpt["state_dict"] if "state_dict" in ckpt else ckpt

    means = sd["means"].detach().cpu().numpy().astype(np.float32)
    quats = sd["quats"].detach().cpu().numpy().astype(np.float32)
    log_scales = sd["log_scales"].detach().cpu().numpy().astype(np.float32)
    opacities_raw = sd["opacities_raw"].detach().cpu().numpy().astype(np.float32).reshape(-1)
    sh0 = sd["sh0"].detach().cpu().numpy().astype(np.float32)

    if sh0.ndim == 3 and sh0.shape[1] == 1:
        sh0 = sh0[:, 0, :]

    quats /= np.maximum(np.linalg.norm(quats, axis=1, keepdims=True), 1e-8)
    scales = np.minimum(np.exp(log_scales[:, :2]), args.max_scale)
    alpha = 1.0 / (1.0 + np.exp(-opacities_raw))
    rgb = np.clip(sh0 * SH_C0 + 0.5, 0.0, 1.0)

    idx = select_indices(means, alpha, args.max_count, args.min_alpha, args.seed, args.grid_size)
    means = means[idx]
    quats = quats[idx]
    scales = scales[idx]
    alpha = alpha[idx]
    rgb = rgb[idx]

    axis0, axis1, normal = quat_axes_wxyz(quats)
    axis0 = axis0 * scales[:, 0:1]
    axis1 = axis1 * scales[:, 1:2]

    records = np.empty((idx.size, FLOATS_PER_SURFEL), dtype=np.float32)
    records[:, 0:3] = means
    records[:, 3:6] = axis0
    records[:, 6:9] = axis1
    records[:, 9:12] = normal
    records[:, 12:15] = rgb
    records[:, 15] = alpha

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        f.write(MAGIC)
        f.write(np.uint32(idx.size).tobytes())
        f.write(np.uint32(FLOATS_PER_SURFEL).tobytes())
        records.tofile(f)

    bbox_min = means.min(axis=0)
    bbox_max = means.max(axis=0)
    print(
        f"wrote {out_path} ({idx.size:,}/{len(opacities_raw):,} surfels, "
        f"alpha>={args.min_alpha}, max_scale={args.max_scale}, "
        f"bbox={bbox_min.round(2)}..{bbox_max.round(2)})"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-count", type=int, default=150_000)
    ap.add_argument("--min-alpha", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--grid-size", type=int, default=80)
    ap.add_argument("--max-scale", type=float, default=0.25,
                    help="cap each exported 2D scale to avoid viewer-covering outliers")
    export_one(ap.parse_args())


if __name__ == "__main__":
    main()
