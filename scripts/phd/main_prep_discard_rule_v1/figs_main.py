"""PHD-MAIN-PREP-DISCARD-RULE-v1: figures and tables of the report (jointbuildgs:dev, CPU).

  python figs_main.py [tradeoff] [boxmaps] [tau] [b0]

tradeoff  per prior and face kind (LoD2 roof, LoD2 wall, ALS roof): wrong discards (x) against wrong keeps (y) of every rule in
          the selection region, panels measured / unmeasured / together (rules/counts.json selection_aggregate)
boxmaps   per box and prior: plan view (u, v; 0.25 m) of the patch decisions of every rule in the box (support keep / discard,
          missing agree / undetermined / discard, invisible); the evaluation range outlined
tau       the tolerance and registration of the 7 ranges re-measured on the training-only MVS against the prep v1.1 values
b0        the seven B0 conditions: patch states, the share that inherits the prior, judgments against the true labels
Writes figs/*.png and tables/*.csv / *.json. scientific_verdict: null."""
import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import numpy as np

from common import CFG, OUT, PREP, jdump, log, xy_to_uv
from src.phd.prior_propagation_v5 import locations as locs
from src.phd.prior_propagation_v5 import rule
from src.phd.prior_propagation_v5 import rules as R

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    try:
        font_manager.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
F = OUT / "figs"; T = OUT / "tables"
F.mkdir(exist_ok=True); T.mkdir(exist_ok=True)
KO = {"current": "지금", "margin_all_1.5": "여유모두1.5", "margin_all_2": "여유모두2", "margin_all_3": "여유모두3",
      "margin_prop_1.5": "여유전파1.5", "margin_prop_2": "여유전파2", "margin_prop_3": "여유전파3", "asymmetric": "비대칭",
      "tau_0.5": "τ×0.5", "tau_2": "τ×2"}
COL = {"current": "#000000", "margin_all": "#1f5fbf", "margin_prop": "#e07b00", "asymmetric": "#7b3fbf", "tau": "#8c8c8c"}


def fam(n):
    return "current" if n == "current" else ("margin_all" if n.startswith("margin_all") else ("margin_prop" if n.startswith("margin_prop") else ("asymmetric" if n == "asymmetric" else "tau")))


