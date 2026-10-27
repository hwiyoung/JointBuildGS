"""Post-only memory policy; the proposed profile is inert without approval."""
import json
from pathlib import Path

DEFAULT=dict(id='resource_resume_v1',host_available_GiB=64,container_limit_GiB=48,stable_seconds=60)
PROPOSED=dict(id='resource_resume_56_40_v1',host_available_GiB=56,container_limit_GiB=40,stable_seconds=60)


def policy_for(root):
    path=Path(root)/'checks/post_memory_56_40_v1/authorization.json'
    if not path.exists():return dict(DEFAULT)
    record=json.loads(path.read_text())
    assert record['status']=='AUTHORIZED' and record['policy']==PROPOSED
    assert record['user_instruction'].strip()
    return dict(PROPOSED)
