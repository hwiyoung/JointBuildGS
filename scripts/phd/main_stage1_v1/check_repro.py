"""PHD-MAIN-STAGE1-v1 reproduction checks (jointbuildgs:dev): exact equality of the arrays of two sets of npz files.

  python check_repro.py labels <dir_a> <dir_b> <out_name>      the label / ownership / GT files of the four boxes (s04 v6 vs v7, z-shift 0)
  python check_repro.py regions <dir_a> <dir_b> <out_name>     region files (stage-0 regions vs the chain's agreement codes)

Writes /out/v3/checks/<out_name>.json (per file and array: equal or the number of differing elements). scientific_verdict: null."""
import sys
from pathlib import Path

import numpy as np

from s1_common import OUT, SITES, jdump

LABEL_FILES = ["labels_LoD2.npz", "labels_ALS.npz", "gt_owner_LoD2.npz", "gt_owner_ALS.npz", "gt_points.npz", "gt_primary.npz", "exclusion_cells.npz"]
B0_EXTRA = ["labels_uls_LoD2.npz", "labels_uls_ALS.npz", "gt_owner_uls_LoD2.npz", "gt_owner_uls_ALS.npz"]


def cmp_npz(fa, fb):
    a, b = np.load(fa), np.load(fb)
    out = {}
    for k in sorted(set(a.files) | set(b.files)):
        if k not in a.files or k not in b.files:
            out[k] = "missing in one"
            continue
        x, y = a[k], b[k]
        if x.shape != y.shape:
            out[k] = f"shape {x.shape} vs {y.shape}"
        elif x.dtype.kind in "fc":
            out[k] = "equal" if np.array_equal(x, y, equal_nan=True) else f"{int((~((x == y) | (np.isnan(x) & np.isnan(y)))).sum())} differ"
        else:
            out[k] = "equal" if np.array_equal(x, y) else f"{int((x != y).sum())} differ"
    return out


def main(mode, da, db, name):
    da, db = Path(da), Path(db)
    res, ok = {}, True
    for site in SITES:
        files = LABEL_FILES + (B0_EXTRA if site.startswith("B0") else []) if mode == "labels" else [f"regions_{site}_LoD2.npz", f"regions_{site}_ALS.npz"]
        for f in files:
            fa = (da / site / f) if mode == "labels" else (da / f)
            fb = (db / site / f) if mode == "labels" else (db / f)
            if not fa.exists() and not fb.exists():
                continue
            r = cmp_npz(fa, fb) if fa.exists() and fb.exists() else "missing file"
            res[f"{site}/{f}"] = r
            ok &= isinstance(r, dict) and all(v == "equal" for v in r.values())
    (OUT / "v3/checks").mkdir(parents=True, exist_ok=True)
    jdump(OUT / "v3/checks" / f"{name}.json", dict(mode=mode, a=str(da), b=str(db), all_equal=bool(ok), files=res, scientific_verdict=None))
    print(name, "all equal" if ok else "DIFFER", {k: v for k, v in res.items() if not (isinstance(v, dict) and all(x == "equal" for x in v.values()))})


if __name__ == "__main__":
    main(*sys.argv[1:5])
