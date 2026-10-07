"""PHD-MAIN-STAGE1-v1 3.6: box meshes and judgment-unit stores with another patch size (jointbuildgs:dev, CPU). A wrapper of the unchanged
discard-task script scripts/phd/main_prep_discard_rule_v1/s02_meshes.py with the box command of that task
(--ranges-file /prep/step06/box_ranges.json --margin 0) and one override: the judgment cell (patch) size.

  python sens_s02.py <patch_0125|patch_05> <site>     -> /out/sens/<variant>/s02_box/<site>/
scientific_verdict: null."""
import sys

sys.path.insert(0, "/repo/scripts/phd/main_prep_discard_rule_v1")
sys.path.insert(0, "/repo")
import common  # noqa: E402  (the discard task's common: OUT = /out)
import s02_meshes  # noqa: E402

SIZE = {"patch_0125": 0.125, "patch_05": 0.5}


def main(variant, site):
    assert common.CFG is s02_meshes.CFG
    common.CFG["judgment"]["cell_m"] = SIZE[variant]
    sys.argv = ["s02_meshes.py", site, "--ranges-file", "/prep/step06/box_ranges.json", "--margin", "0", "--out-sub", f"sens/{variant}/s02_box"]
    s02_meshes.main()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