def tradeoff():
    C = json.loads((OUT / "rules/counts.json").read_text())["selection_aggregate"]
    rows = []
    for prior, kind in (("LoD2", "roof"), ("LoD2", "wall"), ("ALS", "roof")):
        fig, axs = plt.subplots(1, 3, figsize=(17, 5.4), constrained_layout=True)
        for ax, part in zip(axs, ("measured", "unmeasured", "together")):
            for n in R.RULES:
                if part == "together":
                    xs = [C[prior][f"{kind}_{p}"][n] for p in ("measured", "unmeasured")]
                    x = sum(v["wrong_discard"] for v in xs); y = sum(v["wrong_keep"] for v in xs)
                    ta = sum(v["true_agree"] for v in xs); tc = sum(v["true_conflict"] for v in xs)
                else:
                    v = C[prior][f"{kind}_{part}"][n]; x, y, ta, tc = v["wrong_discard"], v["wrong_keep"], v["true_agree"], v["true_conflict"]
                ax.scatter([x], [y], s=55, color=COL[fam(n)], zorder=3)
                ax.annotate(KO[n], (x, y), textcoords="offset points", xytext=(4, 4), fontsize=8)
                rows.append(dict(prior=prior, kind=kind, part=part, rule=n, wrong_discard=x, wrong_keep=y, true_agree=ta, true_conflict=tc,
                                 wrong_discard_rate=round(x / ta, 4) if ta else None, wrong_keep_rate=round(y / tc, 4) if tc else None))
            if part == "measured":   # overlapping points named once (presentation only)
                ax.text(0.02, 0.02, "여유(전파만)·비대칭은 잰 곳을 바꾸지 않아 '지금'과 겹친다\nτ×2는 여유(모두)2와 판정이 같아 겹친다", transform=ax.transAxes,
                        ha="left", va="bottom", fontsize=8, color="#555")
            ax.set_title({"measured": "잰 곳(지지 패치)", "unmeasured": "재지 못한 곳(결측 패치)", "together": "함께"}[part], fontsize=11)
            ax.set_xlabel("잘못 버림 (참 일치인데 버린 패치 수)"); ax.set_ylabel("잘못 지킴 (참 충돌인데 지킨 패치 수)"); ax.grid(alpha=0.3)
        axs[0].legend(handles=[Patch(color=c, label=k) for k, c in (("지금 규칙", COL["current"]), ("여유(모두) k", COL["margin_all"]),
                                                                     ("여유(전파만) k", COL["margin_prop"]), ("비대칭", COL["asymmetric"]),
                                                                     ("허용 오차 배율", COL["tau"]))], fontsize=8, loc="upper right")
        fig.suptitle(f"맞바꿈 — {prior} {'지붕' if kind == 'roof' else '벽'}, 고르는 곳(일곱 범위에서 상자 평가 범위를 뺀 곳)", fontsize=12, x=0.01, ha="left")
        fig.savefig(F / f"tradeoff_{prior}_{kind}.png", dpi=90); plt.close(fig)
    with open(T / "tradeoff.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    log("tradeoff", len(rows))


def raster(uv, z, val, ext, cell=0.25):
    (u0, u1), (v0, v1) = ext
    nu = int(np.ceil((u1 - u0) / cell)); nv = int(np.ceil((v1 - v0) / cell))
    iu = np.floor((uv[:, 0] - u0) / cell).astype(int); iv = np.floor((uv[:, 1] - v0) / cell).astype(int)
    ok = (iu >= 0) & (iu < nu) & (iv >= 0) & (iv < nv)
    o = np.argsort(z[ok])
    img = np.full((nv, nu), -1, np.int16)
    img[iv[ok][o], iu[ok][o]] = val[ok][o]
    return img


def boxmaps():
    boxes = json.loads((PREP / "step06/boxes_v1.json").read_text())["boxes"]
    jc = CFG["judgment"]
    cols = ["#a6dba0", "#f4a582", "#1b7837", "#f0b429", "#b2182b", "#4a6fd1"]
    names = ["지지·지킴", "지지·버림", "결측→일치(지킴)", "결측→미판정(지킴)", "결측→충돌(버림, 심지 않음)", "비가시(이어받음)"]
    for box, bid in (("B0_b10", "B0"), ("B173nb_b10", "B173nb"), ("B173_b0", "B173"), ("R1rep_b10", "R1rep")):
        b = boxes[bid]
        for prior in ("LoD2", "ALS"):
            run = OUT / "s52/box" / box / prior
            U = locs.load_store(run / "units.npz"); pairs = dict(np.load(run / "unit_view_pairs.npz")); kn = np.load(run / "knn.npz")
            sh = np.asarray(json.loads((run / "summary.json").read_text())["registration"]["shift_applied"], float)
            uv = xy_to_uv(U["loc_center"][:, :2] + sh[:2]); z = np.where(U["loc_kind"] == 2, U["loc_center"][:, 2] - 1000, U["loc_center"][:, 2])
            inr = U["loc_in_range"]
            ext = ((uv[inr, 0].min() - 2, uv[inr, 0].max() + 2), (uv[inr, 1].min() - 2, uv[inr, 1].max() + 2))
            fig, axs = plt.subplots(2, 5, figsize=(22, 2 * 4.2 * (ext[1][1] - ext[1][0]) / (ext[0][1] - ext[0][0]) + 1.6), constrained_layout=True)
            for ax, n in zip(axs.ravel(), R.RULES):
                st, vote, J, disc = R.apply(pairs, len(U["state"]), kn["mis"], kn["k_dist"], kn["k_id"], n, jc["majority"], int(jc["min_evidence"]), float(jc["max_distance_m"]))
                c = np.full(len(st), -1, np.int16)
                c[(st == rule.ST_SUPPORT) & ~disc] = 0; c[(st == rule.ST_SUPPORT) & disc] = 1
                c[(st == rule.ST_MISSING) & (J == rule.J_AGREE)] = 2; c[(st == rule.ST_MISSING) & ((J == rule.J_MIXED) | (J == rule.J_INSUFF))] = 3
                c[(st == rule.ST_MISSING) & (J == rule.J_CONFLICT)] = 4; c[st == rule.ST_INVISIBLE] = 5
                img = raster(uv[inr], z[inr], c[inr], ext)
                ax.imshow(np.where(img < 0, 6, img), cmap=ListedColormap(cols + ["#ffffff"]), vmin=0, vmax=6, extent=[ext[0][0], ext[0][1], ext[1][1], ext[1][0]], interpolation="nearest")
                ax.plot([b["eval_u"][0], b["eval_u"][1], b["eval_u"][1], b["eval_u"][0], b["eval_u"][0]], [b["eval_v"][0], b["eval_v"][0], b["eval_v"][1], b["eval_v"][1], b["eval_v"][0]], color="#333333", lw=0.8, ls="--")
                n_up = int(((st == rule.ST_MISSING) & (J == rule.J_CONFLICT) & inr).sum())
                ax.set_title(f"{KO[n]}: 버림 {int((disc & inr).sum()):,} · 심지 않음 {n_up:,}", fontsize=9); ax.set_xticks([]); ax.set_yticks([])
            axs[0, 0].legend(handles=[Patch(color=cols[i], label=names[i]) for i in range(6)], fontsize=7, loc="lower left", framealpha=0.85)
            fig.suptitle(f"상자 {box} · {prior}: 규칙별 학습 전 판정 (점선 = 평가 범위)", fontsize=12, x=0.01, ha="left")
            fig.savefig(F / f"boxmap_{box}_{prior}.png", dpi=75); plt.close(fig)
            log("boxmap", box, prior)


def tau():
    rows = []
    for r in ("R1", "R2", "R3E", "R4", "R5", "SW", "B0"):
        for p in ("LoD2", "ALS"):
            a = json.loads((PREP / "step03" / r / p / "summary.json").read_text()); b = json.loads((OUT / "s52/s03" / r / p / "summary.json").read_text())
            g = json.loads((OUT / "s52/gt" / r / "gt_summary.json").read_text()) if (OUT / "s52/gt" / r / "gt_summary.json").exists() else {}
            gp = json.loads((PREP / "step04" / r / "gt_summary.json").read_text())
            rows.append(dict(range=r, prior=p, views_v11=a["views"], views_new=b["views"],
                             tau_roof_v11=round(a["tolerance"]["roof"]["tau"], 4), tau_roof_new=round(b["tolerance"]["roof"]["tau"], 4),
                             tau_wall_v11=round(a["tolerance"]["wall"]["tau"], 4), tau_wall_new=round(b["tolerance"]["wall"]["tau"], 4),
                             shift_v11=[round(x, 3) for x in a["registration"]["shift_applied"]], shift_new=[round(x, 3) for x in b["registration"]["shift_applied"]],
                             nmad_after_v11=round(a["registration"].get("building_face_nmad_registered") or float("nan"), 4),
                             nmad_after_new=round(b["registration"].get("building_face_nmad_registered") or float("nan"), 4),
                             gt_alignment_v11=round(gp["height_alignment"]["shift_m"], 4), gt_alignment_new=round(g.get("height_alignment", {}).get("shift_m", float("nan")), 4),
                             exclusion_cells_equal=g.get("exclusion_cells_reused", {}).get("equal_to_recomputed")))
    with open(T / "tau_registration.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    jdump(T / "tau_registration.json", rows)
    # figure: v1.1 against new (tau roof / wall, horizontal registration shift, GT height alignment)
    fig, axs = plt.subplots(1, 3, figsize=(16, 5.0), constrained_layout=True)
    mk = {"LoD2": "o", "ALS": "s"}
    for r_ in rows:
        for kind, c in (("roof", "#c0392b"), ("wall", "#2471a3")):
            if r_["prior"] == "ALS" and kind == "wall":
                continue
            x, y = r_[f"tau_{kind}_v11"], r_[f"tau_{kind}_new"]
            axs[0].scatter([x], [y], marker=mk[r_["prior"]], color=c, s=40, zorder=3)
            axs[0].annotate(f"{r_['range']}", (x, y), textcoords="offset points", xytext=(4, -9), fontsize=7)
    lim = [0, max(max(r_["tau_roof_new"], r_["tau_wall_new"], r_["tau_roof_v11"], r_["tau_wall_v11"]) for r_ in rows) * 1.08]
    axs[0].plot(lim, lim, "k--", lw=0.8); axs[0].set_xlim(lim); axs[0].set_ylim(lim)
    axs[0].set_xlabel("허용 오차 τ, 준비 측정 v1.1 (m)"); axs[0].set_ylabel("허용 오차 τ, 새 MVS (m)"); axs[0].grid(alpha=0.3)
    axs[0].legend(handles=[plt.Line2D([], [], marker="o", ls="", color="#c0392b", label="LoD2 지붕"), plt.Line2D([], [], marker="o", ls="", color="#2471a3", label="LoD2 벽"),
                           plt.Line2D([], [], marker="s", ls="", color="#c0392b", label="항공 LiDAR 지붕")], fontsize=8, loc="upper left")
    axs[0].set_title("허용 오차: 점선 위 = 같음", fontsize=11)
    xs = np.arange(len([r_ for r_ in rows if r_["prior"] == "ALS"]))
    als = [r_ for r_ in rows if r_["prior"] == "ALS"]
    for i, r_ in enumerate(als):
        for j, (key, c) in enumerate((("shift_v11", "#999999"), ("shift_new", "#000000"))):
            d = float(np.hypot(*r_[key][:2])) * 100
            axs[1].bar(i + (j - 0.5) * 0.38, d, width=0.36, color=c)
    axs[1].set_xticks(xs); axs[1].set_xticklabels([r_["range"] for r_ in als]); axs[1].set_ylabel("수평 이동 크기 (cm)")
    axs[1].legend(handles=[Patch(color="#999999", label="v1.1"), Patch(color="#000000", label="새 MVS")], fontsize=8); axs[1].grid(alpha=0.3, axis="y")
    axs[1].set_title("항공 LiDAR 정합의 수평 이동 (LoD2는 모두 0)", fontsize=11)
    lods = [r_ for r_ in rows if r_["prior"] == "LoD2"]
    for j, (key, c) in enumerate((("gt_alignment_v11", "#999999"), ("gt_alignment_new", "#000000"))):
        axs[2].bar(np.arange(len(lods)) + (j - 0.5) * 0.38, [r_[key] * 100 for r_ in lods], width=0.36, color=c)
    axs[2].set_xticks(np.arange(len(lods))); axs[2].set_xticklabels([r_["range"] for r_ in lods]); axs[2].set_ylabel("참값 높이 맞춤 (cm)"); axs[2].grid(alpha=0.3, axis="y")
    axs[2].legend(handles=[Patch(color="#999999", label="v1.1"), Patch(color="#000000", label="새 MVS")], fontsize=8)
    axs[2].set_title("참값을 MVS 높이에 맞춘 이동", fontsize=11)
    fig.suptitle("학습 영상만으로 다시 만든 MVS: 허용 오차·정합·참값 맞춤 (준비 측정 v1.1과 견줌)", fontsize=12, x=0.01, ha="left")
    fig.savefig(F / "tau_registration.png", dpi=90); plt.close(fig)
    log("tau", len(rows))


def penalty():
    """the prior penalty with and without the tolerance band (code test values of gpu_tests_r11.json, not training)."""
    g = json.loads((OUT / "gpu_tests_r11.json").read_text())["tests"]["C_penalty"]
    fig, ax = plt.subplots(figsize=(6.4, 4.0), constrained_layout=True)
    ax.plot(g["r_over_tau"], g["band_on"], "o-", color="#1f5fbf", label="켬: τ 안은 0, τ~4τ는 |r|−τ, 4τ 넘으면 3τ")
    ax.plot(g["r_over_tau"], g["band_off"], "s--", color="#c0392b", label="끔: |r| (늘 당김)")
    ax.set_xlabel("잔차 / 허용 오차 (r / τ)"); ax.set_ylabel("벌점 / τ"); ax.grid(alpha=0.3); ax.legend(fontsize=8, loc="upper center")
    ax.set_title("사전 정보 당김의 구간 스위치: 시험값의 벌점 함수", fontsize=10)
    fig.savefig(F / "penalty_band.png", dpi=90); plt.close(fig)
    log("penalty")


def b0():
    conds = tuple(c for c in ("COVER", "A15", "A9", "A3", "N13", "N8", "N2") if (OUT / "s53_gt" / c / "B0" / "labels_LoD2.npz").exists())
    rows = []
    for c in conds:
        for p in ("LoD2", "ALS"):
            run = OUT / "s53" / c / "B0" / p
            U = locs.load_store(run / "units.npz"); G = np.load(OUT / "s53_gt" / c / "B0" / f"labels_{p}.npz")
            summ = json.loads((run / "summary.json").read_text())
            from matplotlib.path import Path as MPath
            from shapely.geometry import Polygon as SPoly
            fpoly = SPoly(json.loads((PREP / "step01/ranges.json").read_text())["B0BLD"]["polygon_local"]).buffer(2.0)   # prep case 6: footprint + 2 m
            in_t = MPath(np.asarray(fpoly.exterior.coords)).contains_points(U["loc_center"][:, :2])
            lab = G["label"]; ex = G["excluded"]; st, vote, J, Jl = U["state"], U["vote"], U["J"], U["J_loc"]
            for region, tgt in (("target", U["loc_in_range"] & in_t), ("crop", U["loc_in_range"])):
              m = tgt & ~ex
              for kname, kv in (("roof", 1), ("wall", 2)):
                  if p == "ALS" and kv == 2:
                      continue
                  mk = m & (U["loc_kind"] == kv)
                  n = int(mk.sum())
                  sup = mk & (st == rule.ST_SUPPORT); mis = mk & (st == rule.ST_MISSING); inv = mk & (st == rule.ST_INVISIBLE)
                  und = mis & ((J == rule.J_MIXED) | (J == rule.J_INSUFF))
                  disc = (sup & (vote == rule.V_CONFLICT)) | (mis & (J == rule.J_CONFLICT))
                  g = lab >= 0
                  # keep counts restricted to the row's region and face kind (fix 06:20: the first version counted every labelled patch)
                  rows.append(dict(condition=c, prior=p, region=region, kind=kname, views=summ["views"], patches=n, labelled=int((mk & g).sum()),
                                   support=round(sup.sum() / max(n, 1), 4), missing=round(mis.sum() / max(n, 1), 4), invisible=round(inv.sum() / max(n, 1), 4),
                                   inherit_share=round((inv.sum() + und.sum()) / max(n, 1), 4),
                                   support_conflict=round((sup & (vote == rule.V_CONFLICT)).sum() / max(sup.sum(), 1), 4),
                                   discard=int(disc.sum()), wrong_discard=int((disc & g & (lab == 0)).sum()), correct_discard=int((disc & g & (lab == 1)).sum()),
                                   wrong_keep=int((mk & ~disc & g & (lab == 1) & ~inv).sum()), correct_keep=int((mk & ~disc & g & (lab == 0) & ~inv).sum()),
                                   inherit_true_agree=int(((inv | und) & g & (lab == 0)).sum()), inherit_true_conflict=int(((inv | und) & g & (lab == 1)).sum()),
                                   tau_roof=summ["tolerance"]["roof"]["tau"], tau_wall=summ["tolerance"]["wall"]["tau"]))
    with open(T / "b0_conditions.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    jdump(T / "b0_conditions.json", rows)
    fig, axs = plt.subplots(1, 3, figsize=(16, 4.8), constrained_layout=True)
    for ax, (p, k) in zip(axs, (("LoD2", "roof"), ("LoD2", "wall"), ("ALS", "roof"))):
        sel = {r_["condition"]: r_ for r_ in rows if r_["prior"] == p and r_["kind"] == k and r_["region"] == "target"}
        xs = np.arange(len(conds))
        ax.bar(xs, [sel[c]["support"] for c in conds], color="#9ad19a", label="지지")
        ax.bar(xs, [sel[c]["missing"] for c in conds], bottom=[sel[c]["support"] for c in conds], color="#f0b429", label="결측")
        ax.bar(xs, [sel[c]["invisible"] for c in conds], bottom=[sel[c]["support"] + sel[c]["missing"] for c in conds], color="#4a6fd1", label="비가시")
        ax.plot(xs, [sel[c]["inherit_share"] for c in conds], "ko-", label="이어받는 몫(비가시+미판정)")
        ax.set_xticks(xs); ax.set_xticklabels([f"{c}\n{sel[c]['views']}장" for c in conds], fontsize=8)
        ax.set_ylim(0, 1); ax.set_title(f"{p} {'지붕' if k == 'roof' else '벽'}", fontsize=11); ax.grid(alpha=0.3, axis="y")
    axs[0].legend(fontsize=8, loc="upper left")
    fig.suptitle("B0 관측의 양 (대상 건물 + 2 m): 패치 상태의 비율과 사전 정보를 이어받는 몫 (A = 저자 경사 영상, N = 연직을 넣은 같은 수, 허용 오차·정합은 B0 크롭 값 고정)", fontsize=11, x=0.01, ha="left")
    fig.savefig(F / "b0_conditions.png", dpi=90); plt.close(fig)
    log("b0", len(rows))


if __name__ == "__main__":
    what = sys.argv[1:] or ["tradeoff", "boxmaps", "tau", "b0", "penalty"]
    for w in what:
        globals()[w]()
