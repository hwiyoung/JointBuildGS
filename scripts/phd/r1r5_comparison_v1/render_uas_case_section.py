"""Inspect a reference-discrepancy case after all candidates/results are frozen."""
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Rectangle
from evaluate_uas_and_localize import OUT,CFG,ART,ROOT,ANALYSIS,BASIS,zones_for,draw_zones,section_segments
from analyze_final_surfaces import read,write,sha,cropped_mesh

r='R1';case=read(OUT/'case_locations.json')['regions'][r]['top_cells']['prior_near_baseline_far'][0]
u,v,z=np.array(case['uvz_min'])+1
spec=dict(v=float(v),u=[float(u-8),float(u+8)])
write(OUT/'case_section_config_v2.json',dict(region=r,case=case,section=spec,role='evaluation-only ranked case inspection'))
ref=np.load(OUT/(r+'_reference.npz'))['xyz'];uv=ref[:,:2]@BASIS.T
sel=(abs(uv[:,1]-v)<=.25)&(abs(uv[:,0]-u)<=8)
cached=OUT/'R1_Z07_case_segments.npz'
if cached.exists():
    cache=np.load(cached);segments={k:cache[k] for k in cache.files}
else:
    modelinfo=read(ANALYSIS/(r+'_summary.json'))['metadata']['models'];segments={}
    for branch,info in modelinfo.items():
        path=Path(info['path']);assert sha(path)==info['sha256']
        xyz,tri,_=cropped_mesh(path,ref[sel],10);segments[branch]=section_segments(xyz,tri,spec)
    run=read(ROOT/'config.json');path=ART/run['r1_prep_relative']/'result/input/surface/mesh_arrays.npz'
    prior=np.load(path);segments['prior']=section_segments(prior['xyz'],prior['faces'],spec)
    np.savez_compressed(cached,**segments)
source=np.load(ANALYSIS/(r+'_paired_samples.npz'));m=source['source']==0;mp=source['xyz'][m];xy=mp[:,:2]@BASIS.T
fig,axs=plt.subplots(2,1,figsize=(12,9),gridspec_kw=dict(height_ratios=[1,2]))
axs[0].scatter(*xy.T,s=.6,c='0.8');draw_zones(axs[0],zones_for(r));axs[0].plot(spec['u'],[v,v],c='red',lw=2)
axs[0].scatter([u],[v],s=70,c='red');axs[0].annotate('Z07 local surface',(u,v),xytext=(u+10,v-15),arrowprops=dict(arrowstyle='->'),fontsize=10)
axs[0].set_title('Reference-only inspection case; not a training mask')
colors=dict(mvs='#1675be',da3='#ed8a20',local_prior0='#9b42a6',prior='#159c6b')
for b,seg in segments.items():axs[1].add_collection(LineCollection(seg,colors=colors[b],linewidths=1.2,label=b,alpha=.85))
axs[1].scatter(uv[sel,0],ref[sel,2],c='black',s=6,label='UAS LiDAR (+/-0.25m strip)',zorder=5)
msel=(abs(xy[:,1]-v)<=.5)&(abs(xy[:,0]-u)<=8)
axs[1].scatter(xy[msel,0],mp[msel,2],c='#08a8bd',marker='x',s=24,label='MVS input (+/-0.5m strip)',zorder=6)
axs[1].add_patch(Rectangle((u-1,z-1),2,2,fill=False,edgecolor='red',linewidth=2,label='Scored 2m cell'))
axs[1].set_xlim(spec['u']);axs[1].set_ylim(z-5,z+5);axs[1].set_xlabel('object u [m]');axs[1].set_ylabel('local z [m]');axs[1].grid(alpha=.3);axs[1].legend(fontsize=9)
axs[1].set_title('Z07: UAS -> prior median %.3fm; UAS -> MVS-GeoGS %.3fm\nDistances use 155 points in the full 2m 3D cell; section is its middle slice'%(case['median_prior_distance'],case['median_baseline_distance']))
fig.tight_layout();fig.savefig(OUT/'R1_Z07_preservation_case_v2.png',dpi=160);plt.close(fig)
write(OUT/'case_section_receipt_v2.json',dict(status='PASS_CASE_SECTION',scientific_verdict=None,segments_sha256=sha(cached),
      mvs_section_points=mp[msel].tolist(),mvs_judgments=source['judgment'][m][msel].tolist(),
      source_sha256=sha(ANALYSIS/(r+'_paired_samples.npz')),figure_sha256=sha(OUT/'R1_Z07_preservation_case_v2.png')))
print('PASS reference-only Z07 case section')
