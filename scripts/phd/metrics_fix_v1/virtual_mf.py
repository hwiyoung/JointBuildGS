"""PHD-MAIN-METRICS-FIX-v1 4.7: the three virtual-view options compared on the four trainings (jointbuildgs:dev, CPU; definitions =
configs metrics_fix_v1.json 'virtual_view_test').

  python virtual_mf.py            measures, the choice (written rule) -> /out/virtual/compare.json, /out/virtual/chosen.json
  python virtual_mf.py --figure   the main unseen wall seen from 3 m in front of the LoD2 wall plane, first mesh crossing coloured
                                  by its distance to the plane, the three options x four trainings -> /out/figs/virtual_options.png
options: current = the trial's meshes (/mt/gpu/<run>/mesh_virtual.ply: 16 views at 124 m, all Gaussians); option1 = 10 views 25 m in
front of the wall; option2 = the 16 views, only the Gaussians inside the TSDF box (/out/virtual/<option>/<run>/).
Measures per mesh: below-roof unseen patch centres within 0.5 m (mesh-level inheritance), above-roof centres within 0.2 m (past
shape), share of the mesh vertices at the unseen walls (within 0.2 m in the plane of a patch centre, within 2 m of the wall)
that lie within 0.2 m of the wall plane, GPU seconds and peak host memory. Choice: the largest LoD2 - ALS gap of the below-roof
share among the options whose mean seed variation is not larger than the current option's; ties by GPU time.
scientific_verdict: null."""
import json
import sys

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

from mf_common import FCFG, MT, OUT, jdump, log, setup_fonts
from src.phd.metrics_v2.surface import MeshScene

RUNS = ["b1_LoD2", "b2_LoD2", "b1_ALS", "b2_ALS"]
OPTS = ["current", "option1", "option2"]


def mesh_path(opt, run):
    return MT / "gpu" / run / "mesh_virtual.ply" if opt == "current" else OUT / "virtual" / opt / run / "mesh_virtual.ply"


def json_path(opt, run):
    return MT / "gpu" / run / "virtual.json" if opt == "current" else OUT / "virtual" / opt / run / "virtual.json"


def measures(opt, run, un):
    cu, li, nrm = un["centre"], un["label_inferred"], un["normal"]
    p = mesh_path(opt, run)
    m = o3d.io.read_triangle_mesh(str(p))
    V = np.asarray(m.vertices)
    sc = MeshScene(V, np.asarray(m.triangles))
    d = sc.distance(cu)
    dd, k = cKDTree(cu).query(V, distance_upper_bound=2.5, workers=-1)
    ok = np.isfinite(dd)
    vv = V[ok] - cu[k[ok]]
    nn = nrm[k[ok]]
    sd = (vv * nn).sum(1)
    inpl = np.linalg.norm(vv - sd[:, None] * nn, axis=1)
    wall = (inpl <= 0.2) & (np.abs(sd) <= 2.0)
    vj = json.loads(json_path(opt, run).read_text())
    sec = vj["seconds"]   # cumulative marks; GPU time = the renders of the training + virtual views and the TSDF (loading and the
    gpu_s = round(sec["virtual_tsdf"] - sec["floaters"], 1) if opt == "current" else round(sec["tsdf"] - sec["load"], 1)   # trial's other steps left out
    return dict(below_roof_within_0_5=round(float((d[li == 0] <= 0.5).mean()), 4), above_roof_within_0_2=round(float((d[li == 1] <= 0.2).mean()), 4),
                wall_vertices=int(wall.sum()), wall_plane_within_0_2=round(float((np.abs(sd[wall]) <= 0.2).mean()), 4) if wall.any() else None,
                gpu_seconds=gpu_s, peak_host_gb=vj["peak_host_gb"], triangles=vj["triangles"], views_virtual=len(vj["virtual"]),
                seen_below_roof_per_view=[v["seen_below_roof"] for v in vj["virtual"]])


