#!/usr/bin/env bash
# Runs only after the current job and the priority-six AXES attempts finish.
set -euo pipefail
task_repo=${JBGS_MESHPATCH_REPO:-$(cd "$(dirname "$0")/../../.." && pwd)}
task_out=$(realpath "$task_repo/../JointBuildGS-artifacts/phase-payloads/phd/main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1")
cd "$task_repo"
while [[ ! -f "$task_out/interview_v2/implementation_ready.json" ]]; do
  printf 'Interview addendum: waiting for validated implementation, %s\n' "$(date -Is)"
  sleep 30
done
bash scripts/phd/main_meshpatch_v1/run_cpu.sh interview-prepare interview_prepare.py
mapfile -t interview_jobs < <(python - <<'PY'
import json
from pathlib import Path
for r in json.loads(Path('docs/experiments/phd/main_meshpatch_v1/interview_v2/jobs.json').read_text())['jobs']:
 print(r['tag'],r['script'],*r.get('args',[]))
PY
)
for task_job in "${interview_jobs[@]}"; do
  read -r -a task_args <<< "$task_job"
  task_tag=${task_args[0]}
  if [[ -f "docs/experiments/phd/main_meshpatch_v1/interview_v2/status/$task_tag.json" ]] && python - "$task_tag" <<'PY'
import json,sys
from pathlib import Path
r=json.loads((Path('docs/experiments/phd/main_meshpatch_v1/interview_v2/status')/(sys.argv[1]+'.json')).read_text())
raise SystemExit(0 if r['status'] in ['PASS','PARTIAL','UNAVAILABLE','WAIT_RESOURCE_REVIEW'] else 1)
PY
  then continue; fi
  if ! bash scripts/phd/main_meshpatch_v1/run_cpu.sh "interview-$task_tag" --large interview_guard.py "$task_tag" "${task_args[@]:1}"; then
    printf '%s\t%s\tinterview_failed\n' "$(date -Is)" "$task_tag" >> "$task_out/logs/queue_failures.tsv"
  fi
  bash scripts/phd/main_meshpatch_v1/run_cpu.sh interview-progress interview_delivery.py
  if [[ "$task_tag" == comparison || "$task_tag" == counts ]]; then
    bash scripts/phd/main_meshpatch_v1/run_cpu.sh interview-package-phase interview_delivery.py --package
  fi
done
python - "$task_out" <<'PY'
import json,sys,datetime
from pathlib import Path
p=Path(sys.argv[1])/'interview_v2/cpu_queue_finished.json'
p.write_text(json.dumps(dict(at=datetime.datetime.now().astimezone().isoformat(),status='FINISHED_ATTEMPTS',scientific_verdict=None))+'\n')
PY
bash scripts/phd/main_meshpatch_v1/run_cpu.sh interview-validation interview_validate.py
bash scripts/phd/main_meshpatch_v1/run_cpu.sh interview-delivery interview_delivery.py --package
