"""Lossless script-tag packets, original report JSON, deterministic sample selection."""
import base64
import os
import shutil
import sys
import zlib
sys.path.insert(0, '/repo/scripts/phd/main_uncert_view_v1')
from common import *

BASE=['centre','normal','surf','roof_like','in_eval','cell','area','roof_type','code','kind',
      'gt_p','gt_status','gt_o','gt_n_inner','gt_runs','u_prior','errP','eL']
FIELDS=['status','p','u','a','s','q','n_col','n_inner_all','n_inner','views','n_ring','ring_found','ring_level',
        'thinned_inner','thinned_ring','quadrants','support_lmeds','support_final','e','qe','f']

def encode(a):
    a=np.ascontiguousarray(a)
    if a.dtype.kind in 'UOS':
        names, inv=np.unique(a.astype(str),return_inverse=True)
        return dict(strings=names.tolist(),index=encode(inv.astype(np.uint16).reshape(a.shape)))
    raw=a.tobytes()
    # Byte shuffle is reversible, including NaN payloads and original float precision.
    shuffled=np.frombuffer(raw,np.uint8).reshape(-1,a.dtype.itemsize).T.copy().tobytes()
    enc=base64.b64encode(zlib.compress(shuffled,9)).decode('ascii')
    return dict(dtype=a.dtype.str,shape=a.shape,data=enc,sha256=hashlib.sha256(raw).hexdigest())

def js(p,name,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(f'window.{name}='+json.dumps(clean(obj),ensure_ascii=False,separators=(',',':'),allow_nan=False)+';\n')

def case_places(site,prior):
    info=load(SRC/'work/places.json')['places']
    ans=[]
    with np.load(SRC/'work/places.npz') as z:
        for k in sorted(z.files):
            if not k.endswith('__'+prior): continue
            name=k.rsplit('__',1)[0]
            meta=info.get(k,info.get(name,{}))
            if meta.get('site','B173nb_b10') != site: continue
            ans.append(dict(id=name,label=meta.get('ko',name),indices=z[k].tolist()))
    return ans

def select_samples(z,site,prior,places,config):
    sc=config['samples']; rng=np.random.default_rng([config['seed'],U.SITE_ID[site],U.SET_ID[prior]])
    picked={}
    def add(ids,reason):
        for i in ids: picked.setdefault(int(i),[]).append(reason)
    def sample(ids,n,reason):
        ids=np.sort(np.asarray(ids,dtype=int)); add(rng.choice(ids,min(n,len(ids)),replace=False),reason)
    ev=z['in_eval'].astype(bool); valid=ev&(z['mvs_a_status']==0)
    for c in range(len(U.CELLS)): sample(np.flatnonzero(valid&(z['cell']==c)),sc['cell_count'],'cell:'+U.CELLS[c])
    for p in places: sample(p['indices'],sc['place_count'],'place:'+p['id'])
    e=z['mvs_a_e']; u=z['mvs_a_u']
    with np.errstate(divide='ignore',invalid='ignore'): ratio=e/u
    m=valid&np.isfinite(e)&(e>.2)&(e>2*u)
    idx=np.flatnonzero(m); add(idx[np.argsort(-ratio[idx],kind='stable')[:sc['missed_top']]],'missed:e/u')
    idx=np.flatnonzero(ev&np.isfinite(z['z_a']));add(idx[np.argsort(-z['z_a'][idx],kind='stable')[:sc['z_top']]],'z')
    if prior=='LoD2':
        for rt in sorted(set(z['roof_type'][ev].tolist())):
            if rt: sample(np.flatnonzero(valid&z['roof_like'].astype(bool)&(z['roof_type']==rt)),sc['roof_type_count'],'roof:'+rt)
    return dict(indices=sorted(picked),reasons=picked)

def main():
    config=load(CFG/'view_v1.json'); assert sha(CFG/'view_v1.json')==load(CFG/'view_v1.lock.json')['sha256']
    web=OUT/'web'; web.mkdir(exist_ok=True)
    manifest=dict(config=config,config_sha256=sha(CFG/'view_v1.json'),cells=U.CELLS,cell_labels=U.CELL_KO,
        roof_types=U.CFG['patch']['roof_type_ko'],cases=[],scientific_verdict=None)
    sample_index={}; sizes=[]
    for site,prior in U.CASES:
        ident=site+'__'+prior; blobs=[]; dedup={}; rings={}; keys=set()
        for r in config['radii']:
            z=pv(site,prior,r); arrays={}
            wanted=BASE+[d+'_'+f for d in L.DATAS[prior] for f in FIELDS]+[k+'_'+v for k in ('w','z','errW','errM') for v in 'ab']
            for k in wanted:
                if k not in z: continue
                a=z[k]; sig=(a.dtype.str,a.shape,hashlib.sha256(a.tobytes()).hexdigest())
                if sig not in dedup: dedup[sig]=len(blobs);blobs.append(encode(a))
                arrays[k]=dedup[sig]; keys.add(k)
            rings[str(r)]=arrays
        places=case_places(site,prior); z=pv(site,prior,config['default_radii'][site])
        samples=select_samples(z,site,prior,places,config);sample_index[ident]=samples
        packet=dict(id=ident,n=len(z['centre']),blobs=blobs,rings=rings,places=places,samples=samples['indices'])
        path=web/'data'/f'{ident}.js';js(path,'UNCERT_PACKET',packet)
        sz=path.stat().st_size; sizes.append(dict(case=ident,bytes=sz))
        manifest['cases'].append(dict(id=ident,site=site,prior=prior,label=U.case_ko(site,prior),n=len(z['centre']),
            eval=int(z['in_eval'].sum()),band=int((~z['in_eval'].astype(bool)).sum()),file='data/'+path.name,bytes=sz,keys=sorted(keys),sample_count=len(samples['indices'])))
        print(ident,'patches',len(z['centre']),'MB',round(sz/1e6,2),'samples',len(samples['indices']),flush=True)
    tables={}
    troot=ROOT/'docs/experiments/phd/main_uncert_v1/tables'
    for folder in ['R1.0','R1.5','R3.0','R_chosen_per_site']:
        tables[folder]={p.stem:load(p) for p in sorted((troot/folder).glob('*.json'))}
    tables['answers']=load(troot/'answers.json')
    js(web/'reports.js','UNCERT_REPORTS',tables)
    js(web/'manifest.js','UNCERT_MANIFEST',manifest)
    dump(OUT/'sample_index.json',sample_index)
    dump(DOC/'tables/bundle_data.json',dict(made=now(),files=sizes,bytes=sum(x['bytes'] for x in sizes),source_values_changed=False,scientific_verdict=None))
    total=sum(p.stat().st_size for p in web.rglob('*') if p.is_file())
    if total>config['encoding']['limit_bytes']: raise SystemExit(f'STOP_SIZE: {total}; no thinning or precision change authorized')
    progress(f'일 2 자료 묶음 완료: {total/1e6:.1f} MB, 원본 수치 정밀도 유지. 여섯 경우 표본 목록 고정. 단면·화면 파일 추가 전 크기.')

if __name__=='__main__':main()
