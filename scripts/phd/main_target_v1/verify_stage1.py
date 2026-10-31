"""Independent scalar/reprojection and byte checks of the stopped preflight evidence."""
import ast,difflib,platform,re
import numpy as np
from common import *


def main():
    cfg,lock=training_locked();fork=REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19'
    manifest=json.loads((CFG/'fork_r19_base.json').read_text());base=REPO/manifest['base'];unchanged=0
    for name,digest in manifest['base_file_sha256'].items():
        if name!='train.py':assert sha(fork/name)==digest,name;unchanged+=1
    changed=[]
    a=(base/'train.py').read_text().splitlines();b=(fork/'train.py').read_text().splitlines()
    for tag,i,j,k,l in difflib.SequenceMatcher(a=a,b=b).get_opcodes():
        if tag!='equal':changed.append(dict(file='train.py',operation=tag,old_start=i+1,old_end=j,new_start=k+1,new_end=l))
    changed.append(dict(file='jbgs_target.py',operation='add',new_start=1,new_end=len((fork/'jbgs_target.py').read_text().splitlines())))
    dump(DOC/'tables/r19_changes.json',dict(unchanged_base_files=unchanged,changes=changed,scientific_verdict=None))
    patch='\n'.join(difflib.unified_diff(a,b,fromfile='r18/train.py',tofile='r19/train.py',lineterm=''))+'\n'
    (DOC/'tables/r19_train.patch').write_text(patch)
    syntax=0
    for p in list(Path(__file__).parent.glob('*.py'))+list(fork.rglob('*.py')):
        compile(p.read_text(),str(p),'exec');syntax+=1
    checks=[];mapfiles=0
    for site in cfg['sites']+cfg['deferred_sites']:
        for prior in cfg['priors']:
            root=OUT/'stage1'/f'{site}_{prior}';receipt=json.loads((root/'seed_receipt.json').read_text())
            assert sha(root/'seeds.npz')==receipt['seeds_sha256']
            assert sha(OUT/'targets'/f'{site}_{prior}.npz')==receipt['target_sha256']
            with np.load(root/'seeds.npz') as z:s={k:z[k] for k in z.files}
            with np.load(OUT/'targets'/f'{site}_{prior}.npz') as z:d={k:z[k] for k in z.files}
            prior_mask=s['origin']==1
            error=float(np.max(abs(s['xyz'][prior_mask]-d['target'][s['patch'][prior_mask]])))
            assert error<=1.6e-5 and np.isfinite(s['sigma']).all() and (s['sigma']>0).all()
            assert np.array_equal(s['xyz'][~prior_mask],s['original_xyz'][s['keep_original'][~prior_mask]])
            index=json.loads((root/'maps/index.json').read_text());assert index['config_sha256']==lock['config_sha256']
            for name,entry in index['views'].items():
                assert sha(root/'maps'/entry['file'])==entry['sha256'];mapfiles+=1
                assert entry['height_error_median_m'] is None or entry['height_error_median_m']<=.01
            checks.append(dict(site=site,prior=prior,seed_position_max_roundoff_m=error,maps=len(index['views']),status='PASS'))
    for p in sorted((OUT/'preflight').glob('*/initial_render.json')):
        r=json.loads(p.read_text());assert r['status']=='FAIL_INITIAL_RENDER_DEPTH_5CM' and r['optimization_steps']==0
        unit=json.loads((p.parent/'unit.json').read_text());assert unit['status']=='PASS'
        for view in [x for x in r['views'] if x.get('representative')]:
            with np.load(p.parent/(view['camera']+'.npz')) as z:
                A=z['render_depth'];B=z['target_depth'];mask=np.isfinite(A)&np.isfinite(B)&(A>0)&(B>0)
                median=float(np.median(abs(A[mask]-B[mask])))
            assert abs(median-view['absolute_depth_error_median_m'])<1e-6
    assert not list((OUT/'runs').glob('**/point_cloud.ply'))
    text=(DOC/'영역별목표학습_보고_v1.md').read_text();assert len(text)<20000
    assert len(re.findall(r'^## [1-8]\. ',text,re.M))==8
    for p in (DOC/'figures').glob('*.png'):assert p.with_suffix('.json').exists()
    result=dict(at=stamp(),status='PASS_STOPPED_PREFLIGHT_EVIDENCE',checks=checks,maps_sha256_checked=mapfiles,
        python_files_syntax_checked=syntax,base_files_unchanged=unchanged,initial_render_gate='FAIL',training_steps=0,
        scientific_verdict=None,verification_environment=dict(python=platform.python_version(),numpy=np.__version__))
    dump(OUT/'stage1_verification.json',result);dump(DOC/'tables/stage1_verification.json',result)
    # Only stage metadata and aggregate experimental diagnostic results are promoted.
    for folder in ['preflight','diagnose','decompose']:
        for p in (OUT/folder).glob('*/*.json'):
            if p.name in ['unit.json','initial_render.json','diagnosis.json']:
                dump(DOC/'tables/stage1_evidence'/folder/p.parent.name/p.name,json.loads(p.read_text()))
    print('STAGE1_VERIFY',json.dumps(result),flush=True)

if __name__=='__main__':main()
