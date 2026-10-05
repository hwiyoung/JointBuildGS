#!/usr/bin/env bash
# Headless-browser check of out/viewer.html (step 4-10): console errors, PNG/sidecar loads, condition
# switching. Uses the host browser only (no project dependency); results go to logs/viewer_check.json.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
TASK="$ART/phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
CHROME=${CHROME:-google-chrome}
URL="file://$TASK/out/viewer.html?selftest=1"
PROFILE=$(mktemp -d)
START=$(date -Iseconds)
timeout 600 "$CHROME" --headless=new --disable-gpu --no-sandbox --allow-file-access-from-files --user-data-dir="$PROFILE" \
  --enable-logging=stderr --v=0 --virtual-time-budget=300000 --window-size=1400,900 --dump-dom "$URL" \
  > "$TASK/logs/viewer_check_dom.html" 2> "$TASK/logs/viewer_check_stderr.log"
RC=$?
rm -rf "$PROFILE"
python3 - "$TASK" "$START" "$RC" "$("$CHROME" --version 2>/dev/null)" <<'PY'
import json,re,sys
task,start,rc,ver=sys.argv[1:5]
err=open(f'{task}/logs/viewer_check_stderr.log',errors='replace').read()
dom=open(f'{task}/logs/viewer_check_dom.html',errors='replace').read()
m=re.search(r'JBGS_SELFTEST (\{.*?\})"',err) or re.search(r'JBGS_SELFTEST (\{.*\})',err)
rep=json.loads(m.group(1).replace('\\"','"')) if m else None
if rep is None:
    m2=re.search(r'<pre id="selftest">(.*?)</pre>',dom,re.S)
    rep=json.loads(m2.group(1)) if m2 else None
console_errors=[l for l in err.splitlines() if 'CONSOLE' in l and 'JBGS_SELFTEST' not in l and ('ERROR:CONSOLE' in l or 'Uncaught' in l or 'error' in l.split('CONSOLE',1)[1].lower())]
out={'browser':ver.strip(),'started_at':start,'exit_code':int(rc),'selftest':rep,'console_error_lines':console_errors,
     'title_pass':'SELFTEST PASS' in dom,'status':'PASS' if (rep and rep.get('ok') and not console_errors) else 'FAILED','scientific_verdict':None}
json.dump(out,open(f'{task}/logs/viewer_check.json','w'),indent=2,ensure_ascii=False)
print(json.dumps(out,ensure_ascii=False)[:1500])
PY
