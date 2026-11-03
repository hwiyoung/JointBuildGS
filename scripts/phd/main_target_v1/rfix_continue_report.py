"""Endpoint tables and scientific figures, without scientific interpretation."""
import csv,math
import numpy as np
from scipy.spatial import cKDTree
from common import *
from report_stage0 import plt
ROOT=OUT/'rfix_continue';E=ROOT/'endpoint';D=DOC/'rfix_continue';F=D/'figures';T=D/'tables'
def read(p):return json.loads(Path(p).read_text())
def save(fig,name,title,values):
 F.mkdir(parents=True,exist_ok=True);fig.suptitle(title,fontsize=13);fig.tight_layout(rect=(0,0,1,.95))
 for ext in ['png','pdf']:fig.savefig(F/(name+'.'+ext),dpi=180,bbox_inches='tight')
 plt.close(fig);dump(F/(name+'.json'),dict(at=stamp(),title=title,values=values,scientific_verdict=None))
def table(name,rows):
 T.mkdir(exist_ok=True,parents=True);dump(T/(name+'.json'),dict(rows=rows,scientific_verdict=None));keys=list(dict.fromkeys(k for r in rows for k in r))
 with (T/(name+'.csv')).open('w',newline='') as f:w=csv.DictWriter(f,keys);w.writeheader();w.writerows(rows)
 lines=['| '+' | '.join(keys)+' |','|'+'---|'*len(keys)]
 for r in rows:lines.append('| '+' | '.join('—' if r.get(k) is None else f'{r[k]:.6g}' if isinstance(r[k],float) else str(r.get(k,'')) for k in keys)+' |')
 (T/(name+'.md')).write_text('\n'.join(lines)+'\n')
