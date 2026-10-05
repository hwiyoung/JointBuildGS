"""Read-only paired sky diagnostic on the previously reviewed R1 pixel sample."""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

cfg=json.loads(Path('/config.json').read_text())
out=Path('/output');out.mkdir(exist_ok=True)
x0,y0,x1,y1=cfg['rectangle'];threshold=cfg['tsdf_depth_trunc_m']
arrays={};rows={}
for name,filename in cfg['depths'].items():
    p=Path(filename)
    if p.suffix=='.npy':a=np.load(p)
    else:
        with Image.open(p) as im:a=np.asarray(im).copy()
    assert a.shape==(1013,1400)
    arrays[name]=a;s=a[y0:y1,x0:x1];valid=np.isfinite(s)&(s>0);v=s[valid]
    rows[name]=dict(pixels=int(s.size),finite_positive=int(valid.sum()),
        within_tsdf_depth_range=int((valid&(s<=threshold)).sum()),
        quantiles_m=np.quantile(v,[0,.1,.5,.9,1]).tolist() if len(v) else [],
        sha256=hashlib.sha256(p.read_bytes()).hexdigest())
with Image.open(cfg['rgb']) as im:rgb=np.asarray(im.convert('RGB'))
for p in cfg['render_gt']:
    with Image.open(p) as im:assert np.array_equal(rgb,np.asarray(im.convert('RGB')))
fig,axes=plt.subplots(2,3,figsize=(15,9),constrained_layout=True)
axes.flat[0].imshow(rgb);axes.flat[0].set_title('Original RGB / fixed sky diagnostic sample')
for ax,(name,a) in zip(list(axes.flat)[1:],arrays.items()):
    cmap=plt.get_cmap('viridis').copy();cmap.set_bad('#ededed')
    plot=ax.imshow(np.ma.masked_where(~np.isfinite(a)|(a<=0),a),cmap=cmap,vmin=0,vmax=240)
    ax.set_title(name)
for ax in axes.flat:
    ax.add_patch(Rectangle((x0,y0),x1-x0,y1-y0,fill=False,edgecolor='red',linewidth=1.2));ax.axis('off')
fig.colorbar(plot,ax=list(axes.flat),shrink=.65,label='Camera depth (m); gray = no valid input')
fig.suptitle('R1 same-view sky: inputs and Gaussian surface depth before TSDF\nDiagnostic pixels only; not a training mask or geometry ground truth')
fig.savefig(out/'R1_sky_comparison.png',dpi=120);plt.close(fig)
result=dict(status='PASS',scientific_verdict=None,config=cfg,statistics=rows,
            training_changed=False,meshes_changed=False,scope='One previously reviewed sky rectangle, same source camera and pixels')
(out/'receipt.json').write_text(json.dumps(result,indent=2,allow_nan=False))
print(json.dumps(rows))
