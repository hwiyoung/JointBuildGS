import subprocess
from gpu_job import R,O,D,dump
from publish import lock,commit
S=R/'scripts/phd/main_release_v1'
subprocess.run(['bash',str(S/'run_cpu.sh'),'select-rule','selection_values.py'],cwd=R,check=True)
with lock():
 head=commit('stage 3 prespecified rule selection',[D/'단계3_고른규칙.json',S/'selection_values.py',S/'select_rule.py']);dump(O/'delivery/stage3_selection.json',dict(commit=head,scientific_verdict=None))
