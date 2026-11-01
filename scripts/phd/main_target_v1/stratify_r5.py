"""Input-only Track-A place strata and separately joined frozen stage-0 truth counts."""
import sys
import numpy as np
from common import *
from judgment_census_r2 import lookup
import track_types_r5 as tt
MP=PH/'main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1';W=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
LABELS=['small_raised','edge_band','glass_or_textureless','other','photo_missing']

def zload(p,keys=None):
    with np.load(p) as z:return {k:z[k] for k in (z.files if keys is None else keys)}
def binding(root,paths):
    dump(root/'inputs.json',dict(at=stamp(),files={str(p):sha(p) for p in paths},config_sha256=sha(CFG/'diagnostics_r5.json'),code_sha256=sha(Path(__file__)),types_code_sha256=sha(Path(tt.__file__)),scientific_verdict=None))
def inp(src):
    n=len(src['area']);d={k:src[k].copy() for k in ['centre','normal','area','mvs_a_status','mvs_a_s']}
    d['cell']=np.zeros(n,np.int8) # length only in extracted units, never truth
    d['bld']=np.unique(src['building'],return_inverse=True)[1].astype('i4')
    d['z']=src.get('signed_difference_over_uncertainty',src.get('z_a'))
    if d['z'] is None:
        den=np.sqrt(src['mvs_a_u'].astype('f8')**2+src['u_prior'].astype('f8')**2)
        d['z']=np.divide(src['mvs_a_p'],den,out=np.full(n,np.nan),where=den>0)
    d['mvs_p']=src.get('mvs_p',src.get('mvs_a_p'))
    d['u_mvs']=src.get('u_mvs',src.get('mvs_a_u'))
    d['mvs_n']=np.stack([src['mvs_a_n'+k] for k in 'xyz'],1).astype('f4')
    for k in d:
        if d[k].dtype==np.float64 and k!='centre':d[k]=d[k].astype('f4')
    assert d['z'] is not None and d['mvs_p'] is not None
    return d

def classify(d,root,key):
    tt.CACHE=root/'types_cache';tt.CACHE.mkdir(parents=True,exist_ok=True)
    E,U,hm=tt.units(key,d);res=tt.types(d,E,U['roofer_def'])
    np.savez_compressed(root/'types.npz',pt=res['pt'],edge=res['edge'],face=res['lab'])
    dump(root/'type_metadata.json',dict(patches=len(d['area']),scatter_threshold=res['scatter_threshold'],building_groups=len(np.unique(d['bld'])),method='same MESHPATCH roofer_def and elem_types rules; own-unit input context',scientific_verdict=None))
    return res['pt'],res['edge']

def rows_for(d,place,split,prior,site,scope_name,scope,T2):
    rows=[];a=d['area'];region=d['region'];photo=d['photo'];dist=abs(d['d']);cell=d['cell']
    for kind in [1,2]:
      den=float(a[scope&(d['kind']==kind)].sum())
      for s,label in enumerate(LABELS):
       m=scope&(d['kind']==kind)&(place==s)
       for rep,rm in [('all',np.ones(len(a),bool)),('original',~d['any_replaced']),('replaced',d['any_replaced'])]:
        sel=m&rm;area=float(a[sel].sum())
        for variant in ['main','prior_only','mvs_only']:
         r=region.copy();sig=np.isin(region,[2,3])
         if variant=='prior_only':r[sig]=2
         if variant=='mvs_only':r[sig]=3
         c1=sel&(cell==1);c2=sel&(cell==2);cor=c2&(r==3);keep=c1&(r==2)
         # Disjoint attribution: threshold takes precedence when both conditions hold.
         threshold=cor&(dist>T2) if variant=='main' else np.zeros(len(a),bool)
         photo_only=cor&~(dist>T2)&(photo==1) if variant=='main' else np.zeros(len(a),bool)
         rows.append(dict(split=split,site=site,prior=prior,kind=kind,scope=scope_name,stratum=label,replacement=rep,variant=variant,
           patches=int(sel.sum()),area_m2=area,share_of_kind_area=area/den if den else None,photo_missing_area_m2=float(a[sel&~d['photo_available']].sum()),
           cell2_area_m2=float(a[c2].sum()),cell2_corrected_area_m2=float(a[cor].sum()),cell2_corrected_T2_area_m2=float(a[threshold].sum()),cell2_corrected_photo_only_area_m2=float(a[photo_only].sum()),
           cell2_corrected_both_evidence_area_m2=float(a[cor&(dist>T2)&(photo==1)].sum()) if variant=='main' else None,
           cell1_area_m2=float(a[c1].sum()),cell1_preserved_area_m2=float(a[keep].sum()),unavailable_area_m2=float(a[sel&(r<0)].sum())))
    return rows

