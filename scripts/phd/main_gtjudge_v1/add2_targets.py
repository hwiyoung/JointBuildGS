import sys
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from add2_common import *
from majority import calculate_targets

def alternatives(site):
    config2();stem=site+'__LoD2'
    if (O/'targets_alt/alt_da'/f'{stem}.json').exists():return
    original=loadz(FT/'targets'/f'{stem}.npz');core=loadz(JA/'core_points'/f'{stem}.npz',['source_index','patch_id','reason'])
    ix=core['source_index'];assert np.array_equal(original['patch_id'][ix],core['patch_id'])
    editable=np.zeros(len(original['patch_id']),bool);editable[ix]=(original['judge_region'][ix]==2)&(core['reason'][5]==2)
    raw=loadz(PH/'main_target_v1/PHD-MAIN-TARGET-v1/stage0_r1/inputs'/f'{site}_LoD2.npz',['building','surf'])
    groups=np.char.add(np.char.add(raw['building'].astype(str),'|'),raw['surf'].astype(str));to_keep=np.zeros(len(editable),bool);components=[]
    for group in np.unique(groups[editable]):
        allix=np.flatnonzero(groups==group);ei=allix[editable[allix]];pts=original['centre'][ei]
        pairs=cKDTree(pts).query_pairs(.36,output_type='ndarray')
        graph=coo_matrix((np.ones(len(pairs)),(pairs[:,0],pairs[:,1])),shape=(len(ei),len(ei)))
        count,labels=connected_components(graph,directed=False);tree=cKDTree(original['centre'][allix])
        for component in range(count):
            members=ei[labels==component];near=tree.query_ball_point(original['centre'][members],.36,workers=4)
            boundary=np.setdiff1d(allix[np.unique(np.concatenate(near))],members)
            reg=original['judge_region'][boundary];why=original['reason'][boundary]
            prior_area=float(original['area'][boundary[((reg==1)&(why==0))|(reg==4)]].sum())
            image_area=float(original['area'][boundary[(reg==2)&(why==1)]].sum())
            choose=prior_area>image_area;to_keep[members]=choose
            reason='prior_greater' if choose else 'no_adjacent_decision' if prior_area==image_area==0 else 'equal' if prior_area==image_area else 'image_greater'
            components.append(dict(site=site,component=len(components),group=group,patches=len(members),area_m2=float(original['area'][members].sum()),prior_side_area_m2=prior_area,image_side_area_m2=image_area,keep=choose,reason=reason))
    table('addendum2/alt_da_components_'+site,components)
    rows=[]
    for variant,changed in [('alt_ga',np.zeros(len(editable),bool)),('alt_na',editable),('alt_da',to_keep)]:
        target={k:v.copy() for k,v in original.items()};target['judge_region'][changed]=1
        if variant!='alt_ga':
            values=calculate_targets(target,'LoD2')
            for key,val in values.items():
                if key in target and np.asarray(val).ndim and len(val)==len(changed):val[~changed]=original[key][~changed]
            target.update(values);target['any_replaced']=target['sigma_replaced']
            active=target['surface_exists'];target['sigma_ref']=np.asarray(target['area'][active].sum()/np.sum(target['area'][active]/target['sigma'][active]))
            assert set(target)==set(original)
            for k in target:
                if target[k].ndim and len(target[k])==len(changed):
                    a=target[k][~changed];b=original[k][~changed]
                    assert np.array_equal(a,b,equal_nan=True) if a.dtype.kind in 'fc' else np.array_equal(a,b),(variant,k)
            out=target_file(site,'LoD2',variant);savez(out,**target)
            dump(out.with_suffix('.json'),dict(at=now(),site=site,variant=variant,changed=int(changed.sum()),target_sha256=sha(out),parent_sha256=sha(FT/'targets'/f'{stem}.npz'),GT_used=False,scientific_verdict=None))
        for kind in [1,2]:
            m=changed&(target['kind']==kind);e=editable&(target['kind']==kind)
            rows.append(dict(site=site,variant=variant,surface='wall' if kind==2 else 'roof',editable_patches=int(e.sum()),editable_area_m2=float(target['area'][e].sum()),changed_patches=int(m.sum()),changed_area_m2=float(target['area'][m].sum())))
        # Reference joins only describe the saved target; they never define it.
        table('addendum2/'+stem+'_'+variant+'_changed_reference',target_membership_rows(site,'LoD2',changed))
        savez(O/'targets_alt'/variant/f'{stem}_changes.npz',editable=editable,changed=changed)
    table('addendum2/'+stem+'_changes',rows)
    print('ALT_TARGETS_READY',site,int(editable.sum()),int(to_keep.sum()),flush=True)

def freespace(site,prior):
    config2();path=target_file(site,prior);t=loadz(path);stem=f'{site}__{prior}'
    mask=t['surface_exists']&np.isfinite(t['prior_height_m'])&np.isfinite(t['sigma_P_m'])&(t['sigma_P_m']>=0)&(abs(t['target_height_m']-t['prior_height_m'])<=1.96*t['sigma_P_m'])
    p=O/'freespace_targets'/f'{stem}.npz'
    if p.exists():
        assert np.array_equal(loadz(p)['patch_id'],t['patch_id'][mask]);return
    savez(p,patch_id=t['patch_id'][mask])
    rec=dict(at=now(),site=site,prior=prior,target_path=str(path),target_sha256=sha(path),patch_file_sha256=sha(p),patches=int(mask.sum()),area_m2=float(t['area'][mask].sum()),by_judgment=[dict(judgment=int(k),patches=int((mask&(t['judge_region']==k)).sum()),area_m2=float(t['area'][mask&(t['judge_region']==k)].sum())) for k in [0,1,2,4,3,9]],GT_used=False,r_added=False,scientific_verdict=None)
    dump(p.with_suffix('.json'),rec);dump(D/'tables/addendum2'/f'{stem}_freespace_targets.json',rec)
    table('addendum2/'+stem+'_freespace_reference',target_membership_rows(site,prior,mask))
    print('FREESPACE_TARGETS_READY',stem,int(mask.sum()),flush=True)
if __name__=='__main__':
    if sys.argv[1]=='alternatives':alternatives(sys.argv[2])
    else:freespace(*sys.argv[2:])
