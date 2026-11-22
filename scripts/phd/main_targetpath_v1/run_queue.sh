#!/bin/bash
# PHD-MAIN-TARGETPATH-v1 queues (CPU only). usage: run_queue.sh a | b | c
#  a: GT buffers (B173, B0) then order-2 pairs for every scene/run except B173 x ALS FINALTRAIN
#  b: B173 x ALS FINALTRAIN CPU compositing of every selected point (its stored base render is absent), then its order-2 pairs
#  c: order-4 compositing (sub) of the remaining scenes, FINALTRAIN then GTT
L="python3 $(dirname "$0")/launch.py cpu"
case "$1" in
 a) for s in B173nb_b10 B0_b10; do TP_CPUS=8 TP_MEM=24g $L tp0_gtbuf.py $s; done
    for s in R1rep_b10__ALS B0_b10__ALS R1rep_b10__LoD2 B173nb_b10__LoD2 B0_b10__LoD2; do TP_CPUS=12 TP_MEM=24g $L tp2_pixels.py $s ft; done
    for s in R1rep_b10__ALS B173nb_b10__ALS B0_b10__ALS R1rep_b10__LoD2 B0_b10__LoD2; do TP_CPUS=12 TP_MEM=24g $L tp2_pixels.py $s gtt; done ;;
 b) TP_CPUS=10 TP_MEM=36g $L tp4_contrib.py B173nb_b10__ALS ft all
    until [ -f /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_targetpath_v1/PHD-MAIN-TARGETPATH-v1/gtbuf/B173nb_b10.json ]; do sleep 20; done
    TP_CPUS=12 TP_MEM=24g $L tp2_pixels.py B173nb_b10__ALS ft ;;
 c) for s in R1rep_b10__ALS R1rep_b10__LoD2 B173nb_b10__LoD2 B0_b10__LoD2; do TP_CPUS=10 TP_MEM=36g $L tp4_contrib.py $s ft sub; done
    for s in R1rep_b10__ALS B173nb_b10__ALS B0_b10__ALS R1rep_b10__LoD2 B0_b10__LoD2; do TP_CPUS=10 TP_MEM=36g $L tp4_contrib.py $s gtt sub; done ;;
esac
