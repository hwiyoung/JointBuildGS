"""Frozen inputs and exact patch-level summaries for interview addendum 2."""
import ast
import csv
from mesh_common import *
from interview_probe import model

IDOC=D/'interview_v2'; IOUT=O/'interview_v2'
FD=PH/'main_floatdiag_v1/PHD-MAIN-FLOATDIAG-v1'
SITES=['B0_b10','B173nb_b10','R1rep_b10']; PRIORS=['ALS','LoD2']
SHORT={'B0_b10':'B0','B173nb_b10':'B173','R1rep_b10':'R1'}
NAMES={'nojudge':'기준선', 'lt_dynnow':'혼합 우도 · 범주별', 'imgonly_2dgs_s0':'2DGS',
       'geogs_ALS_fix1':'GeoGS','trust_LoD2_fix1':'GeoGS'}
CAT_KO=['τ 안','뜬 면','MVS 쪽','사전 정보 쪽','그 밖·면 없음']

def config():
    p=C/'interview_addendum_v2.json';lock=p.with_suffix('.lock.json')
    assert lock.exists() and sha(p)==json.loads(lock.read_text())['sha256']
    return json.loads(p.read_text())

def source(path):
    path=Path(path);return dict(path=str(path),sha256=sha(path),bytes=path.stat().st_size)

def frozen_function(path,name,namespace):
    node=next(x for x in ast.parse(Path(path).read_text()).body if isinstance(x,ast.FunctionDef) and x.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
    return namespace[name]

def evaluation(site,prior):
    root=LT/'direct_stage1_v2'/f'{site}__{prior}'
    with np.load(root/'evaluation.npz') as z:e={k:z[k] for k in z.files}
    with np.load(root/'values.npz') as z:v={k:z[k] for k in z.files}
    return e,v,root

def patch_values(site,prior,result,e):
    key=f'{site}__{prior}__{result}'
    p=LT/'patch_z'/f'{key}.npz'
    if p.exists():
        with np.load(p) as f:z={k:f[k] for k in f.files}
        expected=np.array([f'stage1:{site}:{prior}:{i}' for i in range(len(e['area']))])
        assert np.array_equal(z['patch_id'],expected),key
        receipt=p.with_suffix('.json')
        if receipt.exists():
            rec=json.loads(receipt.read_text());assert rec['patch_z_sha256']==sha(p)
        return z,p
    p=O/'patch_z'/f'{key}__before.npz'
    rec=D/'tables/meshes'/f'{key}.json'
    assert p.exists() and rec.exists(),f'missing scored mesh values: {key}'
    rr=json.loads(rec.read_text());assert rr['status']=='PASS'
    assert rr['target']['evaluation_sha256']==sha(LT/'direct_stage1_v2'/f'{site}__{prior}/evaluation.npz')
    with np.load(p) as f:z={k:f[k] for k in f.files}
    assert len(z['z'])==len(e['area'])
    return z,p

def eligible(e):return e['in_eval']&e['scoring_allowed']

def summary(e,z,mask,**labels):
    cat=classes(e,z);area=float(e['area'][mask].sum())
    row=dict(**labels,patches=int(mask.sum()),area_m2=area)
    for i,k in enumerate(CATEGORIES):
        m=mask&(cat==i);a=float(e['area'][m].sum())
        row.update({k+'_patches':int(m.sum()),k+'_area_m2':a,k+'_pct':100*a/area if area else None})
    a=float(e['area'][mask&z['no_surface']].sum());row.update(no_surface_area_m2=a,no_surface_pct=100*a/area if area else None)
    assert np.isclose(sum(row[k+'_area_m2'] for k in CATEGORIES),area,rtol=1e-10,atol=1e-7)
    return row

def write_table(name,rows,notes=()):
    root=IDOC/'tables';root.mkdir(parents=True,exist_ok=True)
    dump(root/(name+'.json'),dict(rows=rows,notes=list(notes),created_at=now(),scientific_verdict=None))
    if not rows:return
    columns=list(dict.fromkeys(k for row in rows for k in row))
    with (root/(name+'.csv.tmp')).open('w') as f:
        w=csv.DictWriter(f,columns,lineterminator='\n');w.writeheader();w.writerows(rows)
    (root/(name+'.csv.tmp')).replace(root/(name+'.csv'))

def record(job,status='PASS',**extra):
    data=dict(job=job,status=status,at=now(),scientific_verdict=None,**extra)
    dump(IDOC/'status'/f'{job}.json',data);print(json.dumps(safe(data),ensure_ascii=False),flush=True)
    return data

def method_name(result):
    for prefix,label in NAMES.items():
        if result==prefix or result.startswith(prefix+'_'):return label
    if result.startswith('mvsfuse'):return '결합'
    if result.startswith('cdgs'):return 'CDGS'
    return result

def scored_mesh(site,prior,result):
    key=f'{site}__{prior}__{result}'
    row=next((r for r in mesh_config()['targets'] if r['key']==key),None)
    if row:return Path(row['mesh']),dict(expected_sha256=row.get('sha256'))
    return resolve(site,prior,result)
