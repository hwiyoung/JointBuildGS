"""Plot exact served geometry vertices in Z06; diagnostic display, no re-input."""
import json
import hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

cfg=json.loads(Path('/out/plot_config.json').read_text());root=Path(cfg['root']);r1=Path(cfg['r1run'])
manifest=json.loads((root/'viewer/data/manifest.json').read_text());region=next(r for r in manifest['regions'] if r['id']=='R1_Z06')
entries={c['id']:c for c in region['candidates']}
def array(d):
    u=d['url'];p=r1/'viewer/data'/u.removeprefix('/data/r1legacy/') if u.startswith('/data/r1legacy/') else root/'viewer/data'/u.removeprefix('/data/')
    assert hashlib.sha256(p.read_bytes()).hexdigest()==d['sha256']
    return np.fromfile(p,dtype=d['dtype']).reshape(d['shape'])
items=[('mvs','MVS input','points'),('anchor_mesh','Anchor 8k / TSDF','mesh'),
       ('refinement_mesh','MVS GeoGS / TSDF','mesh'),('local_prior0_mesh','Local prior 0 / TSDF','mesh')]
fig,axes=plt.subplots(2,4,figsize=(18,7),sharex='col',sharey='row');stats={}
for col,(key,title,kind) in enumerate(items):
    c=entries[key][kind];xyz=array(c['xyz']);rgb=array(c['rgb'])/255
    sel=(xyz[:,0]>=-66)&(xyz[:,0]<=63)&(xyz[:,1]>=24)&(xyz[:,1]<=42)
    xyz=xyz[sel];rgb=rgb[sel]
    stats[key]=dict(vertices_in_xy_box=len(xyz),z_quantiles=np.quantile(xyz[:,2],[0,.5,.9,.99,1]).tolist(),
                    vertices_above_z_minus25=int((xyz[:,2]>-25).sum()))
    take=np.arange(len(xyz))[::max(1,len(xyz)//100000)];points=xyz[take];colors=rgb[take]
    for row,vertical in [(0,1),(1,2)]:
        ax=axes[row,col];ax.set_facecolor('#16202b');ax.scatter(points[:,0],points[:,vertical],c=colors,s=.65,linewidths=0,rasterized=True)
        ax.set_xlim(-66,63);ax.set_ylim((24,42) if row==0 else (-48,-5));ax.grid(alpha=.12)
        ax.set_xlabel('object u [m]');ax.set_ylabel('-v [m]' if row==0 else 'local z [m]')
    axes[0,col].set_title(title)
fig.suptitle('R1 Z06: same XY crop, top and side projections of displayed geometry\nTSDF vertices shown as points; roof/floater labels are not ground truth')
fig.tight_layout();fig.savefig('/out/Z06_geometry_comparison.png',dpi=160)
Path('/out/geometry_summary.json').write_text(json.dumps(dict(scientific_verdict=None,stats=stats),indent=2))
print(json.dumps(stats))
