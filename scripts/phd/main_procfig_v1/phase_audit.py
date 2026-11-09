from common import *
rows=[]
for it in [7000,15000,30000]:
 s=loadz(MODEL/f'target_monitor/snapshot_{it}.npz',['xyz','opacity','scale','rotation','init_id','origin','target_tag','target_index']);g=loadz(O/'work'/f'state_{it}.npz');same=len(s['xyz'])==len(g['xyz']);row=dict(iteration=it,snapshot_count=len(s['xyz']),checkpoint_count=len(g['xyz']),same_count=same)
 if same:
  for k in s:row[k+'_exact']=bool(np.array_equal(s[k],g[k]));row[k+'_max_abs_difference']=float(np.max(abs(s[k].astype(float)-g[k])))
 rows.append(row)
dump(D/'saved_phase_audit.json',dict(rows=rows,scientific_verdict=None));print('PHASE_AUDIT',[(r['iteration'],r['snapshot_count'],r['checkpoint_count'],r.get('xyz_max_abs_difference')) for r in rows])
