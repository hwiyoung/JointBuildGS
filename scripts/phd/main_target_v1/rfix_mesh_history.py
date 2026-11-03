"""Read-only lineage audit of earlier AXES71 and screen-simulation meshes."""
from r8_screen_prepare import R,PH,O,C,j,sha,dump

def main():
 ax=PH/'main_axes71_v2/PHD-MAIN-AXES71-v2';metrics=j(ax/'tables/a3_metrics.json')['data'];rows=[]
 for prior,key,res,sim,lane in [('ALS','geogs','geogs_ALS_fix1','GeoGS_ALS_30000','main_baselines_v1/PHD-MAIN-BASELINES-v1'),('LoD2','geogs','trust_LoD2_fix1','GeoGS_LoD2_30000','main_fix_v1/PHD-MAIN-FIX-v1'),('ALS','twodgs','imgonly_2dgs_s0','image_only_2DGS_30000','main_baselines_v1/PHD-MAIN-BASELINES-v1'),('LoD2','twodgs','imgonly_2dgs_s0','image_only_2DGS_30000','main_baselines_v1/PHD-MAIN-BASELINES-v1')]:
  run=PH/lane/'runs/B173nb_b10'/res;post=j(run/'post/post.json');meta=ax/'dist'/('B173nb_b10_'+prior+'__'+res+'__x.json');m=j(meta);old=metrics['B173nb_b10/'+prior][key]['values'][res];newpath=O/'screen_sim/scores'/sim/'before'/prior/'values.json';new=j(newpath)['metrics'];cells=[]
  for cell,v in old.items():
   if 'gt' not in v:cells.append(dict(cell=cell,old_status=v['status'],new_status='current training-view mesh'));continue
   fields=['R_tau','mean','n_gt'];diff={f:[v['gt'].get(f),new[cell]['gt'].get(f)] for f in fields if v['gt'].get(f)!=new[cell]['gt'].get(f)}
   for f in ['P_tau','mean','n']:
    if v['res']['E'].get(f)!=new[cell]['res']['E'].get(f):diff['res_'+f]=[v['res']['E'].get(f),new[cell]['res']['E'].get(f)]
   cells.append(dict(cell=cell,old_status=v['status'],same=not diff,differences=diff))
  rows.append(dict(prior=prior,result=res,old_all_R=old['all']['gt']['R_tau'],old_all_P_E=old['all']['res']['E']['P_tau'],new_all_R=new['all']['gt']['R_tau'],new_all_P_E=new['all']['res']['E']['P_tau'],old_training_mesh=str(run/'post/mesh_tsdf.ply'),old_post=str(run/'post/post.json'),old_post_sha256=sha(run/'post/post.json'),old_tsdf=post['tsdf'],old_virtual=m['virtual'],old_distance_meta_sha256=sha(meta),new_values_sha256=sha(newpath),cells=cells))
 dump(O/'rfix/mesh_history.json',dict(rows=rows,old_rule='all and ordinary cells: training-view TSDF; c_inh_invis and c_invis_wrong: separate virtual-view mesh, if available',simulation_rule='same203 training-view TSDF0.05m for all sixteen rows, no virtual-view substitution',code=[dict(path=str(R/p),sha256=sha(R/p)) for p in ['scripts/phd/main_axes71_v2/a3_metrics.py','scripts/phd/main_axes71_v2/ax_arrays.py','scripts/phd/main_dist71_v1/dm_common.py','scripts/phd/main_target_v1/screen_sim_mesh.py']],scientific_verdict=None))
 print([(r['result'],r['prior'],r['old_all_R'],r['old_all_P_E']) for r in rows])
if __name__=='__main__':main()
