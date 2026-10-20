"""PHD-MAIN-FIXTEST-v1 6.3-1 (jointbuildgs:dev, CPU): from the r16-default dry inits of the six cases: patch states (state 2 = missing:
seen by at least one training view, supporting views fewer than half of the seeing views; rule.location_state), invisible patches carry
no judgment (unit_judgment -1) and own no pixel of the per-view patch maps (so no prior-depth-term pixel); missing patches' judgment values.
Writes /out/checks/inv_check.json and .md. scientific_verdict: null."""
import json
from pathlib import Path

import numpy as np

D = Path("/out/checks/dry")
out = {}
for site in ("B0_b10", "B173nb_b10", "R1rep_b10"):
    for prior in ("LoD2", "ALS"):
        M = D / f"r16d_{site}_{prior}" / "model/monitor"
        L = np.load(M / "locations.npz")
        G = np.load(M / "gate_check.npz")
        st, jl = L["state"], L["unit_judgment"]
        inv = st == 0
        px_inv = px_all = px_mis = 0
        for k in G.files:
            if k.startswith("lm_"):
                lm = G[k].astype(np.int64)
                ok = lm >= 0
                s_ = st[lm[ok]]
                px_all += int(ok.sum()); px_inv += int((s_ == 0).sum()); px_mis += int((s_ == 2).sum())
        mis = st == 2
        out[f"{site}/{prior}"] = dict(patches=int(len(st)), invisible=int(inv.sum()), invisible_with_judgment=int((inv & (jl != -1)).sum()),
                                      invisible_pixels=px_inv, located_pixels=px_all, missing=int(mis.sum()), missing_pixels=px_mis,
                                      missing_judgments={str(j): int((mis & (jl == j)).sum()) for j in (-1, 0, 1, 2, 3)})
Path("/out/checks/inv_check.json").write_text(json.dumps(out, indent=1))
md = ["| 경우 | 패치 | 비가시 | 판정 있는 비가시 | 비가시 화소 (학습 영상) | 결측 | 결측 화소 | 결측의 판정 (충돌·일치·섞임·근거 부족) |", "|---|---:|---:|---:|---:|---:|---:|---|"]
for k, v in out.items():
    j = v["missing_judgments"]
    md.append(f"| {k} | {v['patches']:,} | {v['invisible']:,} | {v['invisible_with_judgment']} | {v['invisible_pixels']} | {v['missing']:,} | {v['missing_pixels']:,} | "
              f"{j['0']:,} · {j['1']:,} · {j['2']:,} · {j['3']:,} |")
Path("/out/checks/inv_check.md").write_text("\n".join(md) + "\n")
print(json.dumps(out))
