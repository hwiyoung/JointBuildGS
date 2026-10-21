"""PHD-MAIN-VISCMP-v4 일 가 V2 (상속, request 6.3 V2): no GT, so one plate of grey shaded surfaces.
  입력  자리 = the training image 0146 (prep: the most of the building), face 53's top edge as a yellow line (the wall itself is not seen);
        LoD2 원근 렌더 = v3's left panel (the LoD2 faces, pf_geo.prior_mesh, face 53's frame in yellow); 학습 전 사전 정보 = its
        virtual-view mesh
  결과  2DGS, GeoGS, 결합, CDGS (cdgsnofit_LoD2_s0), 본 방법: the virtual-view meshes (the fill task's virtual component)
every render panel = the v3 left eye (wall centre + 70 m outward + 45 m up, perspective), the meshes in face 53's frame box + 40 m (no
slab cut behind the wall: where a method has no wall the faces behind it show; faces > 1.5 m in front of it are not drawn), the v3 headlight, empty = the blue-grey background, face 53's frame dashed.
Under each panel: 벽이 선 몫 (the fill task's virtual wall share, 0.25 m).  A blind copy goes to /vc/work.
  python f4_v2.py   scientific_verdict: null"""
import time

import numpy as np
from matplotlib import colors

import vc_common  # noqa: F401
import pf_geo as G
import vc_fig as VF
import vc_render as RD
from vc_common import CFG, DOCS, VC, jdump, jl, log, now, res_name, virtual_mesh

KEY, SS, PW, FILE = "V2", 2, 700, "V2_unseen_B173nb_LoD2"
PLACES = CFG.parent / "places_v4.json"
CHECK = {"학습 전 사전 정보": 100.0, "2DGS": 22.8, "GeoGS": 22.3, "결합": 10.5, "CDGS": 19.8, "본 방법": 92.0}
FOOT = "이 벽은 학습 영상에 보이지 않았고 참값도 없어, 세운 벽이 실제 벽 자리인지는 알 수 없다"


def rgb_of(V, F, cam, bg):
    t, n, D = RD.raycast(V, F, cam)
    g, hit = RD.shade(t, n, D)
    img = np.repeat(g[..., None], 3, -1); img[~hit] = bg
    return np.stack([RD.down(img[..., k], SS) for k in range(3)], -1), float(hit.mean())


