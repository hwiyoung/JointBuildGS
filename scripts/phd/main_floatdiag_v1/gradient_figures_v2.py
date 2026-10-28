"""Readability revision: population counts in legends, never overlapping data."""
import json
import numpy as np
import matplotlib.pyplot as plt
from common import *
from build_visuals import save_figure,NAMES
for site in SITES:
    rows=json.loads((DOC/'tables'/f'gradients_{site}.json').read_text())['rows'];fig,axs=plt.subplots(1,2,figsize=(12,5))
    for ax,kind,label in zip(axs,['floating','roof'],['뜬 면 가우시안','지붕 면 가우시안']):
        for res,col in zip(RESULTS,config()['colours']['results']):
            r=next(x for x in rows if x['result']==res and x['case']=='전체' and x['kind']==kind)
            values=[r['photo_centre_gradient_median'],r['depth_centre_gradient_median']]
            ax.plot([0,1],[x if x and x>0 else np.nan for x in values],'o-',color=col,label=NAMES[res]+f" · N={r['count']:,}")
        ax.set(yscale='log',xticks=[0,1],xticklabels=['사진','깊이'],title=label,ylabel='중심 기울기 크기 중앙값')
        ax.grid(alpha=.2);ax.legend(fontsize=9)
    fig.suptitle(site+' · 모든 학습 사진에서 더한 중심 기울기',fontsize=15);fig.tight_layout()
    save_figure(fig,site+'_gradients_A2_v2',dict(site=site,rows=rows,revision='count labels moved to legend after visual QA; measurements unchanged',zero_handling='not plotted on log axis; retained in table'))
