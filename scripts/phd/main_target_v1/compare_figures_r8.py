"""Side-by-side GT-cell measurements with original AXES71-v2 comparison rows."""
import numpy as np
import sys
from common import *
from report_stage0 import plt,save

def read(p):return json.loads(p.read_text())
def val(v):return np.nan if v is None else v

def heat(rows,cells,field,scale,title,name,note):
 vals=np.array([[val(r['values'].get(c,{}).get(field))*scale for c in cells] for r in rows]);fig,ax=plt.subplots(figsize=(13,max(5,len(rows)*.35+2.8)));im=ax.imshow(vals,aspect='auto',cmap='Blues',vmin=0,vmax=100 if scale==100 else None)
 ax.set(xticks=np.arange(len(cells)),xticklabels=[LABELS.get(c,c) for c in cells],yticks=np.arange(len(rows)),yticklabels=[r['label'] for r in rows]);ax.tick_params(axis='x',rotation=45,labelsize=8);ax.tick_params(axis='y',labelsize=8)
 for i in range(len(rows)):
  for j in range(len(cells)):
   v=vals[i,j];ax.text(j,i,'—' if not np.isfinite(v) else f'{v:.1f}',ha='center',va='center',fontsize=7,color='white' if np.isfinite(v) and v>(100 if scale==100 else np.nanmax(vals))*.6 else '#222222')
 boundary=next((i for i,r in enumerate(rows) if r['source']=='AXES71-v2'),len(rows))
 if 0<boundary<len(rows):ax.axhline(boundary-.5,c='#222222',lw=1.5)
 fig.colorbar(im,ax=ax,fraction=.025,pad=.02);fig.subplots_adjust(top=.88,bottom=.24,left=.22,right=.94);save(fig,name,title,dict(rows=rows,cells=cells,field=field,scale=scale),note)

def main():
 global LABELS
 mode=sys.argv[1];assert mode in ['7000','final']
 cfg=read(CFG/'scoring_continue_r7.r1.json');ac=read(REPO/'configs/phd/main_axes71_v2/axes71_v2.json');LABELS={'all':'전체',**ac['cells']['ko']};cells=['all']+ac['cells']['order'];refroot=PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/tables';ref=read(refroot/'a3_metrics.json')['data'];cr=read(refroot/'a6_clumps.json')['data']['hit'];out=OUT/'r7_continue'
 cfg['rows'] = [r for r in cfg['rows']+read(CFG/'scoring_r8.json')['rows'] if mode=='final' or r['iteration']==7000]
 for prior in ['ALS','LoD2']:
  references=[];crefs=[]
  for method,b in ref[f'B173nb_b10/{prior}'].items():
   for name,cb in b['values'].items():
    vv={c:dict(R_tau=cb.get(c,{}).get('gt',{}).get('R_tau'),P_tau=cb.get(c,{}).get('res',{}).get('E',{}).get('P_tau'),gt_mean=cb.get(c,{}).get('gt',{}).get('mean'),res_mean=cb.get(c,{}).get('res',{}).get('E',{}).get('mean')) for c in cells}
    references.append(dict(label='참고 '+name,source='AXES71-v2',values=vv));cl=cr.get(f'B173nb_b10/{prior}',{}).get(method,{}).get(name,{});crefs.append(dict(label='참고 '+name,source='AXES71-v2',values={c:{th:cl.get(c,{}).get(th,{}).get('rate') for th in ['ge_2.5','ge_10']} for c in cells[1:]}))
  for kind in ['current','final']:
   rows=[];clrows=[];allfig=[]
   for r in cfg['rows']:
    if r['prior']!=prior:continue
    p=(OUT/'r8' if r['family']=='r8' else out)/'scoring'/r['key']/kind/'values.json';a=read(p) if p.exists() else {};label={'base':'기준선','r6':'r6','r7':'r7','r8':'r8'}[r['family']]+' '+f"{r['iteration']:,}회";vv={}
    for cell in cells:
     b=a.get('metrics',{}).get(cell,{});sur=a.get('surface',{}).get(cell,{})
     vv[cell]=dict(R_tau=b.get('gt',{}).get('R_tau'),P_tau=b.get('res',{}).get('E',{}).get('P_tau'),gt_mean=b.get('gt',{}).get('mean'),res_mean=b.get('res',{}).get('E',{}).get('mean'),floating=sur.get('floating_fraction'),missing=sur.get('no_surface_fraction'))
    rows.append(dict(label=label+('' if a else ' (채점 대기)' if (Path(r['model'])/f"point_cloud/iteration_{r['iteration']}/point_cloud.ply").exists() else ' (모델 없음)'),source='requested checkpoint',values=vv));clrows.append(dict(label=rows[-1]['label'],source='requested checkpoint',values={c:{th:a.get('clumps',{}).get(c,{}).get('hits',{}).get(th,{}).get('rate') for th in ['ge_2.5','ge_10']} for c in cells[1:]}))
   for field,title,scale in [('R_tau','참값 기준 R(τ), %',100),('P_tau','결과 기준 P(τ), %',100),('gt_mean','참값 기준 평균 거리, cm',1),('res_mean','결과 기준 평균 거리, cm',1)]:heat(rows+references,cells,field,scale,f'{prior} · {kind}: {title}',f'r8_compare_{mode}_{prior}_{kind}_{field}','위: 요청한 저장 시점별 메시 · 아래: AXES71-v2 원래 비교 값(가시/비가시 메시 규칙 유지) · —: 값 없음')
   for field,title in [('floating','뜬 면, %'),('missing','면 없음, %')]:heat(rows,cells,field,100,f'{prior} · {kind}: {title}',f'r8_compare_{mode}_{prior}_{kind}_{field}','각 메시의 참값 열두 칸 · 평가 가능한 넓이 가중 · —: 분모 또는 결과 없음')
   for th in ['ge_2.5','ge_10']:heat(clrows+crefs,cells[1:],th,100,f'{prior} · {kind}: {th[3:]} m² 이상 덩어리 달성률, %',f'r8_compare_{mode}_{prior}_{kind}_{th}','고정 덩어리 ID · 참값 점의 50% 초과가 τ 안 · 참고의 비가시 칸 등 원래 미제공 값은 —')
 print('COMPARISON_FIGURES_COMPLETE',flush=True)
if __name__=='__main__':main()
