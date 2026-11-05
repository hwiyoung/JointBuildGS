"""Host stdlib-only source diff, boundary verification, and partial ZIP receipt."""
import ast
import datetime as dt
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

R=Path(__file__).resolve().parents[3]
ART=R.parent/'JointBuildGS-artifacts'
D=R/'docs/experiments/phd/main_gtjudge_v1'
C=R/'configs/phd/main_gtjudge_v1'
S=R/'scripts/phd/main_gtjudge_v1'
O=ART/'phase-payloads/phd/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
OLD=R/'src/phd/forks/GeoGS-conf-guided-v1-r23'
NEW=R/'src/phd/forks/GeoGS-conf-guided-v1-r25'
ALLOWED=['configs/phd/main_gtjudge_v1/','scripts/phd/main_gtjudge_v1/',
         'docs/experiments/phd/main_gtjudge_v1/','src/phd/forks/GeoGS-conf-guided-v1-r25/']

def now():return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(8<<20),b''):h.update(block)
    return h.hexdigest()

def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def source_diff():
    changes=[];pieces=[];parents={};new_hashes={};identical=0
    for p in sorted(NEW.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(NEW);parent=OLD/rel;new_hashes[str(rel)]=sha(p)
        if parent.exists():parents[str(rel)]=sha(parent)
        if parent.exists() and sha(parent)==sha(p):identical+=1;continue
        a=parent.read_text().splitlines(keepends=True) if parent.exists() else []
        b=p.read_text().splitlines(keepends=True)
        delta=list(difflib.unified_diff(a,b,fromfile=str(parent.relative_to(R)),tofile=str(p.relative_to(R))))
        pieces.extend(delta)
        hunks=[]
        for tag,a1,a2,b1,b2 in difflib.SequenceMatcher(a=a,b=b).get_opcodes():
            if tag!='equal':hunks.append(dict(operation=tag,old_start=a1+1,old_end=a2,new_start=b1+1,new_end=b2))
        changes.append(dict(file=str(p.relative_to(R)),sha256=sha(p),parent_sha256=parents.get(str(rel)),hunks=hunks))
    (D/'provenance/r23_to_r25.patch').write_text(''.join(pieces))
    dump(D/'provenance/r25_changed_lines.json',dict(at=now(),changes=changes,identical_files=identical,
        parent_hashes=parents,new_hashes=new_hashes,scientific_verdict=None))
    return changes

def verify():
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=R,text=True).strip()
    assert branch=='exp/main-experiment'
    status=subprocess.check_output(['git','status','--porcelain=v1','-z'],cwd=R)
    (D/'provenance/workspace_after.zlist').write_bytes(status)
    before=(D/'provenance/workspace_before.zlist').read_bytes()
    def outside(blob):
        # Renames outside scope are intentionally retained as complete raw entries.
        return {x for x in blob.split(b'\0') if x and not any(x[3:].startswith(p.encode()) for p in ALLOWED)}
    added=outside(status)-outside(before);removed=outside(before)-outside(status)
    assert not added and not removed,(added,removed)
    # Inherited score directories include absolute /out symlinks: verify them in
    # their original Docker namespace, without modifying links on the host.
    recheck=json.loads((D/'provenance/source_recheck.json').read_text())
    assert recheck['lock_sha256']==sha(D/'provenance/inspected_source_lock.json')
    assert recheck['status']=='PASS' and not recheck['changed']
    config_lock=json.loads((C/'gtjudge_v1.initial.lock.json').read_text())
    assert sha(C/'gtjudge_v1.json')==config_lock['config_sha256']
    unit=json.loads((D/'tables/unit_default.json').read_text())
    assert unit['model_and_Adam_bit_equal'] and unit['steps']==100
    decision=json.loads((D/'단계0_판정.json').read_text())
    assert not decision['stage0_complete'] and decision['measured_anomaly_signal'] is None
    assert not decision['nearest_fallback_applied']
    state=json.loads((D/'status.json').read_text())
    assert state['training_runs_started']==0 and state['status']=='PARTIAL_PREFLIGHT_ONLY'
    assert not (O/'targets_gt').exists() and not (O/'runs').exists()
    dump(D/'provenance/write_boundary.json',dict(at=now(),status='PASS_SCOPED_CHECK',
        inspected_sources_sha256_match=True,unrelated_status_entries_preserved=len(outside(before)),
        new_paths_outside_scope=[],removed_paths_outside_scope=[],
        limitation='Status comparison does not prove all unrelated dirty-file bytes unchanged; task Docker mounts original inputs read-only',
        scientific_verdict=None))
    return config_lock

def package():
    target=O/'delivery/PHD-MAIN-GTJUDGE-v1.zip'
    target.parent.mkdir(parents=True,exist_ok=True)
    assert not target.exists(),'Immutable delivery already exists'
    files=[]
    for root in [C,S,D,NEW]:
        files.extend(p for p in sorted(root.rglob('*')) if p.is_file()
            and p.suffix!='.pyc' and '__pycache__' not in p.parts
            and p.name not in ['delivery_receipt.json','git_delivery.json'])
    checks=''.join(f'{sha(p)}  {p.relative_to(R)}\n' for p in files)
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,str(p.relative_to(R)))
        z.writestr('SHA256SUMS',checks)
        z.writestr('PARTIAL_STATUS.txt','PARTIAL_PREFLIGHT_ONLY\nStages 0-3 incomplete; 0 experiment training runs.\nSee docs/experiments/phd/main_gtjudge_v1/보고.md\nscientific_verdict: null\n')
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for line in z.read('SHA256SUMS').decode().splitlines():
            digest,name=line.split('  ',1)
            assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
        members=len(z.namelist())
    receipt=dict(at=now(),path=str(target),sha256=sha(target),bytes=target.stat().st_size,members=members,
        crc='PASS',internal_sha256='PASS',status='PARTIAL_PREFLIGHT_ONLY',
        scientific_stages_complete=False,scientific_verdict=None)
    dump(D/'delivery_receipt.json',receipt)
    target.with_suffix('.zip.sha256').write_text(receipt['sha256']+'  '+target.name+'\n')
    print(json.dumps(receipt,ensure_ascii=False))

def main():
    changes=source_diff();lock=verify()
    dump(C/'preflight.final.lock.json',dict(at=now(),config_sha256=lock['config_sha256'],
        files={str(p.relative_to(R)):sha(p) for root in [S,NEW] for p in sorted(root.rglob('*'))
            if p.is_file() and p.suffix!='.pyc' and '__pycache__' not in p.parts},
        stage0_complete=False,scientific_verdict=None))
    (D/'provenance/changed_lines.md').write_text('# r23 → r25 바뀐 줄\n\n'
        '준비본. 실제 장면/전체 A-2 실행 검증은 미완료다. 아래 줄 번호는 r25다.\n\n'
        '| 파일 | 새 줄 |\n|---|---|\n'+''.join('| '+r['file']+' | '+', '.join(
            str(x['new_start'])+'–'+str(x['new_end']) for x in r['hunks'])+' |\n' for r in changes))
    package()

if __name__=='__main__':main()
