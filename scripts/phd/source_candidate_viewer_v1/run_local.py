"""Host-stdlib snapshot/Docker launcher; all project computation runs in Docker."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','qa','status'])
    parser.add_argument('--viewer-id',default='PHD-SOURCE-CANDIDATE-VIEWER-v1')
    parser.add_argument('--qa-id',default='qa-v1');parser.add_argument('--replace-own',action='store_true')
    args=parser.parse_args()
    if not all(v.replace('-','').replace('_','').isalnum() for v in (args.viewer_id,args.qa_id)):raise ValueError('Invalid identifier')
    repo=Path(__file__).resolve().parents[3];backend=repo.parent/'JointBuildGS-artifacts'
    cfg=json.loads((repo/'configs/phd/source_candidate_viewer_v1/viewer.json').read_text())
    task=backend/cfg['source_run'];method=json.loads((task/'run/config.json').read_text())
    out=backend/'phase-payloads/phd/source_candidate_viewer_v1'/args.viewer_id
    url=f"http://{cfg['bind']}:{cfg['port']}/";name='jbgs-source-candidate-viewer-'+str(cfg['port'])
    if args.action=='status':
        print(urlopen(url+'api/health',timeout=5).read().decode());return
    if args.action=='qa':
        if not out.is_dir():raise FileNotFoundError(out)
        qa=out/'browser_qa'/args.qa_id;qa.mkdir(parents=True,exist_ok=False)
        script=repo/'scripts/phd/source_candidate_viewer_v1/browser_qa.mjs'
        shutil.copy2(script,qa/'browser_qa_source.mjs')
        command=['docker','run','--rm','--read-only','--network','host','--cpus','2','--memory','3g',
            '--tmpfs','/tmp:rw,nosuid,size=1g','--shm-size','512m',
            '--env','SOURCE_VIEWER_QA_IMAGE_ID='+cfg['browser_image'],
            '--mount',f'type=bind,src={qa}/browser_qa_source.mjs,dst=/qa/browser_qa.mjs,readonly',
            '--mount',f'type=bind,src={qa},dst=/out',cfg['browser_image'],'/qa/browser_qa.mjs',url,'/out']
        write(qa/'launch.json',dict(command=command,viewer_source_manifest_sha256=sha(out/'source/SOURCE_MANIFEST.json'),scientific_verdict=None))
        print(json.dumps(dict(action='qa',url=url,output=str(qa))),flush=True)
        with (qa/'console.log').open('x') as log:
            with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1) as process:
                for line in process.stdout:print(line,end='',flush=True);log.write(line);log.flush()
                code=process.wait()
        sys.exit(code)
    out.mkdir(parents=True,exist_ok=False)
    existing=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
    if existing.returncode==0:
        record=json.loads(existing.stdout)[0]
        if not args.replace_own or record['Config'].get('Labels',{}).get('jbgs.task')!=cfg['task_id']:
            raise RuntimeError('Existing service preserved; only this task viewer may be explicitly replaced')
        write(out/'replaced_service.json',record)
        (out/'replaced_service.log').write_text(subprocess.run(['docker','logs',name],capture_output=True,text=True).stderr)
        subprocess.run(['docker','stop',name],check=True);subprocess.run(['docker','rm',name],check=True)
    with socket.socket() as probe:
        if probe.connect_ex((cfg['bind'],cfg['port']))==0:raise RuntimeError('Port occupied; unrelated service preserved')
    snapshot=out/'source';snapshot.mkdir()
    sources=[]
    for folder in ('src/apps/source_candidate_viewer_v1','scripts/phd/source_candidate_viewer_v1',
                   'src/phd/source_candidate_v1','scripts/phd/source_candidate_v1','configs/phd/source_candidate_viewer_v1'):
        sources.extend(p for p in (repo/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    sources.extend((repo/'tests/phd').glob('test_source_candidate_viewer_*.py'))
    sources.append(repo/'tests/phd/test_source_candidate_photometry.py')
    sources.append(repo/'src/apps/gs3d_4way_viewer/build/three.module.min.js')
    for p in ('AGENTS.md','src/__init__.py','src/phd/__init__.py','scripts/__init__.py','scripts/phd/__init__.py','tests/__init__.py','tests/phd/__init__.py'):
        if (repo/p).exists():sources.append(repo/p)
    for required in ('src/apps/source_candidate_viewer_v1/index.html','src/apps/source_candidate_viewer_v1/app.js',
                     'scripts/phd/source_candidate_viewer_v1/data.py'):
        if not (repo/required).is_file():raise FileNotFoundError(required)
    ledger={}
    for src in sorted(set(sources)):
        rel=src.relative_to(repo);dst=snapshot/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
        dst.chmod(0o444) # Runtime has no DAC override; normalize only the new snapshot, never source files.
        ledger[str(rel)]=sha(dst)
    write(snapshot/'SOURCE_MANIFEST.json',ledger)
    prefix=['docker','run','--read-only','--cpus',str(cfg['cpus']),'--memory',cfg['memory'],
            '--tmpfs','/tmp:rw,nosuid,size=128m','--cap-drop','ALL','--security-opt','no-new-privileges',
            '--env','PYTHONDONTWRITEBYTECODE=1','--env','OPENBLAS_NUM_THREADS=1','--env','OMP_NUM_THREADS=1',
            '--env','MPLCONFIGDIR=/tmp/matplotlib','--workdir','/workspace/JointBuildGS','--entrypoint','python']
    mounts=[]
    def mount(src,dst):
        if not src.exists():raise FileNotFoundError(src)
        prefix.extend(['--mount',f'type=bind,src={src},dst={dst},readonly']);mounts.append(dict(source=str(src),target=dst,readonly=True))
    mount(snapshot,'/workspace/JointBuildGS');mount(task,'/task')
    mount(snapshot/'src/apps/gs3d_4way_viewer/build/three.module.min.js','/vendor/three.module.min.js')
    for region,spec in method['regions'].items():
        for f in ('native.npz','views.json'):mount(backend/spec['common_root']/f,f'/inputs/{region}/{f}')
    mount(backend/method['rgb_root'],'/artifacts/JointBuildGS/'+method['rgb_root'])
    tests=['tests.phd.test_source_candidate_viewer_http','tests.phd.test_source_candidate_viewer_data']
    test=subprocess.run(prefix+['--rm','--network','none',cfg['image'],'-m','unittest','-v',*tests],capture_output=True,text=True)
    (out/'tests.log').write_text(test.stdout+test.stderr);print(test.stdout+test.stderr,flush=True)
    if test.returncode:raise RuntimeError('Viewer tests failed; see preserved tests.log')
    command=prefix+['-d','--name',name,'--label','jbgs.task='+cfg['task_id'],'--label','jbgs.viewer_run='+args.viewer_id,
        '--publish',f"{cfg['bind']}:{cfg['port']}:8080",cfg['image'],'-u','-m','scripts.phd.source_candidate_viewer_v1.serve']
    write(out/'launch.json',dict(command=command,mounts=mounts,url=url,config=cfg,
        source_manifest_sha256=sha(snapshot/'SOURCE_MANIFEST.json'),source_method_seal_sha256=sha(task/'run/method_seal.json'),
        git_head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        scientific_verdict=None,created_at=datetime.now(timezone.utc).isoformat()))
    cid=subprocess.check_output(command,text=True).strip()
    print(json.dumps(dict(container=cid,url=url,output=str(out))),flush=True)
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        try:
            health=json.loads(urlopen(url+'api/health',timeout=2).read())
            write(out/'startup_receipt.json',dict(container=cid,url=url,health=health,scientific_verdict=None))
            print(json.dumps(dict(status='VIEWER_READY',url=url)),flush=True);return
        except Exception:time.sleep(.5)
    (out/'startup_failure.log').write_text(subprocess.run(['docker','logs',name],capture_output=True,text=True).stderr)
    raise RuntimeError('Viewer startup timed out; failure preserved')


if __name__=='__main__':main()
