"""Exact centre-plane cuts and saved per-row values, with a readable check plot."""
from add6_common import *

def pieces(seg):
 # Join coincident triangle intersections only; never interpolate across a gap.
 keys=np.rint(seg.reshape(-1,2)/1e-6).astype('i8');_,first,inv=np.unique(keys,axis=0,return_index=True,return_inverse=True);points=seg.reshape(-1,2)[first];edges=inv.reshape(-1,2);edges=edges[edges[:,0]!=edges[:,1]];adj={}
 for i,(a,b) in enumerate(edges):adj.setdefault(a,[]).append(i);adj.setdefault(b,[]).append(i)
 used=set();out=[]
 def walk(start,e):
  path=[int(start)];node=start
  while e not in used:
   used.add(e);a,b=edges[e];node=b if node==a else a;path.append(int(node));remaining=[k for k in adj[node] if k not in used]
   if len(adj[node])!=2 or not remaining:break
   e=remaining[0]
  out.append(points[path].tolist())
 for node,es in adj.items():
  if len(es)!=2:
   for e in es:
    if e not in used:walk(node,e)
 for i,e in enumerate(edges):
  if i not in used:walk(e[0],i)
 return out

def main(key):
 c=case(key);rec=selected(c);s=rec['section'];root=root_of(c);row=loadz(root/'rows.npz');lab=loadz(root/'stage1_cells.npz')['case_id'];ids=loadz(W6/'selected'/f"{c['id']}.npz")['strip_row_ids'];P=row['xyz'][ids];direction=(np.array(s['end'])-s['start'])/s['length_m'];along=(P[:,:2]-s['start'])@direction;target=lab[ids]==c['case_id'];data={};segments={};metrics={};scores={};sources=[root/'rows.npz',root/'stage1_cells.npz',W6/'selected'/f"{c['id']}.json",C/'addendum6.json',Path(__file__)]
 for method in methods(c):
  p=meshpath(c,method);line_key=hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()[:16];cache=W6/'sections'/c['id']/line_key/f'{method}.npz'
  if cache.exists():seg=loadz(cache)['segments']
  else:
   V,F=read_surface(p);seg=clip_segments(section_segments(V,F,s),s['length_m']);savez(cache,segments=seg);del V,F;gc.collect()
  segments[method]=seg;data[method]=pieces(seg);dp=root/'distances'/f'{method}.npz';z=loadz(dp,['row_s'])['row_s'][ids];scores[method]=z;metrics[method]=values(z[target],row['row_tau_m'][ids][target]);sources.extend([p,dp]);print('ADD6_SECTION',c['id'],method,len(seg),flush=True)
 gt=[]
 for i,rid in enumerate(ids):gt.append(dict(row_id=int(rid),s=float(along[i]),z=float(P[i,2]),case_id=int(lab[rid]),tau_m=float(row['row_tau_m'][rid]),scores={m:dict(status=str(status(np.array([z[i]]),np.array([row['row_tau_m'][rid]]))[0]),signed_distance_m=float(z[i]) if np.isfinite(z[i]) else None) for m,z in scores.items()}))
 with (R/'docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv').open() as f:tau=next(x for x in csv.DictReader(f) if x['site']==c['site'] and x['prior']==c['prior'])
 line=dict(A_local_xyz=rec['line_xyz'][0],Aprime_local_xyz=rec['line_xyz'][1],A_EPSG25832_xy=(np.array(s['start'])+SHIFT[:2]).tolist(),Aprime_EPSG25832_xy=(np.array(s['end'])+SHIFT[:2]).tolist(),length_m=s['length_m'],direction=rec['selection']['direction'],direction_unit_xy=direction.tolist(),selection_rank=1,score_sum_abs_pp=rec['selection']['score_sum_abs_pp'],condition2_pass=rec['selection']['condition2_pass'],rank_fallback=rec['rank_fallback'])
 bounds=[0,s['length_m'],float(P[target,2].min()-2),float(P[target,2].max()+2)];W=1600;pad=48;pw=W-2*pad;ph=max(120,round(3*pw/s['length_m']*(bounds[3]-bounds[2])));gap=40;H=2*(ph+2*pad)+gap;im=Image.new('RGB',(W,H),'white');panelmeta=[]
 for panel,ms in enumerate([['prior','mvs'],[m for m in methods(c) if m not in ['prior','mvs']]]):
  tile=Image.new('RGB',(pw,ph),'white');draw=ImageDraw.Draw(tile)
  def project(q):q=np.asarray(q);return np.stack([q[...,0]/s['length_m']*(pw-1),(bounds[3]-q[...,1])/(bounds[3]-bounds[2])*(ph-1)],-1)
  for method in ms:
   for poly in data[method]:
    q=project(poly)
    if method=='judgment_mesh':
     for a,b in zip(q[:-1],q[1:]):
      length=np.linalg.norm(b-a);n=max(1,int(np.ceil(length/7)))
      for k in range(0,n,2):draw.line([tuple(a+(b-a)*k/n),tuple(a+(b-a)*min(k+1,n)/n)],fill=AC['method_colors'][method],width=3)
    else:draw.line([tuple(x) for x in q],fill=AC['method_colors'][method],width=3)
  q=project(np.c_[along,P[:,2]])
  for mask,col,radius in [(~target,'#d5d5d5',1.4),(target,'#3a3a3a',2.2)]:
   for x,y in q[mask]:draw.ellipse([x-radius,y-radius,x+radius,y+radius],fill=col)
  y=panel*(ph+2*pad+gap)+pad;im.paste(tile,(pad,y));panelmeta.append(dict(role='inputs' if panel==0 else 'results',methods=ms,plot_bounds_px=[pad,y,pad+pw,y+ph],axis_bounds=bounds,vertical_exaggeration=(ph/(bounds[3]-bounds[2]))/(pw/s['length_m']),A_px=[pad,y+(bounds[3]-rec['anchor_z'])/(bounds[3]-bounds[2])*ph],Aprime_px=[pad+pw,y+(bounds[3]-rec['anchor_z'])/(bounds[3]-bounds[2])*ph]))
 result=dict(case=c['id'],line=line,tau_m={'roof':float(tau['roof_tau_m']),'wall':float(tau['wall_tau_m'])},surfaces=data,gt_points=gt,strip_metrics=metrics,metric_population=f"only case_id={c['case_id']} among stored reference rows in the one-metre strip",reference_points_all_cases=len(ids),reference_points_target_case=int(target.sum()),intersection_rule='single vertical centre plane, no strip averaging; coincident endpoints joined at 1e-6m; all discontinuous pieces retained',section_check=dict(panels=panelmeta,z_limits_rule='target case reference Z range plus 2m on each end',geometry_outside_display_included_in_raw_data=True),sources=[proof(p) for p in sources],scientific_verdict=None)
 dump(F6/f"{c['id']}_section_data.json",result);png(im,c['id']+'_section_check',dict(case=c['id'],panels=panelmeta,A_px=panelmeta[0]['A_px'],Aprime_px=panelmeta[0]['Aprime_px'],box_corners_px=None,line_drawn=False),[F6/f"{c['id']}_section_data.json",Path(__file__)])
 print('ADD6_SECTION_DATA',c['id'],len(ids),int(target.sum()),im.size,flush=True)

if __name__=='__main__':main(sys.argv[1])
