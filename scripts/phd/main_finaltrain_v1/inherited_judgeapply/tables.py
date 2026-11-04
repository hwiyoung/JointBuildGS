"""Requested quantitative tables from saved per-core values; no image/geometry rerun."""
from common import *
from judgments import METHODS,NAMES,quantile,number
import csv
REGION_NAMES={0:'일치',1:'보존',2:'보정',3:'보정(빈 공간)',4:'결측',9:'확인 불가'}
def write_table(name,rows):
    for r in rows:
        if 'source' not in r:r['source']=f'core_points/{r["site"]}__{r["prior"]}.npz' if 'site' in r and 'prior' in r else 'calibration.json'
    root=D/'tables';root.mkdir(exist_ok=True);payload=dict(at=now(),rows=rows,source_tag='[이 발주에서 냄]',scientific_verdict=None)
    dump(root/f'{name}.json',payload)
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with (root/f'{name}.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
    text=['| '+' | '.join(keys)+' |','| '+' | '.join(['---']*len(keys))+' |']
    for r in rows:text.append('| '+' | '.join('확인 불가' if r.get(k) is None else str(r[k]).replace('|','/') for k in keys)+' |')
    (root/f'{name}.md').write_text('\n'.join(text)+'\n')
def rate(d,j,m):
    a=d['area'];c=d['cell'];r=d['region'][j];c1=m&(c==1);c2=m&(c==2);den=float(a[c1|c2].sum())
    um=c1&(r==9);uf=c2&(r==9);miss=c1&(r!=2)&(r!=9);false=c2&(r!=1)&(r!=9)
    A=lambda x:float(a[x].sum());pct=lambda v:100*v/den if den else None
    ma,fa,uma,ufa=A(miss),A(false),A(um),A(uf)
    return dict(method=METHODS[j],method_ko=NAMES[j],count=int(m.sum()),denominator_count=int((c1|c2).sum()),denominator_m2=den,
       error_rate_pct=pct(ma+fa) if uma+ufa==0 else None,missed_pct=pct(ma) if uma==0 else None,false_pct=pct(fa) if ufa==0 else None,
       error_lower_pct=pct(ma+fa),error_upper_pct=pct(ma+fa+uma+ufa),missed_lower_pct=pct(ma),missed_upper_pct=pct(ma+uma),false_lower_pct=pct(fa),false_upper_pct=pct(fa+ufa),
       missed_known_m2=ma,false_known_m2=fa,missed_mixing_m2=A(miss&(r==0)),missed_one_side_m2=A(miss&(r!=0)),false_mixing_m2=A(false&(r==0)),false_one_side_m2=A(false&(r!=0)),
       unavailable_cell1_m2=uma,unavailable_cell2_m2=ufa,cell4_erased_m2=A(m&(c==4)&(r==3)),cell3_m2=A(m&(c==3)),cell5_m2=A(m&(c==5)),cell6_m2=A(m&(c==6)),cell9_m2=A(m&(c==9)),
       status='확인 불가: 분모 안 미판단 영역' if uma+ufa>0 else ('확인 불가: 분모 0' if den==0 else '계산 완료'))
def requested(d,site,prior):
    cross=[];split=[];weights=[];hist=[];r8cross=[];r8=TG/'r8/targets'/f'{site}_{prior}.npz'
    old=None
    if r8.exists():
        old=loadz(r8,['centre','region']);assert np.array_equal(old['centre'][d['source_index']],d['centre']);old=old['region'][d['source_index']]
    for kind in cfg()['priors'][prior]:
      scope=d['kind']==kind;area=d['area'];a=d['region'][5];reason=d['reason'][5]
      categories=[('일치',(a==0)),('보존·사진',(a==1)&(reason==0)),('보존·기본',(a==1)&(reason==2)),('보정·사진',(a==2)&(reason==1)),('보정·기본',(a==2)&(reason==2)),('보정(빈 공간)',a==3),('결측',a==4),('확인 불가',a==9)]
      for label,mask in categories:
       mask=mask&scope;den=float(area[mask].sum())
       for cell in [0,1,2,3,4,5,6,9]:
        m=mask&(d['cell']==cell);v=float(area[m].sum());cross.append(dict(site=site,prior=prior,kind=kind,region_reason=label,cell=cell,count=int(m.sum()),area_m2=v,row_area_m2=den,row_fraction=v/den if den else None,source=f'core_points/{site}__{prior}.npz'))
      m=scope&(a==0)&np.isfinite(d['prior_weight']);x=d['prior_weight'][m];w=area[m]
      weights.append(dict(site=site,prior=prior,kind=kind,count=len(x),area_m2=float(w.sum()),**{f'q{q}':number(np.quantile(x,q/100)) if len(x) else None for q in [10,25,50,75,90]},quantile_rule='per-core unweighted empirical quantile',source=f'core_points/{site}__{prior}.npz'))
      for low in np.arange(10)/10:
        hit=(x>=low)&(x<low+.1 if low<.9 else x<=1.);hist.append(dict(site=site,prior=prior,kind=kind,left=float(low),right=float(low+.1),count=int(hit.sum()),area_m2=float(w[hit].sum())))
      if old is not None:
       for rr in np.unique(old[scope]):
        for new in [0,1,2,3,4,9]:
         m=scope&(old==rr)&(a==new);r8cross.append(dict(site=site,prior=prior,kind=kind,r8_region=int(rr),region=new,count=int(m.sum()),area_m2=float(area[m].sum()),source=str(r8)))
      else:r8cross.append(dict(site=site,prior=prior,kind=kind,status='확인 불가: r8 영역 파일 없음. r7을 r8로 대체하지 않음',count=None,area_m2=None,source=str(r8)))
    if site=='B173nb_b10' and prior=='ALS':
     for label,cut in [('abs_d_le_0.53',abs(d['d_m'])<=.53),('abs_d_gt_0.53',abs(d['d_m'])>.53)]:
      for r in [0,1,2,3,4,9]:
       m=(d['cell']==2)&cut&(d['region'][5]==r);split.append(dict(site=site,prior=prior,split=label,region=r,count=int(m.sum()),area_m2=float(d['area'][m].sum()),source=f'core_points/{site}__{prior}.npz'))
    return cross,split,weights,hist,r8cross
def main():
    start=time.monotonic();rates=[];cross=[];split=[];weights=[];hist=[];r8cross=[];scope=[];limits=[];five=[];photo=[];walls=[]
    for site in cfg()['sites']:
     for prior in cfg()['priors']:
      d=loadz(O/'core_points'/f'{site}__{prior}.npz');source=f'core_points/{site}__{prior}.npz'
      for label,m in [('all',np.ones(len(d['n']),bool))]+[(str(k),d['kind']==k) for k in cfg()['priors'][prior]]:
       for j in range(6):rates.append(dict(site=site,prior=prior,kind=label,**rate(d,j,m),source=source))
      out=requested(d,site,prior)
      for dest,rows in zip([cross,split,weights,hist,r8cross],out):dest.extend(rows)
      for kind in cfg()['priors'][prior]:
        m=d['kind']==kind;w=d['area'];v=d['L_m'][m];v=v[np.isfinite(v)]
        scope.append(dict(site=site,prior=prior,kind=kind,buildings=len(set(d['building'][m])-{''}),count=int(m.sum()),area_m2=float(w[m].sum()),missing_building_count=int((m&(d['building']=='')).sum()),missing_u_count=int((m&~np.isfinite(d['u_mvs'])).sum()),missing_u_observed_count=int((m&(d['n']>=4)&~np.isfinite(d['u_mvs'])).sum()),unavailable_geometry_count=int((m&(d['geometry']==9)).sum()),source=source))
        limits.append(dict(site=site,prior=prior,kind=kind,count=len(v),L_q25_m=number(np.quantile(v,.25)) if len(v) else None,L_median_m=number(np.quantile(v,.5)) if len(v) else None,L_q75_m=number(np.quantile(v,.75)) if len(v) else None,source=source))
        if (prior=='ALS' and kind==1) or (prior=='LoD2' and kind==2):
         base=m&(d['cell']==0);valid=base&np.isfinite(d['L_m']);den=float(w[base].sum())
         for z in [1.645,1.96,2.576]:
          outside=valid&(abs(d['d_m'])>d['L_m']/1.96*z);five.append(dict(site=site,prior=prior,kind=kind,z=z,cell0_count=int(base.sum()),cell0_area_m2=den,outside_area_m2=float(w[outside].sum()),unavailable_area_m2=float(w[base&~valid].sum()),outside_fraction=float(w[outside].sum()/den) if den and np.array_equal(valid,base) else None,source=source))
        for label,mask in [('inside_cell0',m&(d['geometry']==0)&(d['cell']==0))]+[(f'outside_cell{c}',m&(d['geometry']==1)&(d['cell']==c)) for c in [1,2,3]]:
         den=float(w[mask].sum())
         for code in range(10):
          hit=mask&(d['photo_code']==code);v=float(w[hit].sum());photo.append(dict(site=site,prior=prior,kind=kind,condition=label,photo_code=code,count=int(hit.sum()),area_m2=v,row_area_m2=den,row_fraction=v/den if den else None,source=source))
      if prior=='LoD2':
       m=d['kind']==2
       for length in [5,10]:
        n=d['n5'] if length==5 else d['n10'];delta=d['d_m'] if length==5 else d['d10_m'];free=d['free5'] if length==5 else d['free10'];obs=n>=4
        pg=abs(d['prior_height_m']-d['gt_p'])<=d['tau_m'];mg=abs(delta+d['prior_height_m']-d['gt_p'])<=d['tau_m'];truth=(d['gt_status']==0)&np.isfinite(d['gt_p'])
        for label,hit in [('missing',(n<4)&~free),('free_space',(n<4)&free),('outside',obs&(abs(delta)>d['L_m'])),('cell1',obs&truth&~pg&mg),('cell2',obs&truth&pg&~mg)]:
          hit=hit&m;walls.append(dict(site=site,prior=prior,half_length_m=length,category=label,count=int(hit.sum()),area_m2=float(d['area'][hit].sum()),source=source))
    for name,rows in [('table7_1',rates),('section6_3_regions_by_truth',cross),('section6_3_B173_ALS_cell2',split),('section6_3_prior_weight',weights),('section6_3_prior_weight_histogram',hist),('section6_3_r8_cross',r8cross),('scope',scope),('limits',limits),('five_percent_check',five),('photo_by_truth',photo),('wall_5m_10m',walls)]:write_table(name,rows)
    dump(O/'timing/tables.json',dict(at=now(),seconds=time.monotonic()-start,scientific_verdict=None));print('TABLES_COMPLETE',len(rates),flush=True)
if __name__=='__main__':main()
