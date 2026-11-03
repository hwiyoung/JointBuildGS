"""Whole largest tile jointly serves timing and full CPU/GPU numeric verification."""
import json
import photo_score_reply2 as P
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz,savez
from record_setting_reply2 import record

def main():
    base=O/'r2';tile=json.loads((base/'target_census.json').read_text())['benchmark_tile'];root=base/'photo_scores'/tile;root.mkdir(parents=True,exist_ok=True)
    if (root/'complete.json').exists():return
    record('execution','packed_numeric_verification','whole maximum tile CPU/GPU plus all common points with original float64 200-point reference','Combine required whole-tile timing with stronger whole-tile parity while another research task causes long GPU waits; abort redundant scattered 200-point packed run before completion; keep original 200-point float64 parity and exact numerical tolerances')
    dump(C/'photo_direct_benchmark.reply2.lock.json',dict(at=now(),config_sha256=sha(C/'judgecheck_v1.json'),source_sha256={p.name:sha(p) for p in [Path(__file__),Path(P.__file__)]},
        benchmark_tile=tile,full_census_gate='full-tile CPU/GPU parity, all overlap points vs original 200, plane parity and <=48h whole-tile estimate',scientific_verdict=None))
    g=loadz(base/'photo_prepared'/f'{tile}.npz');result,timing=P.score(g,root);savez(root/'scores.npz',**result);timing.update(tile=tile,output_sha256=sha(root/'scores.npz'),device='cuda',parity_pending=True)
    dump(root/'complete.json',timing);print('GPU_WHOLE_TILE_COMPLETE',json.dumps(timing),flush=True)
if __name__=='__main__':main()
