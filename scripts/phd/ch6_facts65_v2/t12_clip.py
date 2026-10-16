"""PHD-CH6-FACTS65-v2 task 12 [이 발주에서 냄]: the share of residuals removed as outliers when the tolerances were computed.
The tolerances used for the experiment boxes came from the search-region runs of the discard-rule task (DR/s52/s03/<range>/
<prior>; B0 for the B0 box, R2 for the two B173 boxes, R1 for R1). Their summary.json keeps the tolerance (tau) only; the
statistics of tolerance.robust_width (k 2.5, one clip at 3 NMAD) were not written. The residual samples it used are saved
(residual_samples.npz: 'roof', 'wall', float32; the run used the same values in float64). This script runs the same function
(src/phd/prior_propagation_v6/tolerance.py, identical to the v5 module that made the values) on the saved samples and writes
the removed share, the counts, the medians and NMADs, and the width next to the recorded tau. The other four search regions
are added as reference (their values were not used for any box). No judgment, no training. (jointbuildgs:dev, CPU)
  python t12_clip.py
Writes /out/t12/clip_shares.json and clip_shares.md. scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v6 import tolerance as tol  # noqa: E402

DR = Path("/dr/s52/s03"); O = Path("/out/t12"); O.mkdir(parents=True, exist_ok=True)
USED = {"B0": "B0", "R2": "B173 주변, B173만", "R1": "R1"}
RANGES = ["B0", "R2", "R1", "R3E", "R4", "R5", "SW"]
KO = {"roof": "지붕면", "wall": "벽면"}


def main():
    rows = []
    for r in RANGES:
        for prior in ("LoD2", "ALS"):
            D = DR / r / prior
            S = json.loads((D / "summary.json").read_text()); Z = np.load(D / "residual_samples.npz")
            for kind in ("roof", "wall"):
                x = Z[kind].astype(np.float64)
                st = tol.robust_width(x)
                rec = S["tolerance"][kind]
                row = dict(range=r, used_for=USED.get(r, ""), prior=prior, kind=kind, recorded_tau=rec["tau"], recorded_side=rec["side"],
                           n=st["n"], n_kept=st["n_kept"], clipped_share=st["clipped_share"], median_before=st["median_before"],
                           nmad_before=st["nmad_before"], median_after=st["median_after"], nmad_after=st["nmad_after"], width=st["width"])
                row["width_minus_recorded"] = (None if st["width"] is None or rec["width"] is None
                                               else float(st["width"] - rec["width"]))
                rows.append(row)
    out = dict(rule=__doc__.split("\n\n")[0], function="tolerance.robust_width(x, k=2.5, clip=3.0)", rows=rows, scientific_verdict=None)
    (O / "clip_shares.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    L = ["# 허용 오차를 구할 때 이상치로 지운 몫 (탐색 지역, 저장된 표본에 같은 함수를 다시 돌림)", "",
         "| 탐색 지역 | 값을 쓴 실험 지역 | 사전 정보 | 면 | 표본 | 지운 몫 | 기록된 허용 오차 | 다시 구한 값 | 차 |", "|---|---|---|---|---|---|---|---|---|"]
    for w in rows:
        if w["n"] == 0:
            L.append(f"| {w['range']} | {w['used_for'] or '쓰지 않음'} | {w['prior']} | {KO[w['kind']]} | 0 | — | {w['recorded_tau']:.4f} m ({w['recorded_side']}) | — | — |")
            continue
        d = w["width_minus_recorded"]
        L.append(f"| {w['range']} | {w['used_for'] or '쓰지 않음'} | {w['prior']} | {KO[w['kind']]} | {w['n']:,} | {100 * w['clipped_share']:.2f} % | "
                 f"{w['recorded_tau']:.4f} m | {w['width']:.4f} m | {'—' if d is None else f'{d:+.1e} m'} |")
    (O / "clip_shares.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
