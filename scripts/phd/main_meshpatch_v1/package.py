"""Immutable deliverables with CRC and SHA-256 verification; no raw inputs."""
import argparse,zipfile
from mesh_common import *

def package(kind):
    files=[]
    if kind=='patch':
        for prior in ['ALS','LoD2']:
            v=json.loads((D/'tables'/f'patch_{prior}_validation.json').read_text());assert v['status']=='PASS'
            for ext in ['npz','csv.gz']:files.append((O/'patch_table'/f'{prior}_patch_table.{ext}',f'patch_table/{prior}_patch_table.{ext}'))
        files +=[(p,'tables/'+p.name) for p in sorted((D/'tables').glob('*')) if p.is_file() and p.suffix in ['.json','.md']]
        files +=[(D/'패치표_열설명.md','패치표_열설명.md')]
        suffix='패치표'
    else:
        # Full handover includes all newly cleaned meshes, but no source models or imagery.
        targets=json.loads((C/'mesh_targets_v1.json').read_text())['targets']
        states=[]
        for r in targets:
            p=D/'tables/meshes'/f"{r['key']}.json"
            states.append(json.loads(p.read_text()) if p.exists() else dict(status='PENDING',target=r))
        assert all(r['status'] in ['PASS','UNAVAILABLE_FROZEN_STOP','UNAVAILABLE'] for r in states),'full handover requires all requested targets accounted for'
        figs=json.loads((D/'tables/case_figures.json').read_text());assert len(figs['cases'])==7 and all(x['status']=='PASS' for x in figs['cases'])
        for folder in ['mesh_post','patch_z','patch_table','case_meshes']:
            files +=[(p,folder+'/'+str(p.relative_to(O/folder))) for p in sorted((O/folder).rglob('*')) if p.is_file()]
        files +=[(p,'docs/'+str(p.relative_to(D))) for p in sorted(D.rglob('*')) if p.is_file()]
        suffix='handover'
    for dirname,root in [('configs',C),('scripts',R/'scripts/phd/main_meshpatch_v1')]:
        files +=[(p,dirname+'/'+str(p.relative_to(root))) for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
    for folder in ['track_a_v3/scripts','geogs_original']:
        files +=[(p,'received/'+str(p.relative_to(O/'received'))) for p in sorted((O/'received'/folder).rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
    for name in ['LoD2_evalseg.json','ALS_evalseg.json','cases.json']:
        p=O/'received/track_a_v3/results'/name;files.append((p,'received/track_a_v3/results/'+name))
    for name in ['메시정리와패치표_보고_v1.md','issues.md','progress.md']:
        if (D/name).exists():files.append((D/name,name))
    folder=O/'deliveries';folder.mkdir(exist_ok=True);dest=folder/f'PHD-MAIN-MESHPATCH-v1_{suffix}.zip'
    assert not dest.exists(),dest;temp=dest.with_suffix('.zip.tmp')
    manifest=[];seen=set()
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
        z.writestr('읽어주세요.md','# PHD-MAIN-MESHPATCH-v1\n\n[이 발주에서 냄]\n\n패치 표의 Roofer 면 수 대조는 미통과입니다. mvs_face_benchmark_passed=false를 확인하세요. 원본 값 보존 검사와 혼동하지 마세요. 새 가시성·영역 계산은 하지 않았습니다.\n\n보고서와 패치표_열설명.md를 먼저 읽으세요. 재계산에는 설정의 입력 경로·해시에 맞는 원본 자료가 필요합니다. 봉인 자료와 원본 학습 모델·영상은 포함하지 않습니다.\n\nscientific_verdict: null\n')
        for p,name in files:
            if name in seen:continue
            seen.add(name)
            if p.suffix in ['.md','.json','.py','.sh']:
                data=p.read_bytes();h=hashlib.sha256(data).hexdigest();size=len(data);z.writestr(name,data)
            else:h=sha(p);size=p.stat().st_size;z.write(p,name)
            manifest.append(dict(name=name,bytes=size,sha256=h))
        z.writestr('manifest.json',json.dumps(dict(task_id='PHD-MAIN-MESHPATCH-v1',created_at=now(),files=manifest,scientific_verdict=None),ensure_ascii=False,indent=2))
    with zipfile.ZipFile(temp) as z:assert z.testzip() is None
    temp.replace(dest);digest=sha(dest);dest.with_suffix('.zip.sha256').write_text(digest+'  '+dest.name+'\n')
    receipt=dict(file=str(dest),bytes=dest.stat().st_size,sha256=digest,crc='PASS',created_at=now(),members=len(manifest)+2,scientific_verdict=None)
    dump(O/'status'/f'delivery_{kind}.json',receipt);print(json.dumps(receipt,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('kind',choices=['patch','handover']);package(p.parse_args().kind)
