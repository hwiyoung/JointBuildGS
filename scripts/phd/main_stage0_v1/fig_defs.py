"""PHD-MAIN-STAGE0-v1 5.4: the figure views and section planes of the stage-0 figures, computed from pre-training data only
and saved before any training (jointbuildgs:dev, CPU; rules = configs stage0_v1.json stage0.figures).

  python fig_defs.py

views     evaluation views of B173nb_b10 (test split of the fork inputs): the 2 nadir (tilt <= 20 deg) and 2 oblique views whose
          projection of the B173 roof centroid (area-weighted, LoD2 roof faces of DEBY_LOD2_4959326) lies nearest the image centre
sections  vertical planes (point c, unit horizontal direction t along the section, extent +-L):
  B173_wing       the larger B173 wing roof face (sites_v1 B173_wings): its centroid, t = its horizontal normal (across the ridge), 15 m
  B173_middle     the 17 sawtooth faces (sites_v1 B173_middle): area-weighted centroid, t = principal direction of their horizontal
                  normals (sign-free), 20 m
  neighbour_wall  the LoD2 wall face of DEBY_LOD2_4959460 with the most patches in the evaluation range (v6 LoD2 box run): the
                  centroid of those patches, t = its horizontal normal, 10 m
  old_upper_wall  the LoD2 wall face of DEBY_LOD2_4959326 with the most invisible patches (v6 LoD2 box run): the centroid of those
                  patches, t = its horizontal normal, 10 m
Writes stage0/fig_defs.json. scientific_verdict: null."""
import json
from pathlib import Path

import numpy as np

from common import DR, OUT, PREP, SCFG, Views, jdump, log, xy_to_uv

SITE = SCFG["stage0"]["site"]


def main():
    sites = {s["id"]: s for s in json.loads(Path("/repo/configs/phd/main_prep_discard_rule_v1/sites_v1.json").read_text())["sites"]}
    md = DR / "s02_box" / SITE
    m = np.load(md / "lod2_mesh.npz"); tab = {r["ext"]: r for r in json.loads((md / "lod2_surfaces.json").read_text())["surfaces"]}
    gml2ext = {r["gml"]: e for e, r in tab.items()}
    V, F, ts = m["V"].astype(np.float64), m["F"], m["tri_surface"]
    tri_area = 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)
    tri_c = V[F].mean(1)

    def face_centroid(exts):
        sel = np.isin(ts, list(exts))
        return (tri_c[sel] * tri_area[sel, None]).sum(0) / tri_area[sel].sum(), float(tri_area[sel].sum())

    def hdir(n):
        h = np.asarray(n, np.float64)[:2]
        return h / np.linalg.norm(h)

    # views
    split = json.loads((OUT / "fork_inputs/s61" / SITE / "split.json").read_text())
    Vw = Views()
    roof_exts = [e for e, r in tab.items() if r["building"] == "DEBY_LOD2_4959326" and r["kind"] == 1]
    cen, _ = face_centroid(roof_exts)
    names = {n.rsplit(".", 1)[0]: n for n in Vw.names}
    cand = []
    for stem in split["test"]:
        n = names[stem]
        u, v, z = Vw.project(n, cen[None])
        if z[0] <= 0 or not (0 <= u[0] < 1024 and 0 <= v[0] < 741):
            continue
        cand.append(dict(view=stem, tilt=round(Vw.tilt(n), 2), dist_px=float(np.hypot(u[0] - 512, v[0] - 370.5))))
    nad = sorted([c for c in cand if c["tilt"] <= 20], key=lambda c: c["dist_px"])[:2]
    obl = sorted([c for c in cand if c["tilt"] > 20], key=lambda c: c["dist_px"])[:2]
    # sections
    sec = {}
    wings = [gml2ext[g] for g in sites["B173_wings"]["faces_gml"]]
    big = max(wings, key=lambda e: face_centroid([e])[1])
    c, _ = face_centroid([big])
    sec["B173_wing"] = dict(face_ext=int(big), gml=tab[big]["gml"], c=c.tolist(), t=hdir(tab[big]["normal"]).tolist(), L=15.0)
    mids = [gml2ext[g] for g in sites["B173_middle"]["faces_gml"]]
    c, _ = face_centroid(mids)
    H = np.array([hdir(tab[e]["normal"]) * face_centroid([e])[1] ** 0.5 for e in mids])
    w, vv = np.linalg.eigh(H.T @ H)
    sec["B173_middle"] = dict(face_ext=[int(e) for e in mids], c=c.tolist(), t=vv[:, -1].tolist(), L=20.0)
    U = np.load(OUT / "s61/box" / SITE / "LoD2" / "units.npz")
    b = json.loads((PREP / "step06/boxes_v1.json").read_text())["boxes"]["B173nb"]
    uv = xy_to_uv(U["loc_center"][:, :2])
    inev = (uv[:, 0] >= b["eval_u"][0]) & (uv[:, 0] <= b["eval_u"][1]) & (uv[:, 1] >= b["eval_v"][0]) & (uv[:, 1] <= b["eval_v"][1]) & U["loc_in_range"]
    ext_of = U["surf_ext"][U["loc_surface"]]
    for key, bld, extra in (("neighbour_wall", "DEBY_LOD2_4959460", inev), ("old_upper_wall", "DEBY_LOD2_4959326", inev & (U["state"] == 0))):
        walls = [e for e, r in tab.items() if r["building"] == bld and r["kind"] == 2]
        counts = {e: int((extra & (ext_of == e) & (U["loc_kind"] == 2)).sum()) for e in walls}
        e = max(counts, key=lambda k: (counts[k], -k))
        msk = extra & (ext_of == e) & (U["loc_kind"] == 2)
        sec[key] = dict(face_ext=int(e), gml=tab[e]["gml"], patches=counts[e], c=U["loc_center"][msk].mean(0).tolist(), t=hdir(tab[e]["normal"]).tolist(), L=10.0)
    jdump(OUT / "stage0/fig_defs.json", dict(rule=__doc__.split("\n\n")[1], views=dict(nadir=nad, oblique=obl, roof_centroid=cen.tolist()),
                                             sections=sec, written_before_training=True, scientific_verdict=None))
    log("views", [v["view"] for v in nad + obl], "sections", {k: (v.get("gml"), v.get("patches")) for k, v in sec.items()})


if __name__ == "__main__":
    main()
