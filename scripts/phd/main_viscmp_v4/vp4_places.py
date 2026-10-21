"""PHD-MAIN-VISCMP-v4 photos and cameras of V1-V6 by the config's rules (work_ga.photo_rule, camera_rule), from geometry only (region
files, patch stores, footprints, cameras, prior render depth, depth-map coverage); no result file is opened. Places = v3's (V1-V5) and the
photo figures' 1 and 2 (V6: the glass case 163 patches and the 18 missing patches around it).
  building box = the footprint (DR/s02_box/<site>/footprints.json) holding the most place patch centres; xy = its extent inside the
                 evaluation range's patches, z = those patches' height range; 4 x 4 x 3 grid points
  photo        = the training view holding every place patch centre with >= 80 % visible (V2: no visibility test - the wall is unseen),
                 maximising inside share x projected hull of the box points; crop = the box's projection + 10 %; a zoom photo when the
                 place is narrower than 15 % of the crop
  camera       = V1: v3's; V2: v3's left perspective eye for every panel; others: the photo camera when it sees the place obliquely
                 (roof 20-60 deg from vertical, wall within 60 deg of the normal), else a virtual perspective camera (roof 40 deg from
                 vertical, wall 30 deg from the normal; azimuth toward the photo camera; V3: perpendicular to the roof's long axis),
                 the place + margin (50 % of its size, >= 2 m) filling 70 % of the panel width
  image depth  = V1: the training view whose depth map covers the most piece pixels; V3 0108, V5 0151 (v3), V6 0146 (photo figure 1)
  python vp4_places.py -> /vc/prep/places.json   scientific_verdict: null"""
import json

import numpy as np
from matplotlib.path import Path as MPath
from scipy.spatial import ConvexHull

import vc_common  # noqa: F401
import p0_places as P0
import vc_fig as VF
from vc_common import ROOTS, S0, VC, jdump, jl, log, now

V3P = json.loads(open("/repo/configs/phd/main_viscmp_v3/viscmp_v3.json").read())["places"]
PF1 = json.loads(open("/repo/configs/phd/main_photofig_v1/photofig_v1.json").read())["places"]


def building_box(site, prior, place):
    R = P0.region(site, prior)
    C = R["centre"].astype(np.float64); ev = R["in_eval"].astype(bool)
    fps = jl(ROOTS["DR"] / "s02_box" / site / "footprints.json")["footprints"]
    pc = C[place][:, :2]
    best, bn = None, -1
    for f in fps:
        ring = np.asarray(f["ring_local"], np.float64)[:, :2]
        n = int(MPath(ring).contains_points(pc).sum())
        if n > bn:
            best, bn = f, n
    if bn <= 0:   # walls on the footprint edge: the nearest footprint
        d = [np.min(np.linalg.norm(np.asarray(f["ring_local"])[:, :2] - pc.mean(0), axis=1)) for f in fps]
        best = fps[int(np.argmin(d))]
    ring = np.asarray(best["ring_local"], np.float64)[:, :2]
    inb = ev & MPath(ring).contains_points(C[:, :2], radius=0.3)
    X = C[inb] if inb.sum() > 10 else C[place]
    lo, hi = X.min(0), X.max(0)
    g = np.stack(np.meshgrid(np.linspace(lo[0], hi[0], 4), np.linspace(lo[1], hi[1], 4), np.linspace(lo[2], hi[2], 3)), -1).reshape(-1, 3)
    return dict(building=best.get("building"), lo=lo.tolist(), hi=hi.tolist(), patches_in=int(inb.sum())), g


def choose_photo(site, prior, place, box_pts, need_visible=True, oblique_only=False):
    U = P0.store(site, prior); P = P0.patch_corners(U, place)
    V = P0.views(); rows = []
    for v in P0.train_views(site):
        k = P0.vname(v)
        if k is None or (oblique_only and V.tilt(k) <= 20.0):
            continue
        u, w, z = V.project(k, P)
        if need_visible:
            if not ((z > 0) & (u >= 0) & (u < 1024) & (w >= 0) & (w < 741)).all():
                continue
            D = np.load(S0 / "s61/export" / site / prior / "prior" / f"{v}.npy")
            d = D[np.clip(np.floor(w).astype(int), 0, 740), np.clip(np.floor(u).astype(int), 0, 1023)]
            if float((np.isfinite(d) & (np.abs(z - d) <= 0.5)).mean()) < P0.VIS_MIN:
                continue
        bu, bw, bz = V.project(k, box_pts)
        ins = (bz > 0) & (bu >= 0) & (bu < 1024) & (bw >= 0) & (bw < 741)
        if ins.sum() < 3:
            continue
        try:
            hull = float(ConvexHull(np.column_stack([bu[ins], bw[ins]])).volume)
        except Exception:  # noqa: BLE001
            hull = 0.0
        rows.append(dict(view=v, inside=float(ins.mean()), hull_px2=hull, score=float(ins.mean()) * hull, tilt_deg=round(V.tilt(k), 2)))
    rows.sort(key=lambda r: -r["score"])
    return rows


