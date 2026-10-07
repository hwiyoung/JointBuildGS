"""PHD-MAIN-STAGE1-v1 3.6: observation-confidence masks re-computed on the depth maps before the filter (GPU, torch; any image with
torch CUDA and numpy; /prep (ro), /art (ro), /out). Definitions = configs main_stage1_v1.json 'sensitivity'.

  python sens_conf.py <site>     -> /out/sens/conf/<site>.npz (per view: uint8 bits, bit 0 current re-implemented, bit 1 strict,
                                    bit 2 loose), /out/sens/conf/<site>.json (sources, agreement with COLMAP's geometric mask)

Pre-filter maps = the COLMAP photometric depth maps of the box MVS (1024 x 741, camera-Z). Sources per view = COLMAP's automatic
choice (Model::GetMaxOverlappingImages: the 20 images sharing most sparse points among those whose 75th-percentile triangulation
angle with the view is >= 1 degree, min_triangulation_angle of the run) from the box's sparse model. A pixel's source agrees when
the forward-backward reprojection (pixel -> 3-D at its depth -> source pixel (nearest) -> 3-D at the source's depth -> view) lands
within the reprojection threshold, and, when a depth ratio is set, |z in the source - source depth| / source depth <= the ratio.
current: >= 2 sources, 1 px, no ratio; strict: >= 3, 1 px, 1 %; loose: >= 2, 2 px, no ratio. scientific_verdict: null."""
import json
import struct
import sys
import time
from pathlib import Path

import numpy as np
import torch

PREP, OUT = Path("/prep"), Path("/out")
W, H = 1024, 741
NSRC, MIN_TRI_DEG, PCTL = 20, 1.0, 75
VARIANTS = {"current": (2, 1.0, None), "strict": (3, 1.0, 0.01), "loose": (2, 2.0, None)}


def read_cameras(p):
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        cams = {}
        for _ in range(n):
            cid, model, w, h = struct.unpack("<iiQQ", f.read(24))
            npar = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8}[model]
            cams[cid] = (model, w, h, np.array(struct.unpack("<" + "d" * npar, f.read(8 * npar))))
    return cams