def main():
    t0 = time.time()
    C = jl(CFG); W = C["work_ga"]; P = jl(PLACES)[KEY]
    site, prior = P["site"], P["prior"]; fr = P["frame"]; lc = P["camera"]
    bg = np.array(colors.to_rgb(W["background"]))
    c, n = np.asarray(fr["centre"], np.float64), np.asarray(fr["normal"], np.float64)
    r = np.cross(-n, [0.0, 0.0, 1.0]); r /= np.linalg.norm(r)
    sr, hr = lc["frame_s"], lc["frame_h"]; z = np.array([0, 0, 1.0])
    frame = np.array([c + a * r + b * z for a, b in ((sr[0], hr[0]), (sr[1], hr[0]), (sr[1], hr[1]), (sr[0], hr[1]))])
    asp = lc["size"][1] / lc["size"][0]; H = int(round(PW * asp))
    cam_hi = RD.LookAt(lc["eye"], lc["target"], lc["up"], frame, [PW * SS, H * SS], margin=lc["margin"])
    cam = RD.LookAt(lc["eye"], lc["target"], lc["up"], frame, [PW, H], margin=lc["margin"])
    box = [float(frame[:, 0].min() - 40), float(frame[:, 1].min() - 40), float(frame[:, 0].max() + 40), float(frame[:, 1].max() + 40)]
    # [그리는 법만 바꿈, 첫 그림 뒤 10-21 16:06] the street, cars and trees in front of the wall (within the 40 m box) hid the wall in every
    # result panel: faces more than 1.5 m outside the wall plane (the fill task's slab half width) toward the camera are not drawn; the wall
    # and everything behind it are kept (request: where there is no wall the faces behind it show)
    behind = lambda X: ((X - c) @ n) <= 1.5  # noqa: E731
    imgs, rec = {}, {}
    Vl, Fl = G.prior_mesh(site, prior)
    kv = (Vl[:, 0] >= box[0]) & (Vl[:, 0] <= box[2]) & (Vl[:, 1] >= box[1]) & (Vl[:, 1] <= box[3]); Fl = Fl[kv[Fl].any(1)]
    imgs["LoD2 원근 렌더"], hs = rgb_of(Vl, Fl, cam_hi, bg)
    rec["LoD2 원근 렌더"] = dict(result="pf_geo.prior_mesh(B173nb_b10, LoD2) (the LoD2 faces; v3 left panel)", faces=int(len(Fl)), hit_share=hs)
    for m in ["학습 전 사전 정보"] + list(W["panels_bottom"]):
        res = res_name(m, prior)
        path, wall = virtual_mesh(site, prior, res)
        if path is None:
            rec[m] = dict(result=res, status="결과 없음"); log("no result", m, res); continue
        V, F, info = RD.load_mesh(path, box, margin=0.0, keep=behind)
        imgs[m], hs = rgb_of(V, F, cam_hi, bg)
        share = None if not wall else 100 * float(wall.get("share"))
        rec[m] = dict(result=res, status="ok", mesh=str(path), mesh_info=info, hit_share=hs, wall=wall, wall_share_pct=share,
                      check_v3_pct=CHECK.get(m), diff_pct=None if share is None or CHECK.get(m) is None else share - CHECK[m])
        log(m, res, share, CHECK.get(m))
    _, w1 = virtual_mesh(site, prior, res_name("본 방법 씨앗 1", prior))
    rec["본 방법 씨앗 1"] = dict(result=res_name("본 방법 씨앗 1", prior), wall=w1, wall_share_pct=None if not w1 else 100 * float(w1.get("share")))
    # the photo: face 53's top edge
    pv = P["photo"]; pc = RD.Pinhole(pv, (0, 0, 1400, 1013), 1)
    eu, ev, ez = pc.project(np.array([frame[3], frame[2]]))
    photo = VF.photo(pv, [0, 0, 1400, 1013])
    fu, fv, _ = cam.project(frame)
    ctx = dict(imgs=imgs, rec=rec, photo=photo, edge=(eu.tolist(), ev.tolist(), ez.tolist()), fu=fu, fv=fv, cam_wh=(cam.W, cam.H), wide=P["crops"]["wide"],
               camera=cam.record(), box=box, t0=t0, P={k: v for k, v in P.items()})
    draw(ctx, W, blind=False)
    draw(ctx, W, blind=True)


def fit_crop(box, aspect, W=1400, H=1013):
    x0, y0, x1, y1 = (float(b) for b in box); w, h = x1 - x0, y1 - y0
    if h / w < aspect:
        h = w * aspect
    else:
        w = h / aspect
    w, h = min(w, W), min(h, H)
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    a = min(max(cx - w / 2, 0), W - w); b = min(max(cy - h / 2, 0), H - h)
    return [a, b, a + w, b + h]


