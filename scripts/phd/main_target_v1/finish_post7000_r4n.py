"""Bounded completion of missing TSDF report metadata; never starts or resumes training."""
import datetime,fcntl,hashlib,json,os,subprocess,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];PH=REPO.parent/'JointBuildGS-artifacts/phase-payloads/phd';OUT=PH/'main_target_v1/PHD-MAIN-TARGET-v1';ROOT=OUT/'r4n';SCRIPT=REPO/'scripts/phd/main_target_v1'
def stamp():return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def call(tag,args,mem='4',image='jointbuildgs:geogs-conf-guided-v1'):
    env=dict(os.environ,TARGET_LANE='post-completion',IMG=image,MEM=mem,CPUS='4')
    with (ROOT/(tag+'_driver.log')).open('x') as f:
        rc=subprocess.run(['bash',str(SCRIPT/'run_cpu.sh'),tag,*args],env=env,stdout=f,stderr=subprocess.STDOUT).returncode
    if rc:raise RuntimeError((tag,rc))
def main():
    # Complete the second input metadata before its merge begins. Array bytes stay identical.
    folder=ROOT/'runs/tg_B173nb_b10_LoD2_s0/post7000/inputs'
    while not (folder/'binding.json').exists():
        if (ROOT/'post7000_LoD2_receipt.json').exists():raise RuntimeError('LoD2 post ended before preparing inputs')
        time.sleep(5)
    call('postmeta-r4n-LoD2',['complete_post_metadata_r4n.py','LoD2'],'2','jointbuildgs:dev')
    while not all((ROOT/f'post7000_{p}_receipt.json').exists() for p in ['ALS','LoD2']):time.sleep(5)
    lock=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock').open('r');fcntl.flock(lock,fcntl.LOCK_EX)
    results=[]
    for prior in ['ALS','LoD2']:
        wd=ROOT/'runs'/f'tg_B173nb_b10_{prior}_s0/post7000';receipt=json.loads((ROOT/f'post7000_{prior}_receipt.json').read_text())
        if receipt['exit_code']:
            error=(wd/'merge.log').read_text();assert "KeyError: 'mean_share_of_pixels_with_depth'" in error,error[-2000:]
            assert (wd/'inputs/metadata_completion.json').exists()
            old=wd/'merge_before_metadata_completion';old.mkdir(exist_ok=False)
            before=sha(wd/'merged.ply');(wd/'merged.ply').rename(old/'merged.ply')
            call('merge-complete-r4n-'+prior,['post7000_r4n.py','merge','B173nb_b10',prior],'40')
            assert sha(wd/'merged.ply')==before,'metadata-only completion changed mesh bytes'
            call('score-complete-r4n-'+prior,['post7000_r4n.py','score','B173nb_b10',prior],'40')
            results.append(dict(prior=prior,original_post_exit=receipt['exit_code'],completion='PASS',mesh_byte_identical=True,mesh_sha256=before))
        else:results.append(dict(prior=prior,original_post_exit=0,completion='NOT_NEEDED'))
    for prior in ['ALS','LoD2']:call('verify-post7000-r4n-'+prior,['verify_post7000_r4n.py',prior],'32')
    dump(ROOT/'post_completion_receipt.json',dict(at=stamp(),status='PASS_POST_COMPLETION_AND_VERIFICATION',rows=results,training_steps=0,scientific_verdict=None))
    print('POST_COMPLETION_DONE',results,flush=True)

if __name__=='__main__':main()
