"""PHD-MAIN-PREP-MEASURE-v1 step 14 (jointbuildgs:dev, CPU): additions for report v1.1 (2026-10-04, after the user's review of v1).

  python step14_v1_1.py coverage-csv     # every coverage_{views,footprints,surfaces}.json (not superseded/) -> .csv beside it
  python step14_v1_1.py case4-fig        # case 4 location maps: invisible patches and the true label of inheriting the prior there
  python step14_v1_1.py agree-check      # where the 'missing -> agree' patches that the true label confirms lie (roof / wall, surfaces)

Why: the order asked for tables as CSV (0) and for a location figure of case 4 (5.4); v1 had JSON coverage tables and no case 4
figure. agree-check re-reads which surfaces carry the confirmed agree propagation, because v1 read one row as a 'grey flat roof'
while its surface is a wall. Nothing here changes a threshold, a rule or a label. Writes step14/. scientific_verdict: null."""
import argparse
import csv
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap
import numpy as np

from common import OUT, jdump, xy_to_uv
from src.phd.prior_propagation_v4 import rule
from step06d_box_cases import in_eval
from step09_maps import raster

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    try:
        font_manager.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

RANGES = ["R1", "R2", "R3", "R3E", "R4", "R5", "SW", "B0"]
BOX_OF = {"B0": "B0_b10", "B173nb": "B173nb_b10", "B173": "B173_b0", "R1rep": "R1rep_b10"}
O = OUT / "step14"


def coverage_csv():
    done = []
    for p in sorted(OUT.rglob("coverage_*.json")):
        if "superseded" in p.parts:
            continue
        d = json.loads(p.read_text())
        if isinstance(d, dict):
            rows = [dict(surface=k, **(v if isinstance(v, dict) else {"value": v})) for k, v in d.items()]
        elif isinstance(d, list) and (not d or isinstance(d[0], dict)):
            rows = d
        else:
            print("skip", p)
            continue
        keys = []
        for r in rows:
            keys += [k for k in r if k not in keys]
        with open(p.with_suffix(".csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in rows:
                w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})
        done.append(str(p.relative_to(OUT).with_suffix(".csv")))
    jdump(O / "coverage_csv.json", dict(files=len(done), written=done, scientific_verdict=None))
    print("coverage csv", len(done))


def range_ext(rid, uv, inr):
    rng = json.loads((OUT / "step02" / rid / "range.json").read_text())
    if rng["kind"] == "uv_box":
        return ((rng["u_m"][0] - 3, rng["u_m"][1] + 3), (rng["v_m"][0] - 3, rng["v_m"][1] + 3))
    q = uv[inr]
    return ((q[:, 0].min() - 3, q[:, 0].max() + 3), (q[:, 1].min() - 3, q[:, 1].max() + 3))


def case4_fig():
    summ = {}
    for prior in ("LoD2", "ALS"):
        fig, axs = plt.subplots(2, 4, figsize=(22, 12), constrained_layout=True)
        for ax, rid in zip(axs.ravel(), RANGES):
            U = dict(np.load(OUT / "step03" / rid / prior / "units.npz"))
            L = np.load(OUT / "step04" / rid / f"labels_{prior}.npz")
            lab = np.where(L["excluded"], -2, L["label"])
            inr = U["loc_in_range"]
            uv = xy_to_uv(U["loc_center"][:, :2]); z = U["loc_center"][:, 2]
            ext = range_ext(rid, uv, inr)
            zz = np.where(U["loc_kind"] == 2, z - 1000.0, z)        # roofs over walls, as in the step 09 maps
            bg = raster(uv[inr], zz[inr], np.where(U["loc_kind"][inr] == 2, 1, 0).astype(np.int16), ext)
            ax.imshow(np.where(bg < 0, 2, bg), cmap=ListedColormap(["#e3e3e3", "#b8b8b8", "#ffffff"]), vmin=0, vmax=2,
                      extent=[ext[0][0], ext[0][1], ext[1][1], ext[1][0]], interpolation="nearest")
            ok = inr & ~L["excluded"]                                # as the case 4 table: excluded cells left out of the counts
            inv = ok & (U["state"] == rule.ST_INVISIBLE)
            inv_ex = inr & L["excluded"] & (U["state"] == rule.ST_INVISIBLE)
            groups = [("평가 제외(세지 않음)", inv_ex, "#9e9e9e", 0.6), ("참값 없음", inv & (lab == -1), "#4a6fd1", 1.0),
                      ("이어받으면 맞음 (참 일치)", inv & (lab == 0), "#1b9e3a", 4.0), ("이어받으면 틀림 (참 충돌)", inv & (lab == 1), "#d62728", 4.0)]
            for name, m, col, s in groups:
                ax.scatter(uv[m, 0], uv[m, 1], s=s, c=col, linewidths=0, label=f"{name} {int(m.sum()):,}")
            n_inv, n_gt = int(inv.sum()), int((inv & (lab >= 0)).sum())
            r_, w_ = int((inv & (lab == 0)).sum()), int((inv & (lab == 1)).sum())
            share = n_inv / max(int(ok.sum()), 1)
            ax.set_title(f"{rid}: 비가시 {n_inv:,} ({share:.1%}), 참값 있음 {n_gt:,} → 맞음 {r_:,} / 틀림 {w_:,}", fontsize=10)
            ax.set_xlim(ext[0]); ax.set_ylim(ext[1][1], ext[1][0]); ax.set_aspect("equal")
            ax.set_xlabel("u (m)", fontsize=8); ax.set_ylabel("v (m)", fontsize=8); ax.tick_params(labelsize=7)
            ax.legend(fontsize=7, loc="lower left", markerscale=3, framealpha=0.85)
            summ[f"{rid}/{prior}"] = dict(units_counted=int(ok.sum()), invisible=n_inv, invisible_share=round(share, 4), with_gt=n_gt,
                                          inherit_right=r_, inherit_wrong=w_, invisible_excluded=int(inv_ex.sum()),
                                          invisible_wall_share=round(float(np.mean(U["loc_kind"][inv] == 2)) if n_inv else 0.0, 3))
        fig.suptitle(f"경우 4 못 본 곳 — {prior}: 어느 학습 시점도 보지 못한 패치(점)와, 그 자리에서 사전 정보를 이어받으면 맞는지(참 라벨). "
                     f"회색 바탕 = 범위의 패치(밝음 지붕, 어두움 벽)", fontsize=12, x=0.01, ha="left")
        fig.savefig(O / f"fig_case4_{prior}.png", dpi=80)
        plt.close(fig)
    jdump(O / "case4_locations.json", dict(results=summ, scientific_verdict=None))
    for k, v in summ.items():
        print("case4", k, v["invisible"], v["with_gt"], v["inherit_right"], v["inherit_wrong"], "wall share", v["invisible_wall_share"])


