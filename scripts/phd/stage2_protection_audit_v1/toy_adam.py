"""Toy test of check 1 (PHD-STAGE2-PROTECTION-AUDIT-v1): where must the 0.01 go for Adam to move 0.01 as far?

One scalar parameter, torch.optim.Adam with the GeoGS settings (betas 0.9/0.999, eps 1e-15), the same gradient
sequence for every variant, 1,000 updates, cumulative movement |x_t - x_0|:
  ga  gradient as is                     na  gradient x 0.01 from the start      da  lr x 0.01 from the start
  ra  gradient x 0.01 from update 500    ma  applied update x 0.01 from the start (the implementation's post-step blend)
  ba  applied update x 0.01 from update 500
Sequences: constant g = 1; noisy g_t = 1 + 2 xi_t (xi ~ N(0,1), numpy seed 0). float64, x_0 = 0 (no rounding).
Supplement (not part of the prompt's four): float32 at x_0 = 40 m with a sparse gradient (non-zero on 1 of 13 updates,
like a disk seen in one training view) and lr 4.5e-3 (xyz lr near iteration 3,000): update x 0.01 by the post-step blend
in float32 vs the same arithmetic in float64, i.e. how often the blended update rounds to exactly 0.
Also a 10,000-update run of 'ra' to show that the gradient-scaling slowdown fades as the second moment forgets.
Outputs: <out>/toy_adam.csv, toy_adam_summary.json, toy_adam.png"""
import json
import sys
from pathlib import Path

import numpy as np
import torch

out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
out.mkdir(parents=True, exist_ok=True)
N, LR, S = 1000, 1e-3, 0.01


def run(grads, kind, lr=LR, dtype=torch.float64, x0=0.0, switch=500):
    x = torch.nn.Parameter(torch.tensor([x0], dtype=dtype))
    opt = torch.optim.Adam([x], lr=lr * (S if kind == "da" else 1.0), betas=(0.9, 0.999), eps=1e-15)
    traj, zero_updates, moved_updates = [], 0, 0
    for t, g in enumerate(grads):
        scale_g = S if (kind == "na" or (kind == "ra" and t >= switch)) else 1.0
        opt.zero_grad()
        x.grad = torch.tensor([g * scale_g], dtype=dtype)
        old = x.detach().clone()
        opt.step()
        if kind == "ma" or (kind == "ba" and t >= switch):
            with torch.no_grad():
                raw = x.detach() - old
                x.data = old + S * (x.data - old)
                if float(raw.abs()) > 0:
                    moved_updates += 1
                    zero_updates += int(float((x.detach() - old).abs()) == 0.0)
        traj.append(abs(float(x.detach()[0]) - x0))
    return np.array(traj), zero_updates, moved_updates


rng = np.random.default_rng(0)
seqs = {"constant": np.ones(N), "noisy": 1.0 + 2.0 * rng.standard_normal(N)}
kinds = ["ga", "na", "da", "ra", "ma", "ba"]
rows, summary = [], {}
curves = {}
for sname, g in seqs.items():
    for k in kinds:
        tr, _, _ = run(g, k)
        curves[(sname, k)] = tr
    ref = curves[(sname, "ga")]
    summary[sname] = {k: dict(final_move=float(curves[(sname, k)][-1]), ratio_to_ga=float(curves[(sname, k)][-1] / ref[-1]),
                              move_500_1000=float(curves[(sname, k)][-1] - curves[(sname, k)][499]),
                              ratio_500_1000=float((curves[(sname, k)][-1] - curves[(sname, k)][499]) / (ref[-1] - ref[499])))
                      for k in kinds}
for t in range(N):
    rows.append([t + 1] + [curves[(s, k)][t] for s in seqs for k in kinds])
hdr = ["update"] + [f"{s}_{k}" for s in seqs for k in kinds]
np.savetxt(out / "toy_adam.csv", np.array(rows), delimiter=",", header=",".join(hdr), comments="", fmt="%.10g")

