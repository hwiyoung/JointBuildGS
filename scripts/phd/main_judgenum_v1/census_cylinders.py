"""One-tile timing gate, then resumable per-tile cylinder census."""
import argparse
import json
from pathlib import Path
import resource
import time
import numpy as np
from lock_config import dump,sha,stamp
from cylinder_runtime import run
O=Path('/out');C=Path('/cfg');D=Path('/docs');S=Path(__file__).parent

def tile_run(tile,cfg):
    dest=O/'cylinders'/f'{tile}.bin'
    if dest.with_suffix('.complete.json').exists():return json.loads(dest.with_suffix('.complete.json').read_text())
    paths=sorted((O/'inputs').glob(tile+'__*.npz'));centres=[];normals=[];parts=[];offset=0
    for path in paths:
        with np.load(path) as z:
            centres.append(z['centre']);normals.append(z['normal']);N=len(z['centre'])
        parts.append({'file':str(path),'sha256':sha(path),'start':offset,'count':N});offset+=N
    mvs=Path(cfg['sources']['mvs_points'].replace('<tile>',tile))
    seconds=run(mvs,np.concatenate(centres),np.concatenate(normals),dest,O/'tmp/cylinders')
    receipt={'tile':tile,'parts':parts,'seconds':seconds,'status':'COMPLETE',
      'maxrss_kib':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
      'config_sha256':sha(C/'judgenum_v1.json'),'scientific_verdict':None}
    dump(dest.with_suffix('.complete.json'),receipt);return receipt

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--benchmark',action='store_true');parser.add_argument('--tile');args=parser.parse_args()
    cfg=json.loads((C/'judgenum_v1.json').read_text());lock=json.loads((C/'judgenum_v1.lock.json').read_text())
    assert sha(C/'judgenum_v1.json')==lock['config_sha256']
    assert cfg['figures']['section_coordinates'] is not None
    check=json.loads((O/'cylinder_verification.json').read_text())
    assert check['status']=='PASS' and check['source_sha256']==sha(S/'cylinders.cpp')
    build=json.loads((O/'tmp/cylinders_build.json').read_text())
    assert build['source_sha256']==sha(S/'cylinders.cpp') and build['binary_sha256']==sha(O/'tmp/cylinders')
    impl={'at':stamp(),'config_sha256':sha(C/'judgenum_v1.json'),
      'sources':{p.name:sha(p) for p in sorted(S.glob('*')) if p.is_file()},'scientific_verdict':None}
    if not (C/'cylinder_implementation.lock.json').exists():dump(C/'cylinder_implementation.lock.json',impl)
    else:
        old=json.loads((C/'cylinder_implementation.lock.json').read_text())
        for key in ['cylinders.cpp','cylinder_runtime.py','census_cylinders.py']:
            assert old['sources'][key]==sha(S/key)
    tiles=sorted({p.stem.split('__')[0] for p in (O/'inputs').glob('*.npz')})
    if args.benchmark:
        tile=cfg['execution']['benchmark_tile'];record=tile_run(tile,cfg)
        estimate=record['seconds']*24
        result={'status':'STOP_CPU_ESTIMATE' if estimate>72*3600 else 'PASS_CPU_ESTIMATE',
          'benchmark_tile':tile,'benchmark_seconds':record['seconds'],'frozen_tile_count':24,
          'nonempty_eligible_tile_count':len(tiles),'estimated_seconds':estimate,
          'estimated_hours':estimate/3600,'basis':'largest eligible tile, all radii and half-lengths; one tile time times 24',
          'scope':'cylinder census only; component/selection/figure time is additional and not yet timed',
          'scientific_verdict':None,'at':stamp()}
        dump(O/'time_gate.json',result);dump(D/'tables/time_gate.json',result);print(json.dumps(result,ensure_ascii=False))
    else:
        assert json.loads((O/'time_gate.json').read_text())['status']=='PASS_CPU_ESTIMATE'
        for tile in [args.tile] if args.tile else tiles:tile_run(tile,cfg)

if __name__=='__main__':main()