def qR(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def read_images(p):
    ims = {}
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            iid = struct.unpack("<i", f.read(4))[0]
            q = np.array(struct.unpack("<dddd", f.read(32)))
            t = np.array(struct.unpack("<ddd", f.read(24)))
            cid = struct.unpack("<i", f.read(4))[0]
            name = b""
            while True:
                c = f.read(1)
                if c == b"\x00":
                    break
                name += c
            n2 = struct.unpack("<Q", f.read(8))[0]
            f.read(24 * n2)
            ims[iid] = dict(name=name.decode(), R=qR(q), t=t, cam=cid)
    return ims


def read_points(p):
    """point xyz and track image ids."""
    xyz, tracks = [], []
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            f.read(8)
            xyz.append(struct.unpack("<ddd", f.read(24)))
            f.read(3 + 8)
            L = struct.unpack("<Q", f.read(8))[0]
            tr = np.frombuffer(f.read(8 * L), dtype=np.int32).reshape(-1, 2)[:, 0]
            tracks.append(np.unique(tr))
    return np.array(xyz), tracks


def read_depth(p):
    """the stage-0 reader (common.read_depth_bin): COLMAP width&height&channels& header, float32 of the first channel."""
    data = Path(p).read_bytes()
    off = 0
    for _ in range(3):
        off = data.find(b"&", off, 100) + 1
    w, h, c = map(int, data[:off].decode("ascii").split("&")[:3])
    return np.frombuffer(data, dtype="<f4", offset=off, count=w * h).reshape((w, h), order="F").T.copy()


def sources(ims, xyz, tracks):
    """COLMAP Model::GetMaxOverlappingImages(20, 1 degree) with the 75th-percentile triangulation angles."""
    C = {i: -im["R"].T @ im["t"] for i, im in ims.items()}
    shared, angles = {}, {}
    for X, tr in zip(xyz, tracks):
        tr = [i for i in tr if i in ims]
        if len(tr) < 2:
            continue
        rays = {i: (X - C[i]) / max(np.linalg.norm(X - C[i]), 1e-12) for i in tr}
        for a in range(len(tr)):
            for b in range(a + 1, len(tr)):
                i, j = tr[a], tr[b]
                ang = float(np.arccos(np.clip(rays[i] @ rays[j], -1, 1)))
                for x_, y_ in ((i, j), (j, i)):
                    shared.setdefault(x_, {}).setdefault(y_, 0)
                    shared[x_][y_] += 1
                    angles.setdefault(x_, {}).setdefault(y_, []).append(ang)
    out = {}
    for i in ims:
        cand = [(j, n) for j, n in shared.get(i, {}).items() if np.percentile(angles[i][j], PCTL) >= np.radians(MIN_TRI_DEG)]
        cand.sort(key=lambda x: -x[1])
        out[i] = [j for j, _ in cand[:NSRC]]
    return out


def main(site):
    t0 = time.time()
    ws = PREP / "mvs" / f"box_{site}"
    cams = read_cameras(ws / "sparse/cameras.bin")
    ims = read_images(ws / "sparse/images.bin")
    xyz, tracks = read_points(ws / "sparse/points3D.bin")
    dm = ws / "stereo/depth_maps"
    ids = sorted(i for i, im in ims.items() if (dm / f"{im['name']}.photometric.bin").exists())
    srcs = sources({i: ims[i] for i in ids}, xyz, tracks)
    t_src = time.time() - t0
    model, w0, h0, par = cams[ims[ids[0]]["cam"]]
    fx, fy, cx, cy = par[0] * W / w0, par[1] * H / h0, par[2] * W / w0, par[3] * H / h0
    dev = "cuda"
    pos = {i: k for k, i in enumerate(ids)}
    D = torch.zeros((len(ids), H, W), dtype=torch.float32, device=dev)
    G = np.zeros(len(ids), np.int64)
    for k, i in enumerate(ids):
        D[k] = torch.from_numpy(read_depth(dm / f"{ims[i]['name']}.photometric.bin").astype(np.float32)).to(dev)
    Rm = torch.tensor(np.stack([ims[i]["R"] for i in ids]), dtype=torch.float64, device=dev)
    tv = torch.tensor(np.stack([ims[i]["t"] for i in ids]), dtype=torch.float64, device=dev)
    Cc = -(Rm.transpose(1, 2) @ tv[..., None])[..., 0]
    yy, xx = torch.meshgrid(torch.arange(H, device=dev, dtype=torch.float64), torch.arange(W, device=dev, dtype=torch.float64), indexing="ij")
    xn = (xx + 0.5 - cx) / fx
    yn = (yy + 0.5 - cy) / fy
    masks, rec = {}, {}
    for k, i in enumerate(ids):
        d = D[k].double()
        ok = d > 0
        pix = torch.nonzero(ok, as_tuple=False)
        dv = d[ok]
        Xc = torch.stack([xn[ok] * dv, yn[ok] * dv, dv], -1)
        Xw = (Xc - tv[k]) @ Rm[k]                                  # R^T (Xc - t)
        cnt = {v: torch.zeros(len(dv), dtype=torch.int16, device=dev) for v in VARIANTS}
        for j in srcs.get(i, []):
            if j not in pos:
                continue
            kj = pos[j]
            Xs = Xw @ Rm[kj].T + tv[kj]
            zs = Xs[:, 2]
            us = fx * Xs[:, 0] / zs + cx
            vs = fy * Xs[:, 1] / zs + cy
            pu, pv = torch.floor(us).long(), torch.floor(vs).long()
            inside = (zs > 0) & (pu >= 0) & (pu < W) & (pv >= 0) & (pv < H)
            ds = torch.zeros_like(zs)
            ds[inside] = D[kj][pv[inside], pu[inside]].double()
            valid = inside & (ds > 0)
            # back-project the source pixel centre at its depth, project into the view
            xs_n = (pu.double() + 0.5 - cx) / fx
            ys_n = (pv.double() + 0.5 - cy) / fy
            Ys = torch.stack([xs_n * ds, ys_n * ds, ds], -1)
            Yw = (Ys - tv[kj]) @ Rm[kj]
            Yr = Yw @ Rm[k].T + tv[k]
            ur = fx * Yr[:, 0] / Yr[:, 2] + cx
            vr = fy * Yr[:, 1] / Yr[:, 2] + cy
            err = torch.hypot(ur - (pix[:, 1].double() + 0.5), vr - (pix[:, 0].double() + 0.5))
            ratio = torch.abs(zs - ds) / torch.clamp(ds, min=1e-9)
            for v, (n_, r_, q_) in VARIANTS.items():
                good = valid & (err <= r_) & (Yr[:, 2] > 0)
                if q_ is not None:
                    good &= ratio <= q_
                cnt[v] += good.short()
        bits = torch.zeros((H, W), dtype=torch.uint8, device=dev)
        for b, (v, (n_, r_, q_)) in enumerate(VARIANTS.items()):
            sel = torch.zeros((H, W), dtype=torch.bool, device=dev)
            sel[ok] = cnt[v] >= n_
            bits |= (sel.to(torch.uint8) << b)
        masks[ims[i]["name"]] = bits.cpu().numpy()
        geo = read_depth(dm / f"{ims[i]['name']}.geometric.bin") > 0
        cur = (masks[ims[i]["name"]] & 1) > 0
        rec[ims[i]["name"]] = dict(photometric=int(ok.sum()), geometric=int(geo.sum()), current=int(cur.sum()), both=int((geo & cur).sum()),
                                   strict=int(((masks[ims[i]["name"]] >> 1) & 1).sum()), loose=int(((masks[ims[i]["name"]] >> 2) & 1).sum()),
                                   sources=[ims[j]["name"] for j in srcs.get(i, [])])
    O = OUT / "sens/conf"
    O.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(O / f"{site}.npz", **masks)
    tot = {k: int(sum(r[k] for r in rec.values())) for k in ("photometric", "geometric", "current", "both", "strict", "loose")}
    tot["jaccard_current_vs_colmap"] = round(tot["both"] / max(tot["geometric"] + tot["current"] - tot["both"], 1), 4)
    (O / f"{site}.json").write_text(json.dumps(dict(site=site, views=len(ids), K=[fx, fy, cx, cy], variants={k: dict(sources_min=v[0], reproj_px=v[1], depth_ratio=v[2]) for k, v in VARIANTS.items()},
                                                    totals=tot, per_view=rec, seconds=dict(sources=round(t_src, 1), all=round(time.time() - t0, 1)),
                                                    scientific_verdict=None), indent=1))
    print(json.dumps(dict(site=site, totals=tot, seconds=round(time.time() - t0, 1))))


if __name__ == "__main__":
    main(sys.argv[1])
