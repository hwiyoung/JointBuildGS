"""PHD-STAGE2-R9-THREE-FIXES-v1 step 13c (jointbuildgs:dev, CPU): what an added (virtual) view sees in front of the aimed
Gaussians, r8 and r9 from the same camera (fix 'da', mesh check).

  python occluders_r9.py      # mounts: /artifacts (ro), /repo (ro), /r8 (ro), /p9 (rw)

The camera = the r8 virtual view of r8's figure (mesh/M_N/virtual_view.npz; r9 rendered from it: virtual_view_r8cam.npz).
Image area = pixels where r8's aimed Gaussians (invisible prior Gaussians, opacity >= 0.5, on outward faces of the target
building) project and lie within 0.5 m of r8's rendered depth (dilated by 2 pixels). In that area, for each run, the
Gaussians that form the rendered surface = opacity >= 0.5, projected into the area, within 0.5 m of that run's rendered
depth at their pixel; counted by origin, initial region and building / face kind of their initial surface.
Projection as the 3DGS camera: [x y z 1] @ world_view -> camera z; [x y z 1] @ full_proj -> NDC -> pixel.
Writes /p9/cases/occluders.json."""
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_dilation

P9 = Path("/p9"); R8 = Path("/r8")
CAT = {0: "image", 1: "support patch", 2: "missing patch", 3: "invisible patch", 4: "prior without a patch"}


def project(X, wv, fp, size):
    W, H = int(size[0]), int(size[1])
    Xh = np.concatenate([X, np.ones((len(X), 1))], 1)
    z = (Xh @ wv)[:, 2]
    c = Xh @ fp
    ndc = c[:, :3] / np.where(np.abs(c[:, 3:4]) < 1e-12, 1e-12, c[:, 3:4])
    u = ((ndc[:, 0] + 1.0) * W - 1.0) * 0.5; v = ((ndc[:, 1] + 1.0) * H - 1.0) * 0.5
    return np.round(u).astype(np.int64), np.round(v).astype(np.int64), z


def surface_of(root, run, view, area=None):
    z = np.load(view)
    wv, fp, size = z["world_view"].astype(np.float64), z["full_proj"].astype(np.float64), z["size"]
    D = z["depth"].astype(np.float64)
    W, H = int(size[0]), int(size[1])
    dz = np.load(root / "runs" / run / "model/dump/iteration_3500/gaussians.npz")
    X = dz["xyz"].astype(np.float64)
    u, v, zc = project(X, wv, fp, size)
    inside = (u >= 0) & (u < W) & (v >= 0) & (v < H) & (zc > 0)
    Dz = np.full(len(X), np.nan); Dz[inside] = D[v[inside], u[inside]]
    on = inside & (np.abs(zc - Dz) <= 0.5) & (dz["opacity"] >= 0.5)
    if area is not None:
        on &= np.zeros(len(X), bool) | (inside & area[np.clip(v, 0, H - 1), np.clip(u, 0, W - 1)])
    ids = dz["init_id"].astype(np.int64)
    ext = np.where(ids >= 0, dz["init_surface_ext"][np.maximum(ids, 0)], -1)
    cat = dz["init_category"]
    return dict(on=on, ext=ext, cat=cat, origin=dz["origin"], u=u, v=v, W=W, H=H, region=None)


tables = {}
for root in (P9, R8):
    t = {r["ext"]: r for r in json.loads((root / "stage1/products/M_N/surfaces_poly.json").read_text())["surfaces"]}
    tables[str(root)] = t
# image area from r8's aimed Gaussians seen in r8's view
iv8 = np.load(R8 / "mesh/M_N/invisible.npz")
s8 = surface_of(R8, "M_N", R8 / "mesh/M_N/virtual_view.npz")
area = np.zeros((s8["H"], s8["W"]), bool)
reg = iv8["region"] & s8["on"]
area[s8["v"][reg], s8["u"][reg]] = True
area = binary_dilation(area, iterations=2)
out = dict(rule=__doc__.split("\n\n")[1], area_px=int(area.sum()), runs={})
for tag, root, view in (("r8", R8, R8 / "mesh/M_N/virtual_view.npz"), ("r9", P9, P9 / "mesh/M_N/virtual_view_r8cam.npz")):
    s = surface_of(root, "M_N", view, area)
    on = s["on"]
    t = tables[str(root)]
    tgt = np.array([bool(t.get(int(e), {}).get("target")) for e in s["ext"][on]])
    typ = np.array([t.get(int(e), {}).get("type", "none") for e in s["ext"][on]])
    cat = s["cat"][on]
    top = {}
    vals, cnt = np.unique(s["ext"][on], return_counts=True)
    for k in np.argsort(-cnt)[:8]:
        e = int(vals[k]); r_ = t.get(e, {})
        top[str(e)] = dict(n=int(cnt[k]), target=bool(r_.get("target")), type=r_.get("type"), building=r_.get("building"))
    out["runs"][tag] = dict(n_surface_gaussians=int(on.sum()),
                            by_category={CAT[c]: int((cat == c).sum()) for c in CAT},
                            target_building=int(tgt.sum()), other_buildings=int((~tgt & (s["ext"][on] >= 0)).sum()), image_origin=int((s["origin"][on] == 0).sum()),
                            by_type={k: int((typ == k).sum()) for k in np.unique(typ)}, top_faces=top)
    print(tag, json.dumps(out["runs"][tag])[:900], flush=True)
(P9 / "cases/occluders.json").write_text(json.dumps(out, indent=1))
