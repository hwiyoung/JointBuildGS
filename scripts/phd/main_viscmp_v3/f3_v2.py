"""PHD-MAIN-VISCMP-v3 V2 (상속, request 4 V2) = v2's v2_unseen.py with: the CDGS panel (cdgsnofit_LoD2_s0's virtual-view mesh), the empty
background light blue-grey in every panel, and the left panel = the LoD2 prior (the distance metric's samepath mesh of B173 주변) seen in
perspective from outside face 53 and above (config places.V2.left_camera), face 53's frame as one yellow rectangle. Panels = the
virtual-view meshes the fill task's virtual component counted the wall on, face 53 seen from outside along its outward normal
(orthographic, 0.025 m rays averaged 2 x 2). One row ('결과 면'); the strips are laid out two per line.
  python f3_v2.py -> /docs/figures/V2_unseen_B173nb_LoD2.png (300 dpi) | .pdf | .json   scientific_verdict: null"""
import time

import numpy as np
from matplotlib import colors

import vc_common  # noqa: F401
import pf_geo as G
import vc_render as RD
from vc_common import CFG, DOCS, jdump, jl, log, mesh_path, now, res_name, virtual_mesh

KEY, SS = "V2", 2


def to_rgb(g, hit, bg):
    img = np.repeat(g[..., None], 3, -1)
    img[~hit] = bg
    return img


def down3(img, f):
    return np.stack([RD.down(img[..., k], f) for k in range(3)], -1)


