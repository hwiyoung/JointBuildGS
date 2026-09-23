"""PHD-STAGE2-R9-THREE-FIXES-v1 (conf-guided image, GPU; /source = r8 fork, /r8 and /p9 mounted): the initial rotations of
the r8 trainings, reproduced for the 'before' column of fix 'da'.

  python r8_initial_rotations.py

The base GaussianModel.create_from_pcd draws rots = torch.rand((N, 4), device="cuda") after train.py's safe_state()
(torch.manual_seed(0)); nothing in between draws from the CUDA generator. Every r8 initial cloud has N = 192,361 points,
so the draw is the same for the four settings. Validation (initial disk -> cloud row through init_points.npz 'planted'):
rows of r8's final PLY equal to the draw exactly (rotation never updated) are counted, and for the Gaussians planted on
invisible patches -- which receive almost no gradient -- the angle between the disk normal of the final PLY and that of
the draw must be small (median < 1 degree) against a shuffled draw (about 50 degrees).
Writes /p9/cases/r8_initial_quaternions.npy (float32 [N, 4], (w, x, y, z) unnormalised as stored) and
r8_initial_quaternions.json."""
import json
import sys
from pathlib import Path

import numpy as np
import torch
from plyfile import PlyData

sys.path.insert(0, "/source")
from utils.general_utils import safe_state  # noqa: E402

R8 = Path("/r8"); OUT = Path("/p9/cases"); OUT.mkdir(parents=True, exist_ok=True)
N = 192361
safe_state(False)
q = torch.rand((N, 4), device="cuda").cpu().numpy()
np.save(OUT / "r8_initial_quaternions.npy", q.astype(np.float32))
rep = {"rule": "torch.manual_seed(0) (safe_state) then torch.rand((N, 4), device='cuda') as GaussianModel.create_from_pcd", "N": N,
       "validation": {}}
for run in ("M_N", "M_B", "L_N", "L_B", "M_N_noprior"):
    rec = json.loads((R8 / "runs" / run / "receipt.json").read_text())
    setting = rec["setting"]
    ip = np.load(R8 / "runs" / f"dry_{setting}" / "model/monitor/init_points.npz")
    assert len(ip["planted"]) == N, (run, len(ip["planted"]))
    rows = np.nonzero(ip["planted"])[0]                                   # initial disk i <- cloud row rows[i]
    v = PlyData.read(str(R8 / "runs" / run / "model/point_cloud/iteration_3500/point_cloud.ply"))["vertex"]
    rot = np.stack([np.asarray(v[f"rot_{k}"], np.float32) for k in range(4)], 1)
    dz = np.load(R8 / "runs" / run / "model/dump/iteration_3500/gaussians.npz")
    ids = dz["init_id"].astype(np.int64)
    ok = ids >= 0
    same = np.zeros(len(ids), bool)
    same[ok] = np.all(rot[ok] == q[rows[ids[ok]]], axis=1)
    cat = dz["init_category"]

    def nrm(qq):
        qq = qq.astype(np.float64) / np.linalg.norm(qq, axis=1, keepdims=True)
        w, x, y, z = qq.T
        return np.stack([2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)], 1)
    m = ok & (cat == 3)
    n1 = nrm(rot[m]); n0 = nrm(q[rows[ids[m]]])
    ang = np.degrees(np.arccos(np.clip(np.abs((n1 * n0).sum(1)), 0, 1)))
    sh = np.random.default_rng(0).permutation(len(n0))
    angs = np.degrees(np.arccos(np.clip(np.abs((n1 * n0[sh]).sum(1)), 0, 1)))
    rep["validation"][run] = dict(rows=int(len(ids)), equal_to_draw=int(same.sum()),
                                  invisible_rows=int(m.sum()), invisible_equal=int((same & m).sum()),
                                  invisible_normal_change_deg=dict(p50=float(np.median(ang)), p90=float(np.percentile(ang, 90)), p99=float(np.percentile(ang, 99))),
                                  shuffled_draw_deg_p50=float(np.median(angs)), image_rows_equal=int((same & (dz["origin"] == 0)).sum()))
    print(run, rep["validation"][run], flush=True)
rep["reproduced"] = all(v["invisible_normal_change_deg"]["p50"] < 1.0 and v["shuffled_draw_deg_p50"] > 30.0 and v["equal_to_draw"] > 0
                        for v in rep["validation"].values())
(OUT / "r8_initial_quaternions.json").write_text(json.dumps(rep, indent=1))
print("reproduced", rep["reproduced"])
