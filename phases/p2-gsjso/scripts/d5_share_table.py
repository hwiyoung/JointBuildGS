#!/usr/bin/env python3
"""P2-D5 pre-check ① — analytic weighted-loss share table for the cp ablation (observe only, verdict=human).

D5 keeps D4's de-noise balance fixed and varies ONLY the coplanar (cp) sub-weight (and, for D5c, the gate).
The "push-force balance" each arm applies is the weighted contribution share of each loss term =
    contribution_i = effective_scalar_i * raw_mean_i   (raw_mean over the steady-state window),
renormalised to 100%. cp's effective scalar = w_structure * w_structure_cp (w_structure = 1.0 here).

Raw means are the LOCKED D-run statistics (gs_prior_full TB, mean[20000-30000], i.e. post cp-gate steady
state) reported in docs/experiments/w_d4/reports/W_D4_precheck.md §3 / P2_D4_사양서 §3. They reproduce the D4 spec's locked shares
(photo 30.7 / depth 16.6 / normal 0 / nc 2.1 / sem 19.0 / cp 31.4 / na ~0). Reproducible, no GPU / no deps.

Expected (spec): cp share = OFF 0% (D5a) / FAIR 31% (D5c = D4 magnitude) / HARD ~57% (D5b).
"""
from pathlib import Path

# LOCKED D-run raw means (mean[20000-30000]); docs/experiments/w_d4/reports/W_D4_precheck.md §3.
# sem raw ~1.09 (W_D4_precheck "~1.1") back-solved to reproduce the D4-locked sem share 19.0%.
RAW_MEAN = {"photo": 0.176, "depth": 3.174, "normal": 0.322, "nc": 0.244,
            "sem": 1.088, "cp": 18.01, "na": 0.003}

# Effective scalars shared by all D4/D5 arms (= D-healthy terms kept; de-noise fixed).
EFF_FIXED = {"photo": 1.0, "depth": 0.03, "normal": 0.0, "nc": 0.05, "sem": 0.1, "na": 0.08}

# Per-arm cp effective scalar (= w_structure 1.0 * w_structure_cp). gate noted for context.
ARMS = [
    ("D5a (cp OFF)",   0.00, 15000),
    ("D4/D5c (cp FAIR)", 0.01, "15000 / 5000"),   # D4 = fair@15000 (reused); D5c = fair@5000 (early gate)
    ("D5b (cp HARD)",  0.03, 15000),
]
ORDER = ["photo", "depth", "normal", "nc", "sem", "cp", "na"]


def shares(cp_scalar):
    contrib = {t: EFF_FIXED[t] * RAW_MEAN[t] for t in EFF_FIXED}
    contrib["cp"] = cp_scalar * RAW_MEAN["cp"]
    tot = sum(contrib.values())
    return {t: 100.0 * contrib[t] / tot for t in ORDER}, contrib, tot


def main():
    lines = []
    def out(s=""):
        lines.append(s); print(s)

    out("# P2-D5 pre-check ① — cp push-force balance (analytic weighted shares, %; 관찰만, 판정=사람)\n")
    out("Raw means = LOCKED D-run mean[20-30k] (docs/experiments/w_d4/reports/W_D4_precheck.md §3). De-noise FIXED = D4 across all arms.\n")
    hdr = f"{'arm':>18} | " + " ".join(f"{t:>6}" for t in ORDER) + " | maxterm"
    out(hdr); out("-" * len(hdr))
    for name, cp, gate in ARMS:
        sh, _, _ = shares(cp)
        mx = max(sh, key=sh.get)
        row = f"{name:>18} | " + " ".join(f"{sh[t]:6.1f}" for t in ORDER) + f" | {mx} {sh[mx]:.0f}%"
        out(row)
    out("")
    out("Reading (verdict=human): cp share OFF 0% -> FAIR 31% -> HARD 58%, as intended (spec §3 ①).")
    out("  - D5a (cp off): no cp gradient; photo becomes the natural top term (~45%) — expected baseline,")
    out("    NOT an abnormal supervision-term dominance. na (0.08) still active post-gate.")
    out("  - D5c: cp magnitude = D4 (31%); only the gate is earlier (5000) — same push force, applied sooner.")
    out("  - D5b: cp ~58% (3x), the strongest planarization pressure — OVER-FLATTEN watch on curved 4906969.")

    p = Path(__file__).resolve().parents[3] / "results/tum_transfer/mob/d5_share_table.txt"
    p.write_text("\n".join(lines) + "\n")
    print(f"\n[done] -> {p}")


if __name__ == "__main__":
    main()
