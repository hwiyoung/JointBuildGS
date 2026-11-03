"""Append operational or derived Stage-A settings, keeping every preceding config."""
import json
from preflight import C,sha,dump,now

def record(section,key,value,reason):
    path=C/'judgecheck_v1.json';cfg=json.loads(path.read_text())
    if cfg.setdefault(section,{}).get(key)==value:return sha(path)
    before=sha(path);rev=C/'revisions/r2'/f'judgecheck_v1.{before[:16]}.json';rev.write_bytes(path.read_bytes());at=now()
    cfg[section][key]=value;cfg['amendments'].append(dict(at=at,reason=reason,previous_config_sha256=before,section=section,key=key,value=value))
    dump(path,cfg);lock=C/'judgecheck_v1.reply2.lock.json';previous=json.loads(lock.read_text());(C/'revisions/r2'/f'judgecheck_v1.{before[:16]}.lock.json').write_bytes(lock.read_bytes())
    previous.update(at=at,config_sha256=sha(path),previous_config_sha256=before,before_resumed_calculation=False,initial_precalculation_lock_preserved_in_revisions=True);dump(lock,previous);return sha(path)
