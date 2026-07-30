#!/usr/bin/env bash
# OVERNIGHT unattended driver — Task A (D12 metric-final, short) THEN Task B (generation 8-way over the
# P0 failure population, long). NO retrain (reuses existing ckpts/npz). Robust: per-item failure -> issues.md
# and CONTINUE; Tasks A & B independent; stop ONLY on fatal repo import break. Resumable (skip done).
# Per-item timestamped logs. OOM-safe (chunked extract). EPSG:25832. Roofer global single setting. Observe only.
# Launch: setsid nohup bash scripts/evaluation/quality_score/run_overnight.sh > results/tum_transfer/mob/overnight.log 2>&1 < /dev/null &
cd "$(dirname "$0")/../../.." || exit 1
OUT=results/tum_transfer/mob; WS=/workspace/JointBuildGS; U="$(id -u):$(id -g)"
GEOJSON=results/tum_transfer/analysis/footprints_aoi.geojson
ISSUES=phases/p2-gsjso/docs/issues.md; SUMMARY=docs/evidence/archive/overnight_coordination/temporary/reports/overnight_summary.md
TOOLS="docker run --rm --user $U -v $PWD:/workspace/JointBuildGS -w /workspace/JointBuildGS jointbuildgs-p0-tools:t0"
mkdir -p "$OUT/overnight_logs"
log(){ echo "[$(date '+%F %T')] $*"; }
issue(){ echo "- [overnight $(date '+%F %T')] $*" >> "$ISSUES"; log "ISSUE LOGGED: $*"; }
[ -f "$ISSUES" ] || echo "# issues.md — 무인 런 실패·스킵 로그" > "$ISSUES"
log "===== OVERNIGHT START (commit=$(git rev-parse --short HEAD) branch=$(git rev-parse --abbrev-ref HEAD)) ====="

# ---- FATAL guard: repo import must work (else write issue + exit) ----
if ! docker compose run --rm -T dev python -c "import src.stage2.train, src.stage2.renderer" > "$OUT/overnight_logs/import_check.log" 2>&1; then
  issue "FATAL: repo import (src.stage2) broken — see overnight_logs/import_check.log; ABORT"
  echo "ABORTED: import" >> "$SUMMARY"; exit 1
fi
log "import OK"

#############################################  TASK A  #############################################
log "===== TASK A (D12 metric-final) start ====="
{
  $TOOLS python3 scripts/evidence_and_attributes/diagnostic_tables/d12_metric_final.py --targets-file "$OUT/d12_targets_79.txt" \
    > "$OUT/overnight_logs/taskA_metric_final.log" 2>&1 \
    && log "Task A metric-final OK" || issue "Task A d12_metric_final.py failed (see taskA_metric_final.log)"
  git add docs/experiments/evaluation/w_d12_metric/reports/W_D12_metric_final.md scripts/evidence_and_attributes/diagnostic_tables/d12_metric_final.py \
          results/tum_transfer/mob/overseg_lever/d12_metric_final.csv 2>/dev/null
  git commit -q -m "d12-metric-final

D12 metric finalization (no retrain, recompute over 78-set): common-dz height + absolute,
support-gated point-weighted slope, facet-match-rate horizontal. textureless 0.55<survivor
1.48 (relative); abs ~2.6m both (textureless=uniform slab shift). B1 weak (dH-0.01/dSupp+0.046).
Report docs/experiments/evaluation/w_d12_metric/reports/W_D12_metric_final.md.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" 2>/dev/null \
    && log "Task A committed d12-metric-final" || log "Task A: nothing new to commit"
}
log "===== TASK A done ====="

