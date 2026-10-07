"""PHD-MAIN-STAGE1-v1 5.1: the section positions of the stage-1 figures, chosen by rule from pre-training data before any stage-1
training result is read (jointbuildgs:dev, CPU). Writes configs/phd/main_stage1_v1/sections_v1.json (through /out/defs/sections_v1.json;
the copy into the repository is done on the host).

Rule (each section: a vertical plane through a patch centre, 12 m long, points within 0.25 m of the plane; direction = the dip direction
of the patch's prior face, the box u axis when the face is flatter than 5 degrees; wall patches: the horizontal outward normal):
  B173_wing        B173nb_b10 LoD2: the roof-like code-11 patch of the south-wing faces (discard sites 'B173_wings') owning most GT points
  B173_sawtooth    B173nb_b10 LoD2: the roof-like patch of the sawtooth faces ('B173_middle') steeper than 17 degrees owning most GT points
  R1_low_roof      R1rep_b10 LoD2: the roof-like code-11 patch with GT below the prior (gt_med < 0) owning most GT points, outside the
                   building of the translucent roof (else both sections fall on the same hall roof)
  R1_translucent   R1rep_b10 LoD2: the roof-like patch of the translucent-roof face ('R1_hall') in the evaluation range owning most GT points
  B0_wall_eaves    B0_b10 LoD2: the wall-like patch of the facade face ('B0_facade') owning most GT points (the plane runs across the wall
                   and the eaves above it)
scientific_verdict: null."""
import json
from pathlib import Path

import numpy as np

from s1_common import DR, OUT, S0, jdump
from src.phd.metrics_v3.surface import MeshScene  # noqa: F401  (import check only)

SITES_CFG = {s["id"]: s for s in json.loads(Path("/repo/configs/phd/main_prep_discard_rule_v1/sites_v1.json").read_text())["sites"]}
PCFG = json.loads(Path("/repo/configs/phd/main_prep_measure_v1/prep_v5.json").read_text())
_a = np.deg2rad(PCFG["frame"]["u_axis_angle_degrees_ccw_from_easting"])
U_AXIS = np.array([np.cos(_a), np.sin(_a)])


def patches(site, prior, faces):
    tab = json.loads((DR / "s02_box" / site / "lod2_surfaces.json").read_text())["surfaces"]
    exts = [r["ext"] for r in tab if r["gml"] in faces]
    U = np.load(S0 / "s61/box" / site / prior / "units.npz")
    se = U["surf_ext"][U["loc_surface"]]
    return np.isin(se, exts), U


def section(site, prior, mask, why):
    R = np.load(OUT / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
    U = np.load(S0 / "s61/box" / site / prior / "units.npz")
    m = mask & R["in_eval"]
    if not m.any():
        return dict(why=why, missing=True)
    k = int(np.nonzero(m)[0][np.argmax(R["gt_points"][m])])
    n = np.cross(U["loc_t1"][k], U["loc_t2"][k])
    n = n / np.linalg.norm(n)
    if U["loc_kind"][k] == 2:
        t = n[:2] / np.linalg.norm(n[:2])
    else:
        n = n * np.sign(n[2])
        tilt = np.degrees(np.arccos(min(1.0, abs(n[2]))))
        t = n[:2] / np.linalg.norm(n[:2]) if tilt > 5.0 else U_AXIS
    return dict(site=site, prior=prior, patch=k, kind=int(U["loc_kind"][k]), centre=R["centre"][k].tolist(), t=[float(t[0]), float(t[1])], L=12.0,
                half_width_m=0.25, code_v3=int(R["code_ext_v3"][k]), gt_med=float(R["gt_med"][k]), gt_points=int(R["gt_points"][k]), why=why)


def main():
    out = {}
    m, _ = patches("B173nb_b10", "LoD2", SITES_CFG["B173_wings"]["faces_gml"])
    R = np.load(OUT / "regions_v3" / "regions_ext_v3_B173nb_b10_LoD2.npz")
    out["B173_wing"] = section("B173nb_b10", "LoD2", m & (R["code_ext_v3"] == 11) & (R["kind"] == 1), "south wing, prior error")
    m, U = patches("B173nb_b10", "LoD2", SITES_CFG["B173_middle"]["faces_gml"])
    n = np.cross(U["loc_t1"], U["loc_t2"])
    sl = np.degrees(np.arccos(np.clip(np.abs(n[:, 2]) / np.linalg.norm(n, axis=1), 0, 1)))
    out["B173_sawtooth"] = section("B173nb_b10", "LoD2", m & (R["kind"] == 1) & (sl > 17.0), "sawtooth glass roof")
    R1 = np.load(OUT / "regions_v3" / "regions_ext_v3_R1rep_b10_LoD2.npz")
    m, _ = patches("R1rep_b10", "LoD2", SITES_CFG["R1_hall"]["faces_gml"])
    tab = {r["ext"]: r["building"] for r in json.loads((DR / "s02_box/R1rep_b10/lod2_surfaces.json").read_text())["surfaces"]}
    U1 = np.load(S0 / "s61/box/R1rep_b10/LoD2/units.npz")
    hall_bld = np.array([tab[int(e)] == SITES_CFG["R1_hall"]["building"] for e in U1["surf_ext"][U1["loc_surface"]]])
    out["R1_low_roof"] = section("R1rep_b10", "LoD2", (R1["code_ext_v3"] == 11) & (R1["kind"] == 1) & (R1["gt_med"] < 0) & ~hall_bld,
                                 "roof lower than LoD2 (prior error), outside the translucent-roof building")
    out["R1_translucent"] = section("R1rep_b10", "LoD2", m & (R1["kind"] == 1), "translucent roof (R1_hall)")
    m, _ = patches("B0_b10", "LoD2", SITES_CFG["B0_facade"]["faces_gml"])
    B = np.load(OUT / "regions_v3" / "regions_ext_v3_B0_b10_LoD2.npz")
    out["B0_wall_eaves"] = section("B0_b10", "LoD2", m & (B["kind"] == 2), "facade wall and eaves")
    jdump(OUT / "defs/sections_v1.json", dict(version="sections_v1", task_id="PHD-MAIN-STAGE1-v1", rule=__doc__, sections=out,
                                              written_before_training_results=True, scientific_verdict=None))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
