"""CPU-only section 3 and export. Ground truth only selects diagnostic groups."""
from common import *
from shapely.geometry import shape, Polygon
from shapely.ops import triangulate
from shapely import vectorized
from scipy.special import expit, logit
sys.path.insert(0,str(R))
from src.phd.prior_propagation_v6.orientation import quat_from_normal,axes_of_quat as quat_to_axes

def scope_mask(P,c):
 p=shape(c['scope']['buffered_footprint']);return vectorized.contains(p,P[:,0],P[:,1])&(P[:,2]>=c['scope']['z_min'])&(P[:,2]<=c['scope']['z_max'])

def prior_geometry(c):
 z=loadz(c['sources']['prior']);V,F=z['V'],z['F'];poly=shape(c['scope']['buffered_footprint']);lo=np.array(poly.bounds[:2]);hi=np.array(poly.bounds[2:]);tri=V[F]
 use=(tri[:,:,:2].max(1)>=lo).all(1)&(tri[:,:,:2].min(1)<=hi).all(1)&(tri[:,:,2].max(1)>=c['scope']['z_min'])&(tri[:,:,2].min(1)<=c['scope']['z_max']);parts=[]
 for t in tri[use]:
  n=np.cross(t[1]-t[0],t[2]-t[0]);
  if abs(n[2])<1e-12:continue
  p=Polygon(t[:,:2]).intersection(poly)
  if p.is_empty:continue
  for tt in triangulate(p):
   if not p.covers(tt):continue
   q=np.asarray(tt.exterior.coords)[:3];zz=t[0,2]-((q-t[0,:2])*n[:2]).sum(1)/n[2];points=np.c_[q,zz]
   # Clip each triangle in Z, preserving its plane and exact area.
   for bound,sign in [(c['scope']['z_min'],1),(c['scope']['z_max'],-1)]:
    out=[]
    for a,b in zip(points,np.roll(points,-1,axis=0)):
     ia=sign*(a[2]-bound)>=0;ib=sign*(b[2]-bound)>=0
     if ia:out.append(a)
     if ia!=ib:out.append(a+(bound-a[2])/(b[2]-a[2])*(b-a))
    points=np.asarray(out).reshape(-1,3)
    if len(points)<3:break
   for j in range(1,len(points)-1):parts.append(points[[0,j,j+1]])
 T=np.asarray(parts);cross=np.cross(T[:,1]-T[:,0],T[:,2]-T[:,0]);area=np.linalg.norm(cross,axis=1)/2;norm=cross/np.maximum(2*area[:,None],1e-20);roof=abs(norm@np.asarray(c['coordinates']['up']))>=.5
 savez(O/'work/prior_clipped.npz',triangles=T.astype('f4'),area=area,roof=roof)
 return float(area[roof].sum())

def q(v,p=.5):return float(np.quantile(v,p)) if len(v) else None
def frac(v):return float(np.mean(v)) if len(v) else None

