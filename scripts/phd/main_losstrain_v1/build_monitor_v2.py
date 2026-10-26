"""Host stdlib: build in Docker, prove only two fork files differ, then promote."""
import json,subprocess,shutil
from train_calibration import OUT,REPO,P,save,sha,now

def main():
    root=OUT/'checks/monitor_v2';fresh=root/'rebuilt_fork';doc=root/'rebuild_docs'
    fresh.mkdir(exist_ok=False);(doc/'provenance').mkdir(parents=True)
    for script in ['build_r17.py','amend_r17_monitor.py']:
        command=['docker','run','--rm','--network','none','--user',str(__import__('os').getuid())+':'+str(__import__('os').getgid()),
            '-e','PYTHONDONTWRITEBYTECODE=1','-v',str(REPO)+':/repo:ro','-v',str(fresh)+':/fork17','-v',str(doc)+':/docs',
            '-w','/repo/scripts/phd/main_losstrain_v1','--entrypoint','python','jointbuildgs:dev',script]
        subprocess.run(command,check=True)
    files=lambda base:sorted(p.relative_to(base) for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
    base=P.SRC['r16'];live=P.SRC['r17'];assert files(base)==files(fresh)==files(live)
    changed=[str(p) for p in files(base) if sha(base/p)!=sha(fresh/p)]
    assert changed==['jbgs_judgment.py','train.py'],changed
    before=(root/'before/src/phd/forks/GeoGS-conf-guided-v1-r17/jbgs_judgment.py')
    if not before.exists():
        before=next((root/'before').rglob('jbgs_judgment.py'))
    marker='# ---------------- PHD-MAIN-LOSSTRAIN-v1 r17 opt-in depth terms ----------------'
    old=before.read_text().split(marker)[1].split('"""Opt-in LOSSTRAIN observations;')[0]
    new=(fresh/'jbgs_judgment.py').read_text().split(marker)[1].split('"""Opt-in LOSSTRAIN observations;')[0]
    assert old==new,'depth-loss source changed'
    test=root/'monitor_check.json';assert json.loads(test.read_text())['status']=='PASS'
    for p in changed:shutil.copyfile(fresh/p,live/p)
    assert all(sha(fresh/p)==sha(live/p) for p in files(fresh))
    for name in ['r16_to_r17_direct.diff','r17_direct_amendment.json']:
        shutil.copyfile(doc/'provenance'/name,REPO/'docs/experiments/phd/main_losstrain_v1/provenance'/name)
    receipt=dict(status='PASS',at=now(),changed=changed,file_count=len(files(fresh)),rebuild_exact=True,
        depth_loss_bytes_unchanged=True,density_model_bytes_unchanged=True,
        source_sha256={p:sha(live/p) for p in changed},monitor_check_sha256=sha(test),scientific_verdict=None)
    save(root/'validation.json',receipt);save(REPO/'docs/experiments/phd/main_losstrain_v1/provenance/monitor_v2_validation.json',receipt)
    print('monitor v2 fresh rebuild and unchanged loss/density PASS')

if __name__=='__main__':main()
