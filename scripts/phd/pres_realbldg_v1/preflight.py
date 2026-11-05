"""Freeze the supplied configuration; inspect only source metadata and schemas."""
import ast, datetime as dt, hashlib, json, os, sys, zipfile
from pathlib import Path
import numpy as np
C,D,O,R=map(Path,['/cfg','/docs','/pres','/repo'])
PH=Path('/art/phase-payloads/phd')
def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def dump(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def schema(p):
    out={}
    with zipfile.ZipFile(p) as z:
        for n in z.namelist():
            if not n.endswith('.npy'):continue
            with z.open(n) as f: v=np.lib.format.read_magic(f);s,o,d=np.lib.format._read_array_header(f,v)
            out[n[:-4]]=dict(shape=s,dtype=str(d))
    return out
def main():
    lock=C/'realbldg_v1.initial.lock.json'
    if not lock.exists():dump(lock,dict(saved_at=now(),config_sha256=sha(C/'realbldg_v1.json'),order_sha256=sha(D/'provenance/order_v1.txt'),source_commit=os.environ['PRES_COMMIT'],image=os.environ['PRES_IMAGE'],calculation_started=False,scientific_verdict=None))
    assert json.loads(lock.read_text())['config_sha256']==sha(C/'realbldg_v1.json')
    records=[]
    for task,patterns in {
      'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1':['scenes/*/stage1_cells.npz','scenes/*/rows.npz','scenes/*/preservation_features.npz','targets_gt/*.json'],
      'main_recount_v1/PHD-MAIN-RECOUNT-v1':['scenes/*/reference_rows.npz'],
      'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1':['core_points/*.npz'],
      'main_widen0_v2/PHD-MAIN-WIDEN0-v2':['scope_split.json','building_split.json','inputs/lod2_buildings.json','patch_values/*.npz','holdout/patch_values/*.npz'],
      'main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1':['r2/core_points/*.npz','r1/inputs/*.npz'],
    }.items():
        root=PH/task
        for pattern in patterns:
            files=sorted(root.glob(pattern));print(task,pattern,'files',len(files),flush=True)
            for i,p in enumerate(files):
                rec=dict(path=str(p),bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns)
                if p.suffix=='.npz' and (i==0 or task.startswith(('main_gtjudge','main_recount','main_judgeapply'))):rec['schema']=schema(p)
                if task.startswith('main_gtjudge') or p.suffix=='.json':rec['sha256']=sha(p)
                records.append(rec)
                if i==0:print(json.dumps(rec,ensure_ascii=False),flush=True)
    dump(D/'provenance/input_inventory.json',dict(at=now(),files=records,scientific_verdict=None))
    w=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2';raw=PH.parent/'p0-audit/data'
    paths=[w/'image_split.json',w/'inputs/image_inventory.json',w/'mvs/full/sparse/images.bin',w/'mvs/full/sparse/cameras.bin',raw/'work/mvs/colmap_input_db_ids/cameras.txt',raw/'work/mvs/colmap_dense/sparse/images.bin',raw/'raw/uav/Images.zip']
    photo=[]
    for p in paths:
        rec=dict(path=str(p),exists=p.exists())
        if p.exists():rec.update(bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns)
        if p.exists() and p.suffix!='.zip':rec['sha256']=sha(p)
        photo.append(rec)
    dump(D/'provenance/photo_inputs.json',dict(at=now(),files=photo,scientific_verdict=None));print('PHOTO_FILES',all(x['exists'] for x in photo))
    dump(D/'provenance/runtime.json',dict(at=now(),python=sys.version,numpy=np.__version__,image=os.environ['PRES_IMAGE'],commit=os.environ['PRES_COMMIT'],gpu_devices=list(map(str,Path('/dev').glob('nvidia*'))),cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),scientific_verdict=None))
if __name__=='__main__':main()