def finish(d,pt,edge,manual,root,split,prior,site,T2,manual_note):
    n=len(d['area']);place=np.full(n,3,np.int8)
    place[~d['photo_available']]=4
    place[(d['photo_available']&(d['photo']==3))|manual]=2
    place[edge]=1;place[pt==3]=0
    np.savez_compressed(root/'strata.npz',place=place,mvs_face_type=pt,mvs_edge_band=edge,manual_glass=manual,**{k:d[k] for k in ['area','kind','cell','region','d','photo','photo_available','any_replaced','centre','normal','h','sigma','gt_offset']})
    scopes=[('all',np.ones(n,bool))] if split!='experiment' else [('evaluation',d['in_eval']),('band',~d['in_eval'])]
    rows=[]
    for scope_name,scope in scopes:rows+=rows_for(d,place,split,prior,site,scope_name,scope,T2)
    # Counts, areas and ratios only leave holdout. Histogram is aggregate area, no identifiers.
    bins=np.linspace(-1.5,1.2,55);hist=[]
    for label in range(5):
      for c in [1,2]:
       m=(place==label)&(d['cell']==c)&(np.ones(n,bool) if split!='experiment' else d['in_eval']);valid=m&np.isfinite(d['d'])&(abs(d['d'])>0)
       values=np.log10(abs(d['d'][valid]));weights=d['area'][valid]
       hist.append(dict(stratum=LABELS[label],cell=c,area_bins=np.histogram(values,bins=bins,weights=weights)[0].tolist(),zero_or_missing_area_m2=float(d['area'][m&~valid].sum()),below_axis_area_m2=float(weights[values<bins[0]].sum()),above_axis_area_m2=float(weights[values>bins[-1]].sum())))
    result=dict(at=stamp(),split=split,prior=prior,site=site,rows=rows,histogram=dict(bins_log10=bins.tolist(),rows=hist),manual_glass=manual_note,scientific_verdict=None)
    dump(root/'summary.json',result);dump(DOC/'tables'/f'places_r5_{split}_{site}_{prior}.json',result)
    print('STRATA_DONE',split,site,prior,n,flush=True)

def public_data(prior):
    keys=['patch_id','centre','normal','building','kind','area','mvs_face_type','mvs_edge_band']+[f'region_source_row_{site}' for site in ['B0_b10','B173nb_b10','B173_b0','R1rep_b10']]
    return zload(MP/'patch_table'/f'{prior}_patch_table.npz',keys)

