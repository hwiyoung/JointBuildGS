"""Display fixed P1 roof cohorts and matched UAS/top-surface profiles."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

assert Path('/.dockerenv').exists()
p=Path('/payload');out=Path('/out');cfg=json.loads((out/'config.json').read_text())
a=np.load(out/'P1_paired_surface.npz');x=a['reference_points'];roof=a['roi_roof_strip']
binding=json.loads((p/cfg['global_root']/'inputs_v2/P1/bindings.json').read_text());c=binding['train'][0]
assert c['name']=='DJI_20241217084553_0100_D.JPG'
xc=x@np.array(c['R']).T+np.array(c['t']);uvh=xc@np.array(c['K']).T;uv=uvh[:,:2]/uvh[:,2:]
fig,axes=plt.subplots(2,2,figsize=(13,10),constrained_layout=True)
axes[0,0].imshow(Image.open(p/cfg['viewer']/'p1_weights_v1/images'/c['name']))
for key,color in [('roof_tip_west','#dc2626'),('roof_middle','#d97706'),('roof_tip_east','#2563eb')]:
    s=a['roi_'+key];sel=np.flatnonzero(s)[::6];axes[0,0].scatter(uv[sel,0],uv[sel,1],s=1,color=color,label=key)
    axes[0,1].scatter(x[sel,0],x[sel,1],s=1,color=color,label=key)
axes[0,0].set_title('P1 0100_D: exact evaluation cohorts');axes[0,0].axis('off')
axes[0,1].set_title('Same roof points / local metric coordinates');axes[0,1].set_aspect('equal');axes[0,1].legend(fontsize=8)
roles=[('global_0005','#ef4444','Global / prior .0005'),('regional_0005','#2563eb','Regional / prior .0005'),('regional_005','#16a34a','Regional / prior .005')]
for ax,y0 in zip(axes[1:,:].ravel(),[6.5,8.]):
    s=roof&(np.abs(x[:,1]-y0)<.15);order=np.flatnonzero(s);order=order[np.argsort(x[order,0])]
    ax.scatter(x[order,0],x[order,2],s=8,color='black',label='Current UAS')
    for role,color,label in roles:
        z=x[order,2]+a[role+'_top_z_error'][order];finite=np.isfinite(z)
        ax.scatter(x[order[finite],0],z[finite],s=4,color=color,label=label)
    ax.set(xlim=(-11,7),ylim=(-44,-32),xlabel='X (m)',ylabel='Top surface Z (m)',title=f'Section Y={y0} +/-0.15m; vertical first-hit surface')
    ax.grid(alpha=.3);ax.legend(fontsize=7)
fig.savefig(out/'P1_roof_scope_profiles.png',dpi=160);plt.close(fig)
