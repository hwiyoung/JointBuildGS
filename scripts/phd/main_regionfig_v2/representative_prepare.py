"""Freeze a presentation-only revision using the eight existing sites and source bytes."""
from draw_figures import *
import os

REV='representative_v1'

def masks(ex,d,g):
    number=int(ex['id']); a=np.array(ex['start_xy']);b=np.array(ex['end_xy'])
    length=np.linalg.norm(b-a);v=(b-a)/length
    along=(d['centre'][:,:2]-a)@v
    across=(d['centre'][:,:2]-a)@np.array([-v[1],v[0]])
    crop=g['inside']&d['roof_like']&np.isfinite(d['gt_p'])
    cell={1:0,2:1,3:1,4:2,5:2,6:2}.get(number)
    target=crop&(d['cell']==cell) if cell is not None else crop&np.isin(d['cell'],[4,5])&(d['judgment']==4 if number==7 else d['judgment']!=4)
    band=crop&(along>=0)&(along<=length)&(abs(across)<=ex['half_width_m'])
    okc=abs(d['z_category'].astype(float)-d['gt_p'])<=d['tau']
    okk=abs(d['z_check'].astype(float)-d['gt_p'])<=d['tau']
    conditions={1:okc&okk,2:(d['judgment']==1)&~okc&okk,3:(d['judgment']==1)&okk,
      4:(d['judgment']==0)&okc&okk,5:(d['judgment']==1)&okc&~okk,
      6:(d['judgment']==0)&~okk,7:(d['judgment']==4)&~np.isfinite(d['mvs_p']),
      8:(d['cell']==5)&(d['judgment']==1)&~np.isfinite(d['mvs_p'])}
    eligible=target&band&conditions[number]
    return target,band,eligible,along,across,length

def summary(d,m):
    a=d['area'].astype(float)
    out=dict(patches=int(m.sum()),area_m2=float(a[m].sum()),patch_ids=d['patch_id'][m],
      judgment_area_m2={str(j):float(a[m&(d['judgment']==j)].sum()) for j in [-1,0,1,2,3,4]})
    for key in ['category','check']:
        ok=abs(d['z_'+key].astype(float)-d['gt_p'])<=d['tau']
        out['ok_'+key+'_pct']=safe_pct(a,m,ok)
    return out

def main():
    cfg=load(CFG/'regionfig_v2.json');rows=[]
    out=CFG/REV/'design.json';assert not out.exists(),'Frozen revision already exists'
    for ex in cfg['examples']:
        d=data(ex['prior'],ex['building']);g=geometry(ex,d)
        target,band,eligible,along,across,length=masks(ex,d,g)
        assert eligible.any(),f'No same-patch witness for {ex["id"]}'
        # Within the explicit outcome conjunction, use a geometry-only tie-break.
        candidates=np.flatnonzero(eligible)
        ix=candidates[np.lexsort((d['patch_id'][candidates],abs(across[candidates]),abs(along[candidates]-length/2)))[0]]
        j=int(np.flatnonzero(g['ids']==ix)[0]);poly=g['polys'][j]
        centre=poly.mean(axis=0)
        row=dict(id=ex['id'],focus_patch_id=d['patch_id'][ix],focus_index_in_building=int(ix),
          focus_along_m=along[ix],focus_across_m=across[ix],focus_polygon_display_px=poly,
          focus_zoom_bounds_px=[centre[0]-180,centre[0]+180,centre[1]-180,centre[1]+180],
          focus_values={k:d[k][ix] for k in ['area','cell','judgment','gt_p','mvs_p','tau','z_category','z_check','centre','normal','v_prior_category','v_prior_check','v_mvs']},
          eligible_count=int(eligible.sum()),target=summary(d,target),section_target=summary(d,target&band),
          same_case=summary(d,target&({1:np.ones(len(target),bool),2:d['judgment']==1,3:d['judgment']==1,
             4:d['judgment']==0,5:d['judgment']==1,6:d['judgment']==0,7:d['judgment']==4,8:d['judgment']==1}[int(ex['id'])])),
          exact_focus_selected_after_results=True,original_site_selected_after_results=ex['selected_after_results'])
        rows.append(row)
        print(ex['id'],row['focus_patch_id'],'eligible',row['eligible_count'],'values',row['focus_values'],
              'target',row['target']['ok_category_pct'],row['target']['ok_check_pct'],flush=True)
    protected=[]
    for root in [CFG,DOC]:
        for p in sorted(root.rglob('*')):
            if p.is_file() and REV not in p.parts:protected.append(dict(path=str(p),sha256=sha(p)))
    for p in [PAY/'joined_ALS.npz',PAY/'joined_LoD2.npz',*sorted((PAY/'input').glob('*'))]:
        if p.is_file():protected.append(dict(path=str(p),sha256=sha(p)))
    record=dict(task_id='PHD-MAIN-REGIONFIG-v2-REP1',at=now(),base_commit=os.environ.get('JBGS_SOURCE_HEAD'),
      authority='User: 권장안으로 진행하자. Representative figures plus retained detailed evidence; pilots 2/5/7 then all eight.',
      base_config_sha256=sha(CFG/'regionfig_v2.json'),examples=rows,protected_inputs=protected,
      design=dict(photo='Exact existing crop and rigid rotation; no retouch. Focus A is one supplied patch.',
        selection='Within the original frozen section band and target cell, require the stated case conjunction; choose closest to section midpoint, then closest to centreline, then patch ID. Post-result illustrative selection, not representative sampling.',
        layout='Two photos with exact A locator; input/result full fixed sections with A raw sample; same vertical limits. Separate exact A normal-error ruler for unambiguous threshold crossing.',
        stats='Target-region crop area rates and same-cell/same-judgment area; never whole-crop rate as case rate.',
        reference='Supplied reference only. Cell uses source mvs_a_e; normal distance is not its substitute.',
        missing='No MVS remains missing. Photo shortage means selected_count < 3, not physical invisibility.',
        result='Supplied analytic loss minima, no training, inference, geometry editing, or photo-check rerun.',
        dpi=300,figsize=[18,12],font='Noto Sans CJK JP'),scientific_verdict=None)
    dump(out,record);dump(out.with_name('design.lock.json'),dict(at=now(),config_sha256=sha(out),scientific_verdict=None))
    dump(PAY/REV/'preparation.json',dict(config_sha256=sha(out),environment=environment()))

if __name__=='__main__':main()
