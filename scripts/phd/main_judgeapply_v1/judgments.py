"""Photo thresholds, six reference-free decisions and future-training targets."""
from common import *
METHODS=['prior_only','image_only','geometry_only','photo_only','fusion','method','oracle']
NAMES=['사전 정보 단독','영상 단독','기하 일관성 검사 단독','광도 일관성 검사 단독','결합','본 방법','맞는 판단']
def quantile(x,w,q):
    mask=np.isfinite(x)&np.isfinite(w)&(w>0);x=x[mask];w=w[mask]
    if not len(x):return np.nan
    ix=np.argsort(x,kind='stable');x=x[ix];w=w[ix]
    return float(x[min(np.searchsorted(np.cumsum(w),q*w.sum(),side='left'),len(x)-1)])
def number(x):return float(x) if np.isfinite(x) else None
def main(site):
    start=time.monotonic();prepared=loadz(O/'photo_prepared'/f'{site}.npz');score=loadz(O/'photo_scores'/site/'scores.npz');thresholds=[];fusions=[]
    assert np.array_equal(prepared['point_id'],score['point_id'])
    for prior in cfg()['priors']:
      d=loadz(O/'geometry'/f'{site}__{prior}.npz');mapping=loadz(O/'photo_mapping'/f'{site}__{prior}.npz');g=loadz(O/'photo_geometry'/f'{site}__{prior}.npz')
      N=len(d['n']);P=len(g['point_id']);ix=np.flatnonzero(prepared['prior']==prior);target=prepared['source_index'][ix]
      pp={k:prepared[k][ix] for k in ['centres','normals','tangent1','tangent2','available','selected_images','prior_height_m','prior_n','mvs_fit_count','mvs_fit_nmad_m','mvs_normal_angle_deg','mvs_fit_reason','mask_fraction_at_zero']}
      pp.update(score=score['score'][ix],texture=score['texture'][ix],texture_by_view=score['texture_by_view'][ix],valid_image_count=score['valid_image_count'][ix],point_id=g['point_id'][target],source_index=target,kind=g['kind'][target],threshold_sample=np.zeros(len(ix),bool),t=np.full(len(ix),np.nan))
      code=np.full(len(ix),9,np.int8)
      for kind in cfg()['priors'][prior]:
        pool=np.flatnonzero(g['all_within'][target]&(g['kind'][target]==kind));chosen=pool
        if len(pool)>5000:chosen=np.random.default_rng(20261103).choice(pool,5000,replace=False)
        pp['threshold_sample'][chosen]=True;x=pp['score'][chosen,0];w=g['area'][target[chosen]];t=quantile(x,w,.05);t10=quantile(x,w,.10)
        part=g['kind'][target]==kind;pp['t'][part]=t
        p,m=pp['score'][:,0],pp['score'][:,1]
        if np.isfinite(t):
            code[part&(p<t)&(m>=t)]=1;code[part&(p>=t)&(m<t)]=0;code[part&(p<t)&(m<t)]=2;code[part&(p>=t)&(m>=t)]=3
            code[part&~np.isfinite(pp['score']).all(1)]=5
        thresholds.append(dict(site=site,prior=prior,kind=kind,t=number(t),t10=number(t10),pool_count=len(pool),sample_count=len(chosen),finite_score_count=int(np.isfinite(x).sum()),sample_area_m2=float(w.sum()),finite_score_area_m2=float(w[np.isfinite(x)].sum()),source='photo_points/'+site+'__'+prior+'.npz',source_tag='[이 발주에서 냄]'))
      code[~pp['available'][:,1]]=4;code[(pp['texture']<5).all(1)]=6;code[((pp['selected_images']>=0).sum(-1)<3).any(1)]=7
      pp['photo_code']=code;allcode=np.full(P,9,np.int8);allcode[target]=code;d['photo_code']=allcode[mapping['point_index']]
      d['photo_point_id']=mapping['point_id'];d['photo_point_index']=mapping['point_index']
      pp.update(centre=g['centre'][target],area=g['area'][target],patch_count=g['patch_count'][target],all_within=g['all_within'][target],source=g['source'][target])
      savez(O/'photo_points'/f'{site}__{prior}.npz',**pp)
      sight=loadz(O/'sight'/f'{site}__{prior}.npz');free=np.where(d['kind']==1,sight['free10'],sight['free5'])
      d.update(sight_votes=sight['votes'],sight_disappeared=sight['disappeared'],free5=sight['free5'],free10=sight['free10'])
      reg=np.full((7,N),9,np.int8);why=np.full((7,N),9,np.int8)
      valid=np.isfinite(d['prior_height_m'])&np.isfinite(d['normal']).all(1);missing=valid&(d['n']>=0)&(d['n']<4);present=valid&(d['n']>=4)&np.isfinite(d['mvs_mean_m'])
      inside=valid&(d['geometry']==0);outside=valid&(d['geometry']==1);default=1 if prior=='ALS' else 2
      for j in [0,1,2,3,5]:reg[j,missing]=4
      for j in [1,2,3,5]:reg[j,missing&free]=3
      reg[0,present]=1;reg[1,present]=2
      reg[2,inside]=0;reg[2,outside]=default;why[2,outside]=2
      for j,mask in [(3,present),(5,outside)]:
        reg[j,mask]=default;why[j,mask]=2
        reg[j,mask&(d['photo_code']==0)]=1;why[j,mask&(d['photo_code']==0)]=0
        reg[j,mask&(d['photo_code']==1)]=2;why[j,mask&(d['photo_code']==1)]=1
      reg[5,inside]=0
      fp=PH/'main_baselines_v1/PHD-MAIN-BASELINES-v1/runs'/site/f'mvsfuse_{prior}/detect/patches.npz'
      meta=fp.with_name('detect.json');fm=json.loads(meta.read_text());threshold=fm['rule']['pixel']['colour_threshold'];key=f'in_change_{int(threshold)}'
      ff=loadz(fp,[key,'area','in_eval']);ii=d['source_index'];assert np.array_equal(ff['area'][ii],d['area']) and ff['in_eval'][ii].all()
      reg[4]=np.where(ff[key][ii],2,1)
      fusions.append(dict(site=site,prior=prior,path=str(fp),sha256=sha(fp),field=key,colour_threshold=threshold,decision_lines='mvsfuse/detect.py:315-353,355-364,725-732,770-772',rules_source='scripts/phd/main_baselines_v1/mvsfuse/mf_common.py:56-101',thresholds=fm['rule']))
      d.update(region=reg,reason=why)
      savez(O/'decisions'/f'{site}__{prior}.npz',**d)
      vm=d['u_mvs']**2+d['sigma_W_m']**2;vp=d['sigma_P_m']**2
      with np.errstate(divide='ignore',invalid='ignore'):
        w=vm/(vp+vm);mixed=(d['mvs_mean_m']*vp+d['prior_height_m']*vm)/(vp+vm)
      h=np.full(N,np.nan);hr=h.copy();a=reg[5]
      h[a==0]=mixed[a==0];hr[a==0]=mixed[a==0]+w[a==0]*d['r_m'][a==0]
      keep=np.isin(a,[1,4]);h[keep]=d['prior_height_m'][keep];hr[keep]=h[keep]+d['r_m'][keep]
      h[a==2]=d['mvs_mean_m'][a==2];hr[a==2]=h[a==2]
      target_region=np.full(N,-1,np.int8)
      for ja,tg in [(0,1),(1,2),(2,3),(3,5),(4,0)]:target_region[a==ja]=tg
      train=dict(patch_id=d['patch_id'],source_index=d['source_index'],centre=d['centre'],normal=d['normal'],kind=d['kind'],area=d['area'],building=d['building'],surf=d['surf'],in_eval=np.ones(N,bool),region=target_region,judge_region=a,reason=why[5],h_no_r=h,h_with_r=hr,target_no_r=d['centre']+h[:,None]*d['normal'],target_with_r=d['centre']+hr[:,None]*d['normal'],u=d['u_mvs'],sigma_p=d['sigma_P_m'],u_M=d['u_mvs'],sigma_P=d['sigma_P_m'],sigma_W=d['sigma_W_m'],r=d['r_m'],surface_exists=np.isin(a,[0,1,2,4]))
      savez(O/'training_regions'/f'{site}__{prior}.npz',**train)
      d['prior_weight']=w;savez(O/'decisions'/f'{site}__{prior}.npz',**d)
    dump(D/'tables'/f'{site}_photo_thresholds.json',dict(rows=thresholds,scientific_verdict=None))
    dump(D/'tables'/f'{site}_fusion_sources.json',dict(rows=fusions,scientific_verdict=None))
    dump(O/'timing'/f'{site}_judgments.json',dict(at=now(),seconds=time.monotonic()-start,scientific_verdict=None));print('JUDGMENTS_COMPLETE',site,flush=True)
if __name__=='__main__':main(sys.argv[1])
