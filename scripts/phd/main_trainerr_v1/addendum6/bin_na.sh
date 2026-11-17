#!/bin/bash
# work na chain (host, GPU 0): order 4.1 states, then the order 4.3 record-check runs
cd /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_trainerr_v1
for j in B0_b10__LoD2:3000 R1rep_b10__ALS:3000 B0_b10__ALS:3000 B173nb_b10__ALS:3000 B173nb_b10__LoD2:3000 R1rep_b10__LoD2:6000 B0_b10__LoD2:6000 R1rep_b10__LoD2:9000 B0_b10__LoD2:9000 R1rep_b10__LoD2:12000 B0_b10__LoD2:12000 sa1_R1_ALS_record6000:3000 sb1_B0_LoD2_record6000:3000 sb2_B0_ALS_record6000:3000; do
  python3 addendum6/a6_launch.py gpu 0 addendum6/a6_na.py grads ${j%%:*} ${j##*:}
done
