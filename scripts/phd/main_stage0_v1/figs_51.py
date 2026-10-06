"""PHD-MAIN-STAGE0-v1 5.1 figures (jointbuildgs:dev, CPU): v6 against v5 on the four boxes.

  python figs_51.py

fig51_changes        per box x prior: share of the judged patches whose discard decision changed by the store fix (rule current,
                     rule margin_all_2) and by the rule default (v6 current -> rule of the run)
fig51_errors         wrong discards / wrong keeps (measured + unmeasured, roof + wall) of v5 current, v6 current, v6 rule
fig51_map_<box>      plan maps of the ALS boxes with a shift: patches whose decision the store fix changed (rule current) and the
                     rule default changed (green = wrong discard undone, red = wrong keep added, grey = other change)
fig51_switches       switch site: expected / changed outputs of the seven switch runs (both priors)
Writes figs/*.png. scientific_verdict: null."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

from common import DCFG, DR, OUT, PREP, jdump, log, xy_to_uv
from src.phd.prior_propagation_v6 import rules as R
from src.phd.prior_propagation_v6 import rule

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    try:
        font_manager.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
F = OUT / "figs"; F.mkdir(exist_ok=True)
BOXES = ["B0_b10", "B173nb_b10", "B173_b0", "R1rep_b10"]
BID = {"B0_b10": "B0", "B173nb_b10": "B173nb", "B173_b0": "B173", "R1rep_b10": "R1rep"}


def changes(C):
    keys = [(b, p) for b in BOXES for p in ("LoD2", "ALS")]
    lab = [f"{b}\n{'LoD2' if p == 'LoD2' else '항공 LiDAR'}" for b, p in keys]
    s1 = [C[f"{b}/{p}"]["store_fix_current_box"]["discard_share"] * 100 for b, p in keys]
    s2 = [C[f"{b}/{p}"]["store_fix_margin_all_2_box"]["discard_share"] * 100 for b, p in keys]
    s3 = [C[f"{b}/{p}"]["rule_default_box"]["discard_share"] * 100 for b, p in keys]
    x = np.arange(len(keys)); w = 0.27
    fig, ax = plt.subplots(figsize=(14, 4.6), constrained_layout=True)
    ax.bar(x - w, s1, w, color="#4c72b0", label="저장소 고침 (지금 규칙)")
    ax.bar(x, s2, w, color="#55a868", label="저장소 고침 (여유(모두) 2)")
    ax.bar(x + w, s3, w, color="#dd8452", label="규칙 기본값 (v6 지금 규칙 → 이번 규칙)")
    for xi, v in zip(x - w, s1):
        ax.text(xi, v + 0.1, f"{v:.2f}", ha="center", fontsize=7)
    for xi, v in zip(x + w, s3):
        ax.text(xi, v + 0.1, f"{v:.1f}", ha="center", fontsize=7)
    ax.axhline(3.0, color="k", ls=":", lw=0.8); ax.text(len(keys) - 0.5, 3.05, "멈춤 기준 3 % (저장소 고침)", ha="right", fontsize=8)
    ax.axhspan(0.5, 1.5, color="#4c72b0", alpha=0.08); ax.text(-0.45, 1.55, "둘째 준비 측정의 예상 0.5~1.5 %", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(lab, fontsize=8); ax.set_ylabel("버림 판단이 바뀐 패치 (판정 패치의 %)")
    ax.set_title("v5 → v6: 무엇이 버림 판단을 바꾸었나 (상자 전체, 지지 + 결측 패치)", fontsize=11); ax.legend(fontsize=9)
    fig.savefig(F / "fig51_changes.png", dpi=110); plt.close(fig)


def errors(C):
    keys = [(b, p) for b in BOXES for p in ("LoD2", "ALS")]
    fig, axs = plt.subplots(1, 2, figsize=(15, 4.6), constrained_layout=True)
    x = np.arange(len(keys)); w = 0.27
    for ax, k, t in ((axs[0], "wrong_discard", "잘못 버림 (참 일치인데 버림)"), (axs[1], "wrong_keep", "잘못 지킴 (참 충돌인데 지킴)")):
        for i, (tag, col, nm) in enumerate((("v5_current", "#999999", "v5 지금 규칙"), ("v6_current", "#4c72b0", "v6 지금 규칙(저장소 고침만)"),
                                            ("v6_rule", "#dd8452", "v6 이번 규칙(기본값)"))):
            v = [C[f"{b}/{p}"][f"labels_{tag}_evaluation"]["judged_total"][k] for b, p in keys]
            ax.bar(x + (i - 1) * w, v, w, color=col, label=nm)
        ax.set_xticks(x); ax.set_xticklabels([f"{b}\n{'LoD2' if p == 'LoD2' else '항공'}" for b, p in keys], fontsize=8)
        ax.set_title(t + " — 평가 범위, 지붕+벽, 잰 곳+재지 못한 곳", fontsize=10); ax.grid(alpha=0.3, axis="y")
    axs[0].legend(fontsize=8)
    fig.savefig(F / "fig51_errors.png", dpi=110); plt.close(fig)


def maps(C):
    from common import CFG
    jc = CFG["judgment"]
    for box in BOXES:
        sh = np.asarray(C[f"{box}/ALS"]["shift"])
        if not np.any(sh):
            continue
        U5 = np.load(DR / "s52/box" / box / "ALS/units.npz"); U6 = np.load(OUT / "s61/box" / box / "ALS/units.npz")
        d5 = np.load(DR / "rules/decisions" / f"{box}_ALS.npz")["current"]
        d6c = R.discard(U6["state"], U6["vote_tau"], U6["J_tau"]); d6r = R.discard(U6["state"], U6["vote"], U6["J"])
        G = np.load(OUT / "s61/box_gt" / box / "labels_ALS.npz"); lab = G["label"]; ex = G["excluded"]
        if box.startswith("B0") and (OUT / "s61/box_gt" / box / "labels_uls_ALS.npz").exists():
            Gu = np.load(OUT / "s61/box_gt" / box / "labels_uls_ALS.npz"); use = (lab < 0) & (Gu["label"] >= 0)
            lab = np.where(use, Gu["label"], lab); ex = ex | (use & Gu["excluded"])
        uv = xy_to_uv(U6["loc_center"][:, :2]); inr = U6["loc_in_range"]
        b = json.loads((PREP / "step06/boxes_v1.json").read_text())["boxes"][BID[box]]
        fig, axs = plt.subplots(1, 2, figsize=(16, 6.5), constrained_layout=True)
        for ax, (a_, b_, t) in zip(axs, ((d5, d6c, "저장소 고침 (지금 규칙: v5 → v6)"), (d6c, d6r, "규칙 기본값 (v6 지금 규칙 → 여유(모두) 2)"))):
            ax.scatter(uv[inr, 0], uv[inr, 1], s=0.3, c="#e6e6e6", marker="s", linewidths=0, rasterized=True)
            ch = inr & (a_ != b_)
            ok = ~ex & (lab >= 0)
            fixed = ch & ok & a_ & ~b_ & (lab == 0); added = ch & ok & a_ & ~b_ & (lab == 1)
            newd_bad = ch & ok & ~a_ & b_ & (lab == 0); newd_ok = ch & ok & ~a_ & b_ & (lab == 1)
            other = ch & ~(fixed | added | newd_bad | newd_ok)
            for m, c, nm in ((other, "#7f7f7f", "바뀜(참값 없음)"), (fixed, "#2ca02c", "잘못 버림 → 지킴(맞음)"), (added, "#d62728", "맞게 버림 → 지킴(잘못 지킴)"),
                             (newd_bad, "#ff7f0e", "지킴 → 버림(잘못 버림)"), (newd_ok, "#1f77b4", "지킴 → 버림(맞음)")):
                ax.scatter(uv[m, 0], uv[m, 1], s=3, c=c, marker="s", linewidths=0, label=f"{nm} {int(m.sum()):,}", rasterized=True)
            ax.plot([b["eval_u"][0], b["eval_u"][1], b["eval_u"][1], b["eval_u"][0], b["eval_u"][0]],
                    [b["eval_v"][0], b["eval_v"][0], b["eval_v"][1], b["eval_v"][1], b["eval_v"][0]], "k-", lw=0.8)
            ax.set_aspect("equal"); ax.set_title(f"{box} 항공 LiDAR — {t}: 바뀐 패치 {int(ch.sum()):,}", fontsize=10)
            ax.legend(fontsize=8, loc="lower left", markerscale=3)
        fig.savefig(F / f"fig51_map_{box}.png", dpi=110); plt.close(fig)
        log("map", box)


def switches(FC):
    exp = DCFG["switches"]["expected_changed_outputs"]
    outs = ["states", "votes", "propagated judgments", "patch judgments", "unplanted", "planted prior points", "g_p", "first E", "protection", "A maps", "prior depth term"]
    sws = list(exp)
    fig, axs = plt.subplots(1, 2, figsize=(15, 4.8), constrained_layout=True)
    for ax, pr in zip(axs, ("LoD2", "ALS")):
        M = np.zeros((len(sws), len(outs)))
        for i, s in enumerate(sws):
            row = FC["switches"].get(s, {}).get(f"B173nb_b10_{pr}", {})
            for j, o in enumerate(outs):
                ch = o in row.get("changed", []); ex_ = o in exp[s]
                M[i, j] = 3 if (ch and not ex_) else (2 if ch else (1 if ex_ else 0))
        ax.imshow(M, cmap=matplotlib.colors.ListedColormap(["#ffffff", "#dddddd", "#4c72b0", "#d62728"]), vmin=0, vmax=3, aspect="auto")
        ax.set_xticks(range(len(outs))); ax.set_xticklabels(outs, rotation=40, ha="right", fontsize=8)
        ax.set_yticks(range(len(sws))); ax.set_yticklabels(sws, fontsize=9)
        ax.set_title(f"B173nb_b10 {pr}: 파랑 = 예상대로 바뀜, 회색 = 바뀔 수 있다고 적었으나 안 바뀜, 빨강 = 예상 밖 변화", fontsize=9)
    fig.savefig(F / "fig51_switches.png", dpi=110); plt.close(fig)


def main():
    C = json.loads((OUT / "compare51/compare.json").read_text())["runs"]
    changes(C); errors(C); maps(C)
    FC = json.loads((OUT / "fork_checks/s61.json").read_text())
    switches(FC)
    log("figs 51 done")


if __name__ == "__main__":
    main()