#############################################  TASK B  #############################################
log "===== TASK B (generation 8-way) start ====="
{
  # Step0 — bucket labels
  $TOOLS python3 scripts/evidence_and_attributes/diagnostic_tables/d12_buckets.py > "$OUT/overnight_logs/taskB_buckets.log" 2>&1 \
    && log "buckets OK" || issue "Task B d12_buckets.py failed"
  if [ ! -f "$OUT/overseg_lever/d12_buckets.csv" ]; then
    issue "Task B: no d12_buckets.csv — skip Task B";
  else
    ALL64="$(awk -F, 'NR>1{print $1}' "$OUT/overseg_lever/d12_buckets.csv" | tr '\n' ' ')"
    METHOD="$(awk -F, 'NR>1 && $3=="True"{print $1}' "$OUT/overseg_lever/d12_buckets.csv" | tr '\n' ' ')"
    log "all64=$(echo $ALL64|wc -w) method-relevant=$(echo $METHOD|wc -w)"

    # baselines for the 64 (bbox + ALS density)
    BASE="$OUT/baselines_gen8.json"
    if [ ! -f "$BASE" ]; then
      $TOOLS python3 scripts/input_and_alignment/tum_transfer/tum_mob_baselines.py \
        --gml "$WS/phases/p0-audit/data/raw/lod2/690_5334.gml" "$WS/phases/p0-audit/data/raw/lod2/690_5336.gml" \
        --geojson "$WS/$GEOJSON" --als-glob "$WS/phases/p0-audit/data/raw/als/*.laz" \
        --targets $ALL64 --out "$WS/$BASE" > "$OUT/overnight_logs/taskB_baselines.log" 2>&1 \
        && log "baselines_gen8 OK" || issue "Task B baselines failed — Roofer box may miss buildings"
    fi

    eval_one(){ # $1=arm $2=npz $3=classifier $4=targets $5=tag
      local arm=$1 npz=$2 clf=$3 tg="$4" tag=$5
      local outj="$OUT/eval_gen8_${arm}_${tag}.json"
      [ -f "$outj" ] && { log "SKIP eval $arm/$tag (done)"; return; }
      python3 scripts/input_and_alignment/tum_transfer/tum_mob_eval.py --configs ${arm}=${npz} --geojson "$GEOJSON" \
        --baselines "$BASE" --targets $tg --densities orig --classifier $clf --out "$outj" \
        > "$OUT/overnight_logs/taskB_eval_${arm}_${tag}.log" 2>&1 \
        && log "eval $arm/$tag rc=0" || issue "Task B eval $arm/$tag failed (see taskB_eval_${arm}_${tag}.log)"
    }

    # ---- raw baselines + LiDAR over ALL 64 (no extract; chunk 16 for safety/resume) ----
    read -ra AA <<< "$ALL64"; NA=${#AA[@]}; CH=16
    for arm in raw_sparse raw_dense raw_acmp raw_lidar; do
      [ -f "$OUT/raw/$arm.npz" ] || { issue "Task B: $OUT/raw/$arm.npz missing — skip arm $arm"; continue; }
      ci=0; for ((i=0;i<NA;i+=CH)); do ci=$((ci+1)); CHKR="${AA[*]:i:CH}"; eval_one "$arm" "$OUT/raw/$arm.npz" smrf "$CHKR" "c$ci"; done
    done

    # ---- GS arms over METHOD-relevant (chunked extract 10 -> gssem eval) ----
    read -ra MM <<< "$METHOD"; NM=${#MM[@]}; CG=10
    for arm in gs_seed_sparse gs_seed_dense gs_seed_acmp; do
      [ -f "$OUT/$arm/ckpt/final.pt" ] || { issue "Task B: $arm ckpt missing — skip"; continue; }
      ci=0
      for ((i=0;i<NM;i+=CG)); do
        ci=$((ci+1)); CHK="${MM[@]:i:CG}"
        local_out="$OUT/eval_gen8_${arm}_g$ci.json"
        [ -f "$local_out" ] && { log "SKIP GS $arm/g$ci (done)"; continue; }
        rm -f "$OUT/tsdf_gen8.npz"
        docker compose run --rm -T dev python scripts/stage3_readout/tum_mob_tsdf_extract.py \
          --ckpt "$WS/$OUT/$arm/ckpt/final.pt" --out "$WS/$OUT/tsdf_gen8.npz" \
          --min-obs 3 --voxel 0.05 --downscale 1.0 --targets $CHK \
          > "$OUT/overnight_logs/taskB_extract_${arm}_g$ci.log" 2>&1
        if [ $? -ne 0 ] || [ ! -f "$OUT/tsdf_gen8.npz" ]; then
          issue "Task B extract $arm/g$ci failed/OOM (npz missing) — chunk skipped"; continue
        fi
        python3 scripts/input_and_alignment/tum_transfer/tum_mob_eval.py --configs ${arm}=$OUT/tsdf_gen8.npz --geojson "$GEOJSON" \
          --baselines "$BASE" --targets $CHK --densities orig --classifier gssem --out "$local_out" \
          > "$OUT/overnight_logs/taskB_eval_${arm}_g$ci.log" 2>&1 \
          && log "GS eval $arm/g$ci rc=0" || issue "Task B GS eval $arm/g$ci failed"
      done
    done

    # Step2 — aggregate + report
    $TOOLS python3 scripts/evaluation/quality_score/gen_8way_aggregate.py > "$OUT/overnight_logs/taskB_aggregate.log" 2>&1 \
      && log "aggregate OK" || issue "Task B gen_8way_aggregate.py failed"
    git add docs/experiments/evaluation/w_generation_8way/reports/W_generation_8way.md scripts/evidence_and_attributes/diagnostic_tables/d12_buckets.py \
            scripts/evaluation/quality_score/gen_8way_aggregate.py scripts/evaluation/quality_score/run_overnight.sh 2>/dev/null
    git commit -q -m "gen-8way-fail

Generation 8-way over the P0 failure population (64, no retrain): eval existing
gs_seed_{sparse,dense,acmp} + raw_{sparse,dense,acmp,lidar} per mechanism bucket
(① textureless / ② assembly / ③ coverage / ④ impossible). Same Roofer global setting.
Report docs/experiments/evaluation/w_generation_8way/reports/W_generation_8way.md.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" 2>/dev/null \
      && log "Task B committed gen-8way-fail" || log "Task B: nothing new to commit"
  fi
}
log "===== TASK B done ====="

#############################################  SUMMARY  #############################################
{
  echo "# overnight_summary — 무인 런 아침 요약 ($(date '+%F %T'))"
  echo ""
  echo "## 완료 여부"
  echo "- Task A (D12 metric-final): $([ -f docs/experiments/evaluation/w_d12_metric/reports/W_D12_metric_final.md ] && echo '완료' || echo '미완') · 커밋 $(git log --oneline | grep -m1 d12-metric-final | awk '{print $1}' || echo none)"
  echo "- Task B (generation 8-way): $([ -f docs/experiments/evaluation/w_generation_8way/reports/W_generation_8way.md ] && echo '완료' || echo '미완') · 커밋 $(git log --oneline | grep -m1 gen-8way-fail | awk '{print $1}' || echo none)"
  echo ""
  echo "## 생성 처리/미처리 (버킷)"
  [ -f "$OUT/overseg_lever/d12_buckets.csv" ] && awk -F, 'NR>1{c[$2]++} END{for(b in c) printf "- %s: %d동\n", b, c[b]}' "$OUT/overseg_lever/d12_buckets.csv"
  echo "- arm별 eval json 생성: $(ls "$OUT"/eval_gen8_*.json 2>/dev/null | wc -l)개"
  echo ""
  echo "## issues.md 요약 ($(grep -c '^- ' "$ISSUES" 2>/dev/null) 항목)"
  tail -25 "$ISSUES" 2>/dev/null
  echo ""
  echo "## 아침 체크리스트"
  echo "- [ ] W_D12_metric_final.md 표·결론 확인 (커밋 d12-metric-final)"
  echo "- [ ] W_generation_8way.md 버킷별 카운트표 확인 (커밋 gen-8way-fail)"
  echo "- [ ] issues.md 실패 항목 검토 (생성 누락 동·OOM 청크)"
  echo "- [ ] 미푸시 — 푸시 여부 판정 (판정=김휘영)"
} > "$SUMMARY"
git add "$SUMMARY" "$ISSUES" docs/experiments/evaluation/w_generation_8way/reports/W_generation_8way.md 2>/dev/null
git commit -q -m "overnight-summary

overnight unattended run summary + issues log.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" 2>/dev/null && log "summary committed" || log "summary: nothing to commit"
log "===== OVERNIGHT DONE ====="
