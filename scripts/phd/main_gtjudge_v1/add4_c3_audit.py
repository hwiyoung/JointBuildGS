"""Inspect the saved c3 surface and exact stored distances; no new case selection."""
from add4_common import *
from normal_line import values
c=case('c3');rec=getcase(c);root=root_of(c);row=loadz(root/'rows.npz');f=loadz(root/'preservation_features.npz');cells=loadz(root/'stage1_cells.npz');ids=loadz(AW/'cases'/f"{c['id']}.npz")['component_row_ids'];band=section_mask(row['xyz'],rec['section']);metrics={}
for name,mask in [('saved_component',np.isin(np.arange(len(row['xyz'])),ids)),('one_metre_strip',band)]:
 metrics[name]={m:values(loadz(root/'distances'/f'{m}.npz',['row_s'])['row_s'][mask],row['row_tau_m'][mask]) for m in ['prior','mvs','fusion','FINALTRAIN_30000']}
 metrics[name].update(n=int(mask.sum()),z_quantiles=np.percentile(row['xyz'][mask,2],[0,10,50,90,100]).tolist(),row_kind_counts={str(int(k)):int((row['row_kind'][mask]==k).sum()) for k in np.unique(row['row_kind'][mask])})
# The point's row_kind is an evaluation assignment, not an independent roof semantic certificate.
p=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1/s02_box/B0_b10';mesh=loadz(p/'lod2_mesh.npz');tab={int(s['ext']):s for s in json.loads((p/'lod2_surfaces.json').read_text())['surfaces']};V,F=mesh['V'],mesh['F'];sc=MeshScene(V,F);P=row['xyz'][ids];orig=np.c_[P[:,:2],np.full(len(P),V[:,2].max()+10)];rays=np.c_[orig,np.tile([0,0,-1],(len(P),1))].astype('f4');hit=sc.sc.cast_rays(sc.o3d.core.Tensor(rays));depth=hit['t_hit'].numpy();valid=np.isfinite(depth);tri=hit['primitive_ids'].numpy()[valid];surfaces={}
for fid in np.unique(tri):
 sid=int(mesh['tri_surface'][fid]);surfaces[str(sid)]=tab.get(sid,{'missing_surface':sid})
z=orig[valid,2]-depth[valid];out=dict(metrics=metrics,semantic_probe=dict(hit_n=int(valid.sum()),roof_above_median_z=float(np.median(z)) if valid.any() else None,median_height_above_component=float(np.median(z-P[valid,2])) if valid.any() else None,surfaces=surfaces),classification_rule_source=proof(R/'scripts/phd/main_stage1_v1/defs_s1.py'),sources=[proof(root/'rows.npz'),proof(root/'preservation_features.npz'),proof(p/'lod2_mesh.npz'),proof(p/'lod2_surfaces.json')],scientific_verdict=None)
dump(D/'verification/addendum4_c3_audit.json',out);print(json.dumps(out,ensure_ascii=False),flush=True)
