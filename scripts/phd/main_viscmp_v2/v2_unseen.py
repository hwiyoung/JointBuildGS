"""PHD-MAIN-VISCMP-v2 V2 (상속, 영상이 보지 못한 곳): B173 주변 LoD2 face 53 seen from outside along its outward normal (orthographic,
0.05 m pixels). Every panel = the virtual-view mesh the fill task's virtual component counted the wall on (the metric TSDF of the training
views has no surface on a wall no training image saw), cut to the wall-flag counting slab (|n| <= 1.5 m, s and z +- 1.5 m), one grey, a
headlight. The face's unseen patches ('맞음으로 미룸', 14,970) are outlined by one thin grey line in every panel. Photo = the nearest
training camera, the wall rectangle projected as one frame. Values = the virtual component's wall.share (SL/work/virtual/metrics).
  python v2_unseen.py -> /docs/figures/V2_unseen_B173nb_LoD2.png|pdf|json   scientific_verdict: null"""
import time

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, binary_fill_holes

import vc_common as VCm
from vc_common import CFG, DENSE_IMG, DOCS, S1, jdump, jl, log, now, res_name, virtual_mesh
import vc_render as RD
import pf_geo as G

KEY = "V2"


def main():
    t0 = time.time()
    C = jl(CFG); P = C["places"][KEY]; F = C["figures"][KEY]
    site, prior = P["site"], P["prior"]
    cd = P["camera"]
    SS = 2                                                   # [그리는 법만 바꿈, 첫 그림 뒤] 2 x 2 supersampling
    cam = RD.Ortho(cd["centre"], cd["right"], cd["up"], cd["toward_viewer"], cd["s_range"], cd["h_range"], cd["pixel"] / SS)
    c, r, n = (np.asarray(cd[k], np.float64) for k in ("centre", "right", "toward_viewer"))
    sr, hr = cd["s_range"], cd["h_range"]; pad, nh = P["slab"]["pad_m"], P["slab"]["normal_half_m"]

    def keep(V):
        d = V - c
        s, h, dn = d @ r, d[:, 2], d @ n
        return (np.abs(dn) <= nh) & (s >= sr[0] - pad) & (s <= sr[1] + pad) & (h >= hr[0] - pad) & (h <= hr[1] + pad)
    corners = np.array([c + a * r + b * np.array([0, 0, 1.0]) for a in (sr[0] - pad, sr[1] + pad) for b in (hr[0], hr[1])])
    box = [float(corners[:, 0].min()), float(corners[:, 1].min()), float(corners[:, 0].max()), float(corners[:, 1].max())]
    # the unseen patches of the face, outlined
    un = np.load(S1 / "defs" / site / "unseen.npz")
    fm = un["surf_ext"] == P["face"]                         # [그리는 법만 바꿈, 첫 그림 뒤] the whole face (the counted-only outline drew the excluded patches as a diagonal pattern)
    fm0 = fm & (un["label_inferred"] == 0)
    pu, pv, _ = cam.project(un["centre"][fm].astype(np.float64))
    occ = np.zeros((cam.H, cam.W), bool)
    ok = (pu >= 0) & (pu < cam.W) & (pv >= 0) & (pv < cam.H)
    occ[np.floor(pv[ok]).astype(int), np.floor(pu[ok]).astype(int)] = True
    occ = binary_fill_holes(binary_dilation(occ, iterations=8))
    occ = RD.down(occ.astype(float), SS) > 0.5
    imgs, rec = {}, {}
    for m in F["panels"][1:]:
        res = res_name(m, prior)
        path, wall = virtual_mesh(site, prior, res)
        if path is None:
            rec[m] = dict(result=res, status="결과 없음"); log("no result", m, res); continue
        V, Fc, info = RD.load_mesh(path, box, margin=0.5, keep=keep)
        t, nn, D = RD.raycast(V, Fc, cam)
        g, hit = RD.shade(t, nn, D)
        imgs[m] = RD.down(g, SS); hit = RD.down(hit.astype(float), SS) > 0.5
        rec[m] = dict(result=res, status="ok", mesh=str(path), mesh_info=info, hit_share_of_image=float(hit.mean()),
                      hit_share_in_outline=float(hit[occ].mean()), wall=wall)
        log(m, res, info.get("kept_faces_after_place_cut"), rec[m]["hit_share_in_outline"], (wall or {}).get("share"))
    extra = {}
    for nm, res in (("본 방법 씨앗 1", res_name("본 방법 씨앗 1", prior)), ("CDGS", f"cdgsnofit_{prior}_s0")):
        _, w = virtual_mesh(site, prior, res)
        extra[nm] = dict(result=res, wall=w)
    # photo
    pv_ = P["photo"]["view"]
    pc = RD.Pinhole(pv_, (0, 0, 1400, 1013), 1)
    wc = np.array([c + a * r + b * np.array([0, 0, 1.0]) for a, b in ((sr[0], hr[0]), (sr[1], hr[0]), (sr[1], hr[1]), (sr[0], hr[1]))])
    qu, qv, qz = pc.project(wc)
    photo = np.asarray(Image.open(DENSE_IMG / f"{pc.k if pc.k.endswith('.JPG') else pc.k + '.JPG'}").convert("RGB"))
    x0, x1 = np.clip([qu.min(), qu.max()], 0, 1400); y0, y1 = np.clip([qv.min(), qv.max()], 0, 1013)
    cx_, cy_ = 0.5 * (x0 + x1), 0.5 * (y0 + y1)              # [그리는 법만 바꿈, 첫 그림 뒤] at least a 400 px square (the wall is edge-on in this view)
    hx, hy = max(0.6 * (x1 - x0), 200), max(0.6 * (y1 - y0), 200)
    x0, x1, y0, y1 = int(max(cx_ - hx, 0)), int(min(cx_ + hx, 1400)), int(max(cy_ - hy, 0)), int(min(cy_ + hy, 1013))
    # draw
    plt = G.setup_plt()
    aspect = imgs[next(iter(imgs))].shape[0] / imgs[next(iter(imgs))].shape[1]
    cw = 8.0
    fig, axs = plt.subplots(3, 2, figsize=(2 * cw + 0.6, 3 * (cw * aspect + 0.9) + 1.0))
    fig.subplots_adjust(left=0.02, right=0.98, top=0.90, bottom=0.07, wspace=0.04, hspace=0.42)
    order = F["panels"]
    for ax, m in zip(axs.ravel(), order):
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(m, fontsize=13)
        if m == "사진":
            ax.imshow(photo[y0:y1, x0:x1], extent=(x0, x1, y1, y0))
            poly = np.column_stack([np.append(qu, qu[0]), np.append(qv, qv[0])])
            ax.plot(poly[:, 0], poly[:, 1], color="#ffd400", lw=2.0)
            ax.set_xlim(x0, x1); ax.set_ylim(y1, y0)
            ax.text(0.5, -0.08, f"영상 {pv_} · 노란 테두리 = 면 {P['face']}(이 영상에서 보이지 않음)", transform=ax.transAxes, ha="center", va="top", fontsize=10)
            continue
        if m not in imgs:
            ax.text(0.5, 0.5, "결과 없음", transform=ax.transAxes, ha="center", va="center", fontsize=14); continue
        ax.imshow(imgs[m], cmap="gray", vmin=0, vmax=1, interpolation="nearest")
        # [그리는 법만 바꿈, 둘째 그림 뒤] no outline: the face patch set itself is a diagonal checkerboard on the left (the 바둑판 무늬), the panel = the face range
        w = rec[m]["wall"] or {}
        ax.text(0.5, -0.08, f"벽이 선 몫 {100 * w.get('share', float('nan')):.1f} % ({w.get('present', 0):,} / {w.get('patches', 0):,}패치)",
                transform=ax.transAxes, ha="center", va="top", fontsize=11)
    fig.suptitle(F["title"], fontsize=15, y=0.975)
    fig.text(0.5, 0.012, F["foot"] + f". 칸 = 가상 시점 메시를 벽 바깥 정면에서 평행 광선으로 렌더(0.05 m 화소), 칸의 범위 = 면 53. 값은 면 53의 맞음으로 미룬 {int(fm0.sum()):,}패치에서 셈(빈칸 채우기 virtual 구성 요소).",
             ha="center", fontsize=10)
    for ext in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"V2_unseen_B173nb_LoD2.{ext}", dpi=130)
    plt.close(fig)
    out = dict(key=KEY, title=F["title"], site=site, prior=prior, face=P["face"], camera=cam.record(), photo=dict(view=pv_, crop_native=[x0, y0, x1, y1], camera=pc.record()),
               panels=rec, extra=extra, outline_patches=int(fm.sum()), counted_patches=int(fm0.sum()), supersample=SS, seconds=round(time.time() - t0, 1), made=now(), scientific_verdict=None)
    jdump(DOCS / "figures" / "V2_unseen_B173nb_LoD2.json", out)
    log("done", out["seconds"])


if __name__ == "__main__":
    main()