# long run of 'ra' (gradient x0.01 from 500): per-update step relative to 'ga'
g_long = 1.0 + 2.0 * np.random.default_rng(1).standard_normal(10000)
tr_ga, _, _ = run(g_long, "ga")
tr_ra, _, _ = run(g_long, "ra")
step_ga, step_ra = np.diff(np.r_[0, tr_ga]), np.diff(np.r_[0, tr_ra])
win = lambda a, i, j: float(np.abs(a[i:j]).sum())
summary["long_noisy_ra"] = {f"{i}-{j}": win(step_ra, i, j) / win(step_ga, i, j)
                            for i, j in [(500, 1000), (1000, 2000), (2000, 4000), (4000, 7000), (7000, 10000)]}

# float32 rounding supplement: sparse gradient, x0 = 40 m
sp = np.zeros(3500); sp[::13] = 1.0 + 0.5 * np.random.default_rng(2).standard_normal(len(sp[::13]))
f32, z32, m32 = run(sp, "ma", lr=4.5e-3, dtype=torch.float32, x0=40.0)
f64, z64, m64 = run(sp, "ma", lr=4.5e-3, dtype=torch.float64, x0=40.0)
ga32, _, _ = run(sp, "ga", lr=4.5e-3, dtype=torch.float32, x0=40.0)
summary["float32_sparse_x40"] = dict(updates=len(sp), moved_updates=m32, zero_applied_updates_f32=z32,
                                     zero_applied_updates_f64=z64, final_move_f32=float(f32[-1]), final_move_f64=float(f64[-1]),
                                     final_move_unlocked_f32=float(ga32[-1]),
                                     float32_spacing_at_40m=float(np.spacing(np.float32(40.0))))
(out / "toy_adam_summary.json").write_text(json.dumps(summary, indent=1))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
lab = {"ga": "(a) grad as is", "na": "(b) grad x0.01 from start", "da": "(c) lr x0.01 from start",
       "ra": "(d) grad x0.01 from 500", "ma": "(e) update x0.01 from start (impl.)", "ba": "(f) update x0.01 from 500"}
sty = {"ga": ("k", "-"), "na": ("tab:orange", "--"), "da": ("tab:blue", "-"), "ra": ("tab:red", "-"),
       "ma": ("tab:cyan", ":"), "ba": ("tab:purple", ":")}
fig, axs = plt.subplots(1, 3, figsize=(15, 4.2))
for ax, s in zip(axs[:2], seqs):
    for k in kinds:
        c, ls = sty[k]
        ax.plot(np.arange(1, N + 1), np.maximum(curves[(s, k)], 1e-9), color=c, ls=ls, lw=1.6, label=lab[k])
    ax.set_yscale("log"); ax.set_xlabel("Adam update"); ax.set_ylabel("cumulative movement |x_t - x_0|")
    ax.set_title(f"Toy Adam, {s} gradient (lr 1e-3, eps 1e-15)"); ax.axvline(500, color="0.7", lw=0.8)
    ax.grid(alpha=0.3)
axs[0].legend(fontsize=7.5, loc="lower right")
ax = axs[2]
ks = list(summary["long_noisy_ra"].keys())
ax.bar(range(len(ks)), [summary["long_noisy_ra"][k] for k in ks], color="tab:red")
ax.axhline(0.01, color="tab:blue", ls="--", lw=1, label="0.01 (lr x0.01)")
ax.axhline(1.0, color="k", lw=0.8, label="1 (no slowdown)")
ax.set_xticks(range(len(ks))); ax.set_xticklabels(ks, fontsize=8); ax.set_yscale("log")
ax.set_xlabel("update window (grad x0.01 switched on at 500)"); ax.set_ylabel("movement / movement without scaling")
ax.set_title("(d) over 10,000 updates: slowdown fades"); ax.legend(fontsize=8); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig(out / "toy_adam.png", dpi=130)
print(json.dumps(summary, indent=1))
