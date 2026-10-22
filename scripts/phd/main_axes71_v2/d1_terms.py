"""PHD-MAIN-AXES71-v2 일 1 '사전 정보 깊이 항과 MVS 깊이 항의 꼴' (jointbuildgs:dev, CPU torch; no training, no GPU; through run_cpu_ax.sh).

The loss is NOT copied: the training module of the fork (src/phd/forks/GeoGS-conf-guided-v1-r15/jbgs_judgment.py and the fixed version r16)
is imported from its file and its method Judgment.losses (r15: jbgs_judgment.py:1320-1352, r16: 1443-1482) is called unbound on a minimal
stand-in object that carries only the attributes the method reads (args.jbgs_depth_norm, args.jbgs_trunc_hi, mode, sw, ab, A, M, P, TAU,
GW; r16 also fix, W, NOTRUNC). The render package is one pixel ({'surf_depth': [1, 1, 1]}), so the method's own pixel normalisation
(denominator = D.numel(), 'pixels') is 1. The two terms are weighted the way train.py:876 does (lambda_mvs * mvs_term, lambda_prior *
prior_term) with the lambdas of the trained runs (receipts). The gradient is torch.autograd's, with respect to the rendered depth D.

One pixel: P (prior depth) = M (MVS depth) = 50 m camera depth, TAU map = tau (camera-depth units: the export divides the metres by the
height factor f, s03_stage1_v6.py:380; here f = 1, a level roof seen straight down, so camera depth = height). d = D - P or D - M from 0 to
5 tau. g = 1 (agree) and g = 0 (conflict) for the prior term; A = 1 (confidence) and A = 0 for the MVS term.

Outputs: /docs/figures/일1_두항의꼴.png (300 dpi), .pdf, .json; AX/work/d1/terms.json (all cases, both forks, fix A / fix B, code checks).
scientific_verdict: null."""
import ast
import difflib
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

sys.path.insert(0, "/repo")
REPO = Path("/repo")
FORKS = {r: REPO / "src/phd/forks" / f"GeoGS-conf-guided-v1-{r}" for r in ("r12", "r15", "r16")}
PH = Path("/ph")
S1 = Path("/out")
S0 = Path("/s0")
FT = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
AX = PH / "main_axes71_v2/PHD-MAIN-AXES71-v2"
DOCS = Path("/docs")
KST_NOW = time.strftime("%Y-%m-%d %H:%M:%S KST", time.gmtime(time.time() + 9 * 3600))
T0 = time.time()
P0 = 50.0
CASES = [("B0_b10", "LoD2"), ("B0_b10", "ALS"), ("B173nb_b10", "LoD2"), ("B173nb_b10", "ALS"), ("R1rep_b10", "LoD2"), ("R1rep_b10", "ALS")]
FIG_CASE = ("B173nb_b10", "ALS")


