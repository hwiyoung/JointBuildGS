"""Ordered census after full-tile numerical and time gates; identical float64 score kernel."""
import json,sys
import photo_score_reply2 as P
from preflight import C,O,Path,sha,dump,now
from geometry import loadz,savez
from record_setting_reply2 import record
BASE=O/'r2'
def main(arg,device='cuda'):
    tile,group=arg.split(':');group=int(group);gate=json.loads((BASE/'timing_estimate.json').read_text());assert gate['status']=='PASS_CONTINUE_STAGE_A' and gate['estimated_hours']<=48
    largest=json.loads((BASE/'target_census.json').read_text())['benchmark_tile'];assert json.loads((BASE/'photo_scores'/largest/'numeric_parity.json').read_text())['status']=='PASS_WHOLE_TILE_PHOTO_PARITY'
    root=BASE/'photo_scores'/tile/f'group{group}';root.mkdir(parents=True,exist_ok=True)
    if (root/'complete.json').exists() or (root.parent/'complete.json').exists():print('PHOTO_SCORE_REUSE',tile,group);return
    assert device in ['cuda','cpu']
    if device=='cpu':assert gate['cpu_estimated_hours']<=72
    record('execution','census_device_rule','try guarded GPU per tile/group; if another research task is active, use the fully verified float64 CPU kernel while the measured CPU estimate stays <=72h; check GPU again for the next tile/group','Original order 1.1 permits CPU or waiting. Another research training started after whole-tile gate passed; continue on CPU without changing any numerical rule, target, threshold or tolerance')
    sources={p.name:sha(p) for p in [Path(__file__),Path(P.__file__)]};lock=C/'photo_group.reply2.lock.json'
    if lock.exists():assert json.loads(lock.read_text())['sources']==sources
    else:dump(lock,dict(at=now(),sources=sources,config_sha256=sha(C/'judgecheck_v1.json'),kernel='same score() verified on full maximum tile',scientific_verdict=None))
    g=P.subset(loadz(BASE/'photo_prepared'/f'{tile}.npz'),group);result,timing=P.score(g,root,device=device,chunk_rows=600000 if device=='cpu' else 900000,batch_rows=1024 if device=='cpu' else 8192);savez(root/'scores.npz',**result);timing.update(tile=tile,group=group,output_sha256=sha(root/'scores.npz'),device=device);dump(root/'complete.json',timing);print('PHOTO_GROUP_COMPLETE',tile,group,json.dumps(timing),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
