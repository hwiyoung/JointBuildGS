"""Redraw frozen region judgments with readable boundaries; display-only."""
import hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager,patheffects
from matplotlib.patches import Polygon

root=Path('/run');output=Path('/output')
font_manager.fontManager.addfont('/font.ttf')
plt.rcParams['font.family']=font_manager.FontProperties(fname='/font.ttf').get_name()
palette=['#9a9da3','#2787ba','#e6a01a','#9a59b5','#477b55']
names=['판단 유보','보존 후보','보정 가설','보완 후보','비대상 후보']
theta=np.deg2rad(70);basis=np.array([[np.cos(theta),np.sin(theta)],[np.sin(theta),-np.cos(theta)]])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
records=[]
for region in ['R2','R3','R4','R5']:
    inputs=[root/region/'review_zones.json',root/region/'audit/result/surface_evidence.npz',root/region/'review/judgments.npz']
    cfg=json.loads(inputs[0].read_text());ev=np.load(inputs[1]);j=np.load(inputs[2])['mvs_judgment'];zones=cfg['zones']
    uv=ev['mvs_xyz'][:,:2]@basis.T;bounds=np.array(zones[0]['polygon']);lo=bounds.min(0);hi=bounds.max(0)
    ratio=(hi[1]-lo[1])/(hi[0]-lo[0]);tall=ratio>1.3
    fig,axs=plt.subplots(1 if tall else 2,2 if tall else 1,
        figsize=(15,15*ratio/2+2.5) if tall else (15,30*ratio+3),layout='constrained')
    axs=np.ravel(axs)
    axs[0].scatter(uv[:,0],uv[:,1],s=5,c=ev['mvs_rgb']/255,alpha=.75,rasterized=True)
    axs[0].set_title(region+' 객체별 검토 구역 · 굵은 청록선과 Z 라벨',fontsize=18,pad=15)
    for k in [0,4,3,1,2]:
        m=j==k;axs[1].scatter(uv[m,0],uv[m,1],s=5,c=palette[k],label=names[k],rasterized=True)
    axs[1].set_title('국소 표면별 판단 초안 · Z 박스 전체의 단일 판정이 아님',fontsize=17,pad=15)
    for ax in axs:
        for z in zones[1:]:
            polygon=np.array(z['polygon'])
            patch=Polygon(polygon,closed=True,facecolor='none',
                          edgecolor='#087884',linewidth=2.5,zorder=5)
            patch.set_path_effects([patheffects.Stroke(linewidth=5,foreground='white',alpha=.95),patheffects.Normal()]);ax.add_patch(patch)
        for z in zones[1:]:
            p=np.array(z['polygon']);ax.text(*p.mean(0),z['id'],fontsize=16,fontweight='bold',ha='center',va='center',color='#07464f',zorder=10,
                bbox=dict(boxstyle='round,pad=.23',facecolor='white',edgecolor='#087884',linewidth=1.7,alpha=.98))
        ax.set_xlim(lo[0],hi[0]);ax.set_ylim(hi[1],lo[1]);ax.set_aspect('equal');ax.set_xlabel('객체축 u [m]',fontsize=12);ax.set_ylabel('객체축 v [m]',fontsize=12)
    axs[1].legend(loc='upper center',bbox_to_anchor=(.5,-.08),ncol=2 if tall else 5,fontsize=12,markerscale=3,frameon=True)
    fig.suptitle(region+' · 구역 경계는 청록색 / 표면 판단은 아래 범례\nZ00은 나머지 경계·혼합 영역 · 입력 근거에 따른 후보이며 정확성 정답이 아님',fontsize=17)
    out=output/region;out.mkdir();image=out/'whole_area_judgment_v3.png';fig.savefig(image,dpi=160,bbox_inches='tight');plt.close(fig)
    receipt=dict(status='PASS_DISPLAY_ONLY',region=region,scientific_verdict=None,
        input_sha256={str(p):sha(p) for p in inputs},output_sha256=sha(image),
        zones=len(zones),judgment_counts=[int((j==k).sum()) for k in range(5)],
        changed='Layout, border contrast, label size, legend only',zoning_changed=False,masks_changed=False)
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2));records.append(receipt)
(output/'receipt.json').write_text(json.dumps(dict(status='PASS_DISPLAY_ONLY',regions=records,scientific_verdict=None),indent=2))
print(json.dumps({r['region']:r['zones'] for r in records}))