def load(rev):
    spec = importlib.util.spec_from_file_location(f"jbgs_judgment_{rev}", FORKS[rev] / "jbgs_judgment.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def stub(rev, *, A, M, P, TAU, GW, W=None, NOTRUNC=None, fixA=False, fixB=False):
    """the attributes Judgment.losses reads, nothing else (r15: jbgs_judgment.py:1320-1352; r16: 1443-1482)."""
    s = SimpleNamespace()
    s.args = SimpleNamespace(jbgs_depth_norm="pixels", jbgs_trunc_hi=4.0)       # receipts: --jbgs_depth_norm pixels --jbgs_trunc_hi 4.0
    s.mode = "P"
    s.sw = dict(confidence_mask=True, judgment=True, propagation=True, prior_band=True, protection=True, init_exclusion=True, prior=True)
    s.ab = dict(loss_judgment=False, density_judgment=False, tolerance_band=False)
    s.A, s.M, s.P, s.TAU, s.GW = {"v": A}, {"v": M}, {"v": P}, {"v": TAU}, {"v": GW}
    if rev == "r16":
        s.fix = dict(prior_share_band=fixA, own_depth_release=fixB)
        s.W = {"v": W} if W is not None else {}
        s.NOTRUNC = {"v": NOTRUNC} if NOTRUNC is not None else {}
    return s


def px(v, dtype=torch.float32):
    return torch.tensor([[v]], dtype=dtype)


def one(mod, rev, term, d, tau, lam, g=1.0, a=1.0, w=None, notrunc=False):
    """(loss, |dloss/dD|) of one pixel. term 'prior': D = P0 + d; term 'mvs': D = P0 + d against M = P0."""
    D = torch.tensor([[[P0 + d]]], dtype=torch.float32, requires_grad=True)
    nan = float("nan")
    if term == "prior":
        kw = dict(A=px(0.0), M=px(nan), P=px(P0), TAU=px(tau), GW=px(g))
    else:
        kw = dict(A=px(a), M=px(P0), P=px(nan), TAU=px(tau), GW=px(1.0))
    if rev == "r16":
        kw.update(W=px(w) if w is not None else None, NOTRUNC=torch.tensor([[bool(notrunc)]]) if notrunc else None,
                  fixA=w is not None, fixB=bool(notrunc))
    s = stub(rev, **kw)
    mvs_term, prior_term, stats = mod.Judgment.losses(s, "v", {"surf_depth": D})
    t = lam * (prior_term if term == "prior" else mvs_term)          # train.py:876: judgment.lambda_* x term
    if t.requires_grad:
        (gr,) = torch.autograd.grad(t, D, allow_unused=True)
        gv = 0.0 if gr is None else float(gr.abs().sum())
    else:
        gv = 0.0
    return float(t.detach()), gv, stats


def sources():
    out = {}
    for rev, root in FORKS.items():
        src = (root / "jbgs_judgment.py").read_text()
        tree = ast.parse(src)
        fns = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in ("rho_truncated", "weighted_l1", "truncated_prior_loss", "rho_band"):
                fns[node.name] = (node.lineno, node.end_lineno, ast.get_source_segment(src, node))
            if isinstance(node, ast.ClassDef) and node.name == "Judgment":
                for b in node.body:
                    if isinstance(b, ast.FunctionDef) and b.name in ("losses", "_g_init"):
                        fns[f"Judgment.{b.name}"] = (b.lineno, b.end_lineno, ast.get_source_segment(src, b))
        tl = [i + 1 for i, l in enumerate((root / "train.py").read_text().splitlines()) if "judgment.lambda_mvs * mvs_term" in l]
        out[rev] = dict(functions={k: [v[0], v[1]] for k, v in fns.items()}, train_total_loss_line=tl, _src={k: v[2] for k, v in fns.items()})
    cmp = {}
    for a, b in (("r12", "r15"), ("r15", "r16")):
        for k in sorted(set(out[a]["_src"]) | set(out[b]["_src"])):
            sa, sb = out[a]["_src"].get(k), out[b]["_src"].get(k)
            if sa is None or sb is None:
                cmp[f"{a}->{b} {k}"] = "한쪽에만 있음"
                continue
            diff = [l for l in difflib.unified_diff(sa.splitlines(), sb.splitlines(), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
            cmp[f"{a}->{b} {k}"] = "같음" if not diff else diff
    for v in out.values():
        v.pop("_src")
    rule = (REPO / "src/phd/prior_propagation_v6/rule.py").read_text().splitlines()
    i = next(n for n, l in enumerate(rule) if l.startswith("def prior_term_off"))
    return dict(forks=out, compare=cmp, prior_term_off=dict(file="src/phd/prior_propagation_v6/rule.py", lines=[i + 1, i + 8]))


def receipts():
    """lambda, truncation, normalisation and tau of the trained 'prop' runs (stage 1; B173 주변 = stage 0) and the fix A runs."""
    out = {}
    paths = []
    for site, prior in CASES:
        for seed in (0, 1):
            p = (S0 / "stage0" / f"b{seed + 1}_{prior}" / "receipt.json") if site == "B173nb_b10" else (S1 / "stage1" / site / f"prop_{prior}_s{seed}" / "receipt.json")
            paths.append((f"{site}/prop_{prior}_s{seed}", p))
    for p in sorted(FT.glob("runs/*/fix*_s0/receipt.json")):
        paths.append((f"{p.parts[-3]}/{p.parts[-2]}", p))
    for key, p in paths:
        if not p.exists():
            out[key] = dict(file=str(p), exists=False)
            continue
        d = json.loads(p.read_text())
        c = d.get("command", [])
        def a(n):
            return c[c.index(n) + 1] if n in c else None
        out[key] = dict(fork=d.get("fork"), lambda_mvs=a("--jbgs_lambda_mvs"), lambda_prior=a("--jbgs_lambda_prior"), trunc_hi=a("--jbgs_trunc_hi"),
                        depth_norm=a("--jbgs_depth_norm"), tau_roof=a("--jbgs_tau_roof"), tau_wall=a("--jbgs_tau_wall"), tau_dir=a("--jbgs_tau_dir"),
                        sw_confidence_mask=a("--jbgs_sw_confidence_mask"), sw_prior_band=a("--jbgs_sw_prior_band"),
                        fixA=a("--jbgs_sw_prior_share_band"), fixA_dir=a("--jbgs_prior_width_dir"), fixB=a("--jbgs_sw_own_depth_release"),
                        lod_lambdas=[a("--lambda_lod_init"), a("--lambda_lod_anchor"), a("--lambda_da_depth")])
    return out


def main():
    mods = {r: load(r) for r in ("r15", "r16")}
    src = sources()
    rec = receipts()
    lam = 0.05
    lams = {(k, v["lambda_mvs"], v["lambda_prior"]) for k, v in rec.items() if v.get("lambda_mvs")}
    assert all(float(m) == lam and float(p) == lam for _, m, p in lams), lams
    wd = {r: json.loads((FT / "prep" / f"w_decision_{r}.json").read_text())["cases"] for r in ("L", "T")}
    # ---------------------------------------------------------------- the figure case, dense grid (midpoints: no exact band edge)
    tau_f = wd["L"][f"{FIG_CASE[0]}/{FIG_CASE[1]}"]["tau_roof"]
    x = (np.arange(2000) + 0.5) / 2000 * 5.0                       # d / tau
    curves = {}
    for rev in ("r15", "r16"):
        cv = {}
        for nm, kw in (("prior_g1", dict(term="prior", g=1.0)), ("prior_g0", dict(term="prior", g=0.0)),
                       ("mvs_a1", dict(term="mvs", a=1.0)), ("mvs_a0", dict(term="mvs", a=0.0))):
            vals = [one(mods[rev], rev, d=float(t * tau_f), tau=tau_f, lam=lam, **kw)[:2] for t in x]
            cv[nm] = dict(loss=[v[0] for v in vals], grad=[v[1] for v in vals])
        curves[rev] = cv
    same = all(np.allclose(curves["r15"][k]["loss"], curves["r16"][k]["loss"], rtol=0, atol=0) and
               np.allclose(curves["r15"][k]["grad"], curves["r16"][k]["grad"], rtol=0, atol=0) for k in curves["r15"])
    # ---------------------------------------------------------------- every case: values at fixed multiples, edges, fix A and fix B
    pts = [0.25, 0.5, 0.999, 1.001, 2.0, 3.0, 3.999, 4.001, 4.5, 5.0]
    edge = [1.0, 4.0]
    per_case = {}
    for site, prior in CASES:
        key = f"{site}/{prior}"
        kinds = {"roof": wd["L"][key]["tau_roof"]} if prior == "ALS" else {"roof": wd["L"][key]["tau_roof"], "wall": wd["L"][key]["tau_wall"]}
        ent = {}
        for kn, tau in kinds.items():
            e = dict(tau_m=tau, pull_band_m=[tau, 4 * tau], cap_loss=lam * 3 * tau, cap_loss_formula="λ·(4−1)·τ (n_px = 1)")
            for nm, kw in (("prior_g1", dict(term="prior", g=1.0)), ("prior_g0", dict(term="prior", g=0.0)), ("mvs_a1", dict(term="mvs", a=1.0)),
                           ("mvs_a0", dict(term="mvs", a=0.0))):
                e[nm] = {f"{t:g}tau": dict(zip(("loss", "grad"), one(mods["r15"], "r15", d=t * tau, tau=tau, lam=lam, **kw)[:2])) for t in pts}
                e[nm + "_at_edges"] = {f"{t:g}tau": dict(zip(("loss", "grad"), one(mods["r15"], "r15", d=t * tau, tau=tau, lam=lam, **kw)[:2])) for t in edge}
            for rd in ("L", "T"):
                wv = wd[rd][key]["w_roof" if kn == "roof" else "w_wall"]
                e[f"fixA_{rd}"] = dict(w_m=wv, w_over_tau=wv / tau, trained=wd[rd][key]["train"], failed=wd[rd][key]["failed"],
                                       values={f"{t:g}tau": dict(zip(("loss", "grad"), one(mods["r16"], "r16", term="prior", d=t * tau, tau=tau, lam=lam, g=1.0, w=wv)[:2]))
                                               for t in [0.5 * wv / tau, 0.5 * (1 + wv / tau)] + pts})
            e["fixB_notrunc"] = {f"{t:g}tau": dict(zip(("loss", "grad"), one(mods["r16"], "r16", term="prior", d=t * tau, tau=tau, lam=lam, g=1.0, notrunc=True)[:2])) for t in pts}
            ent[kn] = e
        per_case[key] = ent
    # ---------------------------------------------------------------- figure
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
        font_manager.fontManager.addfont(f)
    plt.rcParams.update({"font.family": ["Noto Sans CJK JP", "DejaVu Sans"], "axes.unicode_minus": False, "font.size": 9,
                         "axes.edgecolor": "#52514e", "axes.labelcolor": "#0b0b0b", "xtick.color": "#52514e", "ytick.color": "#52514e",
                         "axes.spines.top": False, "axes.spines.right": False})
    BLUE, ORANGE, AQUA, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984"
    xc = x * tau_f * 100.0
    cv = curves["r15"]
    fig, axs = plt.subplots(2, 2, figsize=(7.2, 5.0), constrained_layout=True)
    panels = [(axs[0, 0], "prior", "loss", "사전 정보 깊이 항", "손실"), (axs[1, 0], "prior", "grad", None, "기울기 크기"),
              (axs[0, 1], "mvs", "loss", "MVS 깊이 항", "손실"), (axs[1, 1], "mvs", "grad", None, "기울기 크기")]
    for ax, term, kind, title, ylab in panels:
        if term == "prior":
            ax.plot(xc, cv["prior_g1"][kind], color=BLUE, lw=2, label="일치 (g = 1)")
            ax.plot(xc, cv["prior_g0"][kind], color=ORANGE, lw=2, ls=(0, (4, 2)), label="충돌 (g = 0)")
            ax.set_xlabel("결과 − 사전 정보 깊이 (cm)")
        else:
            ax.plot(xc, cv["mvs_a1"][kind], color=AQUA, lw=2, label="신뢰도 1")
            ax.plot(xc, cv["mvs_a0"][kind], color=GREY, lw=2, ls=(0, (4, 2)), label="신뢰도 0")
            ax.set_xlabel("결과 − MVS 깊이 (cm)")
        for t in (1, 4):
            ax.axvline(t * tau_f * 100, color="#c3c2b7", lw=0.8, zorder=0)
        ax.set_xlim(0, 5 * tau_f * 100)
        ax.set_ylabel(ylab)
        ax.grid(axis="y", color="#e6e5df", lw=0.6)
        top = ax.secondary_xaxis("top", functions=(lambda v: v / (tau_f * 100), lambda v: v * tau_f * 100))
        top.set_xticks([0, 1, 2, 3, 4, 5])
        top.set_xticklabels(["0", "τ", "2τ", "3τ", "4τ", "5τ"])
        top.tick_params(colors="#52514e", labelsize=8)
        if title:
            ax.set_title(title, fontsize=10, loc="left", color="#0b0b0b")
            ax.legend(frameon=False, fontsize=8, loc="upper left")
        if kind == "grad":
            ax.set_ylim(-0.003, 0.06)
    stem = DOCS / "figures" / "일1_두항의꼴"
    stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(stem) + ".png", dpi=300)
    fig.savefig(str(stem) + ".pdf")
    plt.close(fig)
    meta = dict(
        task_id="PHD-MAIN-AXES71-v2", item="일 1 두 항의 꼴", made=KST_NOW, script="scripts/phd/main_axes71_v2/d1_terms.py", new="[새로 그림]",
        what="한 화소에서 결과 깊이를 바꿀 때 사전 정보 깊이 항(위 왼쪽: 손실, 아래 왼쪽: 기울기 크기)과 MVS 깊이 항(오른쪽)의 값. 코드의 Judgment.losses를 그대로 불렀다",
        case=f"{FIG_CASE[0]} · {FIG_CASE[1]}", tau_m=tau_f, tau_source="FT/prep/w_decision_L.json cases['B173nb_b10/ALS'].tau_roof (= 발주문 표 A 14.7 cm)",
        call=("r15 jbgs_judgment.Judgment.losses(stub, 'v', {'surf_depth': D[1,1,1]}); stub = 그 메서드가 읽는 속성만 가진 SimpleNamespace "
              "(args.jbgs_depth_norm='pixels', args.jbgs_trunc_hi=4.0, mode='P', sw, ab, A, M, P, TAU, GW). 한 화소라 분모 n_px = 1. "
              "가중은 train.py:876과 같이 λ × 항, λ_mvs = λ_prior = 0.05 (학습 영수증). 기울기 = torch.autograd.grad(λ×항, D)"),
        pixel=dict(P_m=P0, M_m=P0, f=1.0, note="TAU 지도 = τ ÷ max(f, 1e-3) (s03_stage1_v6.py:380). f = 1은 평평한 지붕을 바로 위에서 본 화소. 다른 f에서는 가로축(깊이 차)의 τ 눈금이 τ/f로 옮겨 간다"),
        x_grid="d/τ = (i + 0.5)/2000 × 5, i = 0..1999 (구간 끝 τ, 4τ를 정확히 밟지 않음)",
        x_cm=xc.tolist(), r15=curves["r15"], r16_switches_off_equal_r15=bool(same),
        lines=dict(prior_g1="일치 (g = 1)", prior_g0="충돌 (g = 0)", mvs_a1="신뢰도 1 (A = 1)", mvs_a0="신뢰도 0 (A = 0)"),
        colors=dict(prior_g1=BLUE, prior_g0=ORANGE, mvs_a1=AQUA, mvs_a0=GREY, band_edges="#c3c2b7"),
        other_cases="AX/work/d1/terms.json per_case (여섯 경우, 지붕·벽 τ, 판 A의 w 두 읽기, 판 B)",
        scientific_verdict=None)
    (Path(str(stem) + ".json")).write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    out = dict(task_id="PHD-MAIN-AXES71-v2", item="일 1 두 항의 꼴 (값과 코드 확인)", written=KST_NOW, script="scripts/phd/main_axes71_v2/d1_terms.py",
               lambda_=lam, receipts=rec, code=src, r16_switches_off_equal_r15=bool(same), per_case=per_case,
               figure=str(stem) + ".png", seconds=round(time.time() - T0, 1), scientific_verdict=None)
    (AX / "work/d1").mkdir(parents=True, exist_ok=True)
    (AX / "work/d1/terms.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("done", round(time.time() - T0, 1), "s; r16 off == r15:", same)


if __name__ == "__main__":
    main()
