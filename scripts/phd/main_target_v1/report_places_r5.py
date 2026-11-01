"""Area distributions, complete comparison table, and non-holdout diagnostic sections."""
import numpy as np
from common import *
from report_stage0 import plt,save,csvout
from report_r5 import LABEL,SITES,pct,read,zload

def main():
 results=[read(p) for p in sorted((DOC/'tables').glob('places_r5_*.json'))];assert len(results)==12,len(results)
 rows=[r for d in results for r in d['rows']];csvout('places_r5_all',rows)
 text=['# 자리별 판단 점검 · r5','','단계 0의 잠근 판단 결과를 그대로 나누어 셌다. 작은 구조물 → 가장자리 → 유리·무늬 없음 → 그 밖 순서로 먼저 해당하는 자리를 썼다. 남은 그 밖에서 사진 곡선이 없는 곳은 사진 없음 행으로 분리하고, 다른 자리에도 사진 없음 넓이를 별도 열로 남겼다. 참값 칸은 분류에 쓰지 않았다. [이 발주에서 냄]','',
 'MVS 면 종류는 MESHPATCH의 `roofer_def` 면에 Track-A `elem_types.py` 규칙을 적용한 값이다. 개발용은 기존 패치 표와 정확한 패치 ID·기하로 연결했다. 확인용은 그 입력들만으로 같은 규칙을 계산했다. 실험 지역은 같은 규칙을 자체 입력에 적용하고, 기존 표와 정확히 연결되는 패치에는 기존 분류를 사용했다. 항공 LiDAR 실험 입력에는 건물 ID가 비어 있어 그 입력의 빈 그룹을 그대로 사용했으며, 임의 건물 ID를 만들지 않았다. 이 때문에 면을 나누는 입력 문맥이 전역 패치 표와 다른 부분은 별도 수로 기록했다.','',
 'B173만의 CPU 불확실도 파일에는 파생 z와 LoD2 사전 σ가 없어, 이미 잠근 동일 패치의 σ로 입력 z의 유한성만 복원했다. 분류 수치·문턱은 그대로다. B173 유리 채광창은 저장된 입력 면 자리 `place_skylight`를 썼고, 참값 칸으로 거른 `case_skylight`는 쓰지 않았다. 유리 띠·둥근 지붕은 UNCERT에 저장된 지역 패치 목록을 사용했다. 다른 단위로 연결할 때는 중심·법선·넓이·면 종류가 모두 같은 패치만 연결했다.','',
 '전체 표는 [CSV](tables/places_r5_all.csv)에 있다. 개발용·확인용·네 실험 지역, 사전 정보, 지붕·벽, 평가 범위·띠, 원값·대체를 나누고, 각 줄에 사전 정보만 믿음·영상만 믿음 비교를 함께 냈다. 넓이 비율의 분모는 해당 묶음의 같은 면 종류 전체 넓이다. 칸 2 보정은 T2 초과를 우선하고, T2 이하이면서 사진 반박인 보정을 별도 열로 세어 두 열이 겹치지 않게 했다. 두 증거가 모두 있는 넓이도 별도 열로 제공한다.','']
 for split,kor in [('development','개발용'),('holdout','확인용'),('experiment','실험 지역')]:
  text += [f'## {kor}','','| 지역 · 사전 · 면 | 자리 | 넓이 m² | 전체 대비 | 칸 2 m² | 칸 2 보정 m² | T2 / 사진 보정 m² | 칸 1 m² | 칸 1 보존 m² |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
  for r in rows:
   if r['split']!=split or r['variant']!='main' or r['replacement']!='all' or (split=='experiment' and r['scope']!='evaluation') or r['area_m2']==0:continue
   name=(SITES.get(r['site'],'전체')+' · '+r['prior']+' · '+('지붕' if r['kind']==1 else '벽'))
   text.append(f"| {name} | {LABEL[r['stratum']]} | {r['area_m2']:.2f} | {pct(r['share_of_kind_area'])} | {r['cell2_area_m2']:.2f} | {r['cell2_corrected_area_m2']:.2f} | {r['cell2_corrected_T2_area_m2']:.2f} / {r['cell2_corrected_photo_only_area_m2']:.2f} | {r['cell1_area_m2']:.2f} | {r['cell1_preserved_area_m2']:.2f} |")
  text+=['']
  ds=[d for d in results if d['split']==split]
  for label,ko in LABEL.items():
   fig,axs=plt.subplots(4 if split=='experiment' else 1,2,figsize=(12,11 if split=='experiment' else 4),squeeze=False)
   plotted=[]
   for ax,d in zip(axs.flat,sorted(ds,key=lambda d:(list(SITES).index(d['site']) if d['site'] in SITES else 0,d['prior']))):
    h=d['histogram'];bins=np.array(h['bins_log10']);sel=[r for r in h['rows'] if r['stratum']==label]
    for cell,color in [(1,'#4c8db7'),(2,'#d58b46')]:
     r=next(x for x in sel if x['cell']==cell);ax.stairs(r['area_bins'],bins,color=color,label=f'칸 {cell}',fill=True,alpha=.4)
    ticks=np.array([.05,.1,.2,.5,1,2,5,10]);ax.set_xticks(np.log10(ticks),[str(v) for v in ticks]);ax.set_xlim(-1.5,1.2);ax.set(xlabel='차이 |d| (m, 로그 눈금)',ylabel='넓이 (m²)',title=SITES.get(d['site'],kor)+' · '+d['prior']);ax.legend(fontsize=7)
    ax.set_ylim(bottom=0)
    if sum(sum(r['area_bins']) for r in sel)==0:
        ax.set_ylim(0,1);ax.text(.5,.5,'축 안 칸 1·2 자료 없음',transform=ax.transAxes,ha='center',color='gray')
    plotted.append(dict(split=split,site=d['site'],prior=d['prior'],rows=sel))
   fig.subplots_adjust(top=.90 if split=='experiment' else .8,bottom=.10 if split=='experiment' else .22,hspace=.6,wspace=.25)
   save(fig,f'r5_places_{split}_{label}',f'{kor} · {ko}: 같은 가로축에서 칸 1과 칸 2의 차이 분포를 비교했다',plotted,'r1_T2와 같은 가로축 · 0·결측·축 밖 넓이는 JSON에 별도 기록 · 실험 지역은 평가 범위만')
   text += [f'![{kor} {ko} 차이 분포](figures/r5_places_{split}_{label}.png)','']
 # Select representatives without opening any holdout details.
 sources=[]
 for site in SITES:
  for p in ['ALS','LoD2']:sources.append(('experiment',site,p,OUT/'r5/places'/f'{site}_{p}'))
 for p in ['ALS','LoD2']:sources.append(('development','all',p,OUT/'r5/places'/f'development_{p}'))
 reps=[];text += ['## 칸 2를 보정한 대표 단면','','실험 지역을 먼저, 없으면 개발용에서 찾았다. 해당 자리의 칸 2·보정 패치 중 넓이가 가장 큰 패치를 고르고, 동률이면 고정된 파일·행 순서를 따랐다. 이 선택은 점검 그림에만 쓰며 판단 규칙을 바꾸지 않는다. 확인용 패치 상세는 열거나 그림에 넣지 않았다.','']
 for category,(label,ko) in enumerate(LABEL.items()):
  candidates=[]
  for order,(split,site,prior,root) in enumerate(sources):
   d=zload(root/'strata.npz');m=(d['place']==category)&(d['cell']==2)&(d['region']==3)
   if split=='experiment':
    with np.load(OUT/'r2/targets'/f'{site}_{prior}.npz') as z:m&=z['in_eval']
   if m.any():
    ids=np.flatnonzero(m);q=ids[np.argmax(d['area'][ids])];candidates.append((0 if split=='experiment' else 1,-d['area'][q],order,int(q),split,site,prior,root))
  if not candidates:
   reps.append(dict(stratum=label,status='unavailable',reason='no corrected cell2 patch in experimental or development inputs'));text += [f'{ko}: 칸 2 보정 대표 후보 없음(확인 불가).',''];continue
  _,_,_,q,split,site,prior,root=min(candidates);d=zload(root/'strata.npz');point=d['centre'][q];normal=d['normal'][q];normal=normal/np.linalg.norm(normal)
  ref=np.array([0.,0.,1.]) if abs(normal[2])<.9 else np.array([0.,1.,0.]);along=np.cross(normal,ref);along/=np.linalg.norm(along);across=np.cross(normal,along)
  delta=d['centre']-point;x=delta@along;off=delta@across;near=(abs(x)<=6)&(abs(off)<=.6)&(abs(delta@normal)<=8)&(abs(d['normal']@normal)>.9)
  base=delta@normal;factor=d['normal']@normal;ys={'사전 정보':base,'MVS':base+d['d']*factor,'참값':base+d['gt_offset']*factor,'목표':base+d['h']*factor}
  fig,axes=plt.subplots(1,2,figsize=(12,4.5))
  for ax in axes:
   for name,color in [('사전 정보','#d6a340'),('MVS','#478bb8'),('참값','#222222')]:ax.scatter(x[near],ys[name][near],s=8,c=color,label=name)
   ax.errorbar(x[near],ys['목표'][near],yerr=1.96*d['sigma'][near]*abs(factor[near]),fmt='.',ms=2,c='#ae497f',alpha=.45,label='목표 ±1.96σ')
   ax.axvline(0,c='gray',ls=':',lw=1);ax.set(xlabel='면 접선 방향 거리 (m)',ylabel='대표 패치 법선 방향 거리 (m)');ax.legend(fontsize=7,loc='upper right')
  axes[0].set_title('전체 12 m 단면');axes[0].set_xlim(-6,6);axes[1].set_title('선택한 칸 2 보정 패치 주변');axes[1].set_xlim(-1.5,1.5)
  centre_values=np.array([v[q] for v in ys.values()]);finite=centre_values[np.isfinite(centre_values)];axes[1].set_ylim(finite.min()-.5,finite.max()+.5)
  fig.subplots_adjust(top=.8,bottom=.2,wspace=.25)
  record=dict(stratum=label,status='available',split=split,site=site,prior=prior,patch_row=q,centre=point.tolist(),patch_area_m2=float(d['area'][q]),cell=2,region=3,section_patches=int(near.sum()),half_width_m=.6,length_m=12,truth_used_only_for_counting_and_figure_selection=True)
  reps.append(record);save(fig,f'r5_place_section_{label}',f'{ko}: 칸 2에서 보정한 대표 단면 · {SITES.get(site,split)} {prior}',record,'점검 사례이며 개선을 뜻하지 않음 · 같은 방향의 면 표본 · 참값·MVS·사전 정보·목표를 함께 표시')
  text += [f'![{ko} 대표 단면](figures/r5_place_section_{label}.png)','']
 dump(DOC/'tables/place_sections_r5.json',dict(rows=reps,scientific_verdict=None))
 text += ['## 손으로 표시한 유리 자리의 연결','','원래 지역 파일의 저장 목록을 우선했다. B173만 등 다른 단위에 정확히 같은 패치가 없으면 유리 소속을 옮겨 쓰지 않았다. 다음 표의 확인 불가는 그 단위의 수동 유리 소속만을 뜻하며, 사진의 무늬 없음 분류는 별도로 남는다.','', '| 지역 | 사전 | 수동 자리 | 상태 | 연결 패치 |','|---|---|---|---|---:|']
 for d in results:
  if d['split']!='experiment':continue
  for k,v in d['manual_glass'].items():
   if isinstance(v,dict) and 'status' in v:text.append(f"| {SITES[d['site']]} | {d['prior']} | {k} | {v['status']} | {v.get('matched_patches',0)} |")
 text += ['','확인용의 공개 출력은 집계 수·넓이·비율과 분포의 구간 넓이뿐이다. 패치 ID·좌표·개별 판단은 전용 holdout 경로에 남겼다. scientific_verdict: null.','']
 (DOC/'자리별_판단점검_r5.md').write_text('\n'.join(text).rstrip()+'\n');print('PLACE_REPORT_DONE',len(rows),flush=True)
if __name__=='__main__':main()
