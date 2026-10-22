"""PHD-MAIN-AXES71-v2 일 9 '맞춰 볼 값' (order 12): the fix test's values against this task's (jointbuildgs:dev, CPU).
보정 합 median |d_g| of 판정만 끈 본 방법 (B0 · LoD2 7.6, R1 · LoD2 13.9 cm) and 영상만 (5.2, 6.7 cm); 결측 영역 (code 4 = 상속 · 결측 + 보존 · 거름
of code 4) R(0.2 m) of 판 B on R1 · LoD2 (84.0 %). Records: docs/experiments/phd/main_fixtest_v1/tables/eval_ft.json. scientific_verdict: null."""
import numpy as np

from ax_common import DOCS, FT, TAB, jdump, jl, now
from ax_arrays import cells

V = jl(TAB / "a9_metrics.json")["values"]
E = jl("/repo/docs/experiments/phd/main_fixtest_v1/tables/eval_ft.json")["cases"]
out = []
for u, res, rec_key, want in (("B0_b10/LoD2", "nojudge_LoD2_s0", "nojudge", 7.6), ("R1rep_b10/LoD2", "nojudge_LoD2_s0", "nojudge", 13.9),
                              ("B0_b10/LoD2", "imgonly_s0", "imgonly", 5.2), ("R1rep_b10/LoD2", "imgonly_s0", "imgonly", 6.7)):
    b = V.get(f"{u}/{res}", {}).get("s_corr", {})
    here = b["gt"]["med"] if str(b.get("status", "")).startswith("있음") else None
    rec = E[u]["places"]["c11"]["dist"][rec_key]["v"]
    out.append(dict(case=u, result=res, value="보정 합 참값 기준 거리의 중앙값 cm", want=want, record_unrounded=rec, here=here,
                    same=here is not None and abs(here - rec) < 1e-6))
C = cells("R1rep_b10", "LoD2")
code = C["code"].astype(np.int64)
cell = C["cell"].astype(np.int64)
from ax_common import CID
m4 = (cell == CID["c_inh_miss"]) | ((cell == CID["c_keep_mask"]) & (code == 4))
z = np.load(FT / "dist/R1rep_b10_LoD2__fixB_LoD2_s0.npz")
sel = m4[z["r_patch"].astype(np.int64)]
here = float((z["r_d"][sel] <= 0.2).mean() * 100)
rec = E["R1rep_b10/LoD2"]["places"]["c4"]["R_0.2"]["B"]["v"]
out.append(dict(case="R1rep_b10/LoD2", result="fixB_LoD2_s0", value="결측 영역 R(0.2 m) %", want=84.0, record_unrounded=rec, here=here, rows=int(sel.sum()),
                same=abs(here - rec) < 1e-6))
jdump(DOCS / "tables/일9_맞춰볼값.json", dict(task="PHD-MAIN-AXES71-v2", made=now(), data=out, scientific_verdict=None))
L = ["# 일 9 맞춰 볼 값 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", "| 경우 | 결과 | 값 | 발주 | 기록(반올림 전) | 여기 | 같음 |", "|---|---|---|---:|---:|---:|---|"]
for c in out:
    L.append(f"| {c['case']} | {c['result']} | {c['value']} | {c['want']} | {c['record_unrounded']:.4f} | {'—' if c['here'] is None else format(c['here'], '.4f')} | {'같음' if c['same'] else '어긋남 !'} |")
(DOCS / "tables/일9_맞춰볼값.md").write_text("\n".join(L) + "\n")
print([(c["result"], c["here"], c["record_unrounded"], c["same"]) for c in out])
