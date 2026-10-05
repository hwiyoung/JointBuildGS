"""Facts about the nominal-scene out-of-width roof pixels (vertical axis, roof pool, tau from checks_v2):
edge-band share, small-face share, main-roof interior share, MVS-nearer share. Writes out_v2/right_scene_facts_v2.json."""
import json
from pathlib import Path

import numpy as np

ART = Path("/artifacts/JointBuildGS")
CFG = json.loads(Path("/repo/configs/phd/stage1_verify_v2/experiment.json").read_text())
S1 = ART / CFG["stage1_relative"]
V2 = Path("/v2")
C = json.loads((V2 / "out_v2/checks_v2.json").read_text())
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
SCENE = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene"
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
Z = np.load(V2 / "inputs_v2/lod2_v2_nominal_local.npz")
prc = Z["poly_region_code"]
poly_normal = np.zeros((len(prc), 3), np.float32)
for p in PJ["polygons"]:
    poly_normal[p["poly_index"]] = p["normal"]
MAIN = 3396
EDGE_PX = 40


def qvec2R(q):
    w, x, y, z = q
    return np.array([[1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * z * w, 2 * x * z + 2 * y * w],
                     [2 * x * y + 2 * z * w, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * x * w],
                     [2 * x * z - 2 * y * w, 2 * y * z + 2 * x * w, 1 - 2 * x * x - 2 * y * y]])


cams, imgs = {}, {}
for l in (SPARSE / "cameras.txt").read_text().splitlines():
    if l.strip() and not l.startswith("#"):
        t = l.split()
        cams[int(t[0])] = dict(W=int(t[2]), H=int(t[3]), p=[float(x) for x in t[4:]])
for l in (SPARSE / "images.txt").read_text().splitlines():
    t = l.split()
    if len(t) >= 10 and not l.startswith("#") and t[9].lower().endswith(".jpg"):
        imgs[t[9]] = dict(q=[float(x) for x in t[1:5]], cam=int(t[8]))
out = {}
for prior in "LM":
    m2, tau = C["per_prior"][prior]["nominal"]["m2"], C["per_prior"][prior]["nominal"]["tau"]
    acc = dict(n_out=0, n_yes=0, edge_band=0, small_faces=0, main_interior=0, mvs_nearer=0)
    for n in sorted(x.name for x in (SCENE / "images").iterdir() if x.suffix.lower() == ".jpg"):
        stem = Path(n).stem
        cam = cams[imgs[n]["cam"]]
        fx, fy, cx, cy = cam["p"]
        R = qvec2R(imgs[n]["q"])
        A = np.load(S1 / "out/conf" / f"{stem}_conf.npy")
        mvs = np.load(S1 / "inputs/mvs_full" / f"{stem}_depth.npy")
        poly = np.load(V2 / "inputs_v2/faceid" / f"{stem}.npy")
        roof = (poly >= 0) & (prc[np.maximum(poly, 0)] == 1)
        pd = np.load(V2 / f"inputs_v2/prior_render/{prior}_nominal/lod2_prior/raw_depth/{stem}.npy").astype(np.float32)
        pok = np.isfinite(pd) & (pd > 0) & (pd < 1e6)
        yes = (A == 1) & pok & roof
        xn = (np.arange(cam["W"]) + 0.5 - cx) / fx
        yn = (np.arange(cam["H"]) + 0.5 - cy) / fy
        d = [(R[0, k] * xn[None, :] + R[1, k] * yn[:, None] + R[2, k]).astype(np.float32) for k in range(3)]
        nrm = poly_normal[np.maximum(poly, 0)]
        vfac = np.abs(nrm[..., 0] * d[0] + nrm[..., 1] * d[1] + nrm[..., 2] * d[2]) / np.maximum(np.abs(nrm[..., 2]), 1e-6)
        rv = (mvs - pd) * vfac
        outm = yes & (np.abs(rv - m2) > tau)
        b = np.zeros(poly.shape, bool)
        b[1:, :] |= poly[1:, :] != poly[:-1, :]
        b[:, 1:] |= poly[:, 1:] != poly[:, :-1]
        from scipy import ndimage
        edge = ndimage.distance_transform_edt(~b) <= EDGE_PX
        acc["n_out"] += int(outm.sum())
        acc["n_yes"] += int(yes.sum())
        acc["edge_band"] += int((outm & edge).sum())
        acc["small_faces"] += int((outm & (poly != MAIN) & ~edge).sum())
        acc["main_interior"] += int((outm & (poly == MAIN) & ~edge).sum())
        acc["mvs_nearer"] += int((outm & (rv < m2)).sum())
        print(prior, stem, acc["n_out"], flush=True)
    out[prior] = dict(acc, out_fraction=acc["n_out"] / acc["n_yes"], edge_band_share=acc["edge_band"] / acc["n_out"], small_faces_share=acc["small_faces"] / acc["n_out"],
                      main_interior_share=acc["main_interior"] / acc["n_out"], main_interior_fraction_of_yes=acc["main_interior"] / acc["n_yes"],
                      mvs_nearer_share=acc["mvs_nearer"] / acc["n_out"], edge_band_px=EDGE_PX, tau=tau, m2=m2)
(V2 / "out_v2/right_scene_facts_v2.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
