"""First deliverable: lossless saved stage-1 rows and denominator verification."""
from add10_common import *
from shapely.geometry import Polygon,mapping
from shapely.ops import unary_union

def main():
 checks=[];scene_info=[];all_sources=[]
 sources=[C/'addendum10.json']
 for key in A10['cases']:
  c=case(key);sources.extend([root_of(c)/'rows.npz',root_of(c)/'stage1_cells.npz',*stored_scores(c).values()]);sources.extend(Path(j['source']) for j in camera_jobs(key))
 dump(W10/'input_lock.json',record(dict(purpose='before row export; render mesh hashes verified separately before raycasting'),sources))
 for key in A10['cases']:
  c=case(key);row,lab=data(c);load_cells=loadz(root_of(c)/'stage1_cells.npz');P=row['xyz'];N=len(P);paths=stored_scores(c);ss={m:loadz(p,['row_s'])['row_s'] for m,p in paths.items()};assert all(len(v)==N for v in ss.values());states={m:status(v,row['row_tau_m']) for m,v in ss.items()};eligible=np.ones(N,bool)
  missing=[m for m in ['prior','mvs','fusion','GeoGS_30000','2DGS_30000','CDGS_30000','baseline_30000','FINALTRAIN_30000','judgment_mesh','gt_judgment_mesh','always_keep_mesh','A1'] if m not in ss]
  # Existing collect.metrics passes every selected row to values(), no eligible exclusion.
  target=D/'tables/stage1'/f"{c['site']}__{c['prior']}_metrics.json";old=json.loads(target.read_text())['rows'];count=0;maximum=0.
  for r in old:
   if r['method'] not in ss or str(r['case_id']) not in ['0','1','2','3','4']:continue
   take=(lab==int(r['case_id']))&eligible;v=values(ss[r['method']][take],row['row_tau_m'][take]);assert v['n']==r['n_gt'];diff=abs(v['within_pct']-r['completeness_pct']) if v['n'] else 0;assert diff<1e-10;maximum=max(maximum,diff);count+=1
  checks.append(dict(case=key,rows=N,checked_method_case_pairs=count,maximum_completeness_difference_pp=maximum,all_match=True))
  path=T10/(key+'_reference_rows.csv.gz');fields=['row_id','x','y','z','E','N','nx','ny','nz','case_id','no_case_reason','eligible']+[x for m in ss for x in [m+'_status',m+'_sd_m']]
  with gzip.open(path,'wt',newline='',compresslevel=6) as f:
   writer=csv.writer(f,lineterminator='\n');writer.writerow(fields)
   for i in range(N):
    classified=int(lab[i]) in range(5);reason='' if classified else 'prior_surface_absent' if load_cells['prior_absent'][i] else 'invalid_tau' if not np.isfinite(row['row_tau_m'][i]) else 'unassigned_saved_stage1'
    base=[i,*[float(x) for x in P[i]],float(P[i,0]+SHIFT[0]),float(P[i,1]+SHIFT[1]),*[float(x) for x in row['normal'][i]],int(lab[i]) if classified else -1,reason,1]
    writer.writerow(base+[x for m in ss for x in [str(states[m][i]),repr(float(ss[m][i])) if np.isfinite(ss[m][i]) else '']])
  spacing=cKDTree(P).query(P,k=2,workers=6)[0][:,1];radius=float(np.median(spacing));assert radius>0
  sources=[root_of(c)/'rows.npz',root_of(c)/'stage1_cells.npz',target,*paths.values()];all_sources+=sources
  info=dict(case=key,scene=c,rows=N,methods=list(ss),missing_methods=missing,score_sources={m:proof(p) for m,p in paths.items()},reference_source=proof(root_of(c)/'rows.npz'),case_source=proof(root_of(c)/'stage1_cells.npz'),radius_m=radius,nearest_neighbor_spacing_m=dict(median=radius,minimum=float(spacing.min()),maximum=float(spacing.max())),eligible_definition='all saved stage1 rows, matching collect.metrics; no extra geometry/visibility/case filtering',sd_definition='stored signed surface-minus-reference displacement along oriented normal; positive is upward on roofs, toward nearest training camera on walls',method_aliases={'2DGS':'2DGS_30000','CDGS':'CDGS_30000','LGDM':'fusion','본 방법':'FINALTRAIN_30000','정답 판단으로 만든 면':'gt_judgment_mesh','늘 보존 면':'always_keep_mesh'},none_sd_representation='empty CSV field; saved nonfinite row_s; no imputation',no_case_count=int((~np.isin(lab,range(5))).sum()),case_counts={str(k):int((lab==k).sum()) for k in range(5)},denominator_check=checks[-1])
  dump(T10/(key+'_reference_rows.json'),record(info,sources));dump(W10/(key+'_scene.json'),info);scene_info.append(info)
  # GroundSurface XY is an evaluation-origin map outline, never a source of Z.
  bp=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/inputs/lod2_buildings.json';buildings={b['id']:b for b in json.loads(bp.read_text())};bid=selected(c)['selection']['building_identity'];b=buildings.get(bid);polys=[]
  if b:
   for poly in b['surfaces'].get('ground',[]):polys.append(Polygon(np.asarray(poly['ext'])[:,:2]-SHIFT[:2],[np.asarray(h)[:,:2]-SHIFT[:2] for h in poly['holes'] if len(h)>3]).buffer(0))
  if polys:outline=unary_union(polys);kind='LoD2 GroundSurface XY'
  else:
   box=BOXES[BIDS[c['site']]];u0,u1=box['eval_u'];v0,v1=box['eval_v'];outline=Polygon(uvxy([[u0,v0],[u1,v0],[u1,v1],[u0,v1]]));kind='experiment region boundary fallback'
  dump(T10/(key+'_outline.geojson'),dict(type='FeatureCollection',coordinate_system=dict(type='local XY metres',world_crs='EPSG:25832',world_xy_offset=SHIFT[:2].tolist()),features=[dict(type='Feature',geometry=mapping(outline),properties=dict(building_id=bid,source_kind=kind,source=proof(bp),GT_derived_XY=True,Z_used=False))]))
  first=json.loads((F9/(key+'_photo.json')).read_text());corners=first['box_corners_local_xyz'];box=BOXES[BIDS[c['site']]];u0,u1=box['eval_u'];v0,v1=box['eval_v'];region=uvxy([[u0,v0],[u1,v0],[u1,v1],[u0,v1]])
  boxes=dict(case=key,panel1_box_corners_local_xy=np.array(corners)[:,:2].tolist(),panel1_box_corners_local_xyz=corners,panel1_box_source=proof(F9/(key+'_photo.json')),scene_bounds_local_xy=[float(P[:,0].min()),float(P[:,1].min()),float(P[:,0].max()),float(P[:,1].max())],scene_bounds_definition='all saved scene reference rows',experiment_region_corners_local_xy=region.tolist(),experiment_region_bounds_local_xy=[*region.min(0).tolist(),*region.max(0).tolist()],crs='EPSG:25832',local_world_shift=SHIFT.tolist(),scientific_verdict=None)
  dump(T10/(key+'_boxes.json'),boxes);dump(W10/(key+'_cameras.json'),camera_jobs(key));print('ADD10_ROWS',key,N,list(ss),'radius',radius,flush=True)
 dump(T10/'denominator_check.json',record(dict(scenes=checks,all_match=True),all_sources));print('ADD10_EXPORT_DONE',flush=True)

if __name__=='__main__':main()
