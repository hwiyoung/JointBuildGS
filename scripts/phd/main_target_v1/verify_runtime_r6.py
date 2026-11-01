"""Freeze r20 runtime, verify r19 preserved, frozen maps and accepted initialization."""
import ast,difflib
from common import *
def main():
    config=CFG/'target_v1.r6.json';lock=json.loads((CFG/'target_v1.r6.lock.json').read_text());assert sha(config)==lock['config_sha256']
    base=json.loads((CFG/'fork_r20_base.json').read_text())
    for name,digest in base['files'].items():assert sha(REPO/name)==digest,name
    f=REPO/'src/phd/forks/GeoGS-conf-guided-v1-r20';old=f.with_name('GeoGS-conf-guided-v1-r19');changes=[];patch=[]
    for p in sorted(f.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(f);prior=old/rel
        if prior.exists() and sha(prior)==sha(p):continue
        assert str(rel) in ['train.py','jbgs_target.py','jbgs_target_r6.py','jbgs_state.py','scene/gaussian_model.py'],str(rel)
        a=prior.read_text().splitlines() if prior.exists() else [];b=p.read_text().splitlines();ast.parse(p.read_text())
        for op,i,j,k,l in difflib.SequenceMatcher(a=a,b=b).get_opcodes():
            if op!='equal':changes.append(dict(file=str(rel),operation=op,old_start=i+1,old_end=j,new_start=k+1,new_end=l))
        patch.extend(difflib.unified_diff(a,b,fromfile='r19/'+str(rel),tofile='r20/'+str(rel),lineterm=''))
    # Unchanged loss and initial scene rules are checked structurally, not inferred from run results.
    oldtree=ast.parse((old/'jbgs_target.py').read_text());newtree=ast.parse((f/'jbgs_target.py').read_text())
    cls=lambda tr:next(n for n in tr.body if isinstance(n,ast.ClassDef) and n.name=='Target')
    assert ast.dump(cls(oldtree))==ast.dump(cls(newtree))
    t=ast.parse((f/'jbgs_target_r6.py').read_text());rcls=next(n for n in t.body if isinstance(n,ast.ClassDef))
    assert not any(isinstance(n,ast.FunctionDef) and n.name=='loss' for n in rcls.body)
    # Accepted r4n preflight + identical seeds/maps/initialization remains applicable.
    assert json.loads((OUT/'r4n/preflight_acceptance.json').read_text())['status']=='PASS_BY_USER_DECISION'
    inputs={}
    for prior in ['ALS','LoD2']:
        root=OUT/'r2/stage1'/f'B173nb_b10_{prior}';index=json.loads((root/'maps/index.json').read_text())
        for v in index['views'].values():assert sha(root/'maps'/v['file'])==v['sha256']
        assert sha(OUT/'r2/targets'/f'B173nb_b10_{prior}.npz')==index['target_sha256']
        inputs[prior]=dict(seed_sha256=sha(root/'seeds.npz'),map_index_sha256=sha(root/'maps/index.json'),views=len(index['views']))
    files={str(p.relative_to(REPO)):sha(p) for p in f.rglob('*') if p.is_file()}
    for name in ['train_entry_r6.py','run_pilot_r6.py','unit_r6.py']:
        p=REPO/'scripts/phd/main_target_v1'/name;files[str(p.relative_to(REPO))]=sha(p)
    dump(CFG/'target_v1.runtime.r6.lock.json',dict(at=stamp(),config_sha256=sha(config),files=files,scientific_verdict=None))
    (DOC/'tables/r20_changes_r6.patch').write_text('\n'.join(patch)+'\n');dump(DOC/'tables/r20_changes_r6.json',dict(changes=changes,scientific_verdict=None))
    result=dict(at=stamp(),status='PASS_R6_SOURCE_AND_INPUTS',r19_preserved_files=len(base['files']),initialization_and_loss_AST_unchanged=True,
        accepted_preflight='r4n user acceptance; exact inherited map/seed bytes verified',inputs=inputs,scientific_verdict=None)
    dump(OUT/'r6/verification/runtime.json',result);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