def photo_crops(view, box_pts, Q):
    pc = VF.RD.Pinhole(view, (0, 0, 1400, 1013), 1)
    bu, bw, bz = pc.project(box_pts)
    ok = bz > 0
    x0, x1, y0, y1 = bu[ok].min(), bu[ok].max(), bw[ok].min(), bw[ok].max()
    mx, my = 0.1 * (x1 - x0), 0.1 * (y1 - y0)
    wide = [int(max(x0 - mx, 0)), int(max(y0 - my, 0)), int(min(x1 + mx, 1400)), int(min(y1 + my, 1013))]
    qu, qv, _ = pc.project(Q.reshape(-1, 3))
    pw = qu.max() - qu.min()
    zoom = None
    if pw < 0.15 * (wide[2] - wide[0]):
        hx, hy = max(0.75 * (qu.max() - qu.min()), 40), max(0.75 * (qv.max() - qv.min()), 30)
        cx, cy = 0.5 * (qu.max() + qu.min()), 0.5 * (qv.max() + qv.min())
        zoom = [int(max(cx - hx, 0)), int(max(cy - hy, 0)), int(min(cx + hx, 1400)), int(min(cy + hy, 1013))]
    return dict(wide=wide, zoom=zoom, place_width_share=float(pw / max(wide[2] - wide[0], 1)))


def camera_for(kind, site, prior, place, Q, photo_view, normal=None, long_axis=False, force_virtual=False, margin_m=None):
    V = P0.views(); k = P0.vname(photo_view); C = V.C(k)
    X = Q.reshape(-1, 3); c = X.mean(0)
    size = float(np.max(X.max(0) - X.min(0)))
    margin = max(0.5 * size, 2.0) if margin_m is None else float(margin_m)
    d = c - C; d /= np.linalg.norm(d)
    oblique = False
    if kind == "roof":
        ang = float(np.degrees(np.arccos(np.clip(-d[2], -1, 1))))
        oblique = 20.0 <= ang <= 60.0
    else:
        n = np.asarray(normal, np.float64); n[2] = 0; n /= np.linalg.norm(n)
        ang = float(np.degrees(np.arccos(np.clip(-d @ n, -1, 1))))
        oblique = ang <= 60.0
    if oblique and not long_axis and not force_virtual:
        return dict(kind="photo camera", view=photo_view, angle_deg=ang, reason=f"the photo camera sees the place at {ang:.0f} deg (oblique)", margin_m=margin)
    az = np.array([C[0] - c[0], C[1] - c[1], 0.0]); az /= max(np.linalg.norm(az), 1e-9)
    if kind == "roof":
        if long_axis:
            w, vec = np.linalg.eigh(np.cov((X[:, :2] - c[:2]).T))
            a = vec[:, np.argmax(w)]; perp = np.array([-a[1], a[0], 0.0])
            az = perp if perp @ az >= 0 else -perp
        t = np.radians(40.0)
        dirv = np.array([az[0] * np.sin(t), az[1] * np.sin(t), np.cos(t)])
    else:
        n = np.asarray(normal, np.float64); n[2] = 0; n /= np.linalg.norm(n)
        side = np.sign(np.cross(n, az)[2]) or 1.0
        t = np.radians(30.0 * side)
        dirv = np.array([n[0] * np.cos(t) - n[1] * np.sin(t), n[0] * np.sin(t) + n[1] * np.cos(t), 0.0])
    dist = max(3.0 * (size + 2 * margin), 30.0)
    eye = c + dist * dirv
    return dict(kind="virtual perspective", eye=eye.tolist(), target=c.tolist(), up=[0, 0, 1], margin_m=margin, fill=0.7,
                reason=("the request: a fixed virtual view; " if force_virtual else ("the photo camera sees the place at %.0f deg, not oblique; " % ang if not long_axis else "the request: the whole roof, long side across; "))
                + ("roof 40 deg from vertical" if kind == "roof" else "wall 30 deg from the normal"), angle_photo_deg=ang)


def depth_view_most(site, prior, place):
    best = None
    for v in P0.train_views(site):
        lm = np.load(S0 / "s61/export" / site / prior / "locmap" / f"{v}.npy")
        m = np.isin(lm, place)
        if not m.any():
            continue
        dep = np.load(S0 / "fork_inputs/s61" / site / "maps/mvs" / f"{v}.npy")
        n = int((m & np.isfinite(dep)).sum())
        if best is None or n > best["depth_pixels"]:
            best = dict(view=v, depth_pixels=n, place_pixels=int(m.sum()), share=float(n / m.sum()))
    return best


