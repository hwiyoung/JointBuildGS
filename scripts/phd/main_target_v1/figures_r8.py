"""Scientific figures from saved measurements, fixed labels and no interpretation."""
import sys
import numpy as np
from common import *
from report_stage0 import plt,save
A=json.loads((REPO/'configs/phd/main_axes71_v2/axes71_v2.json').read_text());CELLS=A['cells']['order'];LABELS=[A['cells']['ko'][k] for k in CELLS]
def fnum(x):return np.nan if x is None else x

def one(key,kind):
 p=OUT/'r8/scoring'/key/kind/'values.json';r=json.loads(p.read_text());assert r['status']=='PASS';x=np.arange(len(CELLS));fig,axes=plt.subplots(3,2,figsize=(16,12));spec=[('참값 기준 R(τ), %','gt','R_tau',100),('결과 기준 P(τ), %','res','P_tau',100),('참값 기준 평균 거리, cm','gt','mean',1),('결과 기준 평균 거리, cm','res','mean',1),('뜬 면, %','surface','floating_fraction',100),('면 없음, %','surface','no_surface_fraction',100)]
 for ax,(title,side,field,scale) in zip(axes.flat,spec):
  vals=[]
  for cell in CELLS:
   block=r['surface'][cell] if side=='surface' else (r['metrics'][cell]['gt'] if side=='gt' else r['metrics'][cell]['res']['E']);vals.append(fnum(block.get(field))*scale)
  ax.bar(x,vals,color='#427eaa');ax.set(xticks=x,xticklabels=LABELS,title=title);ax.tick_params(axis='x',rotation=60,labelsize=7);ax.grid(axis='y',alpha=.2)
  if scale==100:ax.set_ylim(0,100)
 fig.subplots_adjust(top=.92,bottom=.12,hspace=.8,wspace=.24);save(fig,f'r8_{key}_{kind}_cells',f'{key} · {"최종 메시" if kind=="final" else "지금 채점 메시"}: 참값 열두 칸',dict(metrics=r['metrics'],surface=r['surface'],source_sha256=sha(p)),'빈 막대: 참값/채점 범위 없음 · P와 결과 평균은 AXES71-v2 셈 마 · 거리는 자르지 않은 평균')
 fig,axes=plt.subplots(2,3,figsize=(15,8));lines=list(r['axes']);colors=['#438bb6','#a94e83']
 for ax,line in zip(axes.flat,lines):
  values=r['axes'][line];xx=list(values);axis_name=line if line.startswith('axis1') else 'axis2';edges=A['axes'][axis_name]['edges'];labels={str(i):str(edges[i])+'~'+('' if edges[i+1]=='inf' else str(edges[i+1])) for i in range(len(edges)-1)};labels['99']='한 점';title={'axis1_tau':'축 1: 사전 정보 어긋남 / τ','axis1_m':'축 1: 사전 정보 어긋남 (m)','axis2_keep':'축 2: 지킴','axis2_limit':'축 2: 놓음','axis2_mask':'축 2: 거름'}[line];ax.plot(range(len(xx)),[fnum(values[i]['R_tau'])*100 for i in xx],'-o',label='R(τ)',color=colors[0]);ax.plot(range(len(xx)),[fnum(values[i]['P_tau'])*100 for i in xx],'-s',label='P(τ)',color=colors[1]);ax.set(xticks=range(len(xx)),xticklabels=[labels[i] for i in xx],title=title,ylim=(0,100),ylabel='%');ax.legend(fontsize=8);ax.grid(alpha=.2)
 axes.flat[-1].axis('off');fig.subplots_adjust(top=.88,bottom=.15,hspace=.35,wspace=.25);save(fig,f'r8_{key}_{kind}_axes',f'{key} · {kind}: AXES71-v2 두 축 곡선',dict(axes=r['axes'],bins=A['axes'],source_sha256=sha(p)),'구간 번호와 경계는 JSON에 보존 · 참값 열두 칸에서 정한 기존 축을 그대로 사용')
 fig,axes=plt.subplots(1,2,figsize=(14,5));vals=[]
 for ax,threshold in zip(axes,['ge_2.5','ge_10']):
  yy=[fnum(r['clumps'][c]['hits'][threshold]['rate'])*100 for c in CELLS];ax.bar(x,yy,color='#528a74');ax.set(xticks=x,xticklabels=LABELS,ylim=(0,100),ylabel='달성 덩어리, %',title=threshold.replace('ge_','')+' m² 이상');ax.tick_params(axis='x',rotation=60,labelsize=7)
 fig.subplots_adjust(top=.83,bottom=.3,wspace=.2);save(fig,f'r8_{key}_{kind}_clumps',f'{key} · {kind}: 덩어리 단위',dict(clumps=r['clumps'],source_sha256=sha(p)),'기존 덩어리 ID 유지 · 참값 점의 50%를 넘게 τ 안인 덩어리 · 없는 분모는 빈칸')

if __name__=='__main__':one(*sys.argv[1:3])
