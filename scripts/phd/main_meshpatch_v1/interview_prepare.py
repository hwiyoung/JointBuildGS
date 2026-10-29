"""Freeze case membership and the ordered addendum-2 jobs from existing inputs."""
import copy
from scipy import ndimage
from interview_common import *

def main():
    cfg=config();dest=IDOC/'cases.json'
    if dest.exists() and (IDOC/'jobs.json').exists():return
    fcfg=json.loads((R/'configs/phd/main_floatdiag_v1/floatdiag_v1.json').read_text())
    ns=dict(np=np,ndimage=ndimage)
    components=frozen_function(R/'scripts/phd/main_floatdiag_v1/recount.py','components',ns)
    ns=dict(np=np,S1=S1)
    reference=frozen_function(R/'scripts/phd/main_floatdiag_v1/geometry.py','reference',ns)
    camera=frozen_function(R/'scripts/phd/main_floatdiag_v1/geometry.py','camera',ns)
    cases=[];unavailable=[];bindings=[]
    for site,prior,cell,slug,label in [('B173nb_b10','ALS',2,'preserve-b173-als','B173 · 항공 LiDAR · 보존'),
        ('B173nb_b10','LoD2',4,'inherit-b173-lod2','B173 · LoD2 · 상속'),
        ('R1rep_b10','LoD2',4,'inherit-r1-lod2','R1 · LoD2 · 상속')]:
        e,v,base=evaluation(site,prior);z,zp=patch_values(site,prior,f'lt_dynnow_{prior}_s0',e)
        mask=eligible(e)&(e['cell']==cell)
        if cell==4:mask&=classes(e,z)==1
        comps,origin=components(e,mask,fcfg['case_selection'])
        if not comps:
            unavailable.append(dict(slug=slug,status='UNAVAILABLE',reason='해당 칸에 조건을 만족하는 덩어리 없음'))
            record('fig-'+slug,status='UNAVAILABLE',reason=unavailable[-1]['reason']);continue
        c=dict(comps[0],site=site,prior=prior,slug=slug,id=label,kind='preservation' if cell==2 else 'inheritance',
               cell=cell,domain='선택된 원래 패치 덩어리',component_grid_origin=origin.tolist(),
               results=[f'nojudge_{prior}_s0',f'lt_dynnow_{prior}_s0'],human_structure_review='모름' if cell==4 else None)
        gt,gpath=reference(site);b=np.array(c['bbox']);lo=b[:2]-3;hi=b[2:]+3
        g=gt[((gt[:,:2]>=lo)&(gt[:,:2]<=hi)).all(1)]
        assert len(g),'No raw GT points: do not invent crop height'
        low=np.r_[lo,g[:,2].min()-2];high=np.r_[hi,g[:,2].max()+8]
        c.update(crop_min=low.tolist(),crop_max=high.tolist(),translation=((low+high)/2).tolist(),radius=float(np.linalg.norm(high-low)/2))
        c['cameras']=[camera(c,a,b) for a,b in zip(fcfg['cameras']['azimuth_deg'],fcfg['cameras']['elevation_deg'])]
        cases.append(c);bindings.extend([source(base/'evaluation.npz'),source(zp),source(gpath)])
    for site in ['B173nb_b10','R1rep_b10']:
        path=R/'configs/phd/main_floatdiag_v1'/f'geometry_{site}_ALS.json'
        src=json.loads(path.read_text());e,_,_=evaluation(site,'ALS')
        for j,original in enumerate(src['cases']):
            c=copy.deepcopy(original);c['slug']=f'compare-{SHORT[site].lower()}-{j+1}';c['kind']='comparison'
            c['domain']='FLOATDIAG 사례 경계 상자 + 3 m 안 칸 0~3'
            b=np.array(c['bbox']);m=eligible(e)&np.isin(e['cell'],[0,1,2,3])&((e['centre'][:,:2]>=b[:2]-3)&(e['centre'][:,:2]<=b[2:]+3)).all(1)
            c['patch_indices']=np.flatnonzero(m).tolist();c['area_m2']=float(e['area'][m].sum())
            c['results']=['nojudge_ALS_s0','lt_dynnow_ALS_s0']
            for result in ['geogs_ALS_fix1','imgonly_2dgs_s0','mvsfuse_ALS']:
                receipt=D/'tables/meshes'/f'{site}__ALS__{result}.json'
                if receipt.exists() and json.loads(receipt.read_text())['status']=='PASS':c['results'].append(result)
            c['human_structure_review']=None;cases.append(c)
        bindings.append(source(path))
    dump(dest,dict(cases=cases,unavailable=unavailable,sources=bindings,config=source(C/'interview_addendum_v2.json'),scientific_verdict=None))
    jobs=[dict(tag='fig-'+c['slug'],script='interview_figures.py',args=[c['slug']]) for c in cases]
    jobs += [dict(tag='comparison',script='interview_comparison.py'),dict(tag='counts',script='interview_counts.py')]
    for site in SITES:
        for prefix in ['nojudge','lt_dynnow']:
            jobs.append(dict(tag=f'gaussians-{SHORT[site].lower()}-{prefix}',script='interview_gaussians.py',args=[site,prefix]))
    jobs.append(dict(tag='virtual-baseline',script='interview_virtual.py',args=['baseline']))
    for site in SITES:
        for prefix in ['nojudge','lt_dynnow']:
            jobs.append(dict(tag=f'virtual-{SHORT[site].lower()}-{prefix}',script='interview_virtual.py',args=[site,prefix]))
    dump(IDOC/'jobs.json',dict(jobs=jobs,scientific_verdict=None))
    record('prepare',cases=len(cases),unavailable=unavailable,jobs=len(jobs))

if __name__=='__main__':main()
