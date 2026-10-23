"""Validate split ownership and publish only permitted holdout aggregates/hashes."""
import json
from pathlib import Path
import zipfile
import numpy as np
from analysis_common import O,DOC,CFG,save_table
from preflight import sha,dump

def main():
    split=json.loads((O/'building_split.json').read_text());held=set(split['holdout']);dev=set(split['development']);rows=[];hashes=[]
    for sealed in [False,True]:
        root=O/('holdout/patch_values' if sealed else 'patch_values');seen=set()
        for prior in ['LoD2','ALS']:
            n=ng=0;area=0.;buildings=set();cells=np.zeros(7,np.int64);areas=np.zeros(7)
            for f in sorted(root.glob(f'*__{prior}__R1.5.npz')):
                with np.load(f) as z:
                    assert np.all(z['holdout']==sealed),f
                    assert set(z['building'])<=(held if sealed else dev),f
                    assert not seen.intersection(z['patch_id']);seen.update(z['patch_id'])
                    assert np.all((z['cell']>=0)&(z['cell']<7))
                    n+=len(z['cell']);ng+=int((z['gt_status']==0).sum());area+=float(z['area'].sum());buildings.update(z['building'])
                    cells+=np.bincount(z['cell'],minlength=7);areas+=np.bincount(z['cell'],weights=z['area'],minlength=7)
                if sealed:hashes.append(dict(file=str(f.relative_to(O/'holdout')),sha256=sha(f)))
            assert int(cells.sum())==n and np.isclose(areas.sum(),area,rtol=1e-12)
            row=dict(split='holdout' if sealed else 'development',prior=prior,buildings_with_assigned_patches=len(buildings),patches=n,area_m2=area,
                fraction_patches_with_GT=ng/n if n else None)
            if not sealed:row.update(cell_patches=cells.tolist(),cell_area_m2=areas.tolist())
            rows.append(row)
    # Compact sealed archives remain under holdout/. The two delivery archives
    # created later never contain these archives or any holdout payload.
    seals=[]
    for prior in ['LoD2','ALS']:
        files=sorted((O/'holdout/patch_values').glob(f'*__{prior}__R1.5.*'))+sorted((O/'holdout/components').glob(f'{prior}_*'))
        manifest=[dict(file=str(f.relative_to(O/'holdout')),sha256=sha(f)) for f in files]
        mf=O/'holdout'/f'{prior}_SHA256SUMS.json';dump(mf,dict(files=manifest,scientific_verdict=None))
        archive=O/'holdout'/f'{prior}_sealed.zip'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
            for f in files+[mf]:z.write(f,str(f.relative_to(O/'holdout')))
        seals.append(dict(file=f'holdout/{archive.name}',sha256=sha(archive),files=len(files),manifest_sha256=sha(mf)))
        hashes.extend(r for r in manifest if r not in hashes)
    save_table('확인용_봉인', [r for r in rows if r['split']=='holdout'],building_count=len(held),sealed_files=seals)
    save_table('확인용_파일해시',hashes)
    save_table('측정_합계',[r for r in rows if r['split']=='development'])
    forbidden=[]
    for f in DOC.rglob('*'):
        if f.suffix.lower() not in ['.json','.csv','.md']:continue
        text=f.read_text(encoding='utf-8-sig')
        if any(b in text for b in held):forbidden.append(str(f))
    assert not forbidden,forbidden
    for row in json.loads((DOC/'tables/시험자리_정하는곳.json').read_text())['rows']:assert set(row['building_ids'])<=dev
    for row in json.loads((DOC/'tables/대표자리_선정.json').read_text())['rows']:assert set(row['building_ids'])<=dev
    dump(O/'gates/final_values.json',dict(status='PASS',checks=['exclusive seven cells','100 percent area','unique patch IDs','building split for every patch','no holdout IDs in public text','development-only candidate/photo rows'],sealed_files=seals,scientific_verdict=None))
    print('value and seal checks PASS',flush=True)
if __name__=='__main__':main()
