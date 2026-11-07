"""Numerical window/strip diagnostics; no figure or scoring computation."""
from add10_common import *
from matplotlib.path import Path as PolygonPath
from shapely.geometry import Polygon
from shapely.ops import unary_union
import laspy

def counts(labels,mask):return {str(k):int((mask&(labels==k)).sum()) for k in [-1,0,1,2,3,4]}
def spread(z):return dict(n=len(z),minimum_m=float(z.min()) if len(z) else None,maximum_m=float(z.max()) if len(z) else None,range_m=float(np.ptp(z)) if len(z) else None,std_m=float(np.std(z)) if len(z) else None)

def native_rays(pixel,cam):
 q=np.array(pixel,dtype=float);a,b,c,d=cam['crop_xyxy_px'];W,H=cam['output_size_px'];p=cam['parameters'];assert p[4:]==[0.]*8;native=q/[W,H]*[c-a,d-b]+[a,b];v=np.c_[(native[:,0]-p[2])/p[0],(native[:,1]-p[3])/p[1],np.ones(len(q))]@np.array(cam['R']);return v/np.linalg.norm(v,axis=1)[:,None]

def main():
 c=case('c3');row,lab=data(c);P=row['xyz'];along,across=strip_coord(P);wide=(along>=23.2)&(along<=24.7)&(abs(across)<=.5);narrow=(along>=23.2)&(along<=24.7)&(abs(across)<=.1);reports=[]
 for width,mask in [(1.,wide),(.2,narrow)]:
  z=P[mask,2];s=along[mask];t=across[mask];X=np.c_[np.ones(len(z)),s-s.mean(),t-t.mean()];coef=np.linalg.lstsq(X,z,rcond=None)[0];res=z-X@coef;X1=X[:,:2];coef1=np.linalg.lstsq(X1,z,rcond=None)[0]
  reports.append(dict(width_m=width,s_range_m=[23.2,24.7],z=spread(z),case_counts=counts(lab,mask),plane_fit=dict(z_at_mean_st=float(coef[0]),slope_along=float(coef[1]),slope_across=float(coef[2]),mean_s=float(s.mean()),mean_t=float(t.mean()),residual=spread(res),predicted_range_m=float(np.ptp(X@coef))),along_only_residual=spread(z-X1@coef1)))
 bins=[]
 for a in np.arange(22.6,25.6,.5):
  mask=(along>=a)&(along<a+.5)&(abs(across)<=.5);bins.append(dict(start_m=float(a),end_m=float(a+.5),**spread(P[mask,2]),case_counts=counts(lab,mask)))
 fine=[]
 for a in np.arange(23.2,24.7,.1):
  mask=narrow&(along>=a)&(along<a+.1);fine.append(dict(start_m=float(a),end_m=float(a+.1),**spread(P[mask,2])))
 dump(T10/'c3_middle_strip.json',record(dict(strips=reports,bins_0p5m_width1m=bins,bins_0p1m_width0p2m=fine,height_units='local Z metres',standard_deviation='population ddof=0',interpretation=None),[root_of(c)/'rows.npz',root_of(c)/'stage1_cells.npz',W6/'selected'/f"{c['id']}.json"]))
 cam=json.loads((F9/'c3_closeup_photo.json').read_text())['camera'];cam['projection']='perspective';polys=A10['window_polygons_base_photo_px'];paths={k:PolygonPath(v) for k,v in polys.items()};uv,zcam=project(P,cam)
 masks={k:pp.contains_points(uv)&(zcam>0) for k,pp in paths.items()};masks['all_glazing']=np.logical_or.reduce(list(masks.values()))
 # The area uses a disclosed support plane, fitted before raw point-density counts.
 support=(along>=22.6)&(along<=25.6)&(abs(across)<=2.2);Q=P[support];originxy=Q[:,:2].mean(0);design=np.c_[Q[:,:2]-originxy,np.ones(len(Q))];coef=np.linalg.lstsq(design,Q[:,2],rcond=None)[0];normal=np.r_[-coef[:2],1.];normal/=np.linalg.norm(normal);plane_point=np.r_[originxy,coef[2]];centre=np.array(cam['centre']);areas={};xyz_polys={}
 for k,px in polys.items():
  v=native_rays(px,cam);t=((plane_point-centre)@normal)/(v@normal);xyz=centre+t[:,None]*v;xyz_polys[k]=xyz;area=Polygon(xyz[:,:2]).area;areas[k]=dict(plan_area_m2=area,surface_area_m2=area/abs(normal[2]))
 union=unary_union([Polygon(q[:,:2]) for q in xyz_polys.values()]);areas['all_glazing']=dict(plan_area_m2=union.area,surface_area_m2=union.area/abs(normal[2]));xy_masks={k:PolygonPath(q[:,:2]).contains_points(P[:,:2]) for k,q in xyz_polys.items()};xy_masks['all_glazing']=np.logical_or.reduce(list(xy_masks.values()))
 panel=json.loads((F9/'c3_points_mvs.json').read_text());panelids=np.array([r['row_id'] for r in panel['points']]);old=json.loads((F6/f"{c['id']}_section_data.json").read_text());sectionids=np.array([r['row_id'] for r in old['gt_points']]);rows=[]
 for name,mask in masks.items():
  ids=np.flatnonzero(mask);rows.append(dict(region=name,**areas[name],stage1_rows=int(mask.sum()),stage1_rows_per_plan_m2=int(mask.sum())/areas[name]['plan_area_m2'],stage1_rows_per_surface_m2=int(mask.sum())/areas[name]['surface_area_m2'],case_counts=counts(lab,mask),no_case_reasons={'':int(mask.sum())} if np.isin(lab[mask],range(5)).all() else {'unassigned':int((mask&(lab<0)).sum())},ids_in_add9_points=int(np.isin(ids,panelids).sum()),ids_in_add6_section=int(np.isin(ids,sectionids).sum()),add9_colored_case2=int((mask&(lab==2)).sum()),add9_other_case_gray=int((mask&(lab!=2)).sum()),XY_plane_pullback_rows=int(xy_masks[name].sum()),XY_plane_pullback_case_counts=counts(lab,xy_masks[name]),row_ids=ids.tolist()))
 # Exact original ULS source, streamed read-only; all returns, no use/excl/thinning.
 raw=PH.parent/'p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz';summary=json.loads((S1/'v3/box_gt/B0_b10/gt_summary.json').read_text());dz=summary['height_alignment']['passes']['shift_applied_there']+summary['height_alignment']['v7_z_shift_m'];rawcounts={k:0 for k in masks};xycounts={k:0 for k in masks};rawids={k:[] for k in masks};examined=0;kept=[];kept_ids=[]
 rawproof=proof(raw)
 with laspy.open(str(raw)) as f:
  header=dict(point_count=int(f.header.point_count),point_format=int(f.header.point_format.id),min_xyz=f.header.mins.tolist(),max_xyz=f.header.maxs.tolist());ray=native_rays(np.concatenate(list(polys.values())),cam);zlo=f.header.mins[2]-SHIFT[2]+dz;zhi=f.header.maxs[2]-SHIFT[2]+dz;corners=np.concatenate([centre+(z0-centre[2])/ray[:,2,None]*ray for z0 in [zlo,zhi]]);lo=corners[:,:2].min(0)-.01;hi=corners[:,:2].max(0)+.01
  for pts in f.chunk_iterator(5_000_000):
   x=np.asarray(pts.x)-SHIFT[0];y=np.asarray(pts.y)-SHIFT[1];ok=(x>=lo[0])&(x<=hi[0])&(y>=lo[1])&(y<=hi[1]);idx=np.flatnonzero(ok)
   if len(idx):
    Praw=np.c_[x[ok],y[ok],np.asarray(pts.z)[ok]-SHIFT[2]+dz];uv,zz=project(Praw,cam);mm={k:pp.contains_points(uv)&(zz>0) for k,pp in paths.items()};mm['all_glazing']=np.logical_or.reduce(list(mm.values()));xx={k:PolygonPath(p[:,:2]).contains_points(Praw[:,:2]) for k,p in xyz_polys.items()};xx['all_glazing']=np.logical_or.reduce(list(xx.values()))
    for k in masks:rawcounts[k]+=int(mm[k].sum());xycounts[k]+=int(xx[k].sum());rawids[k].extend((examined+idx[mm[k]]).tolist())
    kept.append(Praw[mm['all_glazing']]);kept_ids.append(examined+idx[mm['all_glazing']])
   examined+=len(pts)
 assert examined==header['point_count']
 for r in rows:
  k=r['region'];r.update(raw_drone_points=rawcounts[k],raw_drone_points_per_plan_m2=rawcounts[k]/r['plan_area_m2'],raw_drone_points_per_surface_m2=rawcounts[k]/r['surface_area_m2'],raw_drone_XY_plane_pullback_points=xycounts[k])
 # Distinguish the B0 GeoGS evaluation cloud from the original ULS sensor population.
 primary=loadz(S1/'v3/box_gt/B0_b10/gt_primary.npz',['xyz'])['xyz'];uv,z=project(primary,cam)
 for r in rows:
  pp=paths.get(r['region']);mask=pp.contains_points(uv)&(z>0) if pp else np.logical_or.reduce([p.contains_points(uv)&(z>0) for p in paths.values()]);r['primary_dense_reference_points']=int(mask.sum());r['primary_dense_reference_points_per_plan_m2']=int(mask.sum())/r['plan_area_m2']
 savez(W10/'window_raw_points.npz',xyz=np.concatenate(kept),raw_point_id=np.concatenate(kept_ids))
 sources=[raw,S1/'v3/box_gt/B0_b10/gt_primary.npz',S1/'v3/box_gt/B0_b10/gt_summary.json',F9/'c3_points_mvs.json',F9/'c3_closeup_photo.json',F6/f"{c['id']}_section_data.json",Path(__file__).with_name('add9_detail.py'),Path(__file__).with_name('add6_sections.py')]
 result=dict(regions=rows,window_polygons_photo_px=polys,window_polygons_local_xyz={k:v.tolist() for k,v in xyz_polys.items()},camera=cam,window_definition=A10['window_rule'],reference_area_plane=dict(point=plane_point.tolist(),unit_normal=normal.tolist(),support_rows=len(Q),support_s_m=[22.6,25.6],support_width_m=4.4,fit_residual=spread(Q[:,2]-design@coef)),raw_lidar=dict(source=rawproof,header=header,points_scanned=examined,z_shift_to_stage1_m=dz,no_filtering=True,spatial_prefilter='union photo rays at raw header min/max Z, hence contains all positive-depth glazing rays within source height bounds'),selection_code_difference=dict(add9='add9_detail.panels: XY rectangle length7m width4.4m around s22.6..25.6; all cases included in JSON, only case2 colored by status, other cases gray radius1.8px',add6='add6_sections.main: full26.933m line, width1m, all cases in gt_points, no visibility filter',no_reference_row_dropped_by_case_in_either_json=True))
 dump(T10/'c3_windows.json',record(result,sources));print('ADD10_DIAGNOSTICS',[(r['region'],r['stage1_rows'],r['raw_drone_points']) for r in rows],flush=True)

if __name__=='__main__':main()