def main():
    out = dict(made=now(), scientific_verdict=None, note="결과 파일을 열지 않고 고름")
    # V1
    p = V3P["V1"]; site, prior = p["site"], p["prior"]; U = P0.store(site, prior)
    pl = np.asarray(p["piece_patches"], int); Q = VF.quads(U, pl)
    _, bpts = building_box(site, prior, pl)
    out["V1"] = dict(site=site, prior=prior, place=pl.tolist(), photo=p["photo"]["view"], crops=dict(wide=p["crop_native"], zoom=None), camera=dict(kind="v3 camera", view=p["photo"]["view"], crop_native=p["crop_native"], scale=p["scale"]),
                     zoom=p["zoom"], depth_view=depth_view_most(site, prior, pl), rule="v3 photo, camera and crop (request 6.3)")
    log("V1", out["V1"]["depth_view"])
    # V2
    p = V3P["V2"]; site, prior = p["site"], p["prior"]
    R = P0.region(site, prior); se = R["surf_ext"].astype(int); face = np.nonzero(R["in_eval"].astype(bool) & (se == p["face"]))[0]
    bb, bpts = building_box(site, prior, face)
    rows = choose_photo(site, prior, face, bpts, need_visible=False)
    out["V2"] = dict(site=site, prior=prior, face=p["face"], frame=p["frame"], camera=dict(p["left_camera"], kind="v3 left perspective"), building_box=bb,
                     photo=rows[0]["view"], photo_candidates=rows[:5], crops=photo_crops(rows[0]["view"], bpts, VF.quads(P0.store(site, prior), face)))
    log("V2", rows[0])
    # V3, V5, V6 roofs; V4 wall
    specs = [("V3", "B173nb_b10", "ALS", np.asarray(V3P["V3"]["patches"], int), "roof", True, V3P["V3"]["view"]),
             ("V5", "B173nb_b10", "ALS", np.asarray(V3P["V5"]["patches"], int), "roof", False, V3P["V5"]["view"]),
             ("V6", "B173nb_b10", "ALS", np.asarray(PF1["fig1"]["case_patches"] + PF1["fig2"]["missing_patches"], int), "roof", False, PF1["fig1"]["photo_vertical"]["view"])]
    for key, site, prior, pl, kind, la, dview in specs:
        U = P0.store(site, prior); Q = VF.quads(U, pl)
        bb, bpts = building_box(site, prior, pl)
        rows = choose_photo(site, prior, pl, bpts, need_visible=(key != "V3"), oblique_only=(key == "V3"))   # request 6.3 V3: an oblique photo, the whole roof need not be in
        ph = rows[0]["view"] if rows else dview
        cam = camera_for(kind, site, prior, pl, Q, ph, long_axis=la, margin_m=2.0 if key == "V5" else None)
        out[key] = dict(site=site, prior=prior, place=pl.tolist(), building_box=bb, photo=ph, photo_candidates=rows[:5], crops=photo_crops(ph, bpts, Q), camera=cam, depth_view=dict(view=dview))
        if key == "V6":
            out[key]["glass"] = PF1["fig1"]["case_patches"]; out[key]["ring_missing"] = PF1["fig2"]["missing_patches"]
        log(key, ph, cam["kind"], cam.get("reason"))
    p = V3P["V4"]; site, prior = p["site"], p["prior"]
    R = P0.region(site, prior); U = P0.store(site, prior)
    se = R["surf_ext"].astype(int); ev = R["in_eval"].astype(bool); code = R["code_ext_v3"].astype(int)
    mp = np.nonzero(ev & (se == p["ext"]) & np.isin(code, [4, 13]))[0]; Q = VF.quads(U, mp)
    bb, bpts = building_box(site, prior, mp)
    ph = p["photo"]
    cam = camera_for("wall", site, prior, mp, Q, ph, normal=p["outward_normal"], force_virtual=True, margin_m=2.0)
    cr = photo_crops(ph, bpts, Q); cr["wide"] = [0, 0, 1400, 1013]; cr["rule"] = "request 6.3 V4: the whole image"
    out["V4"] = dict(site=site, prior=prior, place=mp.tolist(), ext=p["ext"], outward_normal=p["outward_normal"], building_box=bb, photo=ph, crops=cr, camera=cam)
    log("V4", out["V4"]["camera"].get("kind"), out["V4"]["crops"])
    jdump(VC / "prep/places.json", out)


if __name__ == "__main__":
    main()
