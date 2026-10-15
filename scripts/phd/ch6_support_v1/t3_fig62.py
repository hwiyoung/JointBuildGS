"""PHD-CH6-SUPPORT-v1 task 3, optional figure (candidate 6.2): per region and prior, prior - GT before training on the patches
of the stage-1 region files v3 (-gt_med; vertical on roof-like, along the outward normal on wall-like patches), over the grey
ULS ortho of t3_ortho.py (jointbuildgs:dev, CPU).

  python t3_fig62.py

Writes /out/t3/fig6_2_prior_minus_gt.png (+ .pdf). Colour scale clipped at +-1 m for both priors (tau marks on the colour bar).
scientific_verdict: null."""
import numpy as np

from ch6_common import BOXDEF, OUT, S1, setup_fonts, xy_to_uv

O = OUT / "t3"
BOXES = [("B0_b10", "B0", 10.0, "B0"), ("B173nb_b10", "B173nb", 10.0, "B173 주변"), ("B173_b0", "B173", 0.0, "B173만"), ("R1rep_b10", "R1rep", 10.0, "R1")]
CLIP = 1.0


def paint_val(shape, u0, v0, res, uv, area, val):
    H, W = shape
    out = np.full((H, W), np.nan)
    side = np.maximum(np.sqrt(area), 0.3)
    iu = ((uv[:, 0] - u0) / res).astype(np.int64); iv = ((uv[:, 1] - v0) / res).astype(np.int64)
    kk = np.ceil(side / res / 2).astype(np.int64); k = int(kk.max()) if len(kk) else 0
    order = np.argsort(np.abs(val))                  # larger |value| painted last (on top)
    iu, iv, kk, val = iu[order], iv[order], kk[order], val[order]
    for du in range(-k, k + 1):
        for dv in range(-k, k + 1):
            ok = (abs(du) <= kk) & (abs(dv) <= kk)
            a = np.clip(iu[ok] + du, 0, W - 1); b = np.clip(iv[ok] + dv, 0, H - 1)
            out[b, a] = val[ok]
    return out


def main():
    plt = setup_fonts()
    import matplotlib.colors as mcolors
    fig, axs = plt.subplots(4, 2, figsize=(10.5, 13.5), constrained_layout=True)
    norm = mcolors.TwoSlopeNorm(vmin=-CLIP, vcenter=0.0, vmax=CLIP)
    cmap = plt.get_cmap("RdBu_r").copy(); cmap.set_bad(alpha=0)
    for row, (box, bid, band, name) in enumerate(BOXES):
        R = np.load(O / f"ortho_{box}.npz")
        rgb = R["rgb"]; u0, v0, res = float(R["u0"]), float(R["v0"]), float(R["res"])
        H, W = rgb.shape[:2]
        grey = rgb.mean(-1)
        for col, prior in enumerate(("LoD2", "ALS")):
            ax = axs[row, col]
            G = np.load(S1 / "regions_v3" / f"regions_ext_v3_{box}_{prior}.npz")
            m = G["in_eval"].astype(bool) & (G["code_ext_v3"] > 0) & np.isfinite(G["gt_med"])
            uv = xy_to_uv(G["centre"][m][:, :2])
            val = -G["gt_med"][m].astype(np.float64)
            img = paint_val((H, W), u0, v0, res, uv, G["area"][m].astype(np.float64), val)
            ax.imshow(grey, origin="lower", extent=[u0, u0 + W * res, v0, v0 + H * res], cmap="gray", vmin=0, vmax=255, interpolation="bilinear")
            im = ax.imshow(np.clip(img, -CLIP, CLIP), origin="lower", extent=[u0, u0 + W * res, v0, v0 + H * res], cmap=cmap, norm=norm, interpolation="nearest")
            b = BOXDEF[bid]
            r = np.array([[b["eval_u"][0], b["eval_v"][0]], [b["eval_u"][1], b["eval_v"][0]], [b["eval_u"][1], b["eval_v"][1]], [b["eval_u"][0], b["eval_v"][1]], [b["eval_u"][0], b["eval_v"][0]]])
            ax.plot(r[:, 0], r[:, 1], "k-", lw=1.0)
            ax.set_xlim(u0, u0 + W * res); ax.set_ylim(v0, v0 + H * res); ax.invert_yaxis(); ax.set_aspect("equal")
            ax.set_xticks([]); ax.set_yticks([])
            tau_r = float(np.median(G["tau"][G["kind"] == 1]))
            big = np.abs(val) > CLIP
            ax.set_title(f"{name} · {'LoD2' if prior == 'LoD2' else '항공 LiDAR'} (지붕 τ = {tau_r:.2f} m, 1 m 넘는 패치 {100 * G['area'][m][big].sum() / max(G['area'][m].sum(), 1e-9):.0f} %)",
                         fontsize=9, loc="left")
    cb = fig.colorbar(im, ax=axs, shrink=0.35, location="bottom", pad=0.01, aspect=40)
    cb.set_label("학습 전 사전 정보 − 참값 (m; 지붕은 높이, 벽은 바깥 방향 거리; ±1 m에서 자름)")
    fig.savefig(O / "fig6_2_prior_minus_gt.png", dpi=220); fig.savefig(O / "fig6_2_prior_minus_gt.pdf"); plt.close(fig)
    print("fig 6.2 candidate written")


if __name__ == "__main__":
    main()
