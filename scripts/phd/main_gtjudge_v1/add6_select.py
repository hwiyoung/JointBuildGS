"""Pre-registered section selection from saved reference-row cases and distances."""
from add6_common import *
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.vectorized import contains

def main(key):
 c=case(key);key=c['id'].split('_')[0];root=root_of(c);row=loadz(root/'rows.npz');lab=loadz(root/'stage1_cells.npz')['case_id'];P=row['xyz'];case_mask=lab==c['case_id'];own=row['row_owner'];corep=JA/'core_points'/f"{c['site']}__{c['prior']}.npz";core=loadz(corep,['area','source_index','building']);valid=own>=0;counts=np.bincount(own[valid],minlength=len(core['area']));weight=np.zeros(len(P));weight[valid]=core['area'][own[valid]]/counts[own[valid]]
 wm=case_mask&(weight>0);center=np.average(P[wm,:2],axis=0,weights=weight[wm]);cov=np.cov(P[wm,:2].T,aweights=weight[wm]);ev,vec=np.linalg.eigh(cov);major=vec[:,-1]
 if major[np.argmax(abs(major))]<0:major=-major
 directions={'parallel':major,'perpendicular':np.array([-major[1],major[0]])};old=getcase(c);old_d=np.array(old['section']['end'])-old['section']['start'];directions['inherited']=old_d/np.linalg.norm(old_d)
 tp=FT/'targets'/f"{c['site']}__{c['prior']}.npz";target=loadz(tp,['centre','normal','kind','prior_height_m','in_eval']);ok=(target['kind']==1)&target['in_eval']&np.isfinite(target['prior_height_m'])&np.isfinite(target['normal']).all(1)&(np.linalg.norm(target['normal'],axis=1)>0);Q=target['centre'][ok]+target['normal'][ok]*target['prior_height_m'][ok,None]
 pairs=cKDTree(Q).query_pairs(A6['roof_boundary']['roof_group_connectivity_m'],output_type='ndarray');g=coo_matrix((np.ones(len(pairs),'u1'),(pairs[:,0],pairs[:,1])),shape=(len(Q),len(Q)));_,components=connected_components(g,directed=False)
 identity=np.full(len(ok),'',dtype=core['building'].dtype);identity[core['source_index']]=core['building'];identity=identity[ok]
 building_path=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/inputs/lod2_buildings.json';buildings={b['id']:b for b in json.loads(building_path.read_text())};missing=np.flatnonzero(identity=='');best=np.full(len(missing),np.inf)
 # Shared GroundSurface XY supplies identity only; it never supplies line ends or heights.
 for bid in sorted(set(core['building'])-{''}):
  polygon=unary_union([Polygon(np.asarray(p['ext'])[:,:2]-SHIFT[:2],[np.asarray(h)[:,:2]-SHIFT[:2] for h in p['holes'] if len(h)>3]).buffer(0) for p in buildings[str(bid)]['surfaces']['ground']]);inside=contains(polygon.buffer(1),Q[missing,0],Q[missing,1]);ii=np.flatnonzero(inside)
  if not len(ii):continue
  known=Q[identity==bid];distance=cKDTree(known).query(Q[missing[ii]],workers=2)[0] if len(known) else np.full(len(ii),np.inf);take=ii[distance<best[ii]];identity[missing[take]]=bid;best[take]=distance[distance<best[ii]]
 group_names=np.array([str(b) if b else 'unassigned_3d_'+str(k) for b,k in zip(identity,components)]);names,groups=np.unique(group_names,return_inverse=True);ng=len(names);qtree=cKDTree(Q);row_group=groups[qtree.query(P,workers=2)[1]]
 lookup=np.full(len(ok),-1,'i8');lookup[np.flatnonzero(ok)]=groups;assigned=np.full(len(P),-1,'i8');assigned[valid]=lookup[core['source_index'][own[valid]]];has=assigned>=0;row_group[has]=assigned[has]
 path=meshpath(c,'prior');V,F=read_surface(path);dist,idx=qtree.query(V,workers=2);tri=V[F];norm=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);length=np.linalg.norm(norm,axis=1);roof=(length>0)&(abs(norm@UP)>=np.cos(np.deg2rad(A6['roof_boundary']['roof_max_tilt_deg']))*length)&(dist[F].min(1)<=A6['roof_boundary']['prior_patch_radius_m']);faces=F[roof];centroids=V[faces].mean(1);face_group=groups[qtree.query(centroids,workers=2)[1]];del tri,norm;gc.collect()
 distances={m:loadz(root/'distances'/f'{m}.npz',['row_s'])['row_s'] for m in methods(c)};targets=A6['targets'][key];records=[];sections={}
 for name in A6['directions'][key]:
  direction=directions[name];side=np.array([-direction[1],direction[0]]);offset=(P[case_mask,:2]-center)@side
  for step in range(int(np.floor(offset.min())),int(np.ceil(offset.max()))+1):
   mid=center+step*side;band=abs((P[:,:2]-mid)@side)<=.5;present=np.unique(row_group[band&case_mask])
   for group in present:
    if str(names[group]).startswith('unassigned_'):continue
    ff=faces[face_group==group]
    if not len(ff):continue
    q=Q[groups==group];along=(q[:,:2]-mid)@direction;lo,hi=float(along.min()-5),float(along.max()+5);s0=dict(start=(mid+lo*direction).tolist(),end=(mid+hi*direction).tolist(),half_width=.5)
    segments=section_segments(V,ff,s0)
    if not len(segments):continue
    a=mid+(lo+segments[:,:,0].min()-1)*direction;b=mid+(lo+segments[:,:,0].max()+1)*direction;s=dict(start=a.tolist(),end=b.tolist(),half_width=.5,length_m=float(np.linalg.norm(b-a)))
    take=section_mask(P,s)&case_mask;n=int(take.sum());uid=f'{name}_{step:+05d}_g{group:04d}';rec=dict(candidate_id=uid,direction=name,offset_m=step,roof_group=int(group),building_identity=str(names[group]),center_x=float((a[0]+b[0])/2),center_y=float((a[1]+b[1])/2),A_x=a[0],A_y=a[1],Aprime_x=b[0],Aprime_y=b[1],length_m=s['length_m'],n_case_points=n,minimum_count_pass=n>=A6['minimum_points'][key])
    for m,z in distances.items():
     v=values(z[take],row['row_tau_m'][take])
     for field,target in [('within_pct','completeness_pct'),('far_hit_pct','far_pct'),('no_surface_pct','none_pct')]:rec[m+'_'+target]=v[field]
    ranked=list(targets);rec['condition2_pass']=bool(n and all(rec[a+'_completeness_pct']+A6['ranking_tolerance_pp']>=rec[b+'_completeness_pct']-1e-10 for i,a in enumerate(ranked) for b in ranked[i+1:]));rec['score_sum_abs_pp']=float(sum(abs(rec[m+'_completeness_pct']-v) for m,v in targets.items())) if n else None
    records.append(rec);sections[uid]=s
 table6('section_candidates_'+c['id'],records);eligible=[r for r in records if r['minimum_count_pass']];ordered=[r for r in eligible if r['condition2_pass']];pool=ordered or eligible
 if not pool:
  dump(W6/'selected'/f"{c['id']}.json",dict(status='UNAVAILABLE_MINIMUM_CASE_COUNT',candidate_n=len(records),maximum_n=max((r['n_case_points'] for r in records),default=0),scientific_verdict=None));print('ADD6_NO_ELIGIBLE',c['id'],flush=True);return
 pool=sorted(pool,key=lambda r:(r['score_sum_abs_pp'],-r['n_case_points'],r['candidate_id']));best=pool[0];s=sections[best['candidate_id']];take=section_mask(P,s);z=float(np.median(P[take&case_mask,2]));A=np.r_[s['start'],z];B=np.r_[s['end'],z];annotation_xyz=np.linspace(A,B,257)
 # Draping is metadata only; no new distances or changed case labels.
 ids=np.flatnonzero(take&(~row['wall']));near=cKDTree(P[ids,:2]).query(annotation_xyz[:,:2])[1];annotation_xyz[:,2]=P[ids[near],2]+.03
 sources=[root/'rows.npz',root/'stage1_cells.npz',corep,tp,path,building_path]+[root/'distances'/f'{m}.npz' for m in methods(c)]
 out=dict(case=c,section=s,selection=best,top3=pool[:3],top3_score_among_min_count=sorted(eligible,key=lambda r:(r['score_sum_abs_pp'],-r['n_case_points'],r['candidate_id']))[:3],rank_fallback=not bool(ordered),candidate_count=len(records),minimum_count_candidates=len(eligible),rank_pass_candidates=len(ordered),principal_axis_xy=major.tolist(),principal_eigenvalues=ev.tolist(),PCA_weight_rule=A6['PCA_weights'],PCA_unowned_case_rows=int((case_mask&~valid).sum()),roof_support_rule=A6['roof_boundary'],roof_faces_total=len(F),roof_faces_selected=len(faces),roof_groups=ng,anchor_z=z,line_xyz=[A.tolist(),B.tolist()],annotation_xyz=annotation_xyz.tolist(),sources=[proof(p) for p in sources],scientific_verdict=None)
 dump(W6/'selected'/f"{c['id']}.json",out);savez(W6/'selected'/f"{c['id']}.npz",strip_row_ids=np.flatnonzero(take),case_strip_row_ids=np.flatnonzero(take&case_mask));print('ADD6_SELECTED',c['id'],json.dumps(best),flush=True)

if __name__=='__main__':main(sys.argv[1])
