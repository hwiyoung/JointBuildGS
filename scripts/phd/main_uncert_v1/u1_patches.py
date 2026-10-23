"""PHD-MAIN-UNCERT-v1 일 1: the patch table of one case (jointbuildgs:dev, CPU): centre c, outward normal n, roof-like flag, surface,
building and roof type, the cells of 1.6 (checked patch by patch against the AXES71 stored cells), the edge distance of 6.5, the GT-free
facts of 일 1.

  python u1_patches.py <site> [...]   -> /out/work/patches_<site>_<prior>.npz, /out/work/patches_<site>.json

Normal (config patch.normal_rule) = scripts/phd/main_stage1_v1/defs_s1.patch_geometry: n = loc_t1 x loc_t2 flipped up; LoD2 walls = the
LoD2 surface normal of DR/s02_box/<site>/lod2_surfaces.json. The LoD2 wall check: per wall face, the share of its patches whose point
c + 0.5 m x (horizontal n) lies outside the building's footprint union (DR/s02_box/<site>/footprints.json) while c - 0.5 m x (horizontal
n) lies inside ('out'), the reverse ('in'), or neither; a face with more 'in' than 'out' patches is flipped. Roof type: P0 raw CityGML
(bldg:roofType of the building, else of its parts). scientific_verdict: null."""
import json
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import uc_common as U  # noqa: E402


def roof_types(buildings):
    """{building gml:id: (code or None, part codes)} from the P0 raw CityGML files (CityGML 1.0)."""
    from lxml import etree
    B = "{http://www.opengis.net/citygml/building/1.0}"
    G = "{http://www.opengis.net/gml}"
    want = set(buildings)
    out = {}
    for f in ("690_5336.gml", "690_5334.gml"):
        p = U.ART / "phase-payloads/p0-audit/data/raw/lod2" / f
        for _, el in etree.iterparse(str(p), events=("end",), tag=B + "Building"):
            gid = el.get(G + "id")
            if gid in want:
                rt = el.find(B + "roofType")
                parts = [x.text for x in el.iter(B + "BuildingPart") for x in [x.find(B + "roofType")] if x is not None]
                out[gid] = dict(code=rt.text if rt is not None else None, parts=parts, file=f)
            el.clear()
            while el.getprevious() is not None:
                del el.getparent()[0]
        if want <= set(out):
            break
    return out


def edge_distance(C, surf, rmax=2.0, chunk=20000):
    """distance from each patch centre to the nearest centre with another surface number (3-D), up to rmax (inf beyond)."""
    tree = cKDTree(C)
    out = np.full(len(C), np.inf)
    for b in range(0, len(C), chunk):
        idx = tree.query_ball_point(C[b:b + chunk], rmax)
        for i, nb in enumerate(idx):
            nb = np.asarray(nb, np.int64)
            nb = nb[surf[nb] != surf[b + i]]
            if len(nb):
                out[b + i] = float(np.min(np.linalg.norm(C[nb] - C[b + i], axis=1)))
    return out


