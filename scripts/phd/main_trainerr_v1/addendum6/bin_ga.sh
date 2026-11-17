#!/bin/bash
# work ga chain (host): dumps then track per scene, R1 x LoD2 first (order 0.2)
cd /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_trainerr_v1
for s in "$@"; do
  python3 addendum6/a6_launch.py cpubig addendum6/a6_ga.py dumps $s || exit 1
  python3 addendum6/a6_launch.py cpubig addendum6/a6_ga.py track $s || exit 1
done