def agree_summary(U, lab, ok):
    st, J, kind = U["state"], U["J"], U["loc_kind"]
    ext = U["surf_ext"][U["loc_surface"]]
    prop = ok & (st == rule.ST_MISSING) & (J == rule.J_AGREE)
    m_r, m_w = prop & (lab == 0), prop & (lab == 1)
    res = dict(agree_right=int(m_r.sum()), agree_right_roof=int((m_r & (kind == 1)).sum()), agree_right_wall=int((m_r & (kind == 2)).sum()),
               agree_wrong=int(m_w.sum()), agree_no_gt=int((prop & (lab < 0)).sum()))
    es, cnt = np.unique(ext[m_r], return_counts=True)
    top = []
    for e, c_ in sorted(zip(es.tolist(), cnt.tolist()), key=lambda t: -t[1])[:6]:
        mm = m_r & (ext == e)
        uvc = xy_to_uv(U["loc_center"][mm, :2]).mean(0)
        top.append(dict(surface=int(e), patches=int(c_), kind="wall" if np.mean(kind[mm] == 2) > 0.5 else "roof",
                        centre_uv=[round(float(uvc[0]), 1), round(float(uvc[1]), 1)], z_median_m=round(float(np.median(U["loc_center"][mm, 2])), 1)))
    res["top_surfaces"] = top
    return res


def agree_check():
    out = {}
    for rid in RANGES:
        for prior in ("LoD2", "ALS"):
            U = dict(np.load(OUT / "step03" / rid / prior / "units.npz")); G = dict(np.load(OUT / "step04" / rid / f"labels_{prior}.npz"))
            out[f"{rid}/{prior}"] = agree_summary(U, G["label"], U["loc_in_range"] & ~G["excluded"])
    boxes = json.loads((OUT / "step06/boxes_v1.json").read_text())["boxes"]
    for bid, rid in BOX_OF.items():
        for prior in ("LoD2", "ALS"):
            U = dict(np.load(OUT / "step06/box_stage1" / rid / prior / "units.npz"))
            G = dict(np.load(OUT / "step06/box_gt" / rid / f"labels_{prior}.npz"))
            ok = in_eval(U["loc_center"][:, :2], boxes[bid]) & U["loc_in_range"] & ~G["excluded"]
            out[f"box {bid}/{prior}"] = agree_summary(U, G["label"], ok)
    jdump(O / "agree_check.json", dict(rule="missing patch, propagated judgment = agree, true label = agree (right) / conflict (wrong); "
                                            "search ranges: in range and not excluded; boxes: evaluation range as in step 06d",
                                       results=out, scientific_verdict=None))
    for k, v in out.items():
        print("agree", k, v["agree_right"], "roof", v["agree_right_roof"], "wall", v["agree_right_wall"], "wrong", v["agree_wrong"],
              "top", [(t["surface"], t["kind"], t["patches"]) for t in v["top_surfaces"][:3]])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("what", choices=["coverage-csv", "case4-fig", "agree-check"])
    a = ap.parse_args()
    O.mkdir(parents=True, exist_ok=True)
    {"coverage-csv": coverage_csv, "case4-fig": case4_fig, "agree-check": agree_check}[a.what]()


if __name__ == "__main__":
    main()