def main(site):
    from matplotlib.path import Path as MPath
    T = U.Timer()
    facts = {}
    lsurf = json.loads((U.DR / "s02_box" / site / "lod2_surfaces.json").read_text())["surfaces"]
    tab = {t["ext"]: t for t in lsurf}
    fps = json.loads((U.DR / "s02_box" / site / "footprints.json").read_text())["footprints"]
    rts = roof_types(sorted({t["building"] for t in lsurf}))
    for prior in U.PRIORS:
        R = U.regions(site, prior)
        Un = np.load(U.S0 / "s61/box" / site / prior / "units.npz")
        c = R["centre"].astype(np.float64)
        assert np.array_equal(Un["loc_center"], R["centre"]), "region file and store differ"
        n = np.cross(Un["loc_t1"], Un["loc_t2"])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        n *= np.where(n[:, 2:3] < 0, -1.0, 1.0)
        se = Un["surf_ext"][Un["loc_surface"]].astype(np.int64)
        assert np.array_equal(se, R["surf_ext"]), "surf_ext differs"
        kind = Un["loc_kind"].astype(np.int8)
        f = {}
        bld = np.array([""] * len(c), dtype=object)
        if prior == "LoD2":
            wl = kind == 2
            n[wl] = np.array([tab[int(e)]["normal"] for e in se[wl]], np.float64)
            bld = np.array([tab[int(e)]["building"] for e in se], dtype=object)
            # the outward check of the LoD2 wall normals
            rings = {}
            for r in fps:
                rings.setdefault(r["building"], []).append(MPath(np.asarray(r["ring_local"])))
            hz = n[:, :2] / np.maximum(np.linalg.norm(n[:, :2], axis=1, keepdims=True), 1e-12)
            res = {}
            flipped = []
            for e in np.unique(se[wl]):
                m = np.nonzero(wl & (se == e))[0]
                b = tab[int(e)]["building"]
                if b not in rings:
                    res[int(e)] = dict(building=b, why="윤곽 없음")
                    continue
                po, pi = c[m, :2] + 0.5 * hz[m], c[m, :2] - 0.5 * hz[m]
                ino = np.zeros(len(m), bool); ini = np.zeros(len(m), bool)
                for P in rings[b]:
                    ino |= P.contains_points(po); ini |= P.contains_points(pi)
                k_out, k_in = int((~ino & ini).sum()), int((ino & ~ini).sum())
                res[int(e)] = dict(building=b, patches=int(len(m)), out=k_out, inward=k_in, neither=int(len(m) - k_out - k_in))
                if k_in > k_out:
                    n[m] *= -1.0
                    flipped.append(int(e))
            tot = {k: int(sum(v.get(k, 0) for v in res.values())) for k in ("patches", "out", "inward", "neither")}
            f["lod2_wall_outward"] = dict(faces=len(res), flipped_faces=flipped, totals=tot, per_face=res)
        rlike = np.abs(n[:, 2]) >= np.cos(np.radians(U.D["roof_like_max_angle_deg"]))
        cell, cf = U.cells_of(site, prior, R)
        axf = U.AX / "work" / f"cells_{site}_{prior}.npz"
        if axf.exists():
            ax = np.load(axf)["cell"].astype(np.int8)
            axcfg = json.loads((U.REPO / "configs/phd/main_axes71_v2/axes71_v2.json").read_text())["cells"]["order"]
            same_order = axcfg == U.CELLS
            cf["axes71_compare"] = dict(file=str(axf), same_cell_order=same_order, patches_equal=int((ax == cell).sum()), patches=int(len(cell)),
                                        differ=int((ax != cell).sum()))
        ev = R["in_eval"].astype(bool)
        edge = edge_distance(c, se)
        rcode = np.array([""] * len(c), dtype=object)
        if prior == "LoD2":
            for b, v in rts.items():
                code = v["code"] if v["code"] else (v["parts"][0] if v["parts"] and len(set(v["parts"])) == 1 else ("부분마다 다름" if v["parts"] else ""))
                rcode[bld == b] = code
        tau = R["tau"].astype(np.float64)
        np.savez(U.WORK / f"patches_{site}_{prior}.npz", centre=c, normal=n, roof_like=rlike, surf=se, kind=kind, in_eval=ev, cell=cell,
                 code=R["code_ext_v3"].astype(np.int8), area=R["area"].astype(np.float64), tau=tau, gt_med=R["gt_med"].astype(np.float64),
                 edge=edge, building=bld.astype(str), roof_type=rcode.astype(str))
        f.update(dict(patches=int(len(c)), in_eval=int(ev.sum()), band=int((~ev).sum()), roof_like=int(rlike.sum()), wall_like=int((~rlike).sum()),
                      roof_like_in_eval=int((rlike & ev).sum()), wall_like_in_eval=int((~rlike & ev).sum()),
                      kind_counts={int(k): int(v) for k, v in zip(*np.unique(kind, return_counts=True))},
                      roof_like_vs_kind=dict(kind1_wall_like=int(((kind == 1) & ~rlike).sum()), kind2_roof_like=int(((kind == 2) & rlike).sum())),
                      area_m2=dict(in_eval=float(R["area"][ev].sum()), band=float(R["area"][~ev].sum())),
                      region_keys=list(R.files), cells=cf,
                      cell_counts={U.CELLS[k]: dict(patches=int((cell == k).sum()), area_m2=float(R["area"][cell == k].sum())) for k in range(len(U.CELLS))},
                      tau_values_cm=sorted({round(float(x) * 100, 2) for x in np.unique(tau)}),
                      edge_bins={"0-0.5": int((edge < 0.5).sum()), "0.5-1": int(((edge >= 0.5) & (edge < 1)).sum()),
                                 "1-2": int(((edge >= 1) & (edge < 2)).sum()), ">2": int((edge >= 2).sum())},
                      surfaces=int(len(np.unique(se))), surf_minus1=int((se < 0).sum())))
        if prior == "LoD2":
            rf = rlike & ev
            f["roof_type"] = {str(k): dict(buildings=sorted({b for b, v in rts.items() if (v["code"] or "") == k}),
                                           roof_like_area_in_eval_m2=float(R["area"][rf & (rcode == k)].sum()))
                              for k in sorted(set(rcode.tolist()))}
            f["roof_type_by_building"] = rts
        facts[prior] = f
        U.log(site, prior, f["patches"], "cells differ" if cf.get("axes71_compare", {}).get("differ") else "cells same", T.mark(prior))
    U.jdump(U.WORK / f"patches_{site}.json", dict(site=site, rule=__doc__, made=U.now(), env=U.env(), facts=facts, seconds=T.marks,
                                                  scientific_verdict=None))


if __name__ == "__main__":
    for s in sys.argv[1:]:
        main(s)
