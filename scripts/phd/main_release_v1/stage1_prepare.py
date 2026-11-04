"""Read V0 only; classify locations/targets without reference geometry."""
import gc,sys
from common import *
sys.path.append('/repo/src/phd/forks/GeoGS-conf-guided-v1-r24')
from release_search import TangentTree

def eval_mask(xyz,site):
    # The inherited PREP evaluation box, not a reference-derived surface mask.
    conf=json.loads((R/'configs/phd/main_prep_measure_v1/prep_v5.json').read_text())
    a=np.deg2rad(conf['frame']['u_axis_angle_degrees_ccw_from_easting']);basis=np.array([[np.cos(a),np.sin(a)],[np.sin(a),-np.cos(a)]])
    key={'R1rep_b10':'R1rep','B173nb_b10':'B173nb','B0_b10':'B0'}[site]
    box=json.loads((PH/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1/step06/boxes_v1.json').read_text())['boxes'][key]
    uv=np.asarray(xyz,dtype='f8')[:,:2]@basis.T
    return (uv[:,0]>=box['eval_u'][0])&(uv[:,0]<=box['eval_u'][1])&(uv[:,1]>=box['eval_v'][0])&(uv[:,1]<=box['eval_v'][1])

def v0_model(site,prior):
    rec=json.loads((FT/'runs'/site/f'ft_{prior}_s0/receipt.json').read_text());assert rec['status']=='TRAINING_COMPLETE_30000'
    return FT/Path(rec['attempts'][-1]['model']).relative_to('/out')

def main(site,prior):
    cfg();start=time.monotonic();stem=f'{site}__{prior}';root=O/'stage1'/stem;root.mkdir(parents=True,exist_ok=True)
    model=v0_model(site,prior);snap=model/'target_monitor/snapshot_30000.npz';s=loadz(snap)
    tfile=FT/'targets'/f'{stem}.npz';target=loadz(tfile)
    active=s['patch_ids'];assert np.array_equal(s['patch_anchor'],target['target'][active].astype('f4'))
    inside=eval_mask(s['xyz'],site);tag=s['target_tag'];released=inside&(tag==2);background=inside&(s['origin']==0)
    tree=TangentTree(target['target'][active].astype(float),s['patch_normal'].astype(float),(np.float32(1.96)*s['patch_sigma']).astype(float),active)
    nearest=np.full(len(tag),-1,'i4');tangent=np.full(len(tag),np.nan);excess=np.full(len(tag),np.nan)
    selected=np.flatnonzero(released|background)
    cached=loadz(root/'gaussians.npz',['nearest_target_index','tangent_m','normal_excess_m']) if (root/'gaussians.npz').exists() else None
    if cached is not None:
        nearest=cached['nearest_target_index'];tangent=cached['tangent_m'];excess=cached['normal_excess_m'];selected_query=np.array([],dtype='i8')
    else:selected_query=selected
    for start2 in range(0,len(selected_query),100000):
        ii=selected_query[start2:start2+100000];d,e,j=tree.query(s['xyz'][ii]);nearest[ii]=j;tangent[ii]=d;excess[ii]=e
        print('TARGET_SEARCH',stem,min(start2+len(ii),len(selected)),len(selected),flush=True)
    case=np.full(len(tag),-1,'i1');case[selected]=np.where(tangent[selected]<=.5,1,0)
    save=dict(xyz=s['xyz'],init_id=s['init_id'],origin=s['origin'],tag=tag,target_index=s['target_index'],inside_eval=inside,
      nearest_target_index=nearest,tangent_m=tangent,normal_excess_m=excess,case=case,opacity=s['opacity'],patch_ids=active,
      first_release_checkpoint=np.full(len(tag),-1,'i4'))
    # Exact current init_id lineage presence, not a claim about a unique direct parent.
    for it in [7000,15000,30000]:
        z=loadz(model/f'target_monitor/snapshot_{it}.npz',['init_id','target_tag']);released_seeds=np.unique(z['init_id'][z['target_tag']==2]);mask=(save['first_release_checkpoint']<0)&(tag==2)&np.isin(s['init_id'],released_seeds);save['first_release_checkpoint'][mask]=it
    seed=loadz(FT/'stage1'/stem/'seeds.npz',['patch']);save['initial_patch']=seed['patch'][s['init_id']]
    save['initial_judgment_region']=np.full(len(tag),-1,'i1');isprior=s['origin']==1;save['initial_judgment_region'][isprior]=target['judge_region'][save['initial_patch'][isprior]]
    savez(root/'gaussians.npz',**save)
    rows=[]
    for r in [0,1,2,3,4,9]:
        reg=save['initial_judgment_region']==r
        for place,m in [('inside',inside),('outside',~inside)]:
            pm=isprior&reg&m;rr=pm&(tag==2)
            for reason in [0,1,-1]:
                ids=rr&(case==reason);rows.append(dict(site=site,prior=prior,judgment_region=r,evaluation_scope=place,release_case=reason,prior_descendants=int(pm.sum()),released_descendants=int(rr.sum()),case_descendants=int(ids.sum()),case_evaluated=place=='inside'))
    table('stage1/'+stem+'_release_counts',rows)
    # Intervention membership uses tags, the locked evaluation box and targets only.
    move=released&(tangent<=.5);delete_bg=background&(tangent<=.5)&(excess>.5)
    savez(root/'simulation_masks.npz',delete_released=released,pull_released=move,delete_background=delete_bg,nearest_target_index=nearest)
    views=score_root(site)/'views'/f'{site}.json'
    if not views.exists():views=BASE/'views'/f'{site}.json'
    dest=O/'views'/views.name;dest.parent.mkdir(exist_ok=True)
    if not dest.exists():dest.write_bytes(views.read_bytes())
    dump(root/'binding.json',dict(at=now(),site=site,prior=prior,model=str(model),snapshot=str(snap),snapshot_sha256=sha(snap),target=str(tfile),target_sha256=sha(tfile),
      views=str(views),views_sha256=sha(views),simulation_counts={k:int(v.sum()) for k,v in [('delete_released',released),('pull_released',move),('delete_background',delete_bg)]},
      GT_used_for_selection=False,eval_box_source='PREP step06/boxes_v1.json + prep_v5 frame; inherited in_eval_uv',lineage_first_seen='first saved checkpoint with any released descendant of the same immutable init_id; direct parent chain unavailable in V0',seconds=time.monotonic()-start,scientific_verdict=None))
    print('STAGE1_PREPARE_COMPLETE',stem,flush=True)
if __name__=='__main__':main(*sys.argv[1:])
