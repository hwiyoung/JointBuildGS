#!/bin/bash
# work da re-run (order 5.1 behind-weight size and distance added), GPU 0, one scene at a time
cd /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_trainerr_v1
for s in R1rep_b10__LoD2 B0_b10__LoD2 R1rep_b10__ALS B0_b10__ALS B173nb_b10__ALS B173nb_b10__LoD2; do python3 addendum6/a6_launch.py gpu 0 addendum6/a6_da.py pix $s; done
python3 addendum6/a6_launch.py cpu addendum6/a6_da.py tables
