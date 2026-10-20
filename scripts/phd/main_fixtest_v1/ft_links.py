#!/usr/bin/env python3
"""PHD-MAIN-FIXTEST-v1: the links the stage-1 / stage-2 post steps need inside this payload (host, stdlib; relative links, nothing copied),
as stage 3's s3_links.py: gpu_root/stage1 -> ../runs ; gpu_root/defs/<site> -> stage 1's defs of the three sites ;
prep/{ruler, workload, figdefs, variants}.json -> the stage-2 prep.  python3 ft_links.py   scientific_verdict: null."""
import os
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
PH = (REPO.parent / "JointBuildGS-artifacts").resolve() / "phase-payloads/phd"
FT, S2, S1 = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1", PH / "main_stage2_v1/PHD-MAIN-STAGE2-v1", PH / "main_stage1_v1/PHD-MAIN-STAGE1-v1"


def link(target, at):
    at.parent.mkdir(parents=True, exist_ok=True)
    if at.is_symlink() or at.exists():
        return
    os.symlink(os.path.relpath(target, at.parent), at)


def main():
    (FT / "runs").mkdir(parents=True, exist_ok=True)
    link(FT / "runs", FT / "gpu_root/stage1")
    for s in ("B0_b10", "B173nb_b10", "R1rep_b10"):
        link(S1 / "defs" / s, FT / "gpu_root/defs" / s)
    for f in ("ruler.json", "workload.json", "figdefs.json", "variants.json"):
        link(S2 / "prep" / f, FT / "prep" / f)
    print("links ok")


if __name__ == "__main__":
    main()
