"""PHD-MAIN-STAGE1-v1 3.7: the settings tables promised to chapter 6 and the mask check (jointbuildgs:dev, CPU; records only, the mask
check is the one new computation).

  python settings_s1.py tables     -> /out/settings/settings.json, settings.md
  python settings_s1.py mask <site> -> /out/settings/mask_<site>.json (share of confidence-1 pixels among building-face pixels)
  python settings_s1.py figure     -> /out/figs/mask_check.png (one sample view per site, the mask over the photo)

Building-face pixels: training views of the box MVS (geometric depth map present); the LoD2 mesh of the box (roof and wall faces, caps
left out) ray-cast at the native grid (1024 x 741); a pixel counts when its first hit is a roof or wall face and the hit point lies in the
box evaluation range; confidence 1 = a valid COLMAP geometric depth at the pixel. scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

from s1_common import DR, GRID_H, GRID_W, MF, OUT, PREP, S0, SITES, Views, boxes, in_eval_uv, jdump, log, read_depth_bin, setup_fonts
from common import DENSE
from src.phd.metrics_v3.surface import MeshScene

O = OUT / "settings"


def tables():
    O.mkdir(parents=True, exist_ok=True)
    cs = json.loads((OUT / "v3/align/common_shift.json").read_text())
    pm = (PREP / "mvs/box_B173nb_b10/patch_match.log").read_text(errors="ignore")
    opts = {}
    for line in pm.splitlines():
        if "patch_match_options.cc" in line and ":" in line.split("] ")[-1]:
            k, v = line.split("] ")[-1].split(":", 1)
            opts.setdefault(k.strip(), set()).add(v.strip())
    common = dict(
        orientation=dict(method="the 937 posed images of the TUM2TWIN UAV flight (2024-12-17): camera calibration and poses of the provider's OPF "
                                "(Open Photogrammetry Format, Zenodo record 14899378, CC BY 4.0) converted to COLMAP (p0-audit T2, opf2colmap; "
                                "4,131,648 sparse points), undistorted to PINHOLE 1400 x 1013 (p0-audit colmap_dense)",
                         georeference="OPF projected CRS (WKT EPSG:32632; numerically EPSG:25832), scene-reference shift taken back; local frame = "
                                      "EPSG:25832 minus (690953, 5336071, 604) m (prep config frame)",
                         record="docs/evidence/p0-audit/w1-input-diagnostics/reports/opf2colmap_summary.md (main branch)"),
        mvs=dict(tool="COLMAP 4.0.4, image colmap/colmap@sha256:187ca5ec98e55ed8fbec5f43f9d8f78b7a322b3b7413356634191f7a43c1efcf (GPU)",
                 images="the box's training images only (box_views.json train)", resolution="max_image_size 1024 (1024 x 741)",
                 patch_match={k: sorted(v) for k, v in opts.items() if k in ("geom_consistency", "num_iterations", "window_radius", "num_samples", "filter",
                                                                              "filter_min_num_consistent", "filter_geom_consistency_max_cost", "filter_min_ncc",
                                                                              "filter_min_triangulation_angle", "min_triangulation_angle", "max_image_size")},
                 note="two passes (photometric without the filter, then geometric with the filter); the geometric depth map is the MVS depth"),
        confidence=dict(rule="a pixel is confidence 1 when it has a valid COLMAP geometric depth: at least 2 agreeing views (filter_min_num_consistent 2) "
                             "within 1 px forward-backward reprojection (filter_geom_consistency_max_cost 1), no depth ratio (COLMAP also: NCC >= 0.1, "
                             "triangulation angle >= 3 degrees)"),
        gt_height=dict(common_shift_m=cs["common_shift_m"], method="the four boxes' bare-ground pixels pooled (per-box selection of the gt_clean method: "
                                                                   "up to 40 training views, GT z-buffer with the 9 x 9 leak filter, MVS geometric depth on bare hard "
                                                                   "ground in the box range), median of the vertical MVS - GT difference, two passes",
                       per_box={b: dict(shift_box_m=r["shift_box_m"], common_minus_box_m=r["common_minus_box_m"]) for b, r in cs["boxes"].items()}))
    per_site = {}
    for site in SITES:
        sp = json.loads((S0 / "fork_inputs/s61" / site / "split.json").read_text())
        fi = json.loads((S0 / "fork_inputs/s61" / site / "fork_inputs.json").read_text())
        for prior in ("LoD2", "ALS"):
            sm = json.loads((S0 / "s61/box" / site / prior / "summary.json").read_text())
            fx = json.loads((Path(sm["registration"]["fixed_from"].replace("/dr", str(DR))) / "summary.json").read_text())["registration"]
            sh = sm["registration"]["shift_applied"]
            per_site[f"{site}/{prior}"] = dict(train_views=len(sp["train"]), eval_views=len(sp["test"]), fixed_from=sm["registration"]["fixed_from"],
                                              shift_horizontal_m=[round(sh[0], 4), round(sh[1], 4)], shift_vertical_m=round(sh[2], 4),
                                              horizontal_accepted=fx.get("accepted_horizontal"), vertical_accepted=fx.get("accepted_vertical"),
                                              vertical_median_after_horizontal_m=round(fx.get("median_after_horizontal", float("nan")), 4),
                                              vertical_nmad_m=round(fx.get("nmad_after_horizontal", float("nan")), 4),
                                              tau_roof_m=round(fi[prior]["tau_roof"], 4), tau_wall_m=round(fi[prior]["tau_wall"], 4))
    jdump(O / "settings.json", dict(common=common, per_site=per_site, scientific_verdict=None))
    md = ["| 지역 · 사전 정보 | 학습 · 평가 영상 | 정합 수평 이동 (m) | 연직 이동 | 허용 오차 지붕 · 벽 (m) |", "|---|---|---|---|---|"]
    for k, v in per_site.items():
        hz = "없음" if not v["horizontal_accepted"] else f"({v['shift_horizontal_m'][0]:+.3f}, {v['shift_horizontal_m'][1]:+.3f})"
        vt = f"없음(중앙값 {v['vertical_median_after_horizontal_m']:+.3f} ≤ NMAD {v['vertical_nmad_m']:.3f})" if not v["vertical_accepted"] else f"{v['shift_vertical_m']:+.3f}"
        md.append(f"| {k.replace('/', ' · ')} | {v['train_views']} · {v['eval_views']} | {hz} | {vt} | {v['tau_roof_m']:.3f} · {v['tau_wall_m']:.3f} |")
    (O / "settings.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


class Caster:
    """Open3D ray casting with the hit triangle (MeshScene.cast gives the distance only)."""

    def __init__(self, V, F):
        import open3d as o3d
        self.o3d = o3d
        self.sc = o3d.t.geometry.RaycastingScene()
        self.sc.add_triangles(o3d.core.Tensor(np.ascontiguousarray(V, np.float32)), o3d.core.Tensor(np.ascontiguousarray(F, np.uint32)))

    def cast(self, O, D):
        O = np.asarray(O, np.float32).reshape(-1, 3)
        D = np.broadcast_to(np.asarray(D, np.float32), O.shape)
        ans = self.sc.cast_rays(self.o3d.core.Tensor(np.ascontiguousarray(np.concatenate([O, D], 1))))
        t = ans["t_hit"].numpy()
        tri = ans["primitive_ids"].numpy().astype(np.int64)
        tri[~np.isfinite(t)] = -1
        return t, tri


def lod2_scene(site):
    m = np.load(DR / "s02_box" / site / "lod2_mesh.npz")
    keep = m["tri_type"] != 2
    tab = {r["ext"]: r for r in json.loads((DR / "s02_box" / site / "lod2_surfaces.json").read_text())["surfaces"]}
    ts = m["tri_surface"][keep]
    kind = np.array([tab[int(e)]["kind"] if int(e) in tab else 0 for e in ts])
    return Caster(m["V"], m["F"][keep]), kind


def mask(site):
    O.mkdir(parents=True, exist_ok=True)
    V = Views()
    sc, kind = lod2_scene(site)
    bx = boxes()[SITES[site]]
    sp = json.loads((S0 / "fork_inputs/s61" / site / "split.json").read_text())["train"]
    names = {n.split(".")[0]: n for n in V.ims}
    dm = PREP / "mvs" / f"box_{site}" / "stereo/depth_maps"
    tot = dict(face=0, conf=0, roof=0, roof_conf=0, wall=0, wall_conf=0)
    per = {}
    for v in sp:
        n = names[v]
        f = dm / f"{n}.geometric.bin"
        if not f.exists():
            continue
        C = V.C(n)
        Dr = V.rays(n, np.float64).reshape(-1, 3)
        t, tri = sc.cast(np.broadcast_to(C, Dr.shape), Dr)
        hit = tri >= 0
        X = C[None, :] + np.where(hit, t, 0)[:, None] * Dr
        face = hit & in_eval_uv(X, bx)
        d = read_depth_bin(f).ravel()
        conf = np.isfinite(d) & (d > 0)
        k = np.where(hit, kind[np.maximum(tri, 0)], 0)
        r = dict(face=int(face.sum()), conf=int((face & conf).sum()), roof=int((face & (k == 1)).sum()), roof_conf=int((face & (k == 1) & conf).sum()),
                 wall=int((face & (k == 2)).sum()), wall_conf=int((face & (k == 2) & conf).sum()))
        per[v] = r
        for kk in tot:
            tot[kk] += r[kk]
    share = dict(all=round(tot["conf"] / max(tot["face"], 1), 4), roof=round(tot["roof_conf"] / max(tot["roof"], 1), 4), wall=round(tot["wall_conf"] / max(tot["wall"], 1), 4))
    jdump(O / f"mask_{site}.json", dict(site=site, views=len(per), totals=tot, share_confidence1=share, per_view=per, scientific_verdict=None))
    log(site, "mask check", share, len(per))


def figure():
    plt = setup_fonts()
    import cv2
    V = Views()
    names = {n.split(".")[0]: n for n in V.ims}
    fig, axs = plt.subplots(2, 2, figsize=(16, 12), constrained_layout=True)
    for ax, site in zip(axs.ravel(), SITES):
        # sample view: the nadir (tilt <= 20 degrees) training view whose projection of the centroid of the site's roof-like region
        # patches lies nearest the image centre (the fix's overlay rule, training views only: the evaluation views have no MVS)
        R = np.load(OUT / "regions_v3" / f"regions_ext_v3_{site}_LoD2.npz")
        cen = R["centre"][np.isin(R["code_ext_v3"], (2, 3, 0)) & (R["kind"] == 1) & R["in_eval"]].mean(0)
        best, bd = None, 1e9
        for vv in json.loads((S0 / "fork_inputs/s61" / site / "split.json").read_text())["train"]:
            nn = names.get(vv)
            if nn is None or V.tilt(nn) > 20 or not (PREP / "mvs" / f"box_{site}" / "stereo/depth_maps" / f"{nn}.geometric.bin").exists():
                continue
            u, w_, z = V.project(nn, cen[None, :])
            if z[0] <= 0:
                continue
            dd = np.hypot(u[0] - GRID_W / 2, w_[0] - GRID_H / 2)
            if dd < bd:
                best, bd = vv, dd
        v = best
        n = names[v]
        img = cv2.cvtColor(cv2.resize(cv2.imread(str(DENSE / "images" / n)), (GRID_W, GRID_H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB).astype(float) / 255
        sc, kind = lod2_scene(site)
        C = V.C(n)
        Dr = V.rays(n, np.float64).reshape(-1, 3)
        t, tri = sc.cast(np.broadcast_to(C, Dr.shape), Dr)
        hit = tri >= 0
        X = C[None, :] + np.where(hit, t, 0)[:, None] * Dr
        face = (hit & in_eval_uv(X, boxes()[SITES[site]])).reshape(GRID_H, GRID_W)
        f = PREP / "mvs" / f"box_{site}" / "stereo/depth_maps" / f"{n}.geometric.bin"
        d = read_depth_bin(f) if f.exists() else np.zeros((GRID_H, GRID_W))
        conf = np.isfinite(d) & (d > 0)
        over = img.copy()
        over[face & conf] = 0.55 * over[face & conf] + 0.45 * np.array([0.2, 0.75, 0.2])
        over[face & ~conf] = 0.45 * over[face & ~conf] + 0.55 * np.array([0.9, 0.1, 0.1])
        ax.imshow(over)
        ax.set_xticks([])
        ax.set_yticks([])
        sh = json.loads((O / f"mask_{site}.json").read_text())["share_confidence1"] if (O / f"mask_{site}.json").exists() else {}
        ax.set_title(f"{site} — {v}{'' if f.exists() else ' (학습 영상 아님: 깊이 지도 없음)'}; 지역 전체 신뢰도 1 몫 {sh.get('all', float('nan')):.0%}"
                     f" (지붕 {sh.get('roof', float('nan')):.0%}, 벽 {sh.get('wall', float('nan')):.0%})", fontsize=10)
    fig.suptitle("관측 신뢰도 마스크 확인: 평가 범위 안 LoD2 건물 면 화소 가운데 신뢰도 1(초록)과 0(빨강) — 표본 시점마다", fontsize=13, x=0.01, ha="left")
    fig.savefig(OUT / "figs/mask_check.png", dpi=80, bbox_inches="tight")
    plt.close(fig)
    print("mask figure")


if __name__ == "__main__":
    {"tables": tables, "mask": lambda: mask(sys.argv[2]), "figure": figure}[sys.argv[1]]()
