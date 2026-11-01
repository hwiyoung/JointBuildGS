"""Freeze r21 executable bytes and independently verify target/seed exclusions."""
import ast,difflib,subprocess,sys
import numpy as np
from common import *
def loadz(p):
    with np.load(p) as z:return {k:z[k] for k in z.files}
def main():
    replay=OUT/'r7/verification/stage0.json'
    if not replay.exists():subprocess.run([sys.executable,str(Path(__file__).with_name('verify_disappearance_r7.py'))],check=True)
    assert json.loads(replay.read_text())['status']=='PASS_DISAPPEARANCE_VOTES_AND_REPLAY'
    for config in ['target_v1.r7','target_v1.r7.stage0']:
        assert sha(CFG/(config+'.json'))==json.loads((CFG/(config+'.lock.json')).read_text())['config_sha256']
    base=json.loads((CFG/'fork_r21_base.json').read_text())
    for path,h in base['files'].items():assert sha(REPO/path)==h,path
    new=REPO/'src/phd/forks/GeoGS-conf-guided-v1-r21';old=new.with_name('GeoGS-conf-guided-v1-r20');changes=[];diff_lines=[]
    for p in sorted(new.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts:continue
        prior=old/p.relative_to(new)
        if prior.exists() and sha(prior)==sha(p):continue
        assert str(p.relative_to(new)) in ['train.py','jbgs_target.py','jbgs_target_r6.py','jbgs_target_r7.py','jbgs_state.py']
        a=prior.read_text().splitlines() if prior.exists() else [];b=p.read_text().splitlines();ast.parse(p.read_text())
        changes += [dict(file=str(p.relative_to(new)),operation=op,old_start=i+1,old_end=j,new_start=k+1,new_end=l) for op,i,j,k,l in difflib.SequenceMatcher(a=a,b=b).get_opcodes() if op!='equal']
        diff_lines+=list(difflib.unified_diff(a,b,fromfile='r20/'+str(p.relative_to(new)),tofile='r21/'+str(p.relative_to(new)),lineterm=''))
    def cls(p):return next(x for x in ast.parse(p.read_text()).body if isinstance(x,ast.ClassDef) and x.name=='Target')
    assert ast.dump(cls(new/'jbgs_target.py'))==ast.dump(cls(old/'jbgs_target.py'))
    rows=[]
    for prior in ['ALS','LoD2']:
        site='B173nb_b10';stem=f'{site}_{prior}';target=loadz(OUT/'r7/targets'/f'{stem}.npz');before=loadz(OUT/'r2/targets'/f'{stem}.npz');votes=loadz(OUT/'r7/stage0'/f'{stem}.votes.npz')
        gone=target['region']==5;assert np.array_equal(gone,votes['disappeared']) and (before['region'][gone]==0).all()
        assert np.array_equal(target['region'][~gone],before['region'][~gone])
        for k in before:assert np.array_equal(target[k][~gone],before[k][~gone],equal_nan=True) if target[k].dtype.kind not in ['U','S'] else np.array_equal(target[k][~gone],before[k][~gone]),k
        for k in ['h','sigma','target']:assert np.isnan(target[k][gone]).all()
        root=OUT/'r7/stage1'/stem;seeds=loadz(root/'seeds.npz');seed0=loadz(OUT/'r2/stage1'/stem/'seeds.npz')
        patch=seeds['patch'];has=patch>=0;assert not gone[patch[has]].any();assert np.array_equal(seeds['xyz'][~has],seed0['xyz'][seed0['origin']==0])
        assert np.max(abs(seeds['xyz'][has]-target['target'][patch[has]]))<=1e-5
        idx=json.loads((root/'maps/index.json').read_text());assert idx['target_sha256']==sha(OUT/'r7/targets'/f'{stem}.npz')
        for meta in idx['views'].values():
            p=root/'maps'/meta['file'];assert sha(p)==meta['sha256'];m=loadz(p);owner=m['owner'];assert not gone[owner[owner>=0]].any()
            assert meta['height_error_median_m'] is None or meta['height_error_median_m']<=.01
        result=dict(at=stamp(),status='PASS_STAGE1_INPUTS',removed_patches=int(gone.sum()),prior_seeds=int(has.sum()),background_seeds=int((~has).sum()),views=len(idx['views']),seed_sha256=sha(root/'seeds.npz'),map_index_sha256=sha(root/'maps/index.json'),scientific_verdict=None)
        dump(OUT/'r7/verification'/f'stage1_{stem}.json',result);rows.append(dict(prior=prior,**result))
    files={str(p.relative_to(REPO)):sha(p) for p in new.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    for name in ['train_entry_r7.py','run_pilot_r7.py','unit_r7.py']:files['scripts/phd/main_target_v1/'+name]=sha(REPO/'scripts/phd/main_target_v1'/name)
    dest=CFG/'target_v1.runtime.r7.lock.json'
    if dest.exists():
        frozen=json.loads(dest.read_text());assert frozen['files']==files and frozen['config_sha256']==sha(CFG/'target_v1.r7.json')
    else:dump(dest,dict(at=stamp(),config_sha256=sha(CFG/'target_v1.r7.json'),files=files,scientific_verdict=None))
    dump(DOC/'tables/r21_changes_r7.json',dict(changes=changes,scientific_verdict=None));(DOC/'tables/r21_changes_r7.patch').write_text('\n'.join(diff_lines)+'\n')
    result=dict(at=stamp(),status='PASS_R7_SOURCE_AND_INPUTS',r20_preserved_files=len(base['files']),loss_and_initialization_class_unchanged=True,rows=rows,scientific_verdict=None)
    dump(OUT/'r7/verification/runtime.json',result);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
