"""PHD-MAIN-STAGE1-v1 3.1 check: the same building 108580335 in B173nb_b10 and B173_b0 has the same GT after the common move
(jointbuildgs:dev). Points of both boxes inside the building's footprint are matched by x, y (within 1 mm); the z difference of the
matched pairs before (s61 = per-box alignment) and after (v3 = common shift). -> /out/v3/checks/building_108580335.json
scientific_verdict: null."""
import json

import numpy as np
from matplotlib.path import Path as MPath
from scipy.spatial import cKDTree

from s1_common import DR, OUT, S0, jdump

B = "DEBY_LOD2_108580335"
fp = [f for f in json.loads((DR / "s02_box/B173_b0/footprints.json").read_text())["footprints"] if f["building"] == B]
out = {}
for tag, root in (("before_per_box", S0 / "s61/box_gt"), ("after_common", OUT / "v3/box_gt")):
    P = {}
    for s in ("B173nb_b10", "B173_b0"):
        X = np.load(root / s / "gt_points.npz")["xyz"].astype(np.float64)
        m = np.zeros(len(X), bool)
        for f in fp:
            m |= MPath(np.asarray(f["ring_local"])).contains_points(X[:, :2])
        P[s] = X[m]
    # the same raw point: x, y equal and z equal up to the difference of the two boxes' moves (taken out before matching in 3-D)
    shift = {"before_per_box": -0.0422461 - 0.0415112, "after_common": 0.0}[tag]
    Q = P["B173_b0"].copy()
    Q[:, 2] += shift
    d, j = cKDTree(Q).query(P["B173nb_b10"], distance_upper_bound=0.001)
    ok = np.isfinite(d)
    dz = P["B173nb_b10"][ok, 2] - P["B173_b0"][j[ok], 2]
    out[tag] = dict(points_nb=len(P["B173nb_b10"]), points_b0=len(P["B173_b0"]), matched_same_point=int(ok.sum()),
                    dz_median_m=float(np.median(dz)) if ok.any() else None, dz_max_abs_m=float(np.abs(dz).max()) if ok.any() else None)
jdump(OUT / "v3/checks/building_108580335.json", dict(building=B, rule="the same raw point matched in 3-D within 1 mm after taking out the difference of the two boxes moves (before: -0.0837 m; after: 0); dz = z(B173nb_b10) - z(B173_b0)", **out, scientific_verdict=None))
print(json.dumps(out))
