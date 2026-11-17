#!/bin/bash
# order 6.2 voxel values (CPU), base and occl_10 of the models of the two walls
cd /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_trainerr_v1
for j in R1rep_b10__LoD2:ft R1rep_b10__LoD2:sb3_7000 R1rep_b10__LoD2:sb3_30000 B0_b10__LoD2:ft B0_b10__LoD2:tl_7000 B0_b10__LoD2:tl_30000 B0_b10__LoD2:sa2_30000; do
  for v in base occl_10; do python3 addendum6/a6_launch.py cpu addendum6/a6_ra_tab.py voxels ${j%%:*} ${j##*:} $v; done
done
