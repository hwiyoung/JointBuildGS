"""Presentation only. Supplied scores/results are never recomputed or optimized."""
import sys
from pathlib import Path
sys.path.insert(0, '/repo/scripts/phd/main_regionfig_v1')
import common as geo
import prepare as old
from common import np, json, sha, load, dump, now, PAY, DOC, CFG, PH, RAW, DENSE, project, poses, cameras
import resource

W=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
V1=PH/'main_regionfig_v1/PHD-MAIN-REGIONFIG-v1'
REGIONS=['다듬기','보정','보존','둘 다 틀림','상속 · 결측','상속 · 비가시']
REGION_COLORS=['#9ecae1','#d9822b','#756bb1','#636363','#fdd835','#c7c7c7']
JUDGMENTS=['지지','반박','유보','사진 부족','판단 없음']
JUDGE_COLORS=['#1b9e77','#e7298a','#ffffff','none','none']

def regions(d):
    r=d['cell'].astype(int).copy()
    inh=np.isin(r,[4,5]);r[inh]=4;r[inh&(d['judgment']==4)]=5
    return r

def judgments(d):
    j=d['judgment'].astype(int).copy();j[j==3]=2;j[j==4]=3;j[j<0]=4
    return j

def data(prior,building=None):
    with np.load(PAY/f'joined_{prior}.npz',allow_pickle=False) as z:
        m=np.ones(len(z['area']),bool) if building is None else z['building']=='DEBY_LOD2_'+str(building)
        return {k:z[k][m] for k in z.files}

def safe_pct(a,mask,ok):
    den=float(a[mask].astype(float).sum())
    return 100*float(a[mask&ok].astype(float).sum())/den if den else None

def metrics(d,inside):
    a=d['area'].astype(float); roof=d['roof_like']; gt=np.isfinite(d['gt_p']); r=regions(d); j=judgments(d)
    result=inside&roof&gt
    out=dict(patches=int(inside.sum()),roof_patches=int((inside&roof).sum()),
             area_m2=float(a[inside].sum()),unpainted_no_reference_area_m2=float(a[inside&~gt].sum()),
             result_patches=int(result.sum()),result_area_m2=float(a[result].sum()),
             region_area_m2={name:float(a[inside&gt&(r==i)].sum()) for i,name in enumerate(REGIONS)},
             judgment_area_m2={name:float(a[inside&gt&(j==i)].sum()) for i,name in enumerate(JUDGMENTS)},
             result_denominator='roof_like & finite gt_p & centre projects inside the native crop',
             per_region=[])
    for key in ['category','check']:
        ok=np.abs(d['z_'+key].astype(float)-d['gt_p'].astype(float))<=d['tau'].astype(float)
        out['ok_'+key+'_pct']=safe_pct(a,result,ok)
    for i,name in enumerate(REGIONS):
        m=result&(r==i);q=dict(region=name,area_m2=float(a[m].sum()),patches=int(m.sum()))
        for key in ['category','check']:
            ok=np.abs(d['z_'+key].astype(float)-d['gt_p'].astype(float))<=d['tau'].astype(float)
            q['ok_'+key+'_pct']=safe_pct(a,m,ok)
        out['per_region'].append(q)
    return out

