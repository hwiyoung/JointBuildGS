"""Seal ZIP bytes, then commit/push only the explicit FINALTRAIN paths."""
import fcntl,hashlib,json,subprocess,sys,time,zipfile
from pathlib import Path
from gpu_job import R,O,C,D,now,dump
S=R/'scripts/phd/main_finaltrain_v1';F=R/'src/phd/forks/GeoGS-conf-guided-v1-r23'
SITES={'B173nb_b10':'B173주변','B0_b10':'B0','R1rep_b10':'R1'};PRIORS={'ALS':'항공LiDAR','LoD2':'LoD2'}
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def git(*args,check=True):
    for i in range(30):
        p=subprocess.run(['git',*map(str,args)],cwd=R,text=True,capture_output=True)
        if p.returncode==0 or not any(s in p.stderr for s in ['index.lock','could not lock','cannot lock ref']):break
        time.sleep(2)
    if check and p.returncode:raise RuntimeError(p.stdout+'\n'+p.stderr)
    return p

def source_check():
    """Check new edits against the frozen parent, preserving copied source bytes."""
    lock=json.loads((C/'runtime.lock.json').read_text())
    assert sha(C/'finaltrain_v1.json')==lock['config_sha256']
    for name,digest in lock['files'].items():
        path=R/Path(name).relative_to('/repo')
        assert sha(path)==digest,('Frozen runtime changed',name)
    parent=json.loads((C/'parent_source.lock.json').read_text())
    for name,digest in parent.items():assert sha(R/name)==digest,('Parent changed',name)
    oldroot=R/json.loads((C/'finaltrain_v1.json').read_text())['parent_fork']
    changed=[];unchanged=0
    for path in sorted(F.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:continue
        old=oldroot/path.relative_to(F)
        if old.exists() and sha(old)==sha(path):unchanged+=1;continue
        check=git('-c','core.whitespace=cr-at-eol','diff','--no-index','--check','--',old if old.exists() else '/dev/null',path,check=False)
        assert check.returncode in [0,1] and not check.stdout and not check.stderr,(path,check.returncode,check.stdout,check.stderr)
        changed.append(str(path.relative_to(R)))
    receipt=dict(at=now(),status='PASS',runtime_files=len(lock['files']),parent_files=len(parent),unchanged_copied_files=unchanged,
        changed_fork_files=changed,check='Authored configs/scripts/docs staged diff; fork additions against frozen r22; all runtime hashes unchanged',scientific_verdict=None)
    dump(D/'source_verification.json',receipt)

def delivery_paths(site,prior):
    if site=='all':return [str(p.relative_to(R)) for p in [C,S,D,F]]
    stem=f'{site}__{prior}';report=f'결과_{SITES[site]}_{PRIORS[prior]}.md'
    docs=[]
    for path in D.rglob('*'):
        if not path.is_file():continue
        if path.parent==D and path.name.startswith('결과_') and path.name!=report:continue
        if path.parent.name in ['tables','figures','delivery'] and '__' in path.name and stem not in path.name:continue
        docs.append(path)
    return [str(p.relative_to(R)) for p in [C,S,F,*sorted(docs)]]

def package(site,prior=None):
    all_=site=='all';stem='all' if all_ else f'{site}__{prior}';members={}
    if all_:
        for p in D.rglob('*'):
            if p.is_file():members['docs/'+str(p.relative_to(D))]=p
    else:
        report=D/f'결과_{SITES[site]}_{PRIORS[prior]}.md';assert report.exists();members['docs/'+report.name]=report
        for name in ['구현변경.md','changes.json','issues.md','source_verification.json']:
            if (D/name).exists():members['docs/'+name]=D/name
        for parent in ['tables','figures']:
            for p in (D/parent).glob('*'):
                if p.is_file() and stem in p.name:members['docs/'+parent+'/'+p.name]=p
    for p in C.rglob('*'):
        if p.is_file():members['configs/'+str(p.relative_to(C))]=p
    arms=[(s,p) for s in SITES for p in PRIORS] if all_ else [(site,prior)]
    for s,p in arms:
        st=f'{s}__{p}'
        for f in [O/'targets'/f'{st}.npz',O/'targets'/f'{st}.json',O/'verification'/f'inputs_{st}.json',O/'verification'/f'loaded_{st}.json',O/'verification'/f'delivery_{st}.json',O/'verification'/f'geometry_extension_{s}.json',O/'verification'/f'extension_judgments_{s}.json',O/'outside'/s/'budget_receipt.json',O/'stage1'/st/'ready.json']:
            if f.exists():members['evidence/'+str(f.relative_to(O))]=f
        for f in [O/'post'/f'{st}.json',O/'verification'/f'visual_{st}.json',O/'scores'/st/'binding.json',O/'rescore/scores'/('ft_'+st)/'values.json']:
            if f.exists():members['evidence/'+str(f.relative_to(O))]=f
        run=O/'runs'/s/f'ft_{p}_s0'
        for f in run.rglob('*'):
            if f.is_file() and (f.name in ['receipt.json','launch.json','input_binding.json','command.json'] or f.parent.name=='target_monitor' and f.suffix in ['.json','.jsonl']):
                members['evidence/'+str(f.relative_to(O))]=f
    for f in [O/'verification/unit_default.json',O/'verification/unit_math.json']:
        members['evidence/'+str(f.relative_to(O))]=f
    archive=O/'delivery'/('PHD-MAIN-FINALTRAIN-v1.zip' if all_ else f'PHD-MAIN-FINALTRAIN-v1_{SITES[site]}_{PRIORS[prior]}.zip');archive.parent.mkdir(exist_ok=True)
    checks=''.join(sha(p)+'  '+n+'\n' for n,p in sorted(members.items()))
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for name,p in sorted(members.items()):z.write(p,name)
        z.writestr('SHA256SUMS',checks)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for line in z.read('SHA256SUMS').decode().splitlines():
            digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
    result=dict(at=now(),status='PASS_ZIP_CRC_AND_SHA256',path=str(archive),sha256=sha(archive),bytes=archive.stat().st_size,members=len(members)+1,scientific_verdict=None)
    dump(D/'delivery'/f'{stem}.json',result);return result

def main(site,prior=None):
    (O/'delivery').mkdir(exist_ok=True)
    with (O/'delivery/git.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        assert git('branch','--show-current').stdout.strip()=='exp/main-experiment'
        source_check();rec=package(site,prior);paths=delivery_paths(site,prior)
        git('add','--',*paths)
        authored=[p for p in paths if p!=str(F.relative_to(R))]
        git('-c','core.whitespace=cr-at-eol','diff','--cached','--check','--',*authored)
        changed=git('diff','--cached','--name-only','--',*paths).stdout.splitlines()
        if changed:
            git('commit','--only','-m',f'PHD-MAIN-FINALTRAIN-v1: deliver {site} {prior or "all"}','--',*paths)
        commit=git('rev-parse','HEAD').stdout.strip();push=git('push','origin',commit+':refs/heads/exp/main-experiment',check=False)
        remote=git('ls-remote','origin','refs/heads/exp/main-experiment').stdout.split()[0]
        ancestry=git('merge-base','--is-ancestor',commit,remote,check=False).returncode==0
        assert remote==commit or ancestry,('Push not verified',push.stderr,remote,commit)
        rec.update(commit=commit,remote=remote,push_verified=True,paths=paths)
        dump(O/'delivery'/('all.json' if site=='all' else f'{site}__{prior}.json'),rec)
        print(json.dumps(rec,ensure_ascii=False),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