def main():
 c=cfg();t=loadz(c['sources']['target']);s=loadz(c['sources']['seeds']);initial=loadz(c['sources']['snapshot_initial_fields'],['initial_scale','normal','anchor','sigma','region','patch_ids'])
 assert np.array_equal(initial['anchor'],s['target']);assert np.allclose(initial['initial_scale'][:,0],initial['initial_scale'][:,1],rtol=0,atol=0)
 # Prior quaternions are exact seed bytes; background uses inherited normal->quat.
 rot=s['quaternion'].copy();bg=s['origin']==0;rot[bg]=quat_from_normal(initial['normal'][bg]).astype('f4')
 a1,a2,n=quat_to_axes(rot);assert np.allclose(n,initial['normal'],atol=1e-6)
 valid=np.flatnonzero((t['region']>=0)&np.isfinite(t['target']).all(1)&np.isfinite(t['normal']).all(1)&np.isfinite(t['sigma'])&(t['sigma']>0));assert np.array_equal(valid,initial['patch_ids'])
 inv=np.full(len(t['region']),-1,'i8');inv[valid]=np.arange(len(valid));idx=np.full(len(s['origin']),-1,'i8');idx[~bg]=inv[s['patch'][~bg]]
 # Same activated scalar as original inverse_sigmoid(.1), in float32.
 alpha=expit(logit(np.full(len(s['origin']),.1,'f4'))).astype('f4')
 savez(O/'work/state_0.npz',xyz=s['xyz'],rotation=rot,scale=initial['initial_scale'],opacity=alpha,origin=s['origin'],init_id=np.arange(len(s['origin']),dtype='i4'),target_tag=s['origin'],target_index=idx,target_released_at=np.full(len(idx),-1,'i4'))
 row=loadz(c['sources']['reference_rows']);labels=loadz(c['sources']['reference_cases']);core=loadz(c['sources']['core'],['source_index','patch_id']);ci=core['source_index'];assert np.array_equal(t['patch_id'][ci],core['patch_id']);owner=row['row_owner'];good=owner>=0;full=np.full(len(owner),-1,'i8');full[good]=ci[owner[good]]
 counts=np.zeros((len(t['region']),5),'i8');good&=np.isin(labels['case_id'],range(5));np.add.at(counts,(full[good],labels['case_id'][good]),1)
 majority1=(counts[:,1]>0)&(counts[:,1,None]>counts[:,[0,2,3,4]]).all(1)
 prior_xyz=t['centre']+t['prior_height_m'][:,None]*t['normal'];patch_inside=scope_mask(prior_xyz,c);gtz=np.full(len(t['region']),np.nan)
 # The exact saved cylinder ownership supplies each patch's reference rows.
 ordered=np.flatnonzero(full>=0);ordered=ordered[np.argsort(full[ordered],kind='stable')];ids,starts=np.unique(full[ordered],return_index=True)
 for pid,a,b in zip(ids,starts,np.r_[starts[1:],len(ordered)]):gtz[pid]=np.median(row['xyz'][ordered[a:b],2])
 dz=prior_xyz[:,2]-gtz;wrong=patch_inside&np.isin(t['judge_region'],[1,4])&majority1&(dz>1);control=patch_inside&(t['judge_region']==2)&majority1
 group=np.zeros(len(t['region']),'i1');group[wrong]=1;group[control]=2
 selected=[]
 for pid in np.flatnonzero(group):selected.append(dict(patch_index=int(pid),patch_id=str(t['patch_id'][pid]),group=int(group[pid]),judge_region=int(t['judge_region'][pid]),area_m2=float(t['area'][pid]),reference_rows=int(counts[pid].sum()),case1_rows=int(counts[pid,1]),prior_z=float(prior_xyz[pid,2]),reference_median_z=float(gtz[pid]),prior_above_reference_m=float(dz[pid])))
 table('selected_patches',selected);savez(O/'work/patch_groups.npz',group=group,reference_counts=counts,reference_median_z=gtz,prior_xyz=prior_xyz,reference_owner=full)
 roof_area=prior_geometry(c);P=np.load(c['sources']['mvs_points'],mmap_mode='r');mv=[]
 for start in range(0,len(P),1000000):part=P[start:start+1000000];mv.append(part[scope_mask(part,c)])
 mv=np.concatenate(mv).astype('f4');savez(O/'work/mvs_building.npz',xyz=mv)
 refinside=scope_mask(row['xyz'],c);savez(O/'work/reference_building.npz',xyz=row['xyz'][refinside],case_id=labels['case_id'][refinside],row_id=np.flatnonzero(refinside),row_tau_m=row['row_tau_m'][refinside],owner=full[refinside])
 sums=[];lineage=[];totals=[];initial_inside=scope_mask(s['xyz'],c);seedgroup=np.zeros(len(s['origin']),'i1');seedgroup[~bg]=group[s['patch'][~bg]];seedgroup[~initial_inside]=0;cover0={};up=np.array(c['coordinates']['up'])
 for it in c['iterations']:
  z=loadz(O/'work'/f'state_{it}.npz');allinside=scope_mask(z['xyz'],c);fullids=np.flatnonzero(allinside);g={k:v[allinside] for k,v in z.items()};axes=quat_to_axes(g['rotation']);g['normal']=axes[2].astype('f4');wall=abs(g['normal']@up)<.5
  current=np.full(len(fullids),-1,'i8');attached=g['target_tag']==1;current[attached]=valid[g['target_index'][attached]];judge=np.full(len(fullids),-1,'i1');judge[attached]=t['judge_region'][current[attached]];initialpatch=s['patch'][g['init_id']];mark=seedgroup[g['init_id']]
  h=np.full(len(fullids),np.nan);limit=h.copy();target_z=h.copy();sigma=h.copy();tarxyz=np.full((len(fullids),3),np.nan,'f4')
  jj=current[attached];h[attached]=np.sum((g['xyz'][attached].astype(float)-t['target'][jj].astype('f4'))*t['normal'][jj].astype('f4'),axis=1);sigma[attached]=t['sigma'][jj].astype('f4');limit[attached]=(np.float32(1.96)*sigma[attached].astype('f4')).astype(float);target_z[attached]=t['target'][jj,2];tarxyz[attached]=t['target'][jj]
  g.update(current_patch=current,initial_patch=initialpatch,judgment=judge,group33=mark,wall=wall,full_gaussian_index=fullids,target_xyz=tarxyz,target_sigma=sigma.astype('f4'),normal_offset=h.astype('f4'))
  savez(O/'gaussians'/f'{it}.npz',**{k:(v.astype('f4') if np.issubdtype(v.dtype,np.floating) else v) for k,v in g.items()})
  totals.append(dict(iteration=it,scene_gaussians=len(z['xyz']),building_gaussians=len(fullids),roof=int((~wall).sum()),wall=int(wall.sum()),roof_prior_area_m2=roof_area))
  for tag,name in [(1,'묶임'),(2,'풀림'),(0,'배경')]:
   for fac,face in [(False,'지붕'),(True,'벽')]:
    for reg in ([-1,0,2,1,4] if tag==1 else [-1]):
     m=(g['target_tag']==tag)&(wall==fac);m&=(judge==reg) if reg!=-1 else True;n=int(m.sum());al=g['opacity'][m];sc=g['scale'][m];ab=abs(h[m]);lim=limit[m];bound=(ab<=lim) if tag==1 else np.array([]);edge=(abs(ab-lim)<=.001) if tag==1 else np.array([])
     sums.append(dict(iteration=it,origin=name,face=face,judgment='전체' if reg==-1 else {0:'일치',2:'보정',1:'보존',4:'결측'}[reg],n=n,opacity_median=q(al),opacity_lt_0p1_fraction=frac(al<.1),long_axis_median_m=q(sc.max(1)) if n else None,short_axis_median_m=q(sc.min(1)) if n else None,density_per_m2=n/roof_area if not fac else None,within_interval_fraction=frac(bound),interval_edge_fraction=frac(edge),target_distance_p50_m=q(ab) if tag==1 else None,target_distance_p90_m=q(ab,.9) if tag==1 else None,denominator=n,interval_roundoff_excess_max_m=float(np.max(ab-lim)) if tag==1 and n else None))
  for gp,name in [(1,'틀린 판정'),(2,'보정 비교')]:
   m=mark==gp;al=g['opacity'][m];sc=g['scale'][m];cover=float(np.sum(al.astype(float)*np.pi*sc[:,0]*sc[:,1]));parents=g['init_id'][m];ip=initialpatch[m];xyz=g['xyz'][m];pn=t['normal'][ip];anchor=prior_xyz[ip];oldz=anchor[:,2]-np.sum((xyz[:,:2]-anchor[:,:2])*pn[:,:2],axis=1)/pn[:,2];near=abs(xyz[:,2]-oldz)<=.5
   if it==0:cover0[gp]=cover
   globalgroup=seedgroup[z['init_id']];outside=(globalgroup==gp)&~allinside
   lineage.append(dict(iteration=it,group=name,patches=int((group==gp).sum()) if it==0 else '',area_m2=float(t['area'][group==gp].sum()) if it==0 else '',live_init_ids=len(np.unique(parents)),descendants=int(m.sum()),opacity_median=q(al),coverage_sum_m2=cover,coverage_ratio=cover/cover0[gp] if cover0[gp]>0 else None,near_old_roof_fraction=frac(near),near_old_roof_opacity_median=q(al[near]),released_fraction=frac(g['target_tag'][m]==2),descendants_outside_scope=int(outside.sum()),live_init_ids_global=len(np.unique(z['init_id'][globalgroup==gp]))))
  print('MEASURED',it,len(fullids),flush=True)
 table('filling_intervals',sums);table('wrong_patch_lineage',lineage);table('building_counts',totals)
 table('input_counts',[dict(panel='input',prior_roof_area_m2=roof_area,mvs_points=len(mv),gaussians='not applicable')])
 dump(D/'measure_receipt.json',dict(at=now(),building_counts=totals,selected_wrong_patches=int(wrong.sum()),selected_control_patches=int(control.sum()),roof_area_m2=roof_area,configuration_sha256=sha(C/'procfig_v1.json'),scientific_verdict=None,initialization=dict(method=c['initialization'],exact_initial_disc_geometry=True,axes_equal=True,optimizer_steps=0),reference_join='saved row_owner -> core.source_index with exact patch_id assertion',sources_sha256=sha(D/'input_lock.json')))
 issue('패치 다수 경우는 기존 majority.py처럼 유일 최빈값만 경우1로 인정. 목표 구간 계산은 저장 float32 anchor/normal 및 1.96*sigma를 사용하며 반올림 초과량을 별도 기록, 허용 구간 비율의 부등호를 완화하지 않음.')
 issue('계보 표는 0회에 건물 범위 안인 씨앗을 고정하고 같은 범위 안 자손을 집계. 범위 밖 자손과 전역 생존 계보 수를 별도 열로 보존. 입력 칸은 가우시안 상태가 아니므로 원자료 수/넓이를 별도 표로 제공.')

if __name__=='__main__':main()
