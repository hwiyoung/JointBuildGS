"""Read-only inventory for the 2026-10-29 interview addendum, in Docker."""
from mesh_common import *
import zipfile

def brief(path):
    path=Path(path)
    if not path.exists():return dict(path=str(path),status='ABSENT')
    arrays={}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            with z.open(name) as f:
                version=np.lib.format.read_magic(f)
                shape,order,dtype=np.lib.format._read_array_header(f,version)
            arrays[name[:-4]]=dict(shape=shape,dtype=str(dtype))
    return dict(path=str(path),bytes=path.stat().st_size,arrays=arrays)

def model(site,prior,prefix):
    result=f'{prefix}_{prior}_s0'
    if prefix=='lt_dynnow':
        root=LT/'runs'/site/result
        receipt=root/'PASS.json'
        return root/f"attempt_{json.loads(receipt.read_text())['attempt']}"/'model' if receipt.exists() else None
    root=S3/'runs'/site/result
    if root.with_name(result+'.finite').exists():root=root.with_name(result+'.finite')
    return root/'model'

def main():
    units=[]
    for site in ['B0_b10','B173nb_b10','R1rep_b10']:
        for prior in ['ALS','LoD2']:
            base=LT/'direct_stage1_v2'/f'{site}__{prior}'
            row=dict(site=site,prior=prior,evaluation=brief(base/'evaluation.npz'),values=brief(base/'values.npz'),
                     region=brief(S1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz'),results=[])
            for prefix in ['nojudge','lt_dynnow']:
                result=f'{prefix}_{prior}_s0';mp=model(site,prior,prefix);mesh,receipt=resolve(site,prior,result)
                root=mp.parent if prefix=='nojudge' else mp.parent.parent
                candidates=[root/'gpu/virtual/mesh_virtual.ply',root/'gpu/mesh_virtual.ply']
                row['results'].append(dict(result=result,model=str(mp),mesh=str(mesh),mesh_exists=mesh.exists(),
                    source_receipt=receipt,patch_z=brief(LT/'patch_z'/f'{site}__{prior}__{result}.npz'),
                    dump=brief(mp/'dump/iteration_30000/gaussians.npz'),
                    virtual=[dict(path=str(p),bytes=p.stat().st_size) for p in candidates if p.exists()]))
            units.append(row)
    dump(D/'interview_v2/input_probe.json',dict(created_at=now(),units=units,scientific_verdict=None))
    for u in units:
        print(u['site'],u['prior'],'eval',u['evaluation']['arrays'],'values',list(u['values']['arrays']),flush=True)
        for r in u['results']:print(r['result'],'dump',r['dump'].get('arrays'),'virtual',r['virtual'],flush=True)

if __name__=='__main__':main()
