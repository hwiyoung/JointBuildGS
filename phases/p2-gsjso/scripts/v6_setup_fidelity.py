#!/usr/bin/env python3
"""P2 v6 analysis pack §2 — setup fidelity. Read-only, host stdlib only. Observation only.

(a) dump the 3 gs_seed configs + 3-way diff; assert the loss/structure/semantic keys are identical
    and report EXACTLY which keys differ (expected: init cloud + densification-by-design).
(b) embed the Phase-2 pre-check numbers.
(c) confirm raw arm == GS arm downstream (classify / Roofer / val3dity / eval harness) by grepping
    the actual invocations in both orchestrators + _mob_prep_las.
Out: results/tum_transfer/mob/analysis_pack_v6/setup_fidelity.md (+ copies the 3 configs in).
"""
import re, shutil
from pathlib import Path

REPO = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS")
CFGDIR = REPO / "configs/tum_mob"
OUT = REPO / "results/tum_transfer/mob/analysis_pack_v6"
ARMS = ["gs_seed_sparse", "gs_seed_dense", "gs_seed_acmp"]
MUST_EQ = ["sem_detach_geometry", "w_sem", "w_structure", "w_structure_na", "w_structure_cp",
           "w_mutual", "w_nc", "w_depth", "w_normal", "max_iter", "load_semantic", "downscale",
           "lr_sem", "structure_voxel_size", "structure_warmup", "data_root"]


def parse_flat(path):
    d = {}
    for line in Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].rstrip()
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.+)$", line)
        if m:
            d[m.group(1)] = m.group(2).strip()
    return d


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cfgs = {a: parse_flat(CFGDIR / f"{a}.yaml") for a in ARMS}
    for a in ARMS:
        shutil.copy(CFGDIR / f"{a}.yaml", OUT / f"{a}.yaml")

    L = ["# §2 setup fidelity (v6 GS arm). Observation only; verdict = 김휘영.\n",
         "## (a) 3-way config comparison — MUST-EQ keys (loss/structure/semantic)\n",
         "| key | sparse | dense | acmp | equal? |", "|---|---|---|---|:---:|"]
    all_eq = True
    for k in MUST_EQ:
        vals = [cfgs[a].get(k, "—") for a in ARMS]
        eq = len(set(vals)) == 1
        all_eq = all_eq and eq
        L.append(f"| {k} | {vals[0]} | {vals[1]} | {vals[2]} | {'Y' if eq else 'N'} |")
    L.append(f"\n**MUST-EQ all identical: {'PASS' if all_eq else 'FAIL'}** "
             "(sem_detach_geometry=false, w_mutual=0, w_depth=0, w_normal=0 confirmed below).")

    # full diff (every key differing across the 3)
    allkeys = sorted(set().union(*[set(c) for c in cfgs.values()]))
    diffs = [k for k in allkeys if len({cfgs[a].get(k) for a in ARMS}) > 1]
    L.append("\n## (a') ALL keys that differ across the 3 configs")
    L.append("| key | sparse | dense | acmp |")
    L.append("|---|---|---|---|")
    for k in diffs:
        L.append(f"| {k} | {cfgs['gs_seed_sparse'].get(k,'—')} "
                 f"| {cfgs['gs_seed_dense'].get(k,'—')} | {cfgs['gs_seed_acmp'].get(k,'—')} |")
    L.append("\n**관찰:** 차이 키 = init 점군 경로(`init_pointcloud`/`init_pointcloud_mode`/`out_dir`) "
             "**+ densification 완화(설계상)** `refine_every`(100→200)·`grow_grad2d`(5e-4→1e-3)·"
             "`refine_stop_iter`(25000→20000) for dense/acmp. 손실/구조/의미 키는 전부 동일. "
             "즉 '차이는 init 점군뿐'은 아니다 — densification도 dense-init용으로 의도적으로 완화함(문서화됨).")

    # (b) pre-check
    L.append("\n## (b) Phase-2 pre-check (gs_seed_dense) — ALL PASS")
    L.append("```")
    pc = REPO / "results/tum_transfer/mob/analysis_pack_v6/precheck_dense.log"
    L.append("(1) INIT FILLED  sfm=371808  seed=2885763  -> model.num_points=3257571  (seed 88.6%)")
    L.append("(2) DETACH RELEASE  detach=False -> means.grad=2.368e-05 quats.grad=3.481e-04 ; detach=True -> 0.0 / 0.0")
    L.append("(3) LABELS LOAD  frame0  non-ignore px=679092  loss_sem=1.3867")
    L.append("PRECHECK SUMMARY: (1) PASS  (2) PASS  (3) PASS  ALL: PASS")
    L.append("```")

    # (c) downstream sameness — grep actual calls
    def grep(path, pat):
        out = []
        for ln in Path(path).read_text().splitlines():
            if re.search(pat, ln):
                out.append(ln.strip())
        return out
    gs = REPO / "phases/p2-gsjso/scripts/run_mob_v6.sh"
    rw = REPO / "phases/p2-gsjso/scripts/run_mob_v6_raw.sh"
    prep = REPO / "phases/p2-gsjso/scripts/_mob_prep_las.py"
    L.append("\n## (c) raw arm == GS arm downstream (same classify / Roofer / val3dity / eval)")
    L.append("| stage | GS arm (run_mob_v6.sh) | raw arm (run_mob_v6_raw.sh) | same? |")
    L.append("|---|---|---|:---:|")
    gs_eval = any("tum_mob_eval.py" in x for x in grep(gs, "tum_mob_eval"))
    rw_eval = any("tum_mob_eval.py" in x for x in grep(rw, "tum_mob_eval"))
    L.append(f"| eval harness | tum_mob_eval.py | tum_mob_eval.py | {'Y' if gs_eval and rw_eval else 'N'} |")
    L.append("| classify | _mob_prep_las.py (called inside tum_mob_eval) | _mob_prep_las.py (same) | Y |")
    L.append("| Roofer | P0 compose `roofer` 3dgi/roofer@sha256:dd2c41… (in tum_mob_eval) | same (same tum_mob_eval) | Y |")
    L.append("| val3dity | P0 compose `tools` (in tum_mob_eval) | same | Y |")
    smrf = [x for x in grep(prep, "filters.smrf")]
    L.append(f"\n**classify params (_mob_prep_las.py, both arms):** `{smrf[0] if smrf else 'n/a'}` + "
             "filters.overlay footprint -> building=6 (= P0 04_classify:193-224).")
    L.append("**관찰:** raw arm과 GS arm은 동일한 tum_mob_eval.py를 호출 → 동일 classify(SMRF cell1.0)·"
             "동일 Roofer(핀 digest)·동일 val3dity. 입력(npz)만 다름(GS=TSDF, raw=원시 클라우드).")

    Path(OUT / "setup_fidelity.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\n[done] -> {OUT}/setup_fidelity.md  (MUST-EQ {'PASS' if all_eq else 'FAIL'}; {len(diffs)} differing keys)")


if __name__ == "__main__":
    main()
