#!/bin/bash
# work da chain (host, GPU 0), R1 x LoD2 first
cd /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_trainerr_v1
for s in R1rep_b10__LoD2 B0_b10__LoD2 R1rep_b10__ALS B0_b10__ALS B173nb_b10__ALS B173nb_b10__LoD2; do python3 addendum6/a6_launch.py gpu 0 addendum6/a6_da.py pix $s; done
