"""PHD-MAIN-FIXTEST-v1 일 6 (jointbuildgs:dev, CPU; run_step_ft.sh): figures 1, 1b, 2, 3, 4 and 5 at the places fixed before training
(FT/prep/figpos.json; figure 1b: the configuration's figure_places_added). Figure 0 is drawn by w1_table.py.
Rules (order 11.1): one sentence to see as the title (written from the values of the place, after they are known), two or three panels with
the same place, view and colour range, one colour per contrast, names and numbers written on the figure, numbers of the place under it (a
json next to every figure), excluded cells in their own colour.
Helpers copied from other scripts name their source (the fill task's figs_fl_common: ply_open, frame, _keep, plane_segments; ch6_common:
setup_fonts); those modules are not imported (they re-point shared helpers at import).
  python figs_ft.py [fig1 fig1b fig2 fig3 fig4 fig5]
Outputs FT/figs/<name>.png + .json. scientific_verdict: null."""
import json
import sys
import textwrap
from pathlib import Path

import numpy as np

PH = Path("/ph")
FTP = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
S1 = Path("/out")
S0 = Path("/s0")
S2 = PH / "main_stage2_v1/PHD-MAIN-STAGE2-v1"
S3 = PH / "main_stage3_v1/PHD-MAIN-STAGE3-v1"
SD = PH / "main_dist71_v1/PHD-MAIN-DIST71-v1"
SL = PH / "main_fill_v1/PHD-MAIN-FILL-v1"
FIGS = FTP / "figs"
FP = json.loads((FTP / "prep/figpos.json").read_text())["figures"]
CFG = json.loads(Path("/repo/configs/phd/main_fixtest_v1/fixtest_v1.json").read_text())
WD = {rd: json.loads((FTP / f"prep/w_decision_{rd}.json").read_text())["cases"] for rd in ("L", "T")}
BLUE, ORANGE, GREY, DARK, GREEN, RED = "#1f5fbf", "#d9822b", "#9a9a9a", "#2b2b2b", "#2e8b57", "#c0392b"
LIGHT, EXCL = "#e6e6e6", "#cfc3a8"
SHARE_CMAP = None   # light grey -> blue, made after matplotlib is set up
SITE_KO = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "R1rep_b10": "R1"}
PRIOR_KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}
_TY = {"float": "<f4", "float32": "<f4", "double": "<f8", "uchar": "u1", "uint8": "u1", "int": "<i4", "int32": "<i4", "uint": "<u4", "uint32": "<u4",
       "short": "<i2", "ushort": "<u2"}


