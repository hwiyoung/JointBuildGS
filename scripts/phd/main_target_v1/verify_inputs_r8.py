"""Independent full-array checks, provenance records and frozen source binding."""
import ast,difflib,sys
import numpy as np
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from common import *
def load(p):
    with np.load(p) as z:return {k:z[k] for k in z.files}
def main():
    assert sha(CFG/'target_v1.r8.json')==json.loads((CFG/'target_v1.r8.lock.json').read_text())['config_sha256']
    base=json.loads((CFG/'fork_r22_base.json').read_text())
    for p,h in base['files'].items():assert sha(REPO/p)==h,p
    new=REPO/'src/phd/forks/GeoGS-conf-guided-v1-r22';old=new.with_name('GeoGS-conf-guided-v1-r21');changes=[];diff=[]
    for p in new.rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts:continue
        previous=old/p.relative_to(new)
        if previous.exists() and sha(previous)==sha(p):continue
        assert p.name in ['jbgs_target.py','jbgs_target_r6.py','jbgs_target_r8.py','jbgs_state.py','train.py'],p
        a=previous.read_text().splitlines() if previous.exists() else [];b=p.read_text().splitlines();ast.parse(p.read_text())
        changes += [dict(file=str(p.relative_to(new)),operation=op,old_start=i+1,old_end=j,new_start=k+1,new_end=l) for op,i,j,k,l in difflib.SequenceMatcher(a=a,b=b).get_opcodes() if op!='equal']
        diff+=list(difflib.unified_diff(a,b,fromfile='r21/'+p.name,tofile='r22/'+p.name,lineterm=''))
    assert sha(new/'jbgs_target_r7.py')==sha(old/'jbgs_target_r7.py')
    def loss(p):
        cls=next(x for x in ast.parse(p.read_text()).body if isinstance(x,ast.ClassDef) and x.name=='Target')
        return ast.dump(next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='loss'))
    assert loss(new/'jbgs_target.py')==loss(old/'jbgs_target.py')
    reps=json.loads((CFG/'representatives_v1.json').read_text())['rows'];rows=[]
    for prior in ['ALS','LoD2']:
        stem=f'B173nb_b10_{prior}';root=OUT/'r8/stage1'/stem;previous=OUT/'r7/stage1'/stem
        a=load(previous/'seeds.npz');b=load(root/'seeds.npz');pa=a['origin']==1;pb=b['origin']==1
        for k in ['xyz','target','normal','sigma','quaternion','origin','region','patch','uncertainty_replaced']:assert a[k][pa].tobytes()==b[k][pb].tobytes(),k
        for k in ['original_xyz','keep_original']:assert a[k].tobytes()==b[k].tobytes(),k
        assert sha(OUT/'r7/targets'/f'{stem}.npz')==sha(OUT/'r8/targets'/f'{stem}.npz')
        ia=json.loads((previous/'maps/index.json').read_text());ib=json.loads((root/'maps/index.json').read_text());assert ia['views'].keys()==ib['views'].keys()
        hist=np.zeros(5,np.int64);ends=np.zeros(2,np.int64);total=0;patch_count=0;sample=None
        camera=next(r['camera']['name'] for r in reps if r['site']=='B173nb_b10' and prior in r['priors'])
        for name,meta in ib['views'].items():
            oldmeta=ia['views'][name];assert oldmeta['sigma_ref']==meta['sigma_ref']
            af=previous/'maps'/oldmeta['file'];bf=root/'maps'/meta['file'];assert sha(af)==oldmeta['sha256'] and sha(bf)==meta['sha256']
            x,y=load(af),load(bf);patch=x['owner']>=0
            for k in ['depth','sigma','owner']:assert x[k].tobytes()==y[k].tobytes(),(name,k)
            assert x['weight'][patch].tobytes()==y['weight'][patch].tobytes()
            bg=(~patch)&np.isfinite(x['depth'])&(x['depth']>0);assert (y['weight'][bg]==1).all()
            assert (y['weight'][~patch&~bg]==0).all()
            w=x['weight'][bg];hist+=np.histogram(w,bins=np.array([.1,.5,1,2,5,10],dtype='f4'))[0];ends+=np.array([(w==np.float32(.1)).sum(),(w==np.float32(10)).sum()]);total+=len(w);patch_count+=int(patch.sum())
            assert np.all(x['sigma'][bg]==np.float32(np.hypot(ia['background_u_median'],.0275)))
            if name==camera:sample=np.where(bg,x['weight'],np.nan)
        assert hist.sum()==total and sample is not None
        rec=dict(prior=prior,background_pixels=total,patch_pixels=patch_count,views=len(ib['views']),
            bins=['[0.1,0.5)','[0.5,1)','[1,2)','[2,5)','[5,10]'],bin_counts=hist.tolist(),bin_fractions=(hist/total).tolist(),
            clipped_endpoint_counts=ends.tolist(),clipped_endpoint_fractions=(ends/total).tolist(),
            sigma_source='same-unit/prior finite original roof u median; sigma=sqrt(u^2+0.0275^2), all background pixels substituted',
            sigma_substituted_fraction=1.,sigma_per_pixel_measured_fraction=0.,background_u_median=ia['background_u_median'],camera=camera,
            patch_seed_bytes_identical=True,all_depth_sigma_owner_bytes_identical=True,patch_weight_bytes_identical=True,background_weight_one=True,scientific_verdict=None)
        rows.append(rec);fig,ax=plt.subplots(1,2,figsize=(12,4));im=ax[0].imshow(sample,norm=LogNorm(vmin=.1,vmax=10),cmap='viridis');fig.colorbar(im,ax=ax[0],label='r7 background weight');ax[0].set_title(camera);ax[0].axis('off')
        ax[1].bar(np.arange(5),hist/total*100);ax[1].set_xticks(np.arange(5),rec['bins'],rotation=20);ax[1].set_ylabel('Background target pixels (%)');ax[1].set_title(prior+' / all 203 training views');fig.tight_layout()
        dest=DOC/'figures'/f'r8_r7_background_weights_{prior}';fig.savefig(dest.with_suffix('.png'),dpi=150);plt.close(fig);dump(dest.with_suffix('.json'),rec)
    dump(DOC/'tables/r22_changes_r8.json',dict(changes=changes,scientific_verdict=None));(DOC/'tables/r22_changes_r8.patch').write_text('\n'.join(diff)+'\n')
    result=dict(at=stamp(),status='PASS_R8_SOURCE_AND_INPUTS',frozen_r21_files=len(base['files']),r7_patch_controller_byte_identical=True,depth_loss_AST_identical=True,rows=rows,scientific_verdict=None)
    dump(OUT/'r8/verification/runtime.json',result);dump(DOC/'tables/r8_input_verification.json',result)
    files={str(p.relative_to(REPO)):sha(p) for p in new.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    for name in ['train_entry_r8.py','run_pilot_r8.py','unit_r8.py','prepare_inputs_r8.py','verify_inputs_r8.py','verify_initial_r8.py']:
        p=REPO/'scripts/phd/main_target_v1'/name;files[str(p.relative_to(REPO))]=sha(p)
    dest=CFG/'target_v1.runtime.r8.lock.json'
    if dest.exists():assert json.loads(dest.read_text())['files']==files
    else:dump(dest,dict(at=stamp(),config_sha256=sha(CFG/'target_v1.r8.json'),files=files,scientific_verdict=None))
    print(result['status'],flush=True)
if __name__=='__main__':main()