def main():
    split,prior=sys.argv[1:3];T2=json.loads((OUT/'r2/stage0/T2.json').read_text())['fits']['main_u']['T2_m']
    if split in ['development','holdout']:
      sealed=split=='holdout';root=(OUT/'holdout/r5' if sealed else OUT/'r5')/'places'/f'{split}_{prior}';root.mkdir(parents=True,exist_ok=True)
      sroot=OUT/'holdout/r2/stage0' if sealed else OUT/'r2/stage0/development';croot=JN/'holdout/core_points' if sealed else JN/'core_points';stats=OUT/'holdout/r2/core_stats' if sealed else OUT/'r2/stage0/core_stats'
      fs=sorted(sroot.glob(f'*__{prior}.npz'));paths=fs+[croot/f.name for f in fs]+[stats/f.name for f in fs]
      wroot=W/'holdout/patch_values' if sealed else W/'patch_values';wfiles=sorted(wroot.glob(f'*__{prior}__R1.5.npz'))
      binding(root,paths+(wfiles if sealed else [MP/'patch_table'/f'{prior}_patch_table.npz']))
      ds=[]
      for f in fs:
        d=zload(f);c=zload(croot/f.name,['patch_id','centre','normal','gt_p']);st=zload(stats/f.name);ix=lookup(c['patch_id'],d['patch_id']);si=lookup(st['patch_id'],d['patch_id']);assert (ix>=0).all() and (si>=0).all()
        d.update(centre=c['centre'][ix],normal=c['normal'][ix],gt_offset=c['gt_p'][ix],d=st['stats'][si,1]);ds.append(d)
      d={k:np.concatenate([v[k] for v in ds]) for k in ds[0]}
      if sealed:
        keys=['patch_id','centre','normal','area','building','mvs_a_status','mvs_a_s','signed_difference_over_uncertainty','mvs_p','u_mvs','mvs_a_nx','mvs_a_ny','mvs_a_nz']
        ws=[zload(f,keys) for f in wfiles];w={k:np.concatenate([v[k] for v in ws]) for k in keys};del ws
        pt0,ed0=classify(inp(w),root,'holdout_'+prior);ix=lookup(w['patch_id'],d['patch_id']);assert (ix>=0).all();assert np.allclose(w['centre'][ix],d['centre'],atol=1e-8,rtol=0)
        pt,ed=pt0[ix],ed0[ix]
      else:
        public=public_data(prior);ix=lookup(public['patch_id'],d['patch_id']);assert (ix>=0).all();assert np.allclose(public['centre'][ix],d['centre'],atol=1e-8,rtol=0)
        pt,ed=public['mvs_face_type'][ix],public['mvs_edge_band'][ix]
      finish(d,pt,ed,np.zeros(len(pt),bool),root,split,prior,'all',T2,dict(status='not_applicable',reason='manual glass only requested for experimental region'))
    elif split=='experiment':
      public=public_data(prior);cases=json.loads((MP/'received/track_a_v3/results/cases.json').read_text())[prior]
      for site in ['B0_b10','B173nb_b10','B173_b0','R1rep_b10']:
        root=OUT/'r5/places'/f'{site}_{prior}';root.mkdir(parents=True,exist_ok=True)
        if (root/'summary.json').exists():continue
        if (root/'inputs.json').exists():(root/'inputs.json').rename(root/('inputs_before_retry_'+stamp().replace(':','-')+'.json'))
        tf=OUT/'r2/targets'/f'{site}_{prior}.npz';ef=OUT/'r2/stage0/evaluation'/f'{site}_{prior}.npz';uf=(OUT/'b173_uncert_r1/patch_values' if site=='B173_b0' else UN/'patch_values')/f'{site}__{prior}__R1.5.npz'
        binding(root,[tf,ef,uf,MP/'patch_table'/f'{prior}_patch_table.npz',MP/'received/track_a_v3/results/cases.json'])
        d=zload(tf);e=zload(ef,['cell','gt_med']);u=zload(uf);assert np.array_equal(d['centre'],u['centre']);d.update(cell=e['cell'],gt_offset=e['gt_med'])
        # B173 CPU uncertainty export omitted derived z and LoD2 u_prior.
        # Use the already-locked same-patch prior sigma solely to restore input-only z finiteness.
        missing_prior=~np.isfinite(u['u_prior'])|(u['u_prior']<=0)
        if site=='B173_b0' and 'z_a' not in u:
            u['u_prior']=np.where(missing_prior,d['sigma_p'],u['u_prior'])
        pt,ed=classify(inp(u),root,site+'_'+prior)
        join=public[f'region_source_row_{site}'];valid=join>=0;ids=np.flatnonzero(valid);q=join[ids];assert len(np.unique(q))==len(q)
        assert np.allclose(public['centre'][ids],d['centre'][q],atol=1e-6,rtol=0)
        pt[q]=public['mvs_face_type'][ids];ed[q]=public['mvs_edge_band'][ids]
        manual=np.zeros(len(pt),bool);notes={}
        for name in ['유리 띠','유리 둥근 지붕','B173 유리 채광창']:
          if name not in cases:notes[name]=dict(status='unavailable',reason='no explicit named membership in stored region/case file');continue
          ci=np.asarray(cases[name],int);sel=join[ci];matched=sel[sel>=0];manual[matched]=True
          notes[name]=dict(status='available' if len(matched) else 'unavailable',matched_patches=len(matched),reason='exact frozen region geometry join only; no nearest-patch transfer')
        notes['type_exact_global_join_patches']=len(q);notes['type_own_input_context_patches']=len(pt)-len(q);notes['missing_building_ids']=int((u['building']=='').sum());notes['type_z_prior_sigma_from_locked_stage0_patches']=int(missing_prior.sum()) if site=='B173_b0' else 0
        finish(d,pt,ed,manual,root,split,prior,site,T2,notes)
    else:raise ValueError(split)
if __name__=='__main__':main()