def compare():
    un = np.load(MT / "defs/unseen.npz")
    res = {o: {r: measures(o, r, un) for r in RUNS} for o in OPTS}
    summ = {}
    for o in OPTS:
        v = res[o]
        var = [abs(v[f"b2_{p}"][k] - v[f"b1_{p}"][k]) for p in ("LoD2", "ALS") for k in ("below_roof_within_0_5", "above_roof_within_0_2")]
        gap = np.mean([v[f"b{s}_LoD2"]["below_roof_within_0_5"] - v[f"b{s}_ALS"]["below_roof_within_0_5"] for s in (1, 2)])
        summ[o] = dict(mean_seed_variation=round(float(np.mean(var)), 4), lod2_minus_als_gap=round(float(gap), 4),
                       mean_gpu_seconds=round(float(np.mean([v[r]["gpu_seconds"] for r in RUNS])), 1), max_peak_host_gb=max(v[r]["peak_host_gb"] for r in RUNS))
        log(o, summ[o])
    ok = [o for o in OPTS if summ[o]["mean_seed_variation"] <= summ["current"]["mean_seed_variation"]]
    best = max(ok, key=lambda o: (summ[o]["lod2_minus_als_gap"], -summ[o]["mean_gpu_seconds"]))
    rule = FCFG["virtual_view_test"]["choice_rule"]
    jdump(OUT / "virtual/compare.json", dict(rule=rule, per_run=res, summary=summ, eligible=ok, chosen=best, scientific_verdict=None))
    jdump(OUT / "virtual/chosen.json", dict(option=best, rule=rule, summary=summ[best], scientific_verdict=None))
    print("chosen", best, summ)


def figure():
    plt = setup_fonts()
    un = np.load(MT / "defs/unseen.npz")
    m = un["surf_ext"] == np.bincount(un["surf_ext"]).argmax()
    c = un["centre"][m]
    n = un["normal"][m][0]
    tvec = np.array([-n[1], n[0], 0.0])
    cc = c.mean(0)
    s = (c - cc) @ tvec
    zr = (c[:, 2].min(), c[:, 2].max())
    sw = (s.min() - 6, s.max() + 6)
    ss, zz = np.meshgrid(np.arange(sw[0], sw[1], 0.1), np.arange(zr[0] - 4, zr[1] + 6, 0.1)[::-1])
    P = cc[None, :] + ss.reshape(-1, 1) * tvec[None, :] + np.column_stack([np.zeros(ss.size), np.zeros(ss.size), zz.reshape(-1) - cc[2]])
    O = P + 3.0 * n[None, :]
    D = np.tile(-n, (len(O), 1))
    cols = np.array([[1, 1, 1], [0.17, 0.63, 0.17], [1.0, 0.5, 0.05], [0.12, 0.47, 0.71]])
    lab = un["label_inferred"][m]
    names = {"current": "지금 안(124 m, 16시점)", "option1": "안 1(벽 앞 25 m, 10시점)", "option2": "안 2(124 m, 상자 밖 가우시안 뺌)"}
    fig, axs = plt.subplots(3, 4, figsize=(22, 8.5), constrained_layout=True)
    for i, o in enumerate(OPTS):
        for j, r in enumerate(RUNS):
            ax = axs[i, j]
            p = mesh_path(o, r)
            if not p.exists():
                ax.set_axis_off()
                continue
            mm = o3d.io.read_triangle_mesh(str(p))
            sc = o3d.t.geometry.RaycastingScene()
            sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mm))
            t = sc.cast_rays(o3d.core.Tensor(np.concatenate([O, D], 1).astype(np.float32)))["t_hit"].numpy()
            k = np.zeros(len(t), int)
            k[np.abs(t - 3.0) <= 0.2] = 1
            k[t < 2.8] = 2
            k[(t > 3.2) & (t <= 10.0)] = 3
            ax.imshow(cols[k].reshape(ss.shape + (3,)), extent=[sw[0], sw[1], zr[0] - 4, zr[1] + 6], interpolation="nearest")
            ax.plot(s[lab == 1], c[lab == 1, 2], ",", color="#d62728", alpha=0.4)
            ax.set_title(f"{names[o]} — {r.split('_')[1]} 씨앗 {0 if r.startswith('b1') else 1}", fontsize=10)
            ax.set_xlabel("벽 방향 (m)")
            ax.set_ylabel("z (m)")
            del sc, mm
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=cols[1], label="LoD2 벽면 ±0.2 m에 면"), Patch(color=cols[2], label="벽면 앞(3 m 안)에 면"),
                        Patch(color=cols[3], label="벽면 뒤(7 m 안)에 면"), Patch(facecolor="white", edgecolor="k", label="면 없음")],
               loc="lower center", ncol=4, fontsize=10, bbox_to_anchor=(0.5, -0.07))
    fig.suptitle("가장 큰 비가시 벽(B173, ext 53)의 가상 시점 메시, 세 안 × 학습 넷: LoD2 벽면 3 m 앞에서 본 첫 메시 면의 자리(빨강 점 = 지금 지붕 위로 추정한 옛 벽 윗부분)", fontsize=12, x=0.01, ha="left")
    fig.savefig(OUT / "figs/virtual_options.png", dpi=75, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    figure() if sys.argv[1:2] == ["--figure"] else compare()
