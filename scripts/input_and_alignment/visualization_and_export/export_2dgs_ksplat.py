"""Export a 2DGS checkpoint directly to GaussianSplats3D .ksplat.

The existing lightweight viewer assets were aggressively downsampled for fast
loading. This exporter is for dense browser visualization: it keeps a large
opacity-ranked subset, writes the native KSPLAT container, and lets
GaussianSplats3D render it with SplatRenderMode.TwoD.

For manageable browser memory, this writes compression level 0 with SH degree 0
(DC color only). File size is about 44 bytes per primitive.
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

import numpy as np
import torch


SH_C0 = 0.28209479177387814
HEADER_BYTES = 4096
SECTION_HEADER_BYTES = 1024
BYTES_PER_SPLAT_SH0_UNCOMPRESSED = 44
SEMANTIC_COLORS = np.array(
    [
        [0, 0, 0],        # BG
        [220, 60, 60],    # Roof
        [60, 80, 200],    # Wall
        [60, 180, 60],    # Terrain
    ],
    dtype=np.uint8,
)


def _as_numpy(t: torch.Tensor) -> np.ndarray:
    return t.detach().cpu().numpy()


def _select_indices(opacity: torch.Tensor, max_count: int, min_alpha: float) -> torch.Tensor:
    mask = opacity >= float(min_alpha)
    idx = torch.nonzero(mask, as_tuple=False).reshape(-1)
    if max_count > 0 and idx.numel() > max_count:
        _, order = torch.topk(opacity[idx], k=max_count, largest=True, sorted=False)
        idx = idx[order]
    idx, _ = torch.sort(idx)
    return idx


def _write_ksplat(path: Path, means: np.ndarray, scales: np.ndarray, quats: np.ndarray,
                  rgb: np.ndarray, alpha: np.ndarray) -> None:
    count = int(means.shape[0])
    header = bytearray(HEADER_BYTES)
    header[0] = 0
    header[1] = 1
    struct.pack_into("<I", header, 4, 1)        # maxSectionCount
    struct.pack_into("<I", header, 8, 1)        # sectionCount
    struct.pack_into("<I", header, 12, count)   # maxSplatCount
    struct.pack_into("<I", header, 16, count)   # splatCount
    struct.pack_into("<H", header, 20, 0)       # compressionLevel
    center = means.mean(axis=0).astype(np.float32)
    struct.pack_into("<fff", header, 24, float(center[0]), float(center[1]), float(center[2]))
    struct.pack_into("<ff", header, 36, -1.5, 1.5)

    section = bytearray(SECTION_HEADER_BYTES)
    storage_bytes = count * BYTES_PER_SPLAT_SH0_UNCOMPRESSED
    struct.pack_into("<I", section, 0, count)          # splatCount
    struct.pack_into("<I", section, 4, count)          # maxSplatCount
    struct.pack_into("<I", section, 28, storage_bytes) # storageSizeBytes
    struct.pack_into("<H", section, 40, 0)             # sphericalHarmonicsDegree

    data = np.zeros((count, BYTES_PER_SPLAT_SH0_UNCOMPRESSED), dtype=np.uint8)
    floats = data[:, :40].view("<f4").reshape(count, 10)
    floats[:, 0:3] = means.astype(np.float32)
    floats[:, 3:6] = scales.astype(np.float32)
    floats[:, 6] = quats[:, 0].astype(np.float32)  # w
    floats[:, 7] = quats[:, 1].astype(np.float32)  # x
    floats[:, 8] = quats[:, 2].astype(np.float32)  # y
    floats[:, 9] = quats[:, 3].astype(np.float32)  # z
    data[:, 40:43] = rgb.astype(np.uint8)
    data[:, 43] = alpha.astype(np.uint8)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(header)
        f.write(section)
        data.tofile(f)


def _normal_colors_from_quats(quats: np.ndarray) -> np.ndarray:
    w, x, y, z = quats[:, 0], quats[:, 1], quats[:, 2], quats[:, 3]
    normal = np.stack(
        [
            2.0 * (x * z + w * y),
            2.0 * (y * z - w * x),
            1.0 - 2.0 * (x * x + y * y),
        ],
        axis=1,
    )
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-8)
    return np.clip((normal * 0.5 + 0.5) * 255.0, 0, 255).round().astype(np.uint8)


def _rgb_colors_from_state(state: dict, idx: torch.Tensor) -> np.ndarray:
    sh0 = state["sh0"][idx]
    if sh0.ndim == 3:
        sh0 = sh0[:, 0, :]
    return _as_numpy(torch.clamp(sh0 * SH_C0 + 0.5, 0.0, 1.0) * 255.0).round().astype(np.uint8)


def _semantic_colors_from_state(state: dict, idx: torch.Tensor) -> np.ndarray:
    if "sem_logits" not in state:
        raise KeyError("checkpoint does not contain sem_logits")
    labels = _as_numpy(state["sem_logits"][idx].argmax(dim=-1)).astype(np.int64)
    labels = np.clip(labels, 0, len(SEMANTIC_COLORS) - 1)
    return SEMANTIC_COLORS[labels]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-count", type=int, default=1_200_000,
                        help="Keep top-opacity primitives; <=0 keeps all primitives.")
    parser.add_argument("--min-alpha", type=float, default=0.0)
    parser.add_argument("--color-mode", choices=["rgb", "normal", "semantic"], default="rgb")
    args = parser.parse_args()

    state = torch.load(args.ckpt, map_location="cpu", weights_only=False)["state_dict"]
    opacity = torch.sigmoid(state["opacities_raw"].reshape(-1))
    idx = _select_indices(opacity, args.max_count, args.min_alpha)

    means = _as_numpy(state["means"][idx]).astype(np.float32)
    scales = _as_numpy(torch.exp(state["log_scales"][idx])).astype(np.float32)
    quats = _as_numpy(state["quats"][idx]).astype(np.float32)
    quats /= np.maximum(np.linalg.norm(quats, axis=1, keepdims=True), 1e-8)

    if args.color_mode == "rgb":
        rgb = _rgb_colors_from_state(state, idx)
    elif args.color_mode == "normal":
        rgb = _normal_colors_from_quats(quats)
    else:
        rgb = _semantic_colors_from_state(state, idx)
    alpha = _as_numpy(torch.clamp(opacity[idx], 0.0, 1.0) * 255.0).round().astype(np.uint8)

    out = Path(args.out)
    _write_ksplat(out, means, scales, quats, rgb, alpha)
    print(f"wrote {out} ({len(idx):,} {args.color_mode} splats, {out.stat().st_size / (1024 ** 2):.1f} MiB)")


if __name__ == "__main__":
    main()
