#!/usr/bin/env bash
# 묶음 나 마무리 셈(사슬 B2 뒤): 두 줄을 함께.
#  줄 1: 캠퍼스 B_orig·B_view·C 의 지워진 점만 원통(_rm, 9절 검산 2 패치마다) → 검산 다시(mf7b).
#  줄 2: 7절 그림(B·C; 지도는 발주대로 방법 A 만) → 상자 MVS 에 B·C(mf10b) → t5_survival_box 다시.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); R="$H/run.sh"; O="$1"
st() { echo "$1 $(date +%H:%M)"; }
TILES_BIG="6909_53361 6909_53359 6908_53359 6908_53360 6910_53361 6909_53360 6910_53360 6908_53361 6909_53362 6910_53362 6910_53359 6911_53362 6910_53363 6909_53358 6909_53363 6911_53361 6908_53362 6908_53358 6907_53359 6911_53360 6907_53360 6910_53358 6911_53363 6912_53362"
(
  for m in B_orig B_view C; do bash "$R" patch_${m}_rm --cpus 40 --mem 30 mf2_patch.py ${m}_rm $TILES_BIG 2>&1 | grep -E "Error|Traceback" | head -5; st "rm $m $(ls $O/patch/${m}_rm/*.npz | wc -l)"; done
  bash "$R" checks_B2 --cpus 4 --mem 16 mf7b_checks.py A B_orig B_view C 2>&1 | grep -E "CHECK|Error|Traceback" | cut -c1-300; st "checks"
) &
(
  for p in LoD2 ALS; do bash "$R" figs_B_$p --cpus 4 --mem 24 mf8_figs.py $p B_orig B_view C 2>&1 | grep -E "Error|Traceback" | head -5; st "figs $p"; done
  bash "$R" box_BC --cpus 8 --mem 30 mf10b_box_bc.py B0_b10 B173nb_b10 R1rep_b10 2>&1 | grep -E "WOLFF|STAT_C|BOXBC|Error|Traceback" | cut -c1-600; st "box BC"
) &
wait
echo CHAIN_B3_DONE $(date +%H:%M)
