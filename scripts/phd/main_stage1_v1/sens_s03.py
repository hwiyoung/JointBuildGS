"""PHD-MAIN-STAGE1-v1 3.6: the pre-training judgment with one value changed (jointbuildgs:dev, CPU). A wrapper of the unchanged stage-0
script scripts/phd/main_stage0_v1/s03_stage1_v6.py: the stage-0 box command (box views, /dr/s02_box store, box MVS, the discard task's
fixed values, rule auto) with one override.

  python sens_s03.py <variant> <site> <prior>      -> /out/sens/<variant>/box/<site>/<prior>/ (units.npz, summary.json, ...)

variants: conf_current / conf_strict / conf_loose (MVS depth = the photometric map masked by the re-computed confidence of
sens_conf.py), patch_0125 / patch_05 (the store of sens_s02.py), majority_half / majority_34 / min_evidence_3 / min_evidence_10 /
max_distance_05 / max_distance_2 (the propagation values). scientific_verdict: null."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
sys.path.insert(0, "/repo")
import numpy as np  # noqa: E402

import common  # noqa: E402
import s03_stage1_v6 as s03  # noqa: E402

FIX = {"B0_b10": "B0", "B173nb_b10": "R2", "B173_b0": "R2", "R1rep_b10": "R1"}
CONF_BIT = {"conf_current": 0, "conf_strict": 1, "conf_loose": 2}
PROP = {"majority_half": ("majority", 0.5), "majority_34": ("majority", 0.75), "min_evidence_3": ("min_evidence", 3), "min_evidence_10": ("min_evidence", 10),
        "max_distance_05": ("max_distance_m", 0.5), "max_distance_2": ("max_distance_m", 2.0)}


def main(variant, site, prior):
    OUT = Path("/out")
    mesh = Path("/dr/s02_box")
    conf = "geometric"
    if variant in CONF_BIT:
        masks = np.load(OUT / "sens/conf" / f"{site}.npz")
        bit = CONF_BIT[variant]
        orig = s03.read_depth_bin

        def masked(p):
            d = orig(p)
            name = Path(p).name[: -len(".photometric.bin")]
            m = ((masks[name] >> bit) & 1).astype(bool)
            return np.where(m, d, 0.0).astype(d.dtype)
        s03.read_depth_bin = masked                  # depth_of() of s03 reads through this name
        conf = "photometric"
    elif variant in ("patch_0125", "patch_05"):
        mesh = OUT / "sens" / variant / "s02_box"
    elif variant in PROP:
        k, v = PROP[variant]
        assert common.CFG is s03.CFG
        common.CFG["judgment"][k] = v
    else:
        raise SystemExit(f"unknown variant {variant}")
    views = json.loads(Path("/prep/step06/box_views.json").read_text())["views"][site]["train"]
    D = OUT / "sens" / variant / "box" / site / prior
    s03.run(site, prior, views, Path(f"/prep/mvs/box_{site}"), mesh / site, D, 0, False, f"/dr/s52/s03/{FIX[site]}", conf, None, "auto")
    (D / "variant.json").write_text(json.dumps(dict(variant=variant, site=site, prior=prior, judgment=common.CFG["judgment"], conf=conf, mesh=str(mesh),
                                                    scientific_verdict=None), indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
