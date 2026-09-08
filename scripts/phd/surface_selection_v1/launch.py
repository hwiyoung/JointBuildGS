"""Host stdlib only: immutable source snapshots and scoped Docker execution."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):
    with Path(p).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

def snapshot(repo,target):
    target.mkdir(exist_ok=False);sources=[]
    for folder in ('src/phd/source_candidate_v1','src/phd/surface_selection_v1',
                   'scripts/phd/source_candidate_v1','scripts/phd/surface_selection_v1',
                   'configs/phd/surface_selection_v1','src/apps/surface_selection_viewer_v1'):
        sources.extend(p for p in (repo/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    sources.extend((repo/'tests/phd').glob('test_surface_selection_*.py'))
    sources.extend((repo/'tests/phd').glob('test_source_candidate_*.py'))
    sources.extend(repo/p for p in ('AGENTS.md','artifacts/manifests/gate_s0/freeze_recovery_v1/technical_freeze_manifest_v1.json',
        'src/apps/gs3d_4way_viewer/build/three.module.min.js','src/__init__.py','src/phd/__init__.py',
        'scripts/__init__.py','scripts/phd/__init__.py','tests/__init__.py','tests/phd/__init__.py') if (repo/p).is_file())
    ledger={}
    for p in sorted(set(sources)):
        rel=p.relative_to(repo);dst=target/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst);dst.chmod(0o444)
        ledger[str(rel)]=sha(dst)
    write(target/'SOURCE_MANIFEST.json',ledger)

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['method','evaluation','report','viewer','qa'])
    p.add_argument('--run-id',default='PHD-SURFACE-SELECTION-P1P2P3-v1');p.add_argument('--attempt-id',default='v1')
    p.add_argument('--replace-own',action='store_true');a=p.parse_args()
    if not all(v.replace('-','').replace('_','').isalnum() for v in (a.run_id,a.attempt_id)):raise ValueError('Invalid ID')
    repo=Path(__file__).resolve().parents[3];backend=repo.parent/'JointBuildGS-artifacts'
    cfg=json.loads((repo/'configs/phd/surface_selection_v1/run_v1.json').read_text())
    out=backend/'phase-payloads/phd/surface_selection_v1'/a.run_id
    if a.stage=='method':out.mkdir(parents=True,exist_ok=False)
    elif not (out/'run/method_seal.json').is_file():raise ValueError('Complete method required')
    attempt=out/(a.stage+'_'+a.attempt_id);attempt.mkdir(exist_ok=False)
    url=f"http://127.0.0.1:{cfg['viewer']['port']}/"
    if a.stage=='qa':
        script=repo/'scripts/phd/surface_selection_v1/browser_qa.mjs';shutil.copy2(script,attempt/'browser_qa.mjs')
        command=['docker','run','--rm','--read-only','--network','host','--cpus','2','--memory','3g','--tmpfs','/tmp:rw,size=1g','--shm-size','512m',
                 '--env','SURFACE_VIEWER_QA_IMAGE_ID='+cfg['viewer']['browser_image'],
                 '--mount',f'type=bind,src={attempt},dst=/out',cfg['viewer']['browser_image'],'/out/browser_qa.mjs',url,'/out']
        write(attempt/'launch.json',dict(command=command,script_sha256=sha(script),scientific_verdict=None))
        return run_command(command,attempt/'console.log')
    source=attempt/'source';snapshot(repo,source)
    image=cfg['runtime']['image'];head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    prefix=['docker','run','--read-only','--user',f'{os.getuid()}:{os.getgid()}','--cpus',str(cfg['runtime']['cpu'] if a.stage!='viewer' else 3),
        '--memory',cfg['runtime']['memory'] if a.stage!='viewer' else '5g','--tmpfs','/tmp:rw,size=512m',
        '--cap-drop','ALL','--security-opt','no-new-privileges','--entrypoint','python','--workdir','/workspace/JointBuildGS',
        '--env','PYTHONDONTWRITEBYTECODE=1','--env','OPENBLAS_NUM_THREADS=1','--env','OMP_NUM_THREADS=1',
        '--env','MPLCONFIGDIR=/tmp/matplotlib','--env','JBGS_SOURCE_GIT_HEAD='+head,'--env','JBGS_CONTAINER_IMAGE_ID='+image]
    mounts=[]
    def mount(path,target,readonly=True):
        if not path.exists():raise FileNotFoundError(path)
        prefix.extend(['--mount',f'type=bind,src={path},dst={target}'+(',readonly' if readonly else '')])
        mounts.append(dict(source=str(path),target=target,readonly=readonly))
    mount(source,'/workspace/JointBuildGS');mount(out,'/output',a.stage=='viewer')
    for region,spec in cfg['regions'].items():
        for f in ('native.npz','views.json'):mount(backend/spec['common_root']/f,f'/inputs/{region}/{f}')
    mount(backend/cfg['rgb_root'],'/artifacts/JointBuildGS/'+cfg['rgb_root'])
    if a.stage in ('evaluation','report','viewer'):mount(backend/cfg['baseline_run'],'/baseline')
    if a.stage=='evaluation':
        for r in cfg['regions']:mount(backend/f'phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run/{r}/reference.npz',f'/reference/{r}/reference.npz')
    modules={'method':'run','evaluation':'evaluate','report':'report','viewer':'serve'}
    args={'method':['--config','configs/phd/surface_selection_v1/run_v1.json'],
          'evaluation':['--run','/output/run','--baseline','/baseline/run'],
          'report':['--run','/output/run','--output','/output/report','--artifact-host-root',str(out)],'viewer':[]}[a.stage]
    if a.stage=='viewer':
        name='jbgs-surface-selection-viewer-'+str(cfg['viewer']['port'])
        existing=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
        if existing.returncode==0:
            record=json.loads(existing.stdout)[0]
            if not a.replace_own or record['Config'].get('Labels',{}).get('jbgs.task')!=cfg['task_id']:raise RuntimeError('Existing viewer preserved')
            write(attempt/'replaced_container.json',record)
            (attempt/'replaced_console.log').write_text(subprocess.run(['docker','logs',name],capture_output=True,text=True).stderr)
            subprocess.run(['docker','stop',name],check=True);subprocess.run(['docker','rm',name],check=True)
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',cfg['viewer']['port']))==0:raise RuntimeError('Port occupied')
        mount(source/'src/apps/gs3d_4way_viewer/build/three.module.min.js','/vendor/three.module.min.js')
        runtime=['-d','--name',name,'--label','jbgs.task='+cfg['task_id'],'--publish',f"127.0.0.1:{cfg['viewer']['port']}:8080"]
    else:runtime=['--rm','--network','none']
    command=prefix+runtime+[image,'-u','-m','scripts.phd.surface_selection_v1.'+modules[a.stage],*args]
    write(attempt/'launch.json',dict(command=command,mounts=mounts,source_manifest_sha256=sha(source/'SOURCE_MANIFEST.json'),
        source_git_head=head,image=image,url=url if a.stage=='viewer' else None,scientific_verdict=None,
        created_at=datetime.now(timezone.utc).isoformat()))
    print(json.dumps(dict(stage=a.stage,attempt=str(attempt),run=str(out))),flush=True)
    if a.stage=='method':
        tests=['tests.phd.test_surface_selection_segmentation','tests.phd.test_surface_selection_units','tests.phd.test_surface_selection_evidence']
        test=prefix+['--rm','--network','none',image,'-m','unittest','-v',*tests]
        run_command(test,attempt/'tests.log')
    if a.stage=='evaluation':run_command(prefix+['--rm','--network','none',image,'-m','unittest','-v','tests.phd.test_surface_selection_evaluation'],attempt/'tests.log')
    if a.stage=='viewer':run_command(prefix+['--rm','--network','none',image,'-m','unittest','-v','tests.phd.test_surface_selection_viewer'],attempt/'tests.log')
    if a.stage!='viewer':return run_command(command,attempt/'console.log')
    cid=subprocess.check_output(command,text=True).strip();deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        try:
            health=json.load(urlopen(url+'api/health',timeout=2))
            write(attempt/'startup_receipt.json',dict(container=cid,url=url,health=health,scientific_verdict=None))
            print(json.dumps(dict(status='VIEWER_READY',url=url,container=cid)),flush=True);return
        except Exception:time.sleep(.5)
    raise RuntimeError('Viewer startup timed out; inspect this task container logs')

def run_command(command,logpath):
    with Path(logpath).open('x') as log:
        with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1) as process:
            for line in process.stdout:print(line,end='',flush=True);log.write(line);log.flush()
            code=process.wait()
    if code:raise SystemExit(code)

if __name__=='__main__':main()
