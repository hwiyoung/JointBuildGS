"""PHD-MAIN-PREP-MEASURE-v1: COLMAP workspace of a training-image subset (jointbuildgs:dev, CPU; the stereo itself runs in
the pinned CUDA COLMAP image, see run_colmap.sh).

  python colmap_subset.py <name> <views_json_relative_to_/out>

Writes /out/mvs/<name>/{images/ (symlinks to the 937 undistorted images), sparse/{cameras,images,points3D}.bin,
stereo/patch-match.cfg ('__auto__, 20' per image), stereo/{depth_maps,normal_maps,consistency_graphs}/}.
The sparse model keeps the training images only: their poses and keypoints unchanged; 3-D points keep the track elements of
those images and are dropped when fewer than 2 remain (their keypoints then carry no 3-D point). Legacy (3.x) binary
format without rigs / frames, which COLMAP 4 reads as single-camera rigs. scientific_verdict: null."""
import json
import os
import struct
import sys
from pathlib import Path

import numpy as np

from common import DENSE, OUT, jdump, log

name, vj = sys.argv[1], sys.argv[2]
views = json.loads((OUT / vj).read_text())
views = views if isinstance(views, list) else views["train"]
W = OUT / "mvs" / name
for sub in ("images", "sparse", "stereo/depth_maps", "stereo/normal_maps", "stereo/consistency_graphs"):
    (W / sub).mkdir(parents=True, exist_ok=True)
src_sparse = DENSE / "sparse"
# images.bin (with keypoints)
raw = (src_sparse / "images.bin").read_bytes()
off = 0
n = struct.unpack_from("<Q", raw, off)[0]; off += 8
recs = {}
for _ in range(n):
    start = off
    iid = struct.unpack_from("<i", raw, off)[0]; off += 4 + 32 + 24
    cid = struct.unpack_from("<i", raw, off)[0]; off += 4
    end = raw.index(b"\x00", off); nm = raw[off:end].decode(); off = end + 1
    n2 = struct.unpack_from("<Q", raw, off)[0]; off += 8
    pts = np.frombuffer(raw, dtype=np.dtype([("x", "<f8"), ("y", "<f8"), ("pid", "<i8")]), count=n2, offset=off).copy(); off += 24 * n2
    recs[nm] = dict(iid=iid, cid=cid, head=raw[start:start + 4 + 32 + 24 + 4], name=nm, pts=pts)
keep = {recs[v]["iid"] for v in views}
assert len(keep) == len(views), "missing views in the model"
# points3D.bin
raw = (src_sparse / "points3D.bin").read_bytes()
off = 0
n = struct.unpack_from("<Q", raw, off)[0]; off += 8
out_pts = []
kept_pid = set()
for _ in range(n):
    pid = struct.unpack_from("<Q", raw, off)[0]
    xyz_rgb_err = raw[off + 8: off + 8 + 24 + 3 + 8]
    off += 8 + 24 + 3 + 8
    tl = struct.unpack_from("<Q", raw, off)[0]; off += 8
    tr = np.frombuffer(raw, dtype=np.dtype([("iid", "<i4"), ("p2", "<i4")]), count=tl, offset=off); off += 8 * tl
    m = np.isin(tr["iid"], list(keep))
    if m.sum() >= 2:
        out_pts.append((pid, xyz_rgb_err, tr[m].copy())); kept_pid.add(pid)
with open(W / "sparse/points3D.bin", "wb") as f:
    f.write(struct.pack("<Q", len(out_pts)))
    for pid, body, tr in out_pts:
        f.write(struct.pack("<Q", pid)); f.write(body); f.write(struct.pack("<Q", len(tr))); f.write(tr.tobytes())
kp = np.array(sorted(kept_pid), np.int64)
with open(W / "sparse/images.bin", "wb") as f:
    f.write(struct.pack("<Q", len(views)))
    for v in sorted(views, key=lambda x: recs[x]["iid"]):
        r = recs[v]
        f.write(r["head"]); f.write(r["name"].encode() + b"\x00")
        pts = r["pts"].copy()
        has = pts["pid"] >= 0
        has[has] = np.isin(pts["pid"][has], kp)
        pts["pid"][~has] = -1
        f.write(struct.pack("<Q", len(pts))); f.write(pts.tobytes())
(W / "sparse/cameras.bin").write_bytes((src_sparse / "cameras.bin").read_bytes())
for v in views:
    link = W / "images" / v
    if link.is_symlink() or link.exists():
        link.unlink()
    os.symlink(f"/art/phase-payloads/p0-audit/data/work/mvs/colmap_dense/images/{v}", link)
(W / "stereo/patch-match.cfg").write_text("".join(f"{v}\n__auto__, 20\n" for v in sorted(views)))
jdump(W / "subset.json", dict(name=name, views=sorted(views), n_views=len(views), points3D_kept=len(out_pts)))
log(name, "views", len(views), "points3D", len(out_pts))
