"""Independent ZIP parts below 400 MB; explicit allowlist excludes holdout payloads."""
import zipfile,time,hashlib
from common import *
def archives(kind,files):
    limit=399000000;parts=[];current=[];size=0
    for path,name in files:
        n=path.stat().st_size+len(name.encode())*4+1024
        assert n<limit,('single source exceeds part limit',path,n)
        if current and size+n>limit:parts.append(current);current=[];size=0
        current.append((path,name));size+=n
    if current:parts.append(current)
    records=[]
    for i,items in enumerate(parts):
        name=f'PHD-MAIN-PHOTOCHECK-v1_{kind}'+(f'_part{i+1:03d}' if len(parts)>1 else '')+'.zip';dest=O/name
        sums=''.join(f'{sha(p)}  {arc}\n' for p,arc in items)
        with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
            for p,arc in items:
                assert 'holdout' not in Path(arc).parts
                z.write(p,arc,compress_type=zipfile.ZIP_STORED if p.suffix in ['.png','.npz'] else zipfile.ZIP_DEFLATED)
            z.writestr('SHA256SUMS',sums)
            z.writestr('묶음_읽기.txt',f'PHD-MAIN-PHOTOCHECK-v1 {kind} {i+1}/{len(parts)}\n각 ZIP은 독립적으로 열립니다. 같은 폴더에 모두 풀면 전체 구성이 됩니다. ZIP 파일을 이어 붙이지 않습니다.\n확인용의 점·패치 값과 판단은 포함하지 않았습니다.\nscientific_verdict: null\n')
        assert dest.stat().st_size<400000000,(dest,dest.stat().st_size)
        with zipfile.ZipFile(dest) as z:
            for line in sums.splitlines():
                expected,arc=line.split('  ',1);h=hashlib.sha256()
                with z.open(arc) as f:
                    for b in iter(lambda:f.read(4<<20),b''):h.update(b)
                assert h.hexdigest()==expected,arc
            assert z.testzip() is None
        records.append(dict(file=name,part=i+1,parts=len(parts),bytes=dest.stat().st_size,members=len(items)+2,sha256=sha(dest),member_sha256_verified=True,CRC_verified=True,holdout_included=False))
        print('archive verified',name,dest.stat().st_size,flush=True)
    return records
def main():
    assert load(O/'gates/delivery.json')['status']=='PASS'
    assert load(O/'gates/visual.json')['status']=='PASS'
    start=time.monotonic();files=[]
    for root,prefix in [(D,'docs'),(C,'configs'),(S,'scripts')]:
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.suffix in ['.md','.json','.csv','.png','.py','.sh']:
                files.append((p,f'{prefix}/{p.relative_to(root)}'))
    extra=[]
    for sub in ['points','patches']:
        for p in sorted((O/sub).glob('*.npz')):
            if sub=='points':
                with np.load(p) as z:assert not z['holdout'].any()
            extra.append((p,f'{sub}/{p.name}'))
    records=archives('handover_light',files)+archives('handover',files+extra)
    dump(O/'handover_manifest.json',dict(archives=records,at=now(),seconds=time.monotonic()-start,light='reports tables figures settings source scripts',full_adds='development point curves and patch judgments',scientific_verdict=None))
    (O/'SHA256SUMS').write_text(''.join(f'{r["sha256"]}  {r["file"]}\n' for r in records))
    print('all delivery parts verified',len(records))
if __name__=='__main__':main()