def sections(ex,d):
    a=np.array(ex['start_xy']);b=np.array(ex['end_xy']);L=np.linalg.norm(b-a);v=(b-a)/L
    along=(d['centre'][:,:2]-a)@v;across=(d['centre'][:,:2]-a)@np.array([-v[1],v[0]])
    band=d['matched']&d['roof_like']&(along>=0)&(along<=L)&(abs(across)<=ex['half_width_m'])
    nb=int(np.ceil(L/.25));edges=np.minimum(np.arange(nb+1)*.25,L);bc=(edges[:-1]+edges[1:])/2
    nz=d['normal'][:,2];z=d['centre'][:,2]
    arrays=[z,z+d['mvs_p']*nz,z+d['gt_p']*nz,z+d['z_category']*nz,z+d['z_check']*nz]
    h=np.full((nb,5),np.nan);r=np.full(nb,-1,int);j=r.copy();counts=np.zeros(nb,int);wrong=np.zeros(nb,bool)
    reg=regions(d);jud=judgments(d);areas=d['area'].astype(float)
    for i in range(nb):
        m=band&(along>=edges[i])&((along<edges[i+1]) if i<nb-1 else (along<=edges[i+1]))
        counts[i]=int(m.sum())
        for k,y in enumerate(arrays):
            q=y[m&np.isfinite(y)]
            if len(q):h[i,k]=np.median(q)
        if m.any():
            r[i]=np.argmax(np.bincount(reg[m],weights=areas[m],minlength=7))
            j[i]=np.argmax(np.bincount(jud[m],weights=areas[m],minlength=5))
            inherited=m&(reg==r[i])&np.isin(d['cell'],[4,5])
            if r[i] in [4,5] and inherited.any():
                wrong[i]=areas[inherited&(d['cell']==5)].sum()>=areas[inherited].sum()/2
    zero=float(np.nanmin(h[:,2])) if np.isfinite(h[:,2]).any() else float(np.nanmin(h[:,0]))
    return dict(bin_edges_m=edges,bin_centres_m=bc,heights_model_m=h,heights_relative_m=h-zero,
                reference_zero_model_m=zero,region=r,judgment=j,inherit_wrong=wrong,bin_patch_counts=counts,
                band_patch_ids=d['patch_id'][band],length_m=L)

def environment():
    cg={}
    for name in ['memory.max','memory.current','memory.peak']:
        p=Path('/sys/fs/cgroup')/name
        if p.exists():cg[name]=p.read_text().strip()
    return dict(at=now(),max_rss_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,cgroup=cg,
                numpy=np.__version__,scientific_verdict=None)

def examples():
    c=load('/repo/configs/phd/main_regionfig_v1/regionfig_v1.json');oldex=c['examples']
    rows=[
      ('1','다듬기','60042','ALS',[-64.03,40.64],[-56.57,37.76],.5,'두 자료가 맞는 넓은 지붕에서 결과는 두 경우 모두 맞다'),
      ('2','보정_실제변화','4959326','ALS',oldex[0]['start_xy'],oldex[0]['end_xy'],oldex[0]['half_width_m'],'범주별로는 옛 지붕에 남은 곳이 검사 기반에서는 지금 지붕으로 옮겨 맞았다'),
      ('3','보정_단순화','4906975','LoD2',oldex[1]['start_xy'],oldex[1]['end_xy'],oldex[1]['half_width_m'],'단순하게 낮게 그린 띠를 사진이 반박했고 결과가 맞았다'),
      ('4','보존','4907519','LoD2',[-53.226,-191.622],[-50.888,-201.345],.6,'영상만 틀린 넓은 지붕을 사진이 지지했고 결과는 대부분 맞았다'),
      ('5','보존_사진반박','4907519','ALS',[-39.02,-210.26],[-37.54,-200.37],.6,'영상만 틀린 곳에서 사진도 반박해 검사 기반 결과가 틀렸다'),
      ('6','보존_사진지지','4906993','LoD2',[57.213,298.440],[65.982,293.634],.6,'사진이 지지했는데도 결과가 영상의 면을 따라 틀렸다'),
      ('7','상속_비가시','4907519','LoD2',[18.59,-233.45],[19.94,-221.52],.6,'사진도 영상의 면도 없는 곳은 사전 정보를 물려받았다'),
      ('8','상속_결측','4906965','LoD2',[-48.24,-105.97],[-59.42,-101.62],.6,'사진은 반박했지만 따라갈 영상의 면이 없어 사전 정보가 틀린 채 남았다')]
    return [dict(id=i,slug=s,building=b,prior=p,start_xy=a,end_xy=z,half_width_m=w,expected=t,
                 selected_after_results=i in ['5','7','8'],fixed_v1_photo={'2':'a','3':'b'}.get(i)) for i,s,b,p,a,z,w,t in rows]
