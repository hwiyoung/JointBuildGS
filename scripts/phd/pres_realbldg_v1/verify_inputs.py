"""Independent source preservation and duplicate/reference-grid audits."""
from common import *
rows=[];population=[]
for p in sorted((O/'data').glob('*.npz')):
    kinds=loadz(p,['kind'])['kind'];values,counts=np.unique(kinds,return_counts=True)
    population.append(dict(scene=p.stem,kind_counts={str(int(k)):int(n) for k,n in zip(values,counts)},ground_rows=int((~np.isin(kinds,[1,2])).sum())))
    if p.stem.startswith('outside'):continue
    d=loadz(p,['xyz','case','area','building','grid_key','owner','kind']);q,inv,count=np.unique(d['xyz'],axis=0,return_inverse=True,return_counts=True)
    row=dict(scene=p.stem,rows=len(d['xyz']),unique_xyz=len(q),duplicate_rows=int(len(d['xyz'])-len(q)),grid_area_m2=float(d['area'].sum()),row_case_conflicts=0,unassigned_wall_rows=int(((d['owner']<0)&(d['kind']==2)).sum()))
    for c in np.unique(d['case']):
        m=d['case']==c;total=len(set(map(tuple,d['grid_key'][m])))*.0625;assert total==d['area'][m].sum()
        bybuilding=sum(float(d['area'][m&(d['building']==b)].sum()) for b in np.unique(d['building']));assert total==bybuilding
    lo=np.full(len(q),999);hi=np.full(len(q),-999);np.minimum.at(lo,inv,d['case']);np.maximum.at(hi,inv,d['case']);row['row_case_conflicts']=int((lo!=hi).sum());rows.append(row)
table('reference_grid_audit',rows)
dump(D/'provenance/saved_population.json',dict(scenes=population,scope='Existing saved cases only; no new ground cases',scientific_verdict=None))
sources={x['path']:x for p in (O/'data').glob('*.json') for x in json.loads(p.read_text())['sources']}
results=[dict(path=p,sha256=v['sha256'],unchanged=sha(p)==v['sha256']) for p,v in sources.items()];assert all(x['unchanged'] for x in results)
dump(D/'provenance/source_preservation.json',dict(at=now(),sources=results,scientific_verdict=None));print('SOURCE_PRESERVATION',len(results));print(json.dumps(rows,ensure_ascii=False));print(json.dumps(population))
