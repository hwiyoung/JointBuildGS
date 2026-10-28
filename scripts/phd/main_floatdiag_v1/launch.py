"""Host stdlib only: execute an immutable shell-script snapshot.

All project libraries and computation remain inside Docker. A resident GNOME
remote-desktop CUDA context is not a training workload and is left untouched.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

here=Path(__file__).resolve().parent
kind,*args=sys.argv[1:]
assert kind in ['cpu','gpu']
script=here/('run_'+kind+'.sh');text=script.read_text()
if kind=='gpu':
    old='busy=$(nvidia-smi -i "$gpu" --query-compute-apps=pid --format=csv,noheader)'
    new='busy=$(nvidia-smi -i "$gpu" --query-compute-apps=pid,process_name --format=csv,noheader | awk -F", " \'$2 != "/usr/libexec/gnome-remote-desktop-daemon" && $2 != "/usr/lib/xorg/Xorg" {print $1}\')'
    assert old in text
    text=text.replace(old,new)
out=here.parents[2].parent/'JointBuildGS-artifacts'
repo=here.parents[2]
payload=repo.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_floatdiag_v1/PHD-MAIN-FLOATDIAG-v1'
folder=payload/'launches';folder.mkdir(parents=True,exist_ok=True)
stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%dT%H%M%S%f')
snapshot=folder/(stamp+'_'+kind+'.sh');snapshot.write_text(text)
(snapshot.with_suffix('.json')).write_text(json.dumps(dict(script=str(script),arguments=args,snapshot=str(snapshot),
    at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),scientific_verdict=None),indent=2)+'\n')
# $0 deliberately points at the canonical script, retaining its repository-root
# resolution while Bash parses the immutable in-memory text in one argument.
raise SystemExit(subprocess.run(['bash','-c',text,str(script),*args]).returncode)
