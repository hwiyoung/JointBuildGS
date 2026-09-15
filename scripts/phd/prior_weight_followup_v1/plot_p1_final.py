"""Matched P1 mesh display, using stored geometry without changing its surface."""
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

assert Path('/.dockerenv').exists()
cfg=json.loads(Path('/out/config.json').read_text());v=Path('/payload')/cfg['viewer']
m=json.loads((v/'prior_weights_v1/manifest.json').read_text())
r=next(x for x in m['regions'] if x['id']=='P1')
o=json.loads((v/'manifest.json').read_text());old=next(x for x in o['regions'] if x['id']=='P1')
global_mesh=next(x for x in old['candidates'] if x['id']=='mvs_0.0005')['mesh']
items=[('Regional / prior .005',r['conditions'][0]['mesh']),('Historical global / prior .0005',global_mesh),('Regional / prior .0005',r['conditions'][1]['mesh'])]
fig=plt.figure(figsize=(15,9),constrained_layout=True)
inputs={}
for col,(title,mesh) in enumerate(items):
    arrays={}
    for k in ['xyz','rgb','indices']:
        d=mesh[k];path=v/d['url'].removeprefix('/data/');raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        assert digest==d['sha256'];inputs[str(path)]=digest
        arrays[k]=np.frombuffer(raw,dtype=d['dtype']).reshape(d['shape'])
    xyz,tri=arrays['xyz'],arrays['indices'];colors=arrays['rgb'][tri].mean(axis=1)/255
    for row,elev in enumerate([60,12]):
        ax=fig.add_subplot(2,3,row*3+col+1,projection='3d')
        ax.add_collection3d(Poly3DCollection(xyz[tri],facecolors=colors,edgecolor='none',rasterized=True))
        for dim,setter in enumerate([ax.set_xlim,ax.set_ylim,ax.set_zlim]):setter(r['bounds']['min'][dim],r['bounds']['max'][dim])
        ax.set_box_aspect(np.subtract(r['bounds']['max'],r['bounds']['min']))
        ax.view_init(elev=elev,azim=-120);ax.set_proj_type('ortho');ax.axis('off');ax.set_title(title)
fig.savefig('/out/P1_mesh_matched.png',dpi=160);plt.close(fig)
Path('/out/mesh_figure_receipt.json').write_text(json.dumps(dict(inputs=inputs,scientific_verdict=None,
    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),bounds=r['bounds'],
    note='Raw RGB meshes, same bounds and cameras; historical global is a context comparator, not isolated mask ablation.'),indent=2))
