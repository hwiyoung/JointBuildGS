#!/usr/bin/env python3
"""Input-only top-height RGB point projection for object boundary inspection."""
import json
from pathlib import Path
import sys
import numpy as np
from plyfile import PlyData
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
sys.path.insert(0,'/repo')
from src.phd.region_view_support_v1 import object_basis,region_mask,sha256

out=Path('/output/overview');out.mkdir(exist_ok=False)
cfg=json.loads(Path('/evidence/config.json').read_text());region=cfg['region'];basis=object_basis(70)
data=PlyData.read('/fused.ply',mmap='r')['vertex'].data
resolution=.1;nu=2050;nv=1000;zbuffer=np.full(nu*nv,-np.inf,np.float32);rgb=np.full((nu*nv,3),240,np.uint8);counts=np.zeros(nu*nv,np.uint32)
for start in range(0,len(data),4_000_000):
    chunk=data[start:start+4_000_000:4];xyz=np.column_stack([chunk[k] for k in 'xyz']);keep=region_mask(xyz,region,basis,[-90,80])
    xyz=xyz[keep];chunk=chunk[keep]
    uv=xyz[:,:2]@basis.T;ij=np.floor((uv-[-135,-65])/resolution).astype(int);flat=ij[:,1]*nu+ij[:,0]
    np.add.at(counts,flat,1)
    order=np.lexsort((-xyz[:,2],flat));ids=order[np.r_[True,np.diff(flat[order])!=0]]
    best=flat[ids];better=xyz[ids,2]>zbuffer[best];ids=ids[better];best=flat[ids]
    zbuffer[best]=xyz[ids,2];rgb[best]=np.column_stack([chunk[k][ids] for k in ('red','green','blue')])
font_manager.fontManager.addfont('/font.ttf');plt.rcParams['font.family']=font_manager.FontProperties(fname='/font.ttf').get_name()
fig,ax=plt.subplots(figsize=(20,10));ax.imshow(rgb.reshape(nv,nu,3),extent=[-135,70,35,-65],origin='upper')
ax.set_xticks(np.arange(-130,71,10));ax.set_yticks(np.arange(-60,36,10));ax.grid(alpha=.4,color='#40bdc9');ax.set_xlabel('객체축 u [m]');ax.set_ylabel('객체축 v [m]');ax.set_title('R1 현재 MVS RGB 최고점 투영 · 표시용 0.1m / 원 PLY stride4 / 빈 셀 보간 없음')
fig.tight_layout();fig.savefig(out/'R1_rgb_top_projection.png',dpi=160);plt.close(fig)
np.savez_compressed(out/'top_projection.npz',rgb=rgb.reshape(nv,nu,3),z=zbuffer.reshape(nv,nu),count=counts.reshape(nv,nu))
Path(out/'receipt.json').write_text(json.dumps(dict(status='PASS_DISPLAY_ONLY',scientific_verdict=None,script_sha256=sha256(__file__),source_vertex_count=len(data),fields=list(data.dtype.names),stride=4,cell_m=.1,filled_cells=int(np.isfinite(zbuffer).sum()),total_cells=nu*nv),indent=2))
print((out/'receipt.json').read_text())