def draw(ctx, W, blind):
    plt = G.setup_plt()
    from matplotlib.lines import Line2D
    fs = 6.5
    plt.rcParams.update({"font.size": fs})
    Wc, Hc = ctx["cam_wh"]; rec = ctx["rec"]
    top = ["자리", "LoD2 원근 렌더", "학습 전 사전 정보"]; bot = list(W["panels_bottom"])
    ncol = max(len(top), len(bot))
    IN = 2.54; fw = 16 / IN; lab = 0.13; rgt = 0.05
    cw = (fw - lab - rgt) / ncol; ch = cw * Hc / Wc
    head = 0.08 if blind else 0.42; valh = 0.0 if blind else 0.14; gap = 0.2 + valh; foot = 0.1 if blind else 0.34
    fh = head + 0.14 + ch + gap + 0.14 + ch + valh + foot
    ys = [fh - head - 0.14 - ch, fh - head - 0.14 - ch - gap - 0.14 - ch]
    wide = fit_crop(ctx["wide"], Hc / Wc)
    fig = plt.figure(figsize=(fw, fh))
    for rr, row in enumerate((top, bot)):
        for j, m in enumerate(row):
            ax = fig.add_axes([(lab + j * cw + 0.012) / fw, ys[rr] / fh, (cw - 0.024) / fw, ch / fh]); ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_linewidth(0.4)
            ax.set_title(m, fontsize=fs + 0.5, pad=2, weight="bold" if m == "본 방법" else "normal")
            if m == "자리":
                ax.imshow(ctx["photo"], interpolation="bilinear")
                eu, ev, _ = ctx["edge"]; ax.plot(eu, ev, color="#ffd400", lw=1.4)
                ax.set_xlim(wide[0], wide[2]); ax.set_ylim(wide[3], wide[1]); continue
            if m not in ctx["imgs"]:
                ax.text(0.5, 0.5, "결과 없음", transform=ax.transAxes, ha="center", va="center"); continue
            ax.imshow(ctx["imgs"][m], interpolation="nearest")
            fu, fv = ctx["fu"], ctx["fv"]
            if m == "LoD2 원근 렌더":
                ax.plot(np.append(fu, fu[0]), np.append(fv, fv[0]), color="#ffd400", lw=1.2)
            else:
                ax.plot(np.append(fu, fu[0]), np.append(fv, fv[0]), color="#000000", lw=0.8, ls=(0, (4, 2)))
            ax.set_xlim(-0.5, Wc - 0.5); ax.set_ylim(Hc - 0.5, -0.5)
            s = rec[m].get("wall_share_pct") if m in rec else None
            if not blind and s is not None:
                ax.text(0.5, -0.025, f"벽이 선 몫 {s:.1f} %", transform=ax.transAxes, ha="center", va="top", fontsize=fs)
    ysep = (ys[0] - gap * 0.5 - 0.02) / fh
    fig.add_artist(Line2D([0.005, 0.995], [ysep, ysep], color="#888888", lw=0.5))
    fig.text(0.06 / fw, (ys[0] + ch / 2) / fh, "입력", rotation=90, ha="center", va="center", fontsize=fs + 1)
    fig.text(0.06 / fw, (ys[1] + ch / 2) / fh, "결과", rotation=90, ha="center", va="center", fontsize=fs + 1)
    note = "노란 선: 면 53의 윗변(사진) · 노란 테두리, 점선: 면 53 · 청회색 바탕: 결과 면 없음"
    if not blind:
        fig.text(0.5, 1 - 0.07 / fh, W["titles"][KEY], ha="center", va="top", fontsize=fs + 1.3, weight="bold")
        fig.text(0.5, 0.2 / fh, note, ha="center", va="bottom", fontsize=fs - 0.5)
        fig.text(0.5, 0.05 / fh, FOOT + ". " + W["cdgs_note"] + ".", ha="center", va="bottom", fontsize=fs - 0.5)
        (DOCS / "figures/판가").mkdir(parents=True, exist_ok=True)
        for e in ("png", "pdf"):
            fig.savefig(DOCS / "figures/판가" / f"{FILE}.{e}", dpi=300)
    else:
        fig.text(0.5, 0.03 / fh, note, ha="center", va="bottom", fontsize=fs - 0.5)
        fig.savefig(VC / "work" / f"blind_{KEY}_판가.png", dpi=300)
    plt.close(fig)
    if not blind:
        out = dict(task="PHD-MAIN-VISCMP-v4", work="일 가", key=KEY, title=W["titles"][KEY], site="B173nb_b10", prior="LoD2", camera=ctx["camera"], render_box_xy=ctx["box"],
                   photo=dict(view=ctx["P"]["photo"], wide_shown=wide, top_edge_px=ctx["edge"], zoom="not drawn: request 6.3 V2 puts the v3 LoD2 render in the second top panel"),
                   panels=rec, place=dict(face=ctx["P"]["face"], frame=ctx["P"]["frame"]), size=dict(width_cm=16.0, height_cm=round(fh * IN, 2), render_panel_cm=round(cw * IN, 2)),
                   light="vc_render.shade: 0.12 + 0.78 |n . d| (v3)", seconds=round(time.time() - ctx["t0"], 1), made=now(), scientific_verdict=None)
        jdump(DOCS / "figures/판가" / f"{FILE}.json", out)
        log("done", out["seconds"], out["size"])


if __name__ == "__main__":
    main()
