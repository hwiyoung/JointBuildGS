"""PHD-MAIN-PREP-DISCARD-RULE-v1 diagnostic (observation only): effect of the store-shift lookup on the judgments. Compares the
prep-input ALS runs of equivalence check 1 (the method's lookup) with the same runs looked up with the shift taken back
(s03 --locate-unshifted, diag/unshift): states, votes, propagated judgments, the discard decision, and against the prep v1.1
true labels (same tolerance) the correct / wrong decisions.
  python diag_store_shift_effect.py B0 R3E
Writes diag/store_shift_effect.json. scientific_verdict: null."""
import json
import sys

import numpy as np

from common import OUT, PREP, jdump, log
from src.phd.prior_propagation_v5 import rule
from src.phd.prior_propagation_v5 import rules as R


def main():
    out = {}
    for rid in sys.argv[1:] or ["B0", "R3E"]:
        a = np.load(OUT / "eq1/s03" / rid / "ALS/units.npz"); b = np.load(OUT / "diag/unshift" / rid / "ALS/units.npz")
        G = np.load(PREP / "step04" / rid / "labels_ALS.npz"); lab = G["label"]; ok = a["loc_in_range"] & ~G["excluded"] & (lab >= 0)
        da = R.discard(a["state"], a["vote"], a["J"]); db = R.discard(b["state"], b["vote"], b["J"])
        r = dict(units_in_range=int(a["loc_in_range"].sum()), with_label=int(ok.sum()),
                 state_changed=int((a["state"] != b["state"])[a["loc_in_range"]].sum()), vote_changed=int((a["vote"] != b["vote"])[a["loc_in_range"]].sum()),
                 judgment_changed=int((a["J"] != b["J"])[a["loc_in_range"]].sum()), discard_changed=int((da != db)[a["loc_in_range"]].sum()))
        for nm, d in (("method_lookup", da), ("shift_taken_back", db)):
            r[nm] = dict(discard=int((d & ok).sum()), wrong_discard=int((d & ok & (lab == 0)).sum()), wrong_keep=int((~d & ok & (lab == 1) & (a["state"] != rule.ST_INVISIBLE)).sum()))
        out[rid] = r
        log(rid, r)
    jdump(OUT / "diag/store_shift_effect.json", dict(rule=__doc__.split("\n\n")[0], runs=out, scientific_verdict=None))


if __name__ == "__main__":
    main()
