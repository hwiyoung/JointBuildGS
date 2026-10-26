"""8.3 exact AXES71 sampling/metric functions, redirected output paths only."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,'/repo/scripts/phd/main_axes71_v2')
import ax_common as AX
import a2x_sample as A
import ax_arrays as AA
from a3_metrics import blocks_of

LT=Path('/lt');DEST=LT/'axes/dist';DEST.mkdir(parents=True,exist_ok=True)
OLD_AX=AX.AX

def find(site,prior,result,suffix=''):
    name=f'{site}_{prior}__{result}{suffix}.npz'
    for d in [DEST,AX.DM/'dist',AX.FT/'dist',OLD_AX/'dist']:
        p=d/name
        if p.exists():return p
    return None

def xfile(site,prior,result):
    name=f'{site}_{prior}__{result}__x.npz'
    original=OLD_AX/'dist'/name
    return original if original.exists() else DEST/name

def mesh(site,result):
    if result.startswith('lt_'):
        p=LT/'runs'/site/result
        return p/'post/mesh_tsdf.ply',p/'gpu/virtual/mesh_virtual.ply','LOSSTRAIN own run'
    if result.startswith('nojudge_'):
        p=AX.PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs'/site/result
        finite=p.with_name(result+'.finite')
        if finite.exists():p=finite
        return p/'post/mesh_tsdf.ply',p/'gpu/virtual/mesh_virtual.ply','original stage3 nojudge post, finite copy where present'
    return AX.mesh_of(site,result)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('site',choices=AX.SITES);ap.add_argument('prior',choices=AX.PRIORS);ap.add_argument('results',nargs='+');a=ap.parse_args()
    assert all(x.startswith(('lt_','nojudge_')) for x in a.results)
    A.DIST=DEST
    A.dist_file=lambda s,p,r:find(s,p,r)
    A.b0gt_file=lambda s,p,r:find(s,p,r,'__b0gt')
    A.x_file=xfile;A.mesh_of=mesh
    A.all_results=lambda site:[(r,r,[a.prior]) for r in a.results]
    A.main(a.site,set(a.results))
    cells=AA.cells(a.site,a.prior)
    for result in a.results:
        paths=(find(a.site,a.prior,result),xfile(a.site,a.prior,result),find(a.site,a.prior,result,'__b0gt'))
        data=AA.arrays(a.site,a.prior,result,cells,paths)
        blocks={k:blocks_of([data],k) for k in ['all']+AX.KEYS}
        out=dict(site=a.site,prior=a.prior,result=result,values=blocks,source_paths=[str(p) if p else None for p in paths],
            metric_source='PHD-MAIN-AXES71-v2 a2x_sample.main, ax_arrays.arrays and a3_metrics.blocks_of; count E',
            implementation_sha256={f:hashlib.sha256(Path('/repo/scripts/phd/main_axes71_v2',f).read_bytes()).hexdigest() for f in ['a2x_sample.py','ax_arrays.py','a3_metrics.py']},
            origin='[이 발주에서 냄]',scientific_verdict=None)
        path=Path('/docs/tables/axes')/f'{a.site}__{a.prior}__{result}.json';path.parent.mkdir(parents=True,exist_ok=True)
        assert not path.exists();path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
        print(a.site,a.prior,result,'AXES71 metrics complete',flush=True)

if __name__=='__main__':main()
