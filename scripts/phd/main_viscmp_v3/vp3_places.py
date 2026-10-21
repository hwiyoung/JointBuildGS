"""PHD-MAIN-VISCMP-v3 places and cameras (request 2.8, 4): V1 and V2 = the v2 places (configs/phd/main_viscmp_v2/viscmp_v2.json); V5 = the
place v5_select.py chose (before any other result file was opened); new cameras from geometry only:
  V3  the oblique training view (tilt > 20 deg) holding every patch of the face-1 roof rows (FT/prep/figpos_fig1_rows.npz) with >= 80 %
      visible and the largest footprint; none -> the v2 vertical view DJI_20241217091131_0108_D.
  V4  wall 19 seen from outside along its outward normal (orthographic, 0.025 m rays averaged 2 x 2), the whole face + 2 m.
  V2  the left panel: a perspective view of the LoD2 prior from outside face 53 and above (eye = wall centre + 70 m outward + 45 m up,
      looking at the wall centre, the face frame + 40 % in view).
  python vp3_places.py -> /vc/prep/places.json   scientific_verdict: null"""
import json

import numpy as np

import vc_common  # noqa: F401
import p0_places as P0
import vc_fig as VF
from vc_common import FT, S1, VC, jdump, jl, log, now

V2CFG = json.loads(open("/repo/configs/phd/main_viscmp_v2/viscmp_v2.json").read())["places"]


def oblique_best(site, prior, P):
    V = P0.views(); rows = []
    for v in P0.train_views(site):
        k = P0.vname(v)
        if k is None or V.tilt(k) <= 20.0:
            continue
        u, w, z = V.project(k, P)
        if not ((z > 0) & (u >= 0) & (u < 1024) & (w >= 0) & (w < 741)).all():
            continue
        D = np.load(P0.S0 / "s61/export" / site / prior / "prior" / f"{v}.npy")
        d = D[np.clip(np.floor(w).astype(int), 0, 740), np.clip(np.floor(u).astype(int), 0, 1023)]
        vis = float((np.isfinite(d) & (np.abs(z - d) <= 0.5)).mean())
        if vis < P0.VIS_MIN:
            continue
        from scipy.spatial import ConvexHull
        rows.append(dict(view=v, visible=vis, hull_px2=float(ConvexHull(np.column_stack([u, w])).volume), tilt_deg=round(V.tilt(k), 2)))
    rows.sort(key=lambda r: -r["hull_px2"])
    return rows


def main():
    out = dict(made=now(), scientific_verdict=None, note="자리와 카메라는 결과 메시를 열지 않고 정함(V5는 v5_select.py가 사전 정보 거리 파일과 영상 깊이로 고름)")
    out["V1"] = dict(V2CFG["V1"], source="v2 config places.V1", crop_native=[872, 355, 1353, 654], scale=4)
    out["V2"] = dict(V2CFG["V2"], source="v2 config places.V2")
    # V2 left panel
    fr = out["V2"]["camera"]; c = np.asarray(fr["centre"]); n = np.asarray(fr["toward_viewer"]); r = np.asarray(fr["right"])
    eye = c + 70.0 * n + np.array([0, 0, 45.0])
    out["V2"]["left_camera"] = dict(kind="lookat", eye=eye.tolist(), target=c.tolist(), up=[0, 0, 1], frame_s=fr["s_range"], frame_h=fr["h_range"], margin=0.4,
                                    size=[1600, 1000], rule="eye = wall centre + 70 m outward + 45 m up; the frame corners + 40 % in view")
    # V3
    site, prior = "B173nb_b10", "ALS"
    Fr = np.load(FT / "prep/figpos_fig1_rows.npz")
    W = np.load(S1 / "defs" / site / f"rows_{prior}.npz")
    patches = np.unique(W["patch"][Fr["rows"]])
    U = P0.store(site, prior)
    cand = oblique_best(site, prior, P0.patch_corners(U, patches))
    out["V3"] = dict(site=site, prior=prior, patches=[int(x) for x in patches], rows_file="FT/prep/figpos_fig1_rows.npz", rows=int(len(Fr["rows"])),
                     view=cand[0]["view"] if cand else "DJI_20241217091131_0108_D", view_rule="oblique (tilt > 20 deg), all inside, >= 80 % visible, largest footprint; none -> 0108",
                     candidates=cand[:6], fallback_used=not bool(cand))
    # V5
    sel = jl(VC / "prep/v5_candidates.json")
    m = sel["chosen"]["main"]
    out["V5"] = dict(site=m["site"], prior=m["prior"], patches=m["patch_list"], area_m2=m["area_m2"], gt_points=m["gt_points"], rows=m["rows"], view=m["camera"]["view"],
                     prior_dist_cm=m["prior_dist_cm"], image_dist_cm=m["image_dist_cm"], tier=sel["chosen"]["tier"],
                     auxiliary={k: v for k, v in (sel["chosen"]["auxiliary"] or {}).items() if k != "patch_list"},
                     auxiliary_patches=(sel["chosen"]["auxiliary"] or {}).get("patch_list"), fill_rule_place=sel["fill_rule_place"],
                     chosen_at=sel["made"], source="v5_select.py")
    # V4 frame
    p4 = V2CFG["V4"]
    site, prior, ext = p4["site"], p4["prior"], p4["ext"]
    R = P0.region(site, prior); U = P0.store(site, prior)
    se = R["surf_ext"].astype(int); ev = R["in_eval"].astype(bool)
    face = np.nonzero(ev & (se == ext))[0]
    Q = VF.quads(U, face).reshape(-1, 3)
    n4 = np.asarray(p4["outward_normal"], np.float64); n4[2] = 0; n4 /= np.linalg.norm(n4)
    r4 = np.cross(-n4, [0.0, 0.0, 1.0]); r4 /= np.linalg.norm(r4)
    c4 = Q.mean(0)
    s, h = (Q[:, :2] - c4[:2]) @ r4[:2], Q[:, 2] - c4[2]
    out["V4"] = dict(p4, source="v2 config places.V4", camera=dict(kind="ortho", centre=c4.tolist(), right=r4.tolist(), up=[0, 0, 1], toward_viewer=n4.tolist(),
                     s_range=[float(s.min() - 2), float(s.max() + 2)], h_range=[float(h.min() - 2), float(h.max() + 2)], pixel=0.05, supersample=2,
                     rule="outward normal, the whole face 19 + 2 m"), face_patches=int(len(face)))
    jdump(VC / "prep/places.json", out)
    log("V3", out["V3"]["view"], cand[:2]); log("V4", out["V4"]["camera"]["s_range"], out["V4"]["camera"]["h_range"]); log("V5", out["V5"]["site"], out["V5"]["view"])


if __name__ == "__main__":
    main()
