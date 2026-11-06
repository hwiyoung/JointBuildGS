"""Add exact existing-mesh sections and export all-height saved reference rows."""
from add9_common import *
from add6_sections import pieces

def make_section(key):
 c=case('c3');row,lab=data(c);oldpath=F6/f"{c['id']}_section_data.json";old=json.loads(oldpath.read_text());full=key=='c3';rec=selected(c) if full else line9('c3_edge');s=rec['section'];ids=np.flatnonzero(section_mask(row['xyz'],s));P=row['xyz'][ids];dr=(np.array(s['end'])-s['start'])/s['length_m'];along=(P[:,:2]-s['start'])@dr;ms=['prior','mvs','fusion','GeoGS_30000','FINALTRAIN_30000','judgment_mesh'];surfaces={};sc=scores(c,ms);sources=[root_of(c)/'rows.npz',root_of(c)/'stage1_cells.npz',oldpath];metrics={};target=lab[ids]==2
 for m in ms:
  if full and m in old['surfaces']:surfaces[m]=old['surfaces'][m]
  else:
   mesh=meshpath(c,m);cache=W9/'sections'/key/hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()[:16]/(m+'.npz')
   if cache.exists():seg=loadz(cache)['segments']
   else:
    V,F=read_surface(mesh);seg=clip_segments(section_segments(V,F,s),s['length_m']);savez(cache,segments=seg);del V,F;gc.collect()
   surfaces[m]=pieces(seg);sources.extend([mesh,cache])
  metrics[m]=values(sc[m][ids][target],row['row_tau_m'][ids][target]);sources.append(scorepath(c,m));print('ADD9_SECTION',key,m,len(surfaces[m]),flush=True)
 ann=np.array(rec['annotation_xyz']);gt=[dict(row_id=int(r),xyz_local=row['xyz'][r].tolist(),s=float(along[i]),z=float(P[i,2]),case_id=int(lab[r]),tau_m=float(row['row_tau_m'][r]),scores={m:dict(status=str(status(np.array([z[r]]),np.array([row['row_tau_m'][r]]))[0]),signed_distance_m=float(z[r]) if np.isfinite(z[r]) else None) for m,z in sc.items()}) for i,r in enumerate(ids)];line=dict(A_local_xyz=ann[0].tolist(),Aprime_local_xyz=ann[-1].tolist(),A_EPSG25832_xy=(np.array(s['start'])+SHIFT[:2]).tolist(),Aprime_EPSG25832_xy=(np.array(s['end'])+SHIFT[:2]).tolist(),length_m=s['length_m'],direction_unit_xy=dr.tolist(),half_width_m=.5)
 name='c3_section_data_with_judgment' if full else 'c3_edge_section_data';dump(F9/(name+'.json'),record(name,dict(case=c['id'],line=line,tau_m=old['tau_m'],surfaces=surfaces,gt_points=gt,strip_metrics=metrics,reference_points_all_cases=len(ids),reference_points_target_case=int(target.sum()),selection=None if full else rec['selection'],intersection_rule='unchanged centre-plane triangle intersections; disconnected pieces retained; no height clipping',scores_reused=True),sources))

def c4_all():
 c=case('c4');row,lab=data(c);rec=selected(c);s=rec['section'];ids=np.flatnonzero(section_mask(row['xyz'],s));oldpath=F6/f"{c['id']}_section_data.json";old=json.loads(oldpath.read_text());oldids={r['row_id'] for r in old['gt_points']};P=row['xyz'][ids];dr=(np.array(s['end'])-s['start'])/s['length_m'];along=(P[:,:2]-s['start'])@dr
 # Report the separated upper terminal group explicitly, without inventing a structure label.
 ordered=np.sort(P[:,2]);gaps=np.diff(ordered);candidates=np.flatnonzero((gaps>.5)&(ordered[:-1]>-28));cut=float((ordered[candidates[-1]]+ordered[candidates[-1]+1])/2) if len(candidates) else float(np.median(P[:,2])+2);upper=P[:,2]>cut;uid=ids[upper]
 points=[dict(row_id=int(r),xyz_local=row['xyz'][r].tolist(),s=float(along[i]),z=float(P[i,2]),case_id=int(lab[r]),in_addendum6=r in oldids) for i,r in enumerate(ids)];summary=dict(all_reference_rows=len(ids),all_rows_already_in_addendum6=all(int(r) in oldids for r in ids),missing_from_addendum6=int(sum(int(r) not in oldids for r in ids)),upper_group_count=int(upper.sum()),upper_group_local_z_range=[float(P[upper,2].min()),float(P[upper,2].max())],upper_group_EPSG25832_height_range=(np.array([P[upper,2].min(),P[upper,2].max()])+SHIFT[2]).tolist(),upper_group_s_range=[float(along[upper].min()),float(along[upper].max())],upper_group_all_in_addendum6=all(int(r) in oldids for r in uid),upper_group_rule=f'upper terminal Z cluster above the highest >0.5m gap above local Z -28m; cut Z={cut:.6f}m',upper_structure_identity='geometric upper group only; the request supplies no exact XY or semantic label for the approximately 2.7m structure',no_height_filter_for_export=True)
 dump(F9/'c4_section_gt_all.json',record('c4_section_gt_all',dict(case=c['id'],line=old['line'],tau_m=old['tau_m'],gt_points=points,verification=summary),[oldpath,root_of(c)/'rows.npz',root_of(c)/'stage1_cells.npz']));print('ADD9_C4_ALL',json.dumps(summary),flush=True)
if __name__=='__main__':
 if len(sys.argv)==1:make_section('c3');c4_all()
 make_section('c3_edge')
