"""Read-only source/schema/frame inspection; no judgment or photo calculation."""
from common import *
import zipfile
def schema(p):
    with np.load(p) as z:return {k:dict(shape=list(z[k].shape),dtype=str(z[k].dtype)) for k in z.files}
def main():
    c=cfg();rows=[]
    for site in c['sites']:
        point=UN/'points'/site
        rec=json.loads((point/'mvs_a.json').read_text())
        f=S0/'fork_inputs/s61'/site
        row=dict(site=site,point_metadata={k:rec[k] for k in ['n_points','views','depth_dir','conf_dir','cameras','crop_rect_uv']},patches={})
        for prior in c['priors']:
            p=TG/'stage0_r1/inputs'/f'{site}_{prior}.npz'
            row['patches'][prior]=dict(path=str(p),sha256=sha(p),schema=schema(p))
            for rel in [f'r8/targets/{site}_{prior}.npz',f'r7/targets/{site}_{prior}.npz']:
                q=TG/rel
                if q.exists():row['patches'][prior][rel]=dict(sha256=sha(q),schema=schema(q))
        for name in ['mvs_a_xyz.npy','mvs_a_view.npy','mvs_a_key.npy','als_xyz.npy','gt_xyz.npy']:
            p=point/name;v=np.load(p,mmap_mode='r');row[name]=dict(shape=list(v.shape),bytes=p.stat().st_size)
        cal=json.loads((f/'scene_LoD2/jbgs_calibration.json').read_text());split=json.loads((f/'split.json').read_text())
        name=sorted(split['train'])[0]
        row['camera_example']=dict(name=name,calibration=cal['images'][name],split_counts={k:len(v) for k,v in split.items() if isinstance(v,list)})
        row['source_mesh_candidates']=[str(p) for p in (S1/'defs'/site).glob('*') if p.is_file()]
        rows.append(row)
    dump(O/'input_inventory.json',dict(at=now(),rows=rows,scientific_verdict=None))
    for row in rows:
        print(json.dumps(row,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