def setup_fonts():
    """copied from scripts/phd/ch6_support_v1/ch6_common.py setup_fonts."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
        try:
            font_manager.fontManager.addfont(f)
        except Exception:
            pass
    plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


plt = setup_fonts()
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
SHARE_CMAP = LinearSegmentedColormap.from_list("share", [LIGHT, BLUE])


def wrap_fit(fig, text, fontsize, weight="normal", frac=0.985):
    """greedy word wrap measured with the renderer (Korean and Latin glyph widths differ too much for a character count)."""
    r = fig.canvas.get_renderer()
    maxw = fig.bbox.width * frac
    probe = fig.text(0, 0, "", fontsize=fontsize, fontweight=weight)
    lines, cur = [], ""
    for word in text.split(" "):
        cand = word if not cur else cur + " " + word
        probe.set_text(cand)
        if cur and probe.get_window_extent(r).width > maxw:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    probe.remove()
    return lines


def save(fig, name, title, caption, values, right=1.0):
    """caption: one string or a list of paragraphs (the last one is the numbers line, rule 6)."""
    FIGS.mkdir(parents=True, exist_ok=True)
    W, H = fig.get_size_inches()
    fig.canvas.draw()
    tl = wrap_fit(fig, title, 12.5, "bold")
    paras = [caption] if isinstance(caption, str) else list(caption)
    cl = [ln for para in paras for ln in wrap_fit(fig, para, 8.6)]
    top = 1.0 - (0.22 + 0.25 * len(tl)) / H
    bottom = (0.12 + 0.165 * len(cl)) / H
    fig.tight_layout(rect=(0, bottom, right, top))
    fig.suptitle("\n".join(tl), x=0.01, y=0.995, ha="left", va="top", fontsize=12.5, fontweight="bold")
    fig.text(0.01, 0.006, "\n".join(cl), fontsize=8.6, va="bottom")
    fig.savefig(FIGS / f"{name}.png", dpi=125)
    plt.close(fig)
    (FIGS / f"{name}.json").write_text(json.dumps(dict(title=title, caption=" ".join(paras), values=values), indent=1, ensure_ascii=False, default=float))
    print("figure", name)


def place_labels(ax, items, fontsize=8.5, curves=None):
    """items: (x, y, text, colour). Each name goes beside its point, first on the side away from the nearest other point, and moves up until
    it overlaps no earlier name and no plotted curve (rule 4: names on the figure, no legend). curves: the Line2D objects to keep clear of."""
    fig = ax.figure
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    pts = []
    for ln in (curves if curves is not None else ax.lines):
        xy = ax.transData.transform(np.column_stack(ln.get_data()).astype(float))
        if len(xy) > 1:
            f = np.linspace(0.0, 1.0, 12)[None, :, None]
            pts.append((xy[:-1, None, :] * (1 - f) + xy[1:, None, :] * f).reshape(-1, 2))
    pts = np.concatenate(pts) if pts else np.zeros((0, 2))
    boxes = []
    ylo, yhi = ax.get_ylim()
    step = 0.03 * (yhi - ylo)
    dx = 0.012 * (ax.get_xlim()[1] - ax.get_xlim()[0])
    for i, (x, y, txt, col) in enumerate(items):
        others = [it[0] for j, it in enumerate(items) if j != i]
        near = min(others, key=lambda o: abs(o - x)) if others else x - 1.0
        sides = (True, False) if near <= x else (False, True)
        placed = False
        for k in range(60):
            for right in sides:
                t = ax.text(x + (dx if right else -dx), y + step * (0.5 + k), txt, color=col, fontsize=fontsize,
                            ha="left" if right else "right", va="bottom")
                bb = t.get_window_extent(r).expanded(1.04, 1.12)
                hit = len(pts) and ((pts[:, 0] > bb.x0) & (pts[:, 0] < bb.x1) & (pts[:, 1] > bb.y0) & (pts[:, 1] < bb.y1)).any()
                if not hit and not any(bb.overlaps(b) for b in boxes) and bb.y1 < ax.bbox.y1:
                    boxes.append(bb)
                    placed = True
                    break
                t.remove()
            if placed:
                break
        if not placed:
            ax.text(x, y, txt, color=col, fontsize=fontsize, ha="center", va="bottom")
    return boxes


def run_dir(site, res):
    if res.startswith("fix"):
        return FTP / "runs" / site / res
    if res.startswith("nojudge_"):
        return S3 / "runs" / site / res
    if res.startswith("abl_band_"):
        return S2 / "runs" / site / res
    if site == "B173nb_b10" and res.startswith("prop_"):
        prior = "LoD2" if "LoD2" in res else "ALS"
        return S0 / "stage0" / f"b{1 if res.endswith('s0') else 2}_{prior}"
    return S1 / "stage1" / site / res


def mesh_path(site, res):
    return run_dir(site, res) / "post/mesh_tsdf.ply"


def done(site, res):
    f = run_dir(site, res) / "receipt.json"
    if res.startswith("fix"):
        return f.exists() and json.loads(f.read_text()).get("status") == "PASS" and mesh_path(site, res).exists()
    return mesh_path(site, res).exists()


# ------------------------------------------------------------------------------------------------ meshes (fill task figs_fl_common)
def ply_open(path):
    """copied from scripts/phd/main_fill_v1/figs_fl_common.py ply_open (itself figs_bl.ply_open): memory maps (vertex records, faces)."""
    with open(path, "rb") as f:
        head = []
        while True:
            ln = f.readline().decode("ascii", "replace").strip()
            head.append(ln)
            if ln == "end_header":
                break
        off = f.tell()
    elems = []
    for ln in head:
        p = ln.split()
        if p and p[0] == "element":
            elems.append([p[1], int(p[2]), []])
        elif p and p[0] == "property":
            elems[-1][2].append(p[1:])
    (vn, nv, vp), (fn, nf, fp) = elems[0], elems[1]
    vdt = np.dtype([(q[1], _TY[q[0]]) for q in vp])
    fdt = np.dtype([("n", _TY[fp[0][1]]), ("i", _TY[fp[0][2]], (3,))])
    vm = np.memmap(path, dtype=vdt, mode="r", offset=off, shape=(nv,))
    fm = np.memmap(path, dtype=fdt, mode="r", offset=off + nv * vdt.itemsize, shape=(nf,))
    return vm, fm


def crop_mesh(path, keep_vertex):
    """triangles with a vertex for which keep_vertex(V) is true -> (V, F) compact."""
    vm, fm = ply_open(path)
    V = np.stack([np.asarray(vm["x"], np.float64), np.asarray(vm["y"], np.float64), np.asarray(vm["z"], np.float64)], 1)
    kv = keep_vertex(V)
    Fi = np.asarray(fm["i"])
    Fc = Fi[kv[Fi].any(1)].astype(np.int64)
    u, inv = np.unique(Fc.ravel(), return_inverse=True)
    return V[u], inv.reshape(-1, 3)


def plane_segments(V, Fc, c, t, L):
    """copied from scripts/phd/main_fill_v1/figs_fl_common.py plane_segments (stage 2's figs_s2): the triangles crossing the vertical plane
    through c along t, as (s, z) segments, cropped to |s| <= L."""
    npn = np.array([-t[1], t[0], 0.0])
    d = (V - c) @ npn
    dt = d[Fc]
    cross = (dt.min(1) < 0) & (dt.max(1) > 0)
    F_, d_ = Fc[cross], dt[cross]
    ms, Xs = [], []
    for a, b_ in ((0, 1), (1, 2), (2, 0)):
        m = (d_[:, a] < 0) != (d_[:, b_] < 0)
        w = d_[:, a] / np.where(m, d_[:, a] - d_[:, b_], 1.0)
        ms.append(m)
        Xs.append(V[F_[:, a]] + w[:, None] * (V[F_[:, b_]] - V[F_[:, a]]))
    ms = np.stack(ms, 1)
    Xs = np.stack(Xs, 1)
    ok = ms.sum(1) == 2
    idx = np.argsort(~ms[ok], axis=1, kind="stable")[:, :2]
    X2 = np.take_along_axis(Xs[ok], idx[:, :, None].repeat(3, 2), 1)
    sv = (X2[..., :2] - c[:2]) @ t[:2]
    seg = np.stack([sv, X2[..., 2]], -1)
    return seg[np.abs(sv).min(1) <= L]


def dist_to_mesh(V, F, P):
    import open3d as o3d
    sc = o3d.t.geometry.RaycastingScene()
    if len(F) == 0:
        return np.full(len(P), np.inf)
    sc.add_triangles(o3d.core.Tensor(np.asarray(V, np.float32)), o3d.core.Tensor(np.asarray(F, np.uint32)))
    return sc.compute_distance(o3d.core.Tensor(np.asarray(P, np.float32))).numpy().astype(np.float64)


# ------------------------------------------------------------------------------------------------ figure 1 and 1b
def measure_new(site, prior, res):
    for base in (FTP / "measure", S2 / "measure"):
        f = base / site / f"{prior}__{res}.npz"
        if f.exists():
            z = np.load(f)
            return z["gentle_row"], z["new"], str(f).replace(str(PH), "PH")
    return None


def hist_lines(ax, curves, lo, hi, bw=0.5):
    edges = np.arange(lo, hi + bw, bw)
    cen = 0.5 * (edges[1:] + edges[:-1])
    out = {}
    for name, (vals, color, ls, lw) in curves.items():
        v = vals[np.isfinite(vals)]
        h, _ = np.histogram(np.clip(v, lo, hi - 1e-6), edges)
        sh = 100.0 * h / max(len(v), 1)
        ax.plot(cen, sh, color=color, ls=ls, lw=lw)
        k = int(np.argmax(sh))
        out[name] = dict(mode_cm=float(cen[k]), median_cm=float(np.median(v)) if len(v) else None, n=int(len(v)),
                         unread=int((~np.isfinite(vals)).sum()), peak_share=float(sh[k]), colour=color)
    return out, cen


def peak_items(vals):
    """one name per curve at its peak; the two seeds of the method share one name when their peaks are within 1 cm."""
    items, used = [], set()
    s0, s1 = vals.get("본 방법 씨앗 0"), vals.get("본 방법 씨앗 1")
    if s0 and s1 and abs(s0["mode_cm"] - s1["mode_cm"]) <= 1.0:
        top = max((s0, s1), key=lambda v: v["peak_share"])
        items.append((top["mode_cm"], top["peak_share"], f"본 방법 씨앗 0·1\n{s0['mode_cm']:+.1f}·{s1['mode_cm']:+.1f}", top["colour"]))
        used |= {"본 방법 씨앗 0", "본 방법 씨앗 1"}
    for k, v in vals.items():
        if k not in used:
            items.append((v["mode_cm"], v["peak_share"], f"{k}\n{v['mode_cm']:+.1f}", v["colour"]))
    return items


def fig_dist(name, site, prior, pos_rows, lines_spec, tau_cm, title_case, caption_rows):
    """the distribution of 'new' (cm) on the given gentle rows for the given results."""
    curves, srcs, missing = {}, {}, []
    gref = None
    for lab, res, color, ls, lw in lines_spec:
        m = measure_new(site, prior, res)
        if m is None:
            missing.append(f"{lab}({res})")
            continue
        g, new, src = m
        if gref is None:
            gref = g
        elif not np.array_equal(g, gref):
            raise RuntimeError(f"gentle rows differ: {res}")
        curves[lab] = (100.0 * new[pos_rows], color, ls, lw)
        srcs[lab] = src
    fig, ax = plt.subplots(figsize=(12.5, 5.6))
    vals, cen = hist_lines(ax, curves, -15.0, 20.0)
    hist_curves = list(ax.lines)
    prior_lab = next((k for k in curves if "학습 전" in k), None)
    pm = vals[prior_lab]["mode_cm"] if prior_lab else 0.0
    ax.set_xlabel("결과 면 높이 − 참값 높이 (cm, 0.5 cm 칸)")
    ax.set_ylabel("행의 몫 (%)")
    ax.set_xlim(-15, 20)
    ymax = max(v["peak_share"] for v in vals.values()) if vals else 1.0
    ax.set_ylim(0, ymax * 1.42)
    wL, wT = 100 * WD["L"][f"{site}/{prior}"]["w_roof"], 100 * WD["T"][f"{site}/{prior}"]["w_roof"]
    vl = [(tau_cm, DARK, f"τ {tau_cm:.1f}")]
    vl += [(wL, BLUE, f"w L {wL:.1f}")] if abs(wL - tau_cm) > 0.05 else []
    vl += [(wT, ORANGE, f"w T {wT:.1f}")] if abs(wT - tau_cm) > 0.05 else []
    for k, (dx, col, lab) in enumerate(sorted(vl)):
        for sgn in (-1, 1):
            ax.axvline(pm + sgn * dx, color=col, lw=0.9, ls=":")
        ax.text(pm + dx + 0.15, ymax * (1.38 - 0.07 * k), lab, color=col, fontsize=8.5, ha="left", va="top")
    place_labels(ax, peak_items(vals), curves=hist_curves)
    return fig, vals, srcs, missing, pm


def fig1():
    f = FP["fig1"]
    z = np.load(FTP / "prep/figpos_fig1_rows.npz")
    pos = z["pos_in_gentle"].astype(np.int64)
    spec = [("본 방법 씨앗 0", "prop_ALS_s0", GREY, "-", 1.6), ("본 방법 씨앗 1", "prop_ALS_s1", GREY, "--", 1.6),
            ("판 A (L)", "fixA_ALS_s0", BLUE, "-", 2.2), ("판 A (T)", "fixAT_ALS_s0", ORANGE, "-", 2.2),
            ("허용 구간 없애기", "abl_band_ALS_s0", GREEN, "-", 1.6), ("학습 전 사전 정보", "samepath_ALS", DARK, ":", 1.8)]
    fig, vals, srcs, missing, pm = fig_dist("fig1", "B173nb_b10", "ALS", pos, spec, 14.70, "B173 주변 항공 LiDAR", None)
    m0, m1 = vals["본 방법 씨앗 0"]["mode_cm"], vals["본 방법 씨앗 1"]["mode_cm"]
    mb = vals.get("허용 구간 없애기", {}).get("mode_cm")
    title = (f"B173 주변 항공 LiDAR 면 1에서 본 방법의 봉우리({m0:+.1f}·{m1:+.1f} cm)는 사전 정보({pm:+.1f} cm)보다 위에 있다"
             + (f"; 허용 구간을 없앤 학습은 {mb:+.1f} cm로 옮겼다" if mb is not None else "") + " — 판 A는 두 읽기 모두 관문에 걸려 학습하지 않았다")
    cap = [f"지지 일치(코드 2) 완만한 지붕 행 {len(pos):,}개(2단계 결정 6 그림과 같은 행), 참값 점마다 연직선이 결과 메시와 만나는 높이 − 참값 높이. "
           f"세로선 = 학습 전 사전 정보의 봉우리 {pm:+.1f} cm에서 ±w(읽기 L, 읽기 T)와 ±τ. w는 두 읽기 모두 관문 전에 구한 값이다."
           + (f" 결과 없음: {', '.join(missing)}." if missing else ""),
           "봉우리·중앙값(cm, 읽은 행): " + "; ".join(f"{k} {v['mode_cm']:+.1f}·{v['median_cm']:+.1f} ({v['n']:,})" for k, v in vals.items())]
    save(fig, "fig1_B173nb_ALS_face1", title, cap, dict(rows=int(len(pos)), prior_mode_cm=pm, curves=vals, sources=srcs, missing=missing))


def fig1b():
    a = CFG["figure_places_added"]["fig1b"]
    g = np.load(S2 / "measure/B0_b10/ALS__prop_ALS_s0.npz")["gentle_row"]
    se = np.load(S1 / "defs/B0_b10/rows_ALS.npz")["surf_ext"]
    pos = np.nonzero(se[g] == a["face"])[0]
    assert len(pos) == a["n_rows"], (len(pos), a["n_rows"])
    spec = [("본 방법 씨앗 0", "prop_ALS_s0", GREY, "-", 1.6), ("본 방법 씨앗 1", "prop_ALS_s1", GREY, "--", 1.6),
            ("판 A (L, w = τ)", "fixA_ALS_s0", BLUE, "-", 2.2), ("판 A (T)", "fixAT_ALS_s0", ORANGE, "-", 2.2),
            ("학습 전 사전 정보", "samepath_ALS", DARK, ":", 1.8)]
    fig, vals, srcs, missing, pm = fig_dist("fig1b", "B0_b10", "ALS", pos, spec, 12.66, "B0 항공 LiDAR", None)
    # 3,848 rows in 0.5 cm bins: the peak moves by a bin or more between runs of one setting (the method's seeds -1.8 / -1.2, fix A
    # reading L = the method's setting -0.2), so the title is written from the medians
    med = {k: v["median_cm"] for k, v in vals.items()}
    t, l_ = med.get("판 A (T)"), med.get("판 A (L, w = τ)")
    runs = [v for k, v in med.items() if "학습 전" not in k and v is not None]
    together = (max(runs) - min(runs)) < 0.5 if runs else False
    title = (f"B0 항공 LiDAR 면 0의 높이 차 중앙값은 본 방법 {med['본 방법 씨앗 0']:+.1f}·{med['본 방법 씨앗 1']:+.1f} cm"
             + (f", 판 A 읽기 T {t:+.1f} cm" if t is not None else "") + (f", 읽기 L(w = τ) {l_:+.1f} cm" if l_ is not None else "")
             + f", 학습 전 사전 정보 {med.get('학습 전 사전 정보', float('nan')):+.1f} cm다" + (" — 학습한 결과의 곡선이 겹친다" if together and t is not None else ""))
    cap = [f"폭이 좁아진 유일한 경우(B0 항공 LiDAR, 읽기 T)에 그림 1과 같은 꼴로 학습 전에 더한 그림. 지지 일치 완만한 지붕 행 가운데 "
           f"면 0의 {len(pos):,}행. 세로선 = 학습 전 사전 정보의 봉우리에서 ±w(읽기 T; 읽기 L은 w = τ)와 ±τ."
           + (f" 결과 없음: {', '.join(missing)}." if missing else ""),
           "봉우리·중앙값(cm, 읽은 행): " + "; ".join(f"{k} {v['mode_cm']:+.1f}·{v['median_cm']:+.1f} ({v['n']:,})" for k, v in vals.items())]
    save(fig, "fig1b_B0_ALS_face0", title, cap, dict(rows=int(len(pos)), prior_mode_cm=pm, curves=vals, sources=srcs, missing=missing))


# ------------------------------------------------------------------------------------------------ middle-report figure for A8 (bands)
BAND_KO = (("lt_w", "w 안"), ("w_tau", "w~τ"), ("tau_2tau", "τ~2τ"), ("2tau_4tau", "2τ~4τ"), ("ge_4tau", "4τ 넘음"))


def fig_a8(site, prior, rd):
    """A8 (order 9.1-4): the shares of agree pixels whose rendered depth at 30,000 is within w and between w and tau of the prior depth, for
    the method's two seeds and fix A of reading rd (band_w.py output). Two panels, the same scale; fix A in its reading's colour."""
    f = FTP / "mech" / f"bands_{site}_{prior}_{rd}.json"
    d = json.loads(f.read_text())
    fixres = f"fix{'A' if rd == 'L' else 'AT'}_{prior}_s0"
    order = [("본 방법 씨앗 0", f"prop_{prior}_s0", GREY), ("본 방법 씨앗 1", f"prop_{prior}_s1", GREY),
             (f"판 A (읽기 {rd})", fixres, BLUE if rd == "L" else ORANGE)]
    sel = "agree"
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8))
    vals = {}
    for ax, (key, ko) in zip(axes, BAND_KO[:2]):
        for i, (lab, res, col) in enumerate(order):
            r = d["results"].get(res)
            if r is None:
                ax.text(i, 0.5, "결과 없음", ha="center", rotation=90, fontsize=9, transform=ax.get_xaxis_transform())
                vals.setdefault(lab, dict(result=res, status="결과 없음"))
                continue
            v = 100.0 * r[sel]["shares"][key]
            ax.scatter([i], [v], s=110, color=col, zorder=3)
            ax.text(i + 0.12, v, f"{v:.2f} %", ha="left", va="center", fontsize=10, color=col if col != GREY else DARK)
            vals.setdefault(lab, dict(result=res, n=r[sel]["n"], shares={k: 100.0 * r[sel]["shares"][k] for k, _ in BAND_KO}))
        ax.set_xticks(range(len(order))); ax.set_xticklabels([o[0] for o in order], fontsize=9.5)
        ax.set_xlim(-0.6, len(order) - 0.2)
        ax.set_title(f"({'가' if key == 'lt_w' else '나'}) {ko}의 몫 (%)", loc="left", fontsize=11)
        got = [100.0 * d["results"][o[1]][sel]["shares"][key] for o in order if o[1] in d["results"]]
        if got:
            lo_, hi_ = min(got), max(got)
            pad = max(1.0, 0.3 * (hi_ - lo_))
            ax.set_ylim(max(0.0, lo_ - pad), min(100.0, hi_ + pad))
        ax.grid(axis="y", color="#eeeeee", lw=0.8)
    m = [vals[o[0]]["shares"] for o in order[:2] if "shares" in vals.get(o[0], {})]
    fx = vals.get(order[2][0], {}).get("shares")
    case = f"{SITE_KO.get(site, site)} {PRIOR_KO.get(prior, prior)}"
    if fx and len(m) == 2:
        mw, mt = np.mean([x["lt_w"] for x in m]), np.mean([x["w_tau"] for x in m])
        title = (f"{case} 일치 화소에서 판 A(읽기 {rd})의 w 안 몫은 {fx['lt_w']:.2f} %(본 방법 평균 {mw:.2f} %), "
                 f"w~τ 몫은 {fx['w_tau']:.2f} %(본 방법 평균 {mt:.2f} %)다")
    else:
        title = f"{case} 일치 화소의 깊이 구간 몫: 판 A(읽기 {rd}) 결과 없음"
    wcase = WD[rd][f"{site}/{prior}"]
    cap = [f"30,000회 덤프의 학습 영상 {d['views']}장에서, 학습 전 판정이 일치인 패치를 보는 사전 정보 화소(렌더 깊이가 있는 것)의 |렌더 깊이 − 사전 정보 깊이|를 "
           f"화소마다 w, τ로 나눈 몫. w는 읽기 {rd}의 지도(지붕 {100 * wcase['w_roof']:.1f} cm, 벽 {100 * wcase['w_wall']:.1f} cm), τ는 사전 정보의 허용 오차 지도. "
           "세로축은 칸마다 값 둘레만 보인다(0에서 시작하지 않음).",
           "구간 몫(w 안·w~τ·τ~2τ·2τ~4τ·4τ 넘음, %, 화소 수): " + "; ".join(
               f"{k} " + "·".join(f"{v['shares'][b]:.2f}" for b, _ in BAND_KO) + f" ({v['n']:,})" for k, v in vals.items() if "shares" in v)]
    save(fig, f"figA8_{site.split('_')[0]}_{prior}_{rd}", title, cap, dict(source=str(f).replace(str(PH), "PH"), selection=sel, values=vals))


# ------------------------------------------------------------------------------------------------ figure 2 (section)
def fig2():
    f = FP["fig2"]
    sec = f["section"]
    c = np.asarray(sec["centre_xyz"], np.float64)
    t = np.array([sec["direction_t_xy"][0], sec["direction_t_xy"][1], 0.0]); t /= np.linalg.norm(t)
    n = np.array([-t[1], t[0], 0.0])
    L = float(sec["half_length_m"])
    zlo, zhi = sec["z_range_m"]
    z = np.load(FTP / "prep/figpos_fig2_rows.npz")
    gs, gd, gz = z["gt_s"].astype(np.float64), z["gt_d"].astype(np.float64), z["gt_z"].astype(np.float64)
    G = c[None, :] + gs[:, None] * t[None, :] + gd[:, None] * n[None, :]
    G[:, 2] = gz
    prior_seg = z["prior_segments"]
    site = "R1rep_b10"
    panels = [("본 방법 씨앗 0", "prop_ALS_s0"), ("판 A (L, w = τ)", "fixA_ALS_s0")]

    def keep(V):
        d = (V - c) @ n; s_ = (V - c) @ t
        return (np.abs(d) <= 1.0) & (np.abs(s_) <= L + 1.5)
    from matplotlib.collections import LineCollection
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.4), sharey=True)
    vals = {}
    for ax, (lab, res) in zip(axes, panels):
        ax.scatter(gs, gz, s=1.5, color=GREY, alpha=0.5, lw=0)
        ax.add_collection(LineCollection(prior_seg, colors=ORANGE, linewidths=1.6))
        if done(site, res):
            V, F_ = crop_mesh(mesh_path(site, res), keep)
            ax.add_collection(LineCollection(plane_segments(V, F_, c, t, L), colors=BLUE, linewidths=2.0))
            d = dist_to_mesh(V, F_, G)
            vals[lab] = dict(result=res, gt_points=int(len(G)), R_0_2=float((d <= 0.2).mean()), median_abs_cm=float(100 * np.median(d)))
            ax.text(-L + 0.2, zhi - 0.15, f"{lab}\nR(0.2 m) {100 * vals[lab]['R_0_2']:.1f} %", color=BLUE, fontsize=10, va="top")
        else:
            ax.text(0, 0.5 * (zlo + zhi), "결과 없음", ha="center")
            vals[lab] = dict(result=res, status="결과 없음")
        ax.set_xlim(-L, L); ax.set_ylim(zlo, zhi)
        ax.set_title(lab, loc="left", fontsize=11)
        ax.set_xlabel("단면을 따른 거리 (m)")
    axes[0].set_ylabel("높이 z (m)")
    if done(site, "samepath_ALS"):
        Vp, Fp = crop_mesh(mesh_path(site, "samepath_ALS"), keep)
        dp = dist_to_mesh(Vp, Fp, G)
        vals["학습 전 사전 정보"] = dict(result="samepath_ALS", R_0_2=float((dp <= 0.2).mean()), median_abs_cm=float(100 * np.median(dp)))
    a_, b_ = vals.get(panels[0][0], {}), vals.get(panels[1][0], {})
    if a_.get("R_0_2") is not None and b_.get("R_0_2") is not None:
        title = (f"R1 항공 LiDAR 영상이 틀린 곳의 단면에서 참값 0.2 m 안 몫은 본 방법 {100 * a_['R_0_2']:.1f} %, 판 A {100 * b_['R_0_2']:.1f} %다 "
                 "— 이 경우 w = τ라 판 A는 손실을 바꾸지 않는다")
    else:
        title = "R1 항공 LiDAR 영상이 틀린 곳의 단면: 판 A 결과 없음"
    cap = (f"영상이 틀린 곳의 덩어리(516패치, 32.5 m², 참값 한 층, 참값 점 32,879)의 중심을 긴 축으로 지나는 12 m × 0.5 m 단면. 파랑 = 결과 메시, "
           f"주황 = 학습 전 사전 정보, 회색 점 = 띠 안의 참값 점 {len(G):,}개. 참값 점에서 결과 메시까지 0.2 m 안 몫(R(0.2 m))과 거리 중앙값: "
           + "; ".join(f"{k} {100 * v['R_0_2']:.1f} %, {v['median_abs_cm']:.1f} cm" for k, v in vals.items() if v.get("R_0_2") is not None))
    save(fig, "fig2_R1_ALS_section", title, cap, dict(section=sec, values=vals))


# ------------------------------------------------------------------------------------------------ figure 3 and 4 (plan maps)
def plan_panels(name, site, prior, idx, codes, centres, extent, panels, mark, rule_fn, title_fn, cap_fn):
    fig, axes = plt.subplots(1, len(panels), figsize=(7.2 * len(panels), 7.8), sharey=True)
    vals = {}
    for ax, (lab, res) in zip(np.atleast_1d(axes), panels):
        ok = rule_fn(res)
        if ok is None:
            ax.text(0.5, 0.5, "결과 없음", transform=ax.transAxes, ha="center")
            vals[lab] = dict(result=res, status="결과 없음")
        else:
            for cd, edge in ((4, "none"), (13, DARK)):
                m = codes == cd
                ax.scatter(centres[m & ok, 0], centres[m & ok, 1], s=22, marker="s", color=BLUE, edgecolors=edge, linewidths=0.8)
                ax.scatter(centres[m & ~ok, 0], centres[m & ~ok, 1], s=22, marker="s", color=LIGHT, edgecolors=edge if cd == 13 else GREY, linewidths=0.8)
            if mark is not None:
                ax.scatter(centres[mark, 0], centres[mark, 1], s=3, color=RED, zorder=5)
            vals[lab] = dict(result=res, **{f"code{cd}": dict(patches=int((codes == cd).sum()), within_0_2=int((ok & (codes == cd)).sum()),
                                                               share=float(ok[codes == cd].mean()) if (codes == cd).any() else None) for cd in (4, 13)})
        ax.set_xlim(extent[0], extent[2]); ax.set_ylim(extent[1], extent[3]); ax.set_aspect("equal")
        ax.set_title(lab, loc="left", fontsize=11)
        ax.set_xlabel("x (m)")
    np.atleast_1d(axes)[0].set_ylabel("y (m)")
    save(fig, name, title_fn(vals), cap_fn(vals), dict(values=vals, patches=int(len(idx))))


def fig3():
    """R1 LoD2 missing patches (codes 4 and 13) from above; colour = the result mesh within 0.2 m of the patch centre (on the prior surface).
    Rule 8: wall patches stack in a plan view and codes 4 and 13 hide each other, so the codes go to two rows (가: code 4, 나: code 13);
    the two columns are the compared pair. In every panel the patches within 0.2 m are drawn over the others (the same rule in both
    columns); red dots = patches whose reading fix B changed (item 2)."""
    f = FP["fig3"]
    site, prior = "R1rep_b10", "LoD2"
    R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
    idx = np.asarray(f["patch_list"]["index"], np.int64)
    codes = R["code_ext_v3"][idx].astype(np.int64)
    cen = R["centre"][idx].astype(np.float64)
    L = np.load(FTP / "checks/dry" / f"r16B_{site}_{prior}" / "model/monitor/locations.npz")
    mark = L["own_depth_changed"].astype(bool)[idx]
    ext = f["extent_xy"]
    zl, zh = cen[:, 2].min() - 5, cen[:, 2].max() + 5
    panels = [("본 방법 씨앗 0", "prop_LoD2_s0"), ("판 B", "fixB_LoD2_s0")]
    oks = {}
    for lab, res in panels:
        if not done(site, res):
            oks[lab] = None
            continue
        V, F_ = crop_mesh(mesh_path(site, res), lambda V: (V[:, 0] >= ext[0] - 2) & (V[:, 0] <= ext[2] + 2) & (V[:, 1] >= ext[1] - 2) & (V[:, 1] <= ext[3] + 2)
                          & (V[:, 2] >= zl) & (V[:, 2] <= zh))
        oks[lab] = dist_to_mesh(V, F_, cen) <= 0.2
    fig, axes = plt.subplots(2, 2, figsize=(12.0, 15.5), sharex=True, sharey=True)
    vals = {}
    for r_, (cd, rlab) in enumerate(((4, "(가) 코드 4: 사전 정보가 맞는 결측 패치"), (13, "(나) 코드 13: 사전 정보가 틀린 결측 패치"))):
        m = codes == cd
        for c_, (lab, res) in enumerate(panels):
            ax = axes[r_, c_]
            ok = oks[lab]
            if ok is None:
                ax.text(0.5, 0.5, "결과 없음", transform=ax.transAxes, ha="center")
            else:
                key = np.round(cen[m, :2] / 0.3).astype(np.int64)
                u, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
                inv = inv.ravel()
                xy = np.stack([np.bincount(inv, weights=cen[m, j]) / cnt for j in (0, 1)], 1)
                share = np.bincount(inv, weights=ok[m].astype(float)) / cnt
                chg = np.bincount(inv, weights=mark[m].astype(float)) > 0
                order = np.argsort(cnt)[::-1]
                sc = ax.scatter(xy[order, 0], xy[order, 1], s=14 + 9 * np.sqrt(cnt[order]), marker="s", c=share[order], cmap=SHARE_CMAP, vmin=0, vmax=1,
                                edgecolors=GREY, linewidths=0.5)
                ax.scatter(xy[chg, 0], xy[chg, 1], s=4, color=RED, zorder=5)
                vals.setdefault(lab, dict(result=res))[f"code{cd}"] = dict(patches=int(m.sum()), within_0_2=int((ok & m).sum()), share=float(ok[m].mean()) if m.any() else None,
                                                                         changed=int((m & mark).sum()), changed_within=int((m & mark & ok).sum()))
                ax.text(0.03, 0.97, f"0.2 m 안 {int((ok & m).sum())}/{int(m.sum())}", transform=ax.transAxes, va="top", fontsize=10.5, color=BLUE)
            ax.set_xlim(ext[0], ext[2]); ax.set_ylim(ext[1], ext[3]); ax.set_aspect("equal")
            ax.set_title(f"{rlab}\n{lab}" if c_ == 0 else f"\n{lab}", loc="left", fontsize=10.5)
            if r_ == 1:
                ax.set_xlabel("x (m)")
            if c_ == 0:
                ax.set_ylabel("y (m)")
    cax = fig.add_axes([0.92, 0.42, 0.012, 0.16])
    cb = fig.colorbar(plt.cm.ScalarMappable(cmap=SHARE_CMAP, norm=plt.Normalize(0, 1)), cax=cax)
    cb.set_label("자리의 패치 가운데 0.2 m 안 몫", fontsize=8.5)
    cb.ax.tick_params(labelsize=7.5)
    a_, b_ = vals.get("본 방법 씨앗 0", {}), vals.get("판 B", {})
    if "code4" in a_ and "code4" in b_:
        title = (f"R1 LoD2 결측 패치에서 결과 메시가 사전 정보 면 0.2 m 안인 패치는 판 B에서 코드 4가 {a_['code4']['within_0_2']} → {b_['code4']['within_0_2']}개"
                 f"({a_['code4']['patches']}개 가운데), 코드 13이 {a_['code13']['within_0_2']} → {b_['code13']['within_0_2']}개({a_['code13']['patches']}개 가운데)다")
    else:
        title = "R1 LoD2 결측 패치: 판 B 결과 없음"
    cap = [f"평가 범위의 결측 패치(코드 4 {int((codes == 4).sum())}개, 코드 13 {int((codes == 13).sum())}개)를 위에서 본 것. 높이가 다른 벽 패치가 위에서 겹치므로(코드 4의 198개가 "
           "51자리에, 한 자리에 많게는 28개) 0.3 m 자리마다 묶어 그렸다: 짙기 = 그 자리 패치 가운데 결과 메시가 패치 중심(사전 정보 면 위) 0.2 m 안인 몫(사전 정보 면을 지킴), "
           "크기 = 패치 수, 빨간 점 = 일 2에서 읽기가 바뀐 패치가 있는 자리. 같은 파랑이 코드 4(가)에서는 좋은 쪽, 코드 13(나)에서는 나쁜 쪽이다. 두 코드는 겹쳐 줄을 나눴다(규칙 8).",
           "0.2 m 안 패치 수(읽기가 바뀐 패치 가운데): " + "; ".join(
               f"{k}: 코드 4 {x['code4']['within_0_2']}/{x['code4']['patches']} ({x['code4']['changed_within']}/{x['code4']['changed']}), "
               f"코드 13 {x['code13']['within_0_2']}/{x['code13']['patches']} ({x['code13']['changed_within']}/{x['code13']['changed']})" for k, x in vals.items() if "code4" in x)]
    save(fig, "fig3_R1_LoD2_missing_map", title, cap, dict(values=vals, patches=int(len(idx))), right=0.9)


def fig4():
    """plan view of the skylight case region and its 2 m band (the fill task's undecidable_aux view); dots = the thinned GT rows of the
    missing patches at their own GT position, blue when the GT point is within 0.2 m of the result's training-view mesh (dist71 d2 r_d);
    an enlarged inset of the missing patches (rule 10: they are 2.7 % of the place's area)."""
    f = FP["fig4"]
    site, prior = "B173nb_b10", "ALS"
    R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
    idx = np.asarray(f["missing"]["index"], np.int64)
    codes = np.asarray(f["missing"]["code"], np.int64)
    case = np.asarray(f["case_region"]["patch_list"], np.int64)
    band = np.asarray(f["band"]["patch_list"], np.int64)
    outside = np.asarray(f["missing_in_extent_outside_place"]["index"], np.int64)
    ext, zext = f["extent_xy"], f["zoom_candidate"]["extent_xy"]
    rows = np.load(S1 / "defs" / site / f"rows_{prior}.npz")
    G = np.load(S1 / "defs" / site / "gt_classes.npz")
    X = {0: G["xyz_gt_points"]}
    if "xyz_gt_primary" in G.files:
        X[1] = G["xyz_gt_primary"]
    panels = [("본 방법 씨앗 0", "prop_ALS_s0"), ("판 B", "fixB_ALS_s0")]
    fig, axes = plt.subplots(1, 2, figsize=(13, 9.5), sharey=True)
    vals = {}

    def draw(ax, P, ok, c13, big):
        ax.scatter(R["centre"][band, 0], R["centre"][band, 1], s=6 if big else 30, marker="s", color="#f0f0f0", lw=0)
        ax.scatter(R["centre"][case, 0], R["centre"][case, 1], s=6 if big else 30, marker="s", color="#d8d8d8", lw=0)
        ax.scatter(R["centre"][outside, 0], R["centre"][outside, 1], s=8 if big else 40, marker="s", color=EXCL, lw=0)
        if P is None:
            return
        sz = 10 if big else 26
        for m_, col in ((ok, BLUE), (~ok, "#9e9e9e")):
            ax.scatter(P[m_ & ~c13, 0], P[m_ & ~c13, 1], s=sz, color=col, lw=0, zorder=4)
            ax.scatter(P[m_ & c13, 0], P[m_ & c13, 1], s=sz, color=col, edgecolors=DARK, lw=0.9, zorder=5)

    for ax, (lab, res) in zip(axes, panels):
        fz = next((base / f"{site}_{prior}__{res}.npz" for base in (FTP / "dist", SD / "dist") if (base / f"{site}_{prior}__{res}.npz").exists()), None)
        P = ok = c13 = None
        if fz is None:
            ax.text(0.5, 0.5, "결과 없음", transform=ax.transAxes, ha="center")
            vals[lab] = dict(result=res, status="결과 없음")
        else:
            z = np.load(fz)
            rp, rd, ri = z["r_patch"].astype(np.int64), z["r_d"].astype(np.float64), z["r_idx"].astype(np.int64)
            sel = np.isin(rp, idx)
            src, pt = rows["src"][ri[sel]].astype(np.int64), rows["point"][ri[sel]].astype(np.int64)
            P = np.stack([X[int(k)][q, :2] for k, q in zip(src, pt)]) if sel.any() else np.zeros((0, 2))
            ok = rd[sel] <= 0.2
            c13 = np.isin(rp[sel], idx[codes == 13])
            e = {}
            for cd, m_ in ((4, ~c13), (13, c13)):
                e[f"code{cd}"] = dict(patches=int((codes == cd).sum()), rows=int(m_.sum()), within_0_2=int((ok & m_).sum()), share=float(ok[m_].mean()) if m_.any() else None)
            vals[lab] = dict(result=res, source=str(fz).replace(str(PH), "PH"), **e)
        draw(ax, P, ok, c13, True)
        ax.add_patch(plt.Rectangle((zext[0], zext[1]), zext[2] - zext[0], zext[3] - zext[1], fill=False, ec=DARK, lw=0.8, ls="--"))
        ins = ax.inset_axes([0.40, 0.60, 0.57, 0.36])
        draw(ins, P, ok, c13, False)
        ins.set_xlim(zext[0], zext[2]); ins.set_ylim(zext[1], zext[3]); ins.set_aspect("equal")
        ins.tick_params(labelsize=7)
        ins.set_title("결측 패치 둘레 확대", fontsize=8.5, loc="left")
        if lab in vals and "code4" in vals[lab]:
            e = vals[lab]
            ax.text(0.02, 0.985, f"0.2 m 안 행\n코드 4 {e['code4']['within_0_2']}/{e['code4']['rows']}\n코드 13 {e['code13']['within_0_2']}/{e['code13']['rows']}",
                    transform=ax.transAxes, fontsize=9.5, va="top", color=BLUE)
        ax.set_xlim(ext[0], ext[2]); ax.set_ylim(ext[1], ext[3]); ax.set_aspect("equal")
        ax.set_title(lab, loc="left", fontsize=11)
        ax.set_xlabel("x (m)")
    axes[0].set_ylabel("y (m)")
    a_, b_ = vals.get("본 방법 씨앗 0", {}), vals.get("판 B", {})
    if "code4" in a_ and "code4" in b_:
        title = (f"B173 주변 항공 LiDAR 유리 채광창 둘레의 결측 패치(코드 4)에서 참값 0.2 m 안 행은 본 방법 {a_['code4']['within_0_2']}개, "
                 f"판 B {b_['code4']['within_0_2']}개다(행 {a_['code4']['rows']}개)")
    else:
        title = "B173 주변 항공 LiDAR 유리 채광창 둘레: 판 B 결과 없음"
    cap = [("유리 채광창 사례 영역(짙은 회색 칸 163패치)과 2 m 둘레(옅은 회색 칸 751패치)를 위에서 본 것(빈칸 채우기 undecidable_aux와 같은 범위). 점 = 둘레의 결측 패치 "
            f"{len(idx)}개(코드 4 17, 코드 13 1)의 솎은 참값 행을 그 참값 점 자리에 찍은 것. 파랑 = 참값 점에서 결과 메시까지 0.2 m 안, 회색 = 아님, 검은 테두리 = 코드 13, "
            "갈색 칸 = 범위 안이지만 사례 영역과 둘레 밖의 결측 패치(평가에서 뺌, 4개). 점선 상자 = 오른쪽 위 확대 창의 범위. 사례 영역의 참값이 유리와 그 안쪽으로 여러 층인 "
            "패치는 24/163(14.7 %)이다(규칙 5). 결측 패치는 사례 영역과 둘레 넓이의 2.7 %다."),
           "0.2 m 안 행: " + "; ".join(f"{k} 코드 4 {x['code4']['within_0_2']}/{x['code4']['rows']}, 코드 13 {x['code13']['within_0_2']}/{x['code13']['rows']}"
                                       for k, x in vals.items() if "code4" in x)]
    save(fig, "fig4_B173nb_ALS_skylight", title, cap, dict(values=vals, missing_patches=idx.tolist()))


# ------------------------------------------------------------------------------------------------ figure 5 (bars)
def fig5():
    E = json.loads((FTP / "tables/eval_ft.json").read_text())["cases"]
    keys = list(E)
    panels = [("(가) 두 자료가 모두 맞는 곳의 거리 (cm), 판 A − 본 방법 평균", "c2", "dist", ("A", "AT")),
              ("(나) 결측 R(0.2 m) (%p), 판 B − 본 방법 평균", "c4", "R_0.2", ("B",)),
              ("(다) 결측 영역의 과거 형상 유입률 (%p, 코드 13), 판 B − 본 방법 평균", "c4", "infl13", ("B",))]
    fig, axes = plt.subplots(3, 1, figsize=(13, 11))
    vals = {}
    for ax, (ttl, place, m, fixes) in zip(axes, panels):
        xs = np.arange(len(keys))
        for i, k in enumerate(keys):
            row = E[k]["places"][place].get(m, {})
            mean = row.get("mean", {}).get("v")
            for j, fx in enumerate(fixes):
                r = row.get(f"read_{fx}", {})
                v = row.get(fx, {}).get("v")
                off = (j - (len(fixes) - 1) / 2) * 0.3
                if v is None or mean is None or r.get("grade") in ("표본 부족", None) or row.get(fx, {}).get("status") != "있음":
                    ax.text(i + off, 0, row.get(fx, {}).get("status") or r.get("grade") or "—", ha="center", va="bottom", fontsize=7.5, rotation=90)
                    continue
                crit = r.get("criterion") or 0.0
                ax.add_patch(plt.Rectangle((i + off - 0.14, -2 * crit), 0.28, 4 * crit, color="#f2f2f2", zorder=0))
                ax.add_patch(plt.Rectangle((i + off - 0.14, -crit), 0.28, 2 * crit, color="#dcdcdc", zorder=0))
                col = BLUE if fx == "A" else (ORANGE if fx == "AT" else GREEN)
                ax.bar(i + off, v - mean, 0.22, color=col)
                ax.text(i + off, v - mean, f"{v - mean:+.1f}\n{r.get('grade')}", ha="center", va="bottom" if v >= mean else "top", fontsize=7.5)
                vals.setdefault(ttl, {})[f"{k}/{fx}"] = dict(diff=v - mean, value=v, mean=mean, criterion=crit, grade=r.get("grade"), n=row.get(fx, {}).get("n"))
        ax.axhline(0, color=DARK, lw=0.6)
        ax.set_xlim(-0.6, len(keys) - 0.4)
        ax.set_xticks(np.arange(len(keys))); ax.set_xticklabels([E[k]["case"] for k in keys], fontsize=9)
        ax.set_title(ttl, loc="left", fontsize=10.5)
    cap = ("막대 = 고친 판 − 본 방법 두 씨앗의 평균(파랑 판 A 읽기 L, 주황 판 A 읽기 T, 초록 판 B). 짙은 띠 = ±기준, 옅은 띠 = ±기준의 두 배(발주 9.2). "
           "막대가 없는 경우는 그 판을 학습하지 않았거나(관문) 표본이 100점 미만이다.")
    save(fig, "fig5_bars", "두 판이 바꾼 크기: 경우마다 고친 판과 본 방법 평균의 차와 기준의 띠", cap, vals)


if __name__ == "__main__":
    todo = sys.argv[1:] or ["fig1", "fig1b", "fig2", "fig3", "fig4", "fig5"]
    for k in todo:
        if k.startswith("figA8:"):            # figA8:<site>:<prior>:<reading>
            fig_a8(*k.split(":")[1:])
        else:
            globals()[k]()