def jl(p):return [json.loads(s) for s in p.read_text().splitlines()] if p.exists() else []
def main():
 D.mkdir(exist_ok=True,parents=True);cfg=read(CFG/'rfix_endpoint.json');it=cfg['state']['iteration'];model=ROOT/'runs/r8_LoD2_rfix/model';stop=read(ROOT/'STOP_LoD2.json') if (ROOT/'STOP_LoD2.json').exists() else None;metrics=read(E/'scores/r8_LoD2_rfix/current/LoD2/values.json');ac=read(REPO/'configs/phd/main_axes71_v2/axes71_v2.json');labels={'all':'전체',**ac['cells']['ko'],**{k:v[0] for k,v in ac['cells']['sums'].items()}};rows=[]
 for cell,v in metrics['metrics'].items():
  surf=metrics['surface'][cell];g=v['gt'];r=v['res']['E'];rows.append(dict(cell=cell,label=labels.get(cell,cell),n_gt=g['n_gt'],n_result_E=r['n'],area_m2=surf['area_m2'],unscorable_area_m2=surf['unscorable_area_m2'],total_eval_area_m2=surf['area_m2']+surf['unscorable_area_m2'],R_tau=g.get('R_tau'),P_tau=r.get('P_tau'),gt_mean_cm=g.get('mean'),result_mean_cm=r.get('mean'),floating_fraction=surf['floating_fraction'],no_surface_fraction=surf['no_surface_fraction']))
 table('axes71',rows);rs=read(E/'scores/r8_LoD2_rfix/current/LoD2/result_vs_target.json')['rows'];table('result_vs_target',rs)
 fig,axes=plt.subplots(2,2,figsize=(16,9));xx=np.arange(len(rows))
 for ax,k,lab,scale in zip(axes.ravel(),['R_tau','P_tau','gt_mean_cm','result_mean_cm'],['참값 기준 R(τ), %','결과 기준 P(τ), %','참값 기준 평균 거리, cm','결과 기준 평균 거리, cm'],[100,100,1,1]):
  ax.bar(xx,[np.nan if r[k] is None else r[k]*scale for r in rows]);ax.set(xticks=xx,xticklabels=[r['label'] for r in rows],ylabel=lab);ax.tick_params(axis='x',rotation=55,labelsize=7)
  if scale==100:ax.set_ylim(0,100)
 save(fig,'axes71',f'r8 LoD2 rfix {it:,}회 · 지금 채점 메시',rows)
 fig,axes=plt.subplots(1,2,figsize=(15,5))
 for ax,k,title in zip(axes,['floating_fraction','no_surface_fraction'],['뜬 면 (%)','면 없음 (%)']):ax.bar(xx,[np.nan if r[k] is None else r[k]*100 for r in rows]);ax.set(xticks=xx,xticklabels=[r['label'] for r in rows],ylabel=title);ax.tick_params(axis='x',rotation=55,labelsize=7)
 save(fig,'surface',f'r8 LoD2 rfix {it:,}회 · 참값 칸별 넓이',rows)
 fig,axes=plt.subplots(1,3,figsize=(15,4));names={0:'관측 없음',5:'사라짐',1:'일치',2:'보존',3:'보정'}
 for ax,kind in zip(axes,['all','original','replaced']):
  q=[r for r in rs if r['replacement']==kind];x=np.arange(len(q))
  for dx,key,label in [(-.18,'target_within_tau_fraction','목표 자체'),(.18,'result_within_tau_fraction','결과')]:ax.bar(x+dx,[np.nan if v[key] is None else v[key]*100 for v in q],width=.36,label=label)
  ax.set(title=kind,xticks=x,xticklabels=[names[r['region']] for r in q],ylim=(0,100),ylabel='τ 안 넓이 (%)');ax.legend()
 save(fig,'result_vs_target','판단 영역별 목표 자체와 결과',rs)
 traces=[];states=read(CFG/'rfix.json')['states']
 for key,name in [('base_LoD2_30000','기준선 LoD2'),('r7_LoD2_30000','r7 LoD2'),('r8_ALS_30000','r8 항공 LiDAR')]:
  row=next(r for r in states if r['key']==key);curve=jl(Path(row['model'])/'jbgs_trace.jsonl');traces.append(dict(label=name,source=row['model'],rows=[dict(iteration=r['iteration'],gaussians=r['gaussians']) for r in curve]))
 curves=[]
 for m in [OUT/'r8/runs/tg_B173nb_b10_LoD2_s0_r8/model',OUT/'r8_recorded_continue/runs/tg_B173nb_b10_LoD2_s0_r8/model',model]:curves+=jl(m/'jbgs_trace.jsonl')
 # Earlier stopped attempt contains later records; keep only <=14030 before the new continuation.
 cur=[]
 for r in curves:
  if r['iteration']<=14030:cur.append(r)
 cur+=jl(model/'jbgs_trace.jsonl');by={r['iteration']:r['gaussians'] for r in cur};traces.append(dict(label='r8 LoD2 rfix',rows=[dict(iteration=k,gaussians=v) for k,v in sorted(by.items())]))
 fig,ax=plt.subplots(figsize=(10,5))
 for t in traces:ax.plot([r['iteration'] for r in t['rows']],[r['gaussians']/1e6 for r in t['rows']],label=t['label'])
 n6000=read(CFG/'rfix_continue.json')['count_at_6000'];ax.axhline(3*n6000/1e6,color='black',ls='--',label='r8 LoD2: 6,000회 수 × 3');ax.set(xlabel='반복',ylabel='가우시안 수 (백만)',xlim=(0,30000));ax.legend();save(fig,'gaussian_curves','같은 축의 가우시안 수',traces)
 perf=jl(model/'recording/rfix_100.jsonl');runtime_rows=[]
 for r in perf:
  record={k:r[k] for k in ['iteration','completed_in_block','block_seconds','seconds_per_iteration','sample_iteration_seconds','maximum_overlap','maximum_binning_bytes']};record.update(r['gpu']);record.update({'near30_'+k:v for k,v in r['near_camera30_counts'].items()});runtime_rows.append(record)
 table('runtime_100',runtime_rows);table('view_maxima_100',[dict(block_end=r['iteration'],**v) for r in perf for v in r['view_maxima']]);counts=[]
 for r in jl(model/'recording/after_iteration_100.jsonl'):
  a=np.asarray(r['counts']);a=np.stack([a[0],a[1],a[2]+a[3]])
  for tag_ in range(3):
   for x in range(4):
    for h in range(4):counts.append(dict(iteration=r['iteration'],provenance=['background','patch','released'][tag_],xy_bin=x,height_bin=h,gaussians=int(a[tag_,x,h])))
 table('counts_100',counts);fig,axes=plt.subplots(1,3,figsize=(14,4))
 for ax,key,title,scale in zip(axes,['seconds_per_iteration','maximum_overlap','maximum_binning_bytes'],['반복당 초','구간 최대 겹침 (백만)','구간 최대 정렬 버퍼 (GiB)'],[1,1e-6,1/2**30]):ax.plot([r['iteration'] for r in perf],[r[key]*scale for r in perf]);ax.set(xlabel='반복',ylabel=title)
 save(fig,'runtime_100','100회 구간별 시간과 부하',perf)
 gs=np.load(E/'gaussians.npz');xyz=gs['xyz'];snap=np.load(cfg['state']['snapshot']);tag=snap['target_tag'];assert len(xyz)==len(tag)
 views=set(read(CFG/'rfix.json')['views']);cameras=[v for v in read(model/'cameras.json') if v['img_name'] in views];assert len(cameras)==203;centres=np.array([v['position'] for v in cameras]);dist=cKDTree(centres).query(xyz,workers=4)[0];near=dist<=30;rad=gs['max_radius'];con=gs['total_contribution'];step=max(1,math.ceil(len(xyz)/200000));ids=np.arange(0,len(xyz),step);fig,ax=plt.subplots(figsize=(9,6))
 for mask,color,label in [(~near,'#628cb4','카메라 30 m 밖'),(near,'#d78c32','카메라 30 m 안')]:
  use=ids[mask[ids]];ax.scatter(np.maximum(rad[use],.1),np.maximum(con[use],1e-12),s=.4,alpha=.3,c=color,label=label)
 ax.set(xscale='log',yscale='log',xlabel='203장 중 화면 반지름 최댓값 (px)',ylabel='203장 총 색 기여 Σ(alpha×T)');ax.legend(markerscale=5);save(fig,'radius_contribution','화면 반지름과 실제 색 기여',dict(source=str(E/'gaussians.npz'),gaussians=len(xyz),plot_stride=step,zero_radius_display=.1,zero_contribution_display=1e-12,near_camera30=int(near.sum())))
 basis=np.asarray(read(OUT/'r8_lod2_cause/boundaries.json')['basis']);bounds=read(OUT/'r8_lod2_cause/boundaries.json');lo,hi=np.array(bounds['lo']),np.array(bounds['hi']);uv=np.array([[lo[0],lo[1]],[hi[0],lo[1]],[hi[0],hi[1]],[lo[0],hi[1]],[lo[0],lo[1]]]);poly=uv@basis;fig,axes=plt.subplots(1,3,figsize=(16,5))
 for ax,t,color,label in zip(axes,[0,1,2],['#57a3a4','#a55783','#d99834'],['배경','패치','풀림']):
  take=ids[tag[ids]==t];ax.scatter(xyz[take,0],xyz[take,1],s=.25,c=color,alpha=.45);ax.scatter(centres[:,0],centres[:,1],s=5,c='black',marker='^');ax.plot(poly[:,0],poly[:,1],c='red');ax.set(title=f'{label}: {int((tag==t).sum()):,}',xlabel='지역 동쪽 (m)',ylabel='지역 북쪽 (m)',aspect='equal')
 save(fig,'origin_top','위에서 본 출신과 카메라·평가 상자',dict(snapshot=cfg['state']['snapshot'],plot_stride=step,counts={str(t):int((tag==t).sum()) for t in [0,1,2]},camera_source=str(model/'cameras.json')))
 for suffix in ['0020','0109']:
  name={'0020':'DJI_20241217102535_0020_D','0109':'DJI_20241217091133_0109_D'}[suffix];old=np.load(OUT/'screen_sim/states/r8_LoD2_stop/before'/(name+'_float.npz'));new=np.load(E/'states/r8_LoD2_rfix/current'/(name+'_float.npz'));fig,axes=plt.subplots(1,3,figsize=(15,4.5))
  for ax,a,title in zip(axes,[new['gt'],old['rgb'],new['rgb']],['사진','r8 LoD2 14,030회',f'rfix {it:,}회']):ax.imshow(np.clip(a.transpose(1,2,0),0,1));ax.set_title(title);ax.axis('off')
  save(fig,'render_'+suffix,name,dict(camera=name,range=[0,1],iteration=it))
 rep=next(r for r in read(CFG/'representatives_v1.json')['rows'] if r['id']==1);t=np.load(OUT/'r7/targets/B173nb_b10_LoD2.npz');ev=np.load(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2/B173nb_b10__LoD2/evaluation.npz');a,b=np.array(rep['start']),np.array(rep['end']);direction=(b-a)/np.linalg.norm(b-a);length=np.linalg.norm(b-a);q=t['centre'][:,:2]-a;dd=q@direction;off=abs(q[:,0]*direction[1]-q[:,1]*direction[0]);sel=(dd>=0)&(dd<=length)&(off<=rep['half_width']);roof=sel&(t['kind']==1)&ev['scoring_allowed'];limits=read(DOC/'figures/r6_LoD2_section_comparison.json')['values']['height_limits_m'];gt=t['centre'][:,2]+ev['p_gt']*t['normal'][:,2];fig,axes=plt.subplots(1,3,figsize=(16,4.7));paths=[OUT/'screen_sim/scores/base_LoD2_30000/before/LoD2/patch_z.npz',OUT/'screen_sim/scores/r7_LoD2_30000/before/LoD2/patch_z.npz',E/'scores/r8_LoD2_rfix/current/LoD2/patch_z.npz']
 for ax,p,title in zip(axes,paths,['기준선 LoD2 30,000회','r7 LoD2 30,000회',f'rfix {it:,}회']):
  z=np.load(p);h=t['centre'][:,2]+z['z']*t['normal'][:,2];ok=roof&np.isfinite(h);ax.scatter(dd[roof],gt[roof],s=5,c='black',label='참값');ax.scatter(dd[sel],t['centre'][sel,2],s=3,c='#e6ab42',label='사전');ax.errorbar(dd[roof],t['target'][roof,2],yerr=1.96*t['sigma'][roof]*abs(t['normal'][roof,2]),fmt='.',ms=1,c='gray',alpha=.25,label='목표 폭');ax.scatter(dd[ok],h[ok],s=5,c='#438bb6',label='결과');ax.set(title=title,ylim=limits,xlim=(0,length),xlabel='고정 단면 거리(m)');ax.legend(fontsize=6)
 save(fig,'section','B173 날개 고정 단면',dict(section=rep,height_limits_m=limits,sources=list(map(str,paths))))
 add=read(OUT/'rfix_addends/result.json');table('addends',add['states']);allrow=rows[0]
 lines=['# r8 LoD2 렌더러 교체 이어 학습 결과','',f"상태: {cfg['status']}. 완료 반복: {it:,}. scientific_verdict: null.",'','[진행 설정과 사용자 기준 변경](진행.md) · [실행 예외](실행예외.md)','']
 if stop:lines +=[f"중단 사유: `{stop['error']}`. 가우시안 {stop['gaussians']:,}개 / 6,000회 {n6000:,}개 = {stop['gaussians']/n6000:.6f}배. 완전 상태와 PLY를 저장했다. 자동 재개하지 않았다.",'']
 lines +=['| 전체 지금 메시 | 값 |','|---|---:|']+[f'| {k} | {v} |' for k,v in allrow.items() if k not in ['cell','label']]
 first=next(v for v in perf[0]['view_maxima'] if v['iteration']==14031);lines +=['',f"재개 첫 영상은 {first['camera']}이며 겹침 {first['overlaps']:,}개, 정렬 버퍼 {first['binning_bytes']:,}바이트였다. 같은 14,030회 상태의 사전 점검과 일치한다."]
 lines +=['','12칸·세 합계·전체의 점 수, 넓이와 모든 값은 [채점 표](tables/axes71.md), 판단 영역별 원값·대체값 비교는 [목표와 결과 표](tables/result_vs_target.md)에 있다.','',f"추가 입력항 검사는 {add['total_rows']}개 행 모두 바이트 단위 일치다. 상대 L2 재판정은 이전 1,680개 비교 모두 1e-4 이내다. 이전 판정은 삭제하지 않았다.",'','현재 학습 빌드는 ae90687632d7…이며 속도 개선 후보를 학습에 쓰지 않았다. 나머지 여섯 판은 시작하지 않았다.','']
 lines +=['[기록 정의](기록정의.md)','']
 lines +=['채점표의 area_m2는 표면 채점 가능 넓이, unscorable_area_m2는 같은 평가 칸의 표면 채점 제외 넓이, total_eval_area_m2는 두 넓이의 합이다. 뜬 면·면 없음 비율의 분모는 area_m2다. R·P의 점 모집단과 넓이 모집단은 원래 AXES71-v2 정의를 그대로 사용했다.','']
 lines +=['100회 구간의 반복당 시간은 해당 구간의 실제 경과 시간이다. 다시 붙이기·건강 검사·기록·정기 상태 저장과 해당 반복의 점검 렌더 시간을 포함한다. 첫 구간은 14,031~14,100회의 70회다.','']
 lines +=['산점도에서는 로그 축 표시를 위해 반지름 0을 0.1 px, 총 색 기여 0을 1e-12에 놓았다. 원래 배열과 교차표의 0은 그대로다.','']
 for name in ['gaussian_curves','runtime_100','axes71','surface','result_vs_target','radius_contribution','origin_top','render_0020','render_0109','section']:lines +=[f'![{name}](figures/{name}.png)','']
 (D/'보고서.md').write_text('\n'.join(lines)+'\n');dump(ROOT/'report_receipt.json',dict(at=stamp(),endpoint_iteration=it,figures=10,status='GENERATED',scientific_verdict=None));print('CONTINUE_REPORT_GENERATED',it)
if __name__=='__main__':main()
