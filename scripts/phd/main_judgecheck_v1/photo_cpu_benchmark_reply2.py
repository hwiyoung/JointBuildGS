"""Whole-tile CPU alternative timing while the mandated GPU wait is active."""
import json
import photo_score_reply2 as P
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz,savez

def main():
    base=O/'r2';tile=json.loads((base/'target_census.json').read_text())['benchmark_tile'];root=base/'cpu_benchmark'/tile;root.mkdir(parents=True,exist_ok=True)
    if (root/'complete.json').exists():return
    dump(C/'photo_cpu_benchmark.reply2.lock.json',dict(at=now(),source_sha256={p.name:sha(p) for p in [Path(__file__),Path(P.__file__)]},
        purpose='full-tile CPU timing alternative during waiting for another research GPU task',chunk_rows=600000,batch_rows=1024,gpu_use=False,scientific_verdict=None))
    g=loadz(base/'photo_prepared'/f'{tile}.npz');P.BASE=base/'cpu_benchmark' # Private write cache; no cache-write race with GPU run.
    result,timing=P.score(g,root,device='cpu',chunk_rows=600000,batch_rows=1024);savez(root/'scores.npz',**result);timing.update(tile=tile,status='CPU_WHOLE_TILE_MEASURED',output_sha256=sha(root/'scores.npz'),device='cpu')
    dump(root/'complete.json',timing);dump(D/'tables/reply2_cpu_whole_tile.json',timing);print('CPU_WHOLE_TILE_COMPLETE',json.dumps(timing),flush=True)
if __name__=='__main__':main()
