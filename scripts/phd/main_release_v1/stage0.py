"""Reuse locked per-point distances; change only reporting cells / tau."""
import gc,sys
from common import *
sys.path.append('/repo/scripts/phd/main_rescore_v1')
from geometry import context
from metrics import four,inherited_result_mask
from columns import presence
from scipy.spatial import cKDTree

def cell_labels(dprior,dmvs,tau,has_prior,has_mvs):
    p=dprior<=tau;m=dmvs<=tau
    cell=np.full(len(p),3,'i1');cell[p&m]=0;cell[~p&m]=1;cell[p&~m]=2
    cell[~has_mvs&~p]=3;cell[~has_mvs&p]=4;cell[~has_prior]=-1
    return cell

def main(site,prior):
    start=time.monotonic();c=cfg();stem=f'{site}__{prior}';out=O/'stage0'/stem;out.mkdir(parents=True,exist_ok=True)
    ctx=context(site,prior);core=ctx['core'];own=ctx['row_owner'];good=own>=0
    v2=ctx['v2'];old=np.full(len(own),-1,'i1');old[good]=v2['cell_v2'][own[good]]
    inputs={};has={}
    for method in ['prior','mvs']:
        p=score_dir(site,prior,method);v=json.loads((p/'values.json').read_text());inputs[method]=loadz(p/'points.npz',['row_distance_m','row_tau_m','row_owner'])
        assert np.array_equal(inputs[method]['row_owner'],own)
        has[method]=presence(core,Path(v['mesh']),out/f'{method}_presence.npz')
    hp=np.zeros(len(own),bool);hm=hp.copy();hp[good]=has['prior'][own[good]];hm[good]=has['mvs'][own[good]]
    dtp=inputs['prior']['row_distance_m'];dtm=inputs['mvs']['row_distance_m'];tau=inputs['prior']['row_tau_m']
    assert np.array_equal(tau,inputs['mvs']['row_tau_m'],equal_nan=True)
    labels={f:cell_labels(dtp,dtm,tau*f,hp,hm) for f in c['stage0']['tau_multipliers']}
    target=loadz(FT/'targets'/f'{stem}.npz');ix=core['source_index'];assert np.array_equal(target['patch_id'][ix],core['patch_id'])
    reg=target['judge_region'][ix];err=abs(target['target_height_m'][ix]-core['gt_p']);ptau=v2['tau_v2_m'];valid=np.isfinite(err)&np.isfinite(ptau)
    rows=[];cross=[];quality=[];repro=[];scene=[]
    judge=loadz(score_dir(site,prior,'judgment_mesh')/'points.npz',['row_distance_m','row_tau_m'])
    for k in [0,1,2,4]:
        m=old==k;n=int(m.sum());pm=v2['cell_v2']==k;den=float(core['area'][pm&valid].sum());num=float(core['area'][pm&valid&(err<=ptau)].sum())
        mismatch=(dtp>tau)|(dtm>tau) if k==0 else dtp<=tau if k==1 else dtm<=tau
        rows.append(dict(site=site,prior=prior,cell=k,n_gt=n,small='적음' if n<1000 else '',mismatch_fraction=float(mismatch[m].mean()) if n else None,
          mvs_column_presence_fraction=float(hm[m].mean()) if n else None,target_correct_area_m2=num,valid_target_area_m2=den,target_correct_fraction=num/den if den else None,
          judgment_mesh_completeness=float((judge['row_distance_m'][m]<=judge['row_tau_m'][m]).mean()) if n else None))
    for k in np.unique(old):
        m=old==k
        for new in [-1,0,1,2,3,4]:
            n=int((m&(labels[1.]==new)).sum());cross.append(dict(site=site,prior=prior,old_cell=int(k),score_cell=new,n_gt=n,old_cell_fraction=n/int(m.sum()),scene_fraction=n/len(own)))
    count=np.bincount(own[good],minlength=len(core['area']));area_per_gt=np.zeros(len(own));area_per_gt[good]=core['area'][own[good]]/count[own[good]]
    for mode,lab in [('original',old),('score',labels[1.])]:
        for k in [0,1,2,3,4,-1]:
            for r in [0,1,2,3,4,9]:
                m=good&(lab==k);m[good]&=reg[own[good]]==r
                vt=np.zeros(len(m),bool);ok=vt.copy();vt[good]=valid[own[good]];ok[good]=(err<=ptau)[own[good]]&valid[own[good]]
                weights=area_per_gt if mode=='score' else area_per_gt
                den=float(weights[m&vt].sum());num=float(weights[m&ok].sum())
                quality.append(dict(site=site,prior=prior,cell_basis=mode,cell=k,judgment_region=r,n_gt=int(m.sum()),area_m2=float(weights[m].sum()),valid_target_reference_area_m2=den,target_correct_area_m2=num,target_correct_fraction=num/den if den else None,
                  judgment_correct=(r=={0:0,1:2,2:1,4:4}.get(k,-99)),area_rule='patch area split by inherited reference-row counts; patches without reference rows reported separately'))
    no_ref=dict(site=site,prior=prior,patches_without_rows=int((count==0).sum()),area_without_rows_m2=float(core['area'][count==0].sum()),prior_absent_rows=int((~hp).sum()))
    table('stage0/'+stem+'_mismatch',rows);table('stage0/'+stem+'_crosswalk',cross);table('stage0/'+stem+'_target_judgment',quality);dump(out/'unassigned.json',no_ref)
    tree=cKDTree(np.c_[own[good].astype(float)*100000.,ctx['row_points'][good]]);reference_rows=np.flatnonzero(good)
    allrows=[]
    for method in c['stage0']['methods']:
        root=score_dir(site,prior,method);z=loadz(root/'points.npz');v=json.loads((root/'values.json').read_text());assert np.array_equal(z['row_owner'],own)
        qo=z['sample_owner'];inside=qo>=0;idx=np.full(len(qo),-1,'i8')
        for start2 in range(0,len(qo),200000):
            ids=np.arange(start2,min(start2+200000,len(qo)));ids=ids[inside[ids]]
            if len(ids):
                jj=reference_rows[tree.query(np.c_[qo[ids].astype(float)*100000.,z['sample_xyz'][ids]],workers=2)[1]]
                keep=own[jj]==qo[ids];idx[ids[keep]]=jj[keep]
        save={'sample_reference_row':idx,'row_owner':own}
        for factor in c['stage0']['tau_multipliers']:
            for mode,lab in [('original',old),('score',labels[factor])]:
                samplelab=np.full(len(qo),-1,'i1')
                if mode=='original':samplelab[inside]=v2['cell_v2'][qo[inside]]
                else:samplelab[idx>=0]=lab[idx[idx>=0]]
                mask=inherited_result_mask(z['sample_region_distance_m'],z['sample_region_lat_m'])
                for k in [0,1,2,4,3,-1]:
                    met=four(z['row_distance_m'],z['sample_region_distance_m'],z['row_tau_m']*factor,z['sample_tau_m']*factor,lab==k,(samplelab==k)&mask)
                    row=dict(site=site,prior=prior,method=method,tau_multiplier=factor,cell_basis=mode,cell=k,small='적음' if met['n_gt']<1000 else '',**met);allrows.append(row)
                    if factor==1 and mode=='original' and k!=-1:
                        oldmet=next(a for a in v['cells'] if a['cell']==k);delta=max(abs(met[x]-oldmet[x])*100 for x in ['completeness','accuracy'] if met[x] is not None and oldmet[x] is not None)
                        assert delta<=.1,(stem,method,k,delta);repro.append(dict(site=site,prior=prior,method=method,cell=k,max_abs_delta_pp=delta))
            sc=four(z['scene_distance_m'],z['sample_distance_m'],z['scene_tau_m']*factor,z['sample_tau_m']*factor,result_mask=inherited_result_mask(z['sample_distance_m'],z['sample_lat_m']))
            scene.append(dict(site=site,prior=prior,method=method,tau_multiplier=factor,**sc))
        savez(out/(method+'_assignment.npz'),**save)
        print('STAGE0_METHOD',stem,method,flush=True);del z;gc.collect()
    savez(out/'cells.npz',old_cell=old,**{'score_cell_'+str(f).replace('.','p'):lab for f,lab in labels.items()},xyz=ctx['row_points'],row_owner=own,row_tau_m=tau,prior_distance_m=dtp,mvs_distance_m=dtm,prior_presence=hp,mvs_presence=hm)
    table('stage0/'+stem+'_table4',allrows,csv_only=True);table('stage0/'+stem+'_scene',scene);table('stage0/'+stem+'_reproduction',repro)
    dump(out/'receipt.json',dict(at=now(),status='PASS',site=site,prior=prior,seconds=time.monotonic()-start,max_reproduction_delta_pp=max(r['max_abs_delta_pp'] for r in repro),scientific_verdict=None))
    print('STAGE0_COMPLETE',stem,flush=True)
if __name__=='__main__':main(*sys.argv[1:])
