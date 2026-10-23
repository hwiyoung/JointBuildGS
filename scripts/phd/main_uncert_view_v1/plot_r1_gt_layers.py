import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
fm.fontManager.addfont('/font/NotoSansCJK-Regular.ttc')
plt.rcParams['font.family']=fm.FontProperties(fname='/font/NotoSansCJK-Regular.ttc').get_name()
plt.rcParams['axes.unicode_minus']=False
z=np.load('/audit/three_m_patch_82749.npz');t=z['t'];sel=z['selected']
fig,ax=plt.subplots(figsize=(10,4.4));bins=np.arange(-.2,4.11,.1)
ax.hist([t[~sel],t[sel]],bins=bins,stacked=True,color=['#7d919e','#168b91'],label=['선택하지 않은 참값','계산에 사용한 참값'])
ax.axvline(0,color='#d57b1b',lw=2,label='prior 면: 0 m')
ax.axvspan(3.0,3.3,color='#168b91',alpha=.12,label='처음 조건을 충족한 30 cm 층')
ax.axvline(np.median(t[sel]),color='#117278',ls='--',lw=1.7)
ax.annotate('prior 부근: 409점\n중앙값 +0.042 m\n계산에서 제외됨',xy=(.04,115),xytext=(.55,160),arrowprops={'arrowstyle':'->','color':'#566775'},fontsize=10)
ax.text(2.32,133,'선택된 먼 층: 162점\n중앙값 +3.128 m',fontsize=10,color='#11676c')
ax.set(xlabel='prior 법선 방향 거리 (m)',ylabel='참값 점 개수',title='R1 · LoD2 L22 · 패치 82749: 여러 층 중 바깥층을 선택한 사례',xlim=(-.25,4.2),ylim=(0,float(np.histogram(t,bins)[0].max())*1.15))
ax.legend(loc='upper right',fontsize=8);ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15)
fig.text(.12,.015,'원본 GT 586점 · 먼 쪽 30 cm 층 118점 ≥ 전체의 20% (117.2점) → 그 주변 ±1 m 선택',fontsize=9,color='#596a72')
fig.tight_layout(rect=(0,.055,1,1));fig.savefig('/audit/three_m_layer_selection.png',dpi=180)
