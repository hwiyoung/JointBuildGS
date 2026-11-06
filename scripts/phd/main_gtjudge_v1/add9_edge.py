"""Select the expressly requested second c3 line using frozen row scores."""
from add9_common import *
from normal_line import tangents
from shapely.geometry import LineString

def main():
 ec=json.loads((C/'addendum9_edge_population.json').read_text());assert sha(C/'addendum9_edge_population.json')==json.loads((C/'addendum9_edge_population.lock.json').read_text())['config_sha256']
 c=case('c3');row,lab=data(c);P=row['xyz'];feat=loadz(root_of(c)/'preservation_features.npz');target=lab==2;edgeonly=target&(feat['quadrant']==2);tp=FT/'targets'/f"{c['site']}__{c['prior']}.npz";t=loadz(tp);valid=np.isfinite(t['prior_height_m'])&np.isfinite(t['normal']).all(1);Q=t['centre'][valid]+t['prior_height_m'][valid,None]*t['normal'][valid];aa,bb=tangents(t['normal'][valid]);tree=cKDTree(t['centre'][valid]);edge=np.zeros(len(Q),bool)
 for dr in [aa,-aa,bb,-bb]:
  dist,ix=tree.query(t['centre'][valid]+.25*dr,workers=2);edge|=(dist>.125)|(abs(Q[ix,2]-Q[:,2])>.5)
 E=Q[edge,:2];etree=cKDTree(E);centers=P[edgeonly,:2];_,ix=np.unique(np.rint(centers/.25).astype('i8'),axis=0,return_index=True);centers=centers[ix];targetP=P[target];current=line9('c3');old=LineString([current['section']['start'],current['section']['end']]);targets=A6['targets']['c3'];distances=scores(c,list(targets));rows=[];sections={};ms=list(targets)
 for k,mid in enumerate(centers):
  ei=etree.query_ball_point(mid,2.);near=E[ei]
  if len(near)<3:continue
  ev,vec=np.linalg.eigh(np.cov(near.T));edgeaxis=vec[:,-1];dr=np.array([-edgeaxis[1],edgeaxis[0]])
  if dr[np.argmax(abs(dr))]<0:dr=-dr
  for length in A9['edge']['lengths_m']:
   a,b=mid-length/2*dr,mid+length/2*dr;s=dict(start=a.tolist(),end=b.tolist(),length_m=float(length),half_width=.5);distance=old.distance(LineString([a,b]));mask=section_mask(targetP,s);n=int(mask.sum());full=np.flatnonzero(target)[mask];uid=f'edge_{k:04d}_{length}';r=dict(candidate_id=uid,A_x=a[0],A_y=a[1],Aprime_x=b[0],Aprime_y=b[1],length_m=length,distance_from_current_segment_m=distance,n_case2=n,n_edge_only=int((feat['quadrant'][full]==2).sum()),eligible=n>=20 and distance>5 and int((feat['quadrant'][full]==2).sum())>=ec['minimum_edge_only_points'],edge_local_PCA_eigenvalues=ev.tolist())
   for m,z in distances.items():r[m+'_completeness_pct']=values(z[full],row['row_tau_m'][full])['within_pct']
   r['rank_pass']=bool(n and all(r[a+'_completeness_pct']+A6['ranking_tolerance_pp']>=r[b+'_completeness_pct']-1e-10 for i,a in enumerate(ms) for b in ms[i+1:]));r['score_sum_abs_pp']=float(sum(abs(r[m+'_completeness_pct']-v) for m,v in targets.items())) if n else None;rows.append(r);sections[uid]=s
 eligible=[r for r in rows if r['eligible']];ranked=[r for r in eligible if r['rank_pass']];assert eligible,'No 20-point candidate >5m from current line';best=min(ranked or eligible,key=lambda r:(r['score_sum_abs_pp'],-r['n_case2'],r['candidate_id']));s=sections[best['candidate_id']];mask=section_mask(P,s);ids=np.flatnonzero(mask);z=float(np.median(P[mask&target,2]));xy=np.linspace(s['start'],s['end'],257);ann=np.c_[xy,np.full(len(xy),z)];roof=mask&~row['wall'];near=cKDTree(P[roof,:2]).query(xy)[1];ann[:,2]=P[roof,2][near]+.03
 rec=dict(case=c['id'],section=s,annotation_xyz=ann.tolist(),selection=best,rank_fallback=not bool(ranked),candidate_count=len(rows),eligible_count=len(eligible),rank_pass_count=len(ranked),targets=targets,reference_rows_all_cases=len(ids),A_EPSG25832_xy=(np.array(s['start'])+SHIFT[:2]).tolist(),Aprime_EPSG25832_xy=(np.array(s['end'])+SHIFT[:2]).tolist(),scientific_verdict=None,sources=[proof(tp),proof(root_of(c)/'preservation_features.npz')]);dump(W9/'edge_selected.json',rec);dump(W9/'edge_candidates.json',dict(candidates=rows));print('ADD9_EDGE_SELECTED',json.dumps(rec['selection']),flush=True)
if __name__=='__main__':main()
