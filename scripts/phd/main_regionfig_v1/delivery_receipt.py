"""Record shell-observed Git delivery results and preserve unrelated status entries."""
import sys
from common import *

prefixes=('configs/phd/main_regionfig_v1/','scripts/phd/main_regionfig_v1/','docs/experiments/phd/main_regionfig_v1/')
def outside(path):
    entries=Path(path).read_bytes().split(b'\0')
    return sorted(x.decode() for x in entries if x and not x[3:].decode().startswith(prefixes))

before=outside(PAY/'baseline_git_status.z');after=outside(PAY/'final_git_status.z')
changed=(PAY/'committed_paths.txt').read_text().splitlines()
assert all(p.startswith(prefixes) for p in changed),changed
assert before==after,'Unrelated Git status changed; inspect before delivering'
commit=(PAY/'task_commit.txt').read_text().strip();remote=(PAY/'remote_head.txt').read_text().split()[0]
push_code=int((PAY/'push_exit_code.txt').read_text().strip())
receipt=dict(task_id='PHD-MAIN-REGIONFIG-v1',recorded_at=now(),commit=commit,branch='exp/main-experiment',
             pushed=push_code==0 and remote==commit,push_exit_code=push_code,remote_head=remote,
             changed_paths=changed,unrelated_git_status_unchanged=True,
             source_changes=False,training=False,gpu_used=False,scientific_verdict=None)
dump(PAY/'delivery_receipt.json',receipt)
print(json.dumps(receipt,ensure_ascii=False,indent=2))
