"""Read a prepared point cloud as Gaussian init (P2 make-or-break v6: MVS-seed init).

INIT/DATA PATH ONLY — no engine logic. The heavy work (AOI crop, per-cloud geoid
Z shift to the GS-LOCAL ellipsoidal frame, voxel downsample, outlier clip) is done
*offline* by ``phases/p2-gsjso/scripts/tum_mob_seed_prep.sh`` (PDAL, p0-tools
container). This reader just loads the resulting GS-LOCAL cloud so the training
image needs no LAZ/PDAL dependency.

Frame contract: the file is ALREADY in the GS-LOCAL frame (EPSG:25832 minus
world_offset [690953, 5336071, 604], ellipsoidal). NO transform is applied here.
Supported: .ply (via open3d, already used by the TSDF extractor), .npz / .npy.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def read_init_pointcloud(path: str) -> np.ndarray:
    """Return an (M, 3) float32 array of GS-LOCAL point centres."""
    p = Path(path)
    suf = p.suffix.lower()
    if suf == ".ply":
        import open3d as o3d  # present in the dev image (cf. tum_mob_tsdf_extract.py)

        pc = o3d.io.read_point_cloud(str(p))
        xyz = np.asarray(pc.points)
        if xyz.size == 0:
            raise ValueError(f"empty point cloud: {p}")
    elif suf == ".npy":
        xyz = np.load(p)[:, :3]
    elif suf == ".npz":
        d = np.load(p)
        # accept common key names; the seed-prep / TSDF extractor conventions
        for k in ("xyz", "points", "P_local", "P_utm_clean", "P_utm"):
            if k in d:
                xyz = np.asarray(d[k])[:, :3]
                break
        else:
            xyz = np.asarray(d[d.files[0]])[:, :3]
    else:
        raise ValueError(f"unsupported init_pointcloud format: {suf} ({p})")
    return np.ascontiguousarray(xyz, dtype=np.float32)
