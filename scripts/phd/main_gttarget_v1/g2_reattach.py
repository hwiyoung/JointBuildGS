"""Stage 2: re-attach to a training container whose host launcher died with the session (2026-11-19 17:01). Follows the container log into
train_reattached.log, waits for exit, writes receipt.json with the launch.py rule (status COMPLETED / HEALTH_STOP / ERROR) plus reattached=true. usage: g2_reattach.py <stem> <run>"""
import datetime as dt, json, subprocess, sys
from pathlib import Path
R = Path(__file__).resolve().parents[3]; O = R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_gttarget_v1/PHD-MAIN-GTTARGET-v1'
stem, run = sys.argv[1:3]; root = O/'runs'/stem/run; name = json.loads((root/'command.json').read_text())[json.loads((root/'command.json').read_text()).index('--name')+1]
with open(root/'train_reattached.log', 'x') as f: lg = subprocess.Popen(['docker', 'logs', '-f', '--since', '2026-11-19T17:01:00+09:00', name], stdout=f, stderr=subprocess.STDOUT)
rc = int(subprocess.run(['docker', 'wait', name], capture_output=True, text=True).stdout.strip() or -1); lg.wait(timeout=60)
t0 = dt.datetime.fromisoformat(json.loads((root/'launch.json').read_text())['at']); now = dt.datetime.now().astimezone(); stop = root/'model/target_monitor/STOP.json'
status = 'COMPLETED' if rc == 0 and (root/'TRAINING_COMPLETE.json').exists() else ('HEALTH_STOP' if stop.exists() else 'ERROR')
rec = dict(at=now.isoformat(), stem=stem, run=run, exit_code=rc, seconds=(now-t0).total_seconds(), status=status, health=json.loads(stop.read_text()) if stop.exists() else None,
           reattached=True, note='host launcher died at session end ~17:01; container kept running; log after 17:01 in train_reattached.log', scientific_verdict=None)
json.dump(rec, open(root/'receipt.json', 'x'), ensure_ascii=False, indent=1); print(json.dumps(rec))