def main():
    t0 = time.time()
    C = jl(CFG); P = C["places"][KEY]; F = C["figures"][KEY]; D = C["draw"]
    site, prior = F["site"], F["prior"]
    bg = np.array(colors.to_rgb(D["v2_background"]))
    cd = P["camera"]
    cam = RD.Ortho(cd["centre"], cd["right"], cd["up"], cd["toward_viewer"], cd["s_range"], cd["h_range"], cd["pixel"] / SS)
    c, r, n = (np.asarray(cd[k], np.float64) for k in ("centre", "right", "toward_viewer"))
    sr, hr = cd["s_range"], cd["h_range"]; pad, nh = P["slab"]["pad_m"], P["slab"]["normal_half_m"]

    def keep(V):
        d = V - c
        s, h, dn = d @ r, d[:, 2], d @ n
        return (np.abs(dn) <= nh) & (s >= sr[0] - pad) & (s <= sr[1] + pad) & (h >= hr[0] - pad) & (h <= hr[1] + pad)
    corners = np.array([c + a * r + b * np.array([0, 0, 1.0]) for a in (sr[0] - pad, sr[1] + pad) for b in (hr[0], hr[1])])
    box = [float(corners[:, 0].min()), float(corners[:, 1].min()), float(corners[:, 0].max()), float(corners[:, 1].max())]
    imgs, rec = {}, {}
    for m in F["inputs"] + F["methods"]:
        res = res_name(m, prior)
        path, wall = virtual_mesh(site, prior, res)
        if path is None:
            rec[m] = dict(result=res, status="결과 없음"); log("no result", m, res); continue
        V, Fc, info = RD.load_mesh(path, box, margin=0.5, keep=keep)
        t, nn, Dd = RD.raycast(V, Fc, cam)
        g, hit = RD.shade(t, nn, Dd)
        imgs[m] = down3(to_rgb(g, hit, bg), SS)
        rec[m] = dict(result=res, status="ok", mesh=str(path), mesh_info=info, hit_share=float(hit.mean()), wall=wall)
        log(m, res, (wall or {}).get("share"))
    _, w1 = virtual_mesh(site, prior, res_name("본 방법 씨앗 1", prior))
    rec["본 방법 씨앗 1"] = dict(result=res_name("본 방법 씨앗 1", prior), wall=w1)
    # left panel: the LoD2 prior in perspective, face 53's frame in yellow
    lc = P["left_camera"]
    frame = np.array([c + a * r + b * np.array([0, 0, 1.0]) for a, b in ((sr[0], hr[0]), (sr[1], hr[0]), (sr[1], hr[1]), (sr[0], hr[1]))])
    lcam_hi = RD.LookAt(lc["eye"], lc["target"], lc["up"], frame, [lc["size"][0] * SS, lc["size"][1] * SS], margin=lc["margin"])
    lcam = RD.LookAt(lc["eye"], lc["target"], lc["up"], frame, lc["size"], margin=lc["margin"])
    # [그리는 법만 바꿈, 첫 그림 뒤] the LoD2 faces themselves (pf_geo.prior_mesh): the samepath metric mesh is the training-view TSDF of the
    # prior and has no face 53, which no training view saw
    pm = "pf_geo.prior_mesh(B173nb_b10, LoD2) (LoD2 faces)"
    eye = np.asarray(lc["eye"])
    lb = [float(min(eye[0], frame[:, 0].min()) - 40), float(min(eye[1], frame[:, 1].min()) - 40), float(max(eye[0], frame[:, 0].max()) + 40), float(max(eye[1], frame[:, 1].max()) + 40)]
    Vl, Fl = G.prior_mesh(site, prior); kv = (Vl[:, 0] >= lb[0]) & (Vl[:, 0] <= lb[2]) & (Vl[:, 1] >= lb[1]) & (Vl[:, 1] <= lb[3]); Fl = Fl[kv[Fl].any(1)]
    linfo = dict(faces=int(len(Fl)))
    t, nn, Dd = RD.raycast(Vl, Fl, lcam_hi)
    g, hit = RD.shade(t, nn, Dd)
    left = down3(to_rgb(g, hit, bg), SS)
    fu, fv, _ = lcam.project(frame)
    # draw
    plt = G.setup_plt(); plt.rcParams.update({"font.size": D["font_size"]})
    sw = 7.2; sh = sw * imgs[next(iter(imgs))].shape[0] / imgs[next(iter(imgs))].shape[1]
    lay = [["left", "학습 전 사전 정보"], ["2DGS", "GeoGS"], ["결합", "CDGS"], ["본 방법", None]]
    fig = plt.figure(figsize=(2 * sw + 0.6, 4 * (sh + 0.55) + 1.3))
    gs = fig.add_gridspec(4, 2, height_ratios=[max(sh, 2.6), sh, sh, sh], wspace=0.05, hspace=0.42, left=0.02, right=0.98, top=0.89, bottom=0.06)
    for i, row in enumerate(lay):
        for j, m in enumerate(row):
            ax = fig.add_subplot(gs[i, j]); ax.set_xticks([]); ax.set_yticks([])
            if m is None:
                ax.axis("off"); continue
            if m == "left":
                ax.imshow(left, interpolation="bilinear"); ax.plot(np.append(fu, fu[0]), np.append(fv, fv[0]), color="#ffd400", lw=1.6)
                ax.set_title("학습 전 사전 정보(LoD2), 면 53 바깥 위에서", fontsize=D["font_size"] + 1)
                ax.text(0.5, -0.04, "노란 테두리 = 면 53", transform=ax.transAxes, ha="center", va="top", fontsize=D["font_size"]); continue
            ax.set_title(m, fontsize=D["font_size"] + 2)
            if m not in imgs:
                ax.text(0.5, 0.5, "결과 없음", transform=ax.transAxes, ha="center", va="center"); continue
            ax.imshow(imgs[m], interpolation="nearest")
            w = rec[m]["wall"] or {}
            ax.text(0.5, -0.05, f"벽이 선 몫 {100 * w.get('share', float('nan')):.1f} %", transform=ax.transAxes, ha="center", va="top", fontsize=D["font_size"] + 2)
    y1 = gs[0, 1].get_position(fig).y1 + 0.03; y2 = gs[1, 0].get_position(fig).y1 + 0.028
    fig.text(gs[0, 1].get_position(fig).x0, y1, "입력", ha="left", fontsize=D["font_size"] + 3)
    ysep = 0.5 * (gs[0, 0].get_position(fig).y0 + gs[1, 0].get_position(fig).y1)
    fig.text(0.02, ysep - 0.004, "결과", ha="left", va="top", fontsize=D["font_size"] + 3)
    fig.add_artist(plt.Line2D([0.02, 0.98], [ysep, ysep], color="#666666", lw=0.6, transform=fig.transFigure))
    fig.suptitle(F["title"], fontsize=D["title_size"] + 2, y=0.975)
    fig.text(0.5, 0.024, F["foot"] + ". " + D["cdgs_note"] + ".", ha="center", fontsize=D["font_size"] + 1)
    fig.text(0.5, 0.008, f"칸 = 가상 시점 메시를 벽 바깥 정면에서 평행 광선으로 렌더(0.05 m 화소), 청회색 = 면 없음, 벽이 선 몫 = 맞음으로 미룬 "
             f"{(rec['본 방법']['wall'] or {}).get('patches', 0):,}패치에서 셈(빈칸 채우기 virtual 구성 요소의 값)", ha="center", fontsize=D["font_size"])
    for e in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"{F['file']}.{e}", dpi=D["dpi"])
    plt.close(fig)
    out = dict(key=KEY, title=F["title"], site=site, prior=prior, face=P["face"], camera=cam.record(), left_camera=lcam.record(), left_mesh=str(pm), left_mesh_info=linfo,
               panels=rec, supersample=SS, seconds=round(time.time() - t0, 1), made=now(), scientific_verdict=None)
    jdump(DOCS / "figures" / f"{F['file']}.json", out)
    log("done", out["seconds"])


if __name__ == "__main__":
    main()
