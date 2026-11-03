"""Make the last interval strictly >4 m, using saved row distances only."""
from common import *
def main():
 records=[]
 for p in sorted((O/'scores').glob('*/values.json')):
  v=json.loads(p.read_text())
  if v.get('legacy') or not v.get('offsets') or 'lower_inclusive' in v['offsets'][0]:continue
  core=loadz(JA/'core_points'/f"{v['site']}__{v['prior']}.npz",['prior_height_m','mvs_mean_m','gt_p']);cell=loadz(CELLS/f"{v['site']}__{v['prior']}.npz",['cell_v2'])['cell_v2'];z=loadz(p.parent/'points.npz',['row_owner','row_distance_m','row_tau_m']);owner=z['row_owner'];valid=owner>=0;offsets=[];edge_n=0
  for j,name in [(1,'prior_height_m'),(2,'mvs_mean_m')]:
   delta=abs(core[name]-core['gt_p']);edge_n+=int(((cell==j)&(delta==4)).sum())
   for lo,hi in zip([0.,.5,1.,2.,4.],[.5,1.,2.,4.,np.inf]):
    mask=(cell==j)&((delta>lo) if lo==4 else (delta>=lo))&((delta<=hi) if hi==4 else (delta<hi));take=np.zeros(len(owner),bool);take[valid]=mask[owner[valid]];n=int(take.sum());offsets.append(dict(cell=j,lower_m=lo,upper_m=None if np.isinf(hi) else hi,lower_inclusive=lo!=4,upper_inclusive=hi==4,n_gt=n,completeness=float((z['row_distance_m'][take]<=z['row_tau_m'][take]).mean()) if n else None,patches=int(mask.sum())))
  old=p.with_name('values.before_offset_edges.json');assert not old.exists();old.write_text(p.read_text());v['offsets']=offsets;v['offset_recount']=dict(source=str(old),source_sha256=sha(old),exact_4m_patches=edge_n,rule='2<=offset<=4 and offset>4; lower bins retain half-open boundaries',source_code_sha256=sha(__file__));dump(p,v);records.append(dict(key=v['key'],exact_4m_patches=edge_n))
 table('offset_edge_recount',records)
if __name__=='__main__':main()
