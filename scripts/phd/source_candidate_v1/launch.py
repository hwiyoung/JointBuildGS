"""Host stdlib Docker launcher: snapshots/mounts only, scientific work in Docker."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['method','evaluation','figures','report'])
    parser.add_argument('--run-id',default='PHD-SOURCE-CANDIDATE-P1P2P3-v1')
    parser.add_argument('--retry',action='store_true',help='Archive an incomplete evaluation/figures attempt, preserving every byte')
    args=parser.parse_args()
    if not args.run_id.replace('-','').replace('_','').isalnum(): raise ValueError('Invalid run id')
    repo=Path(__file__).resolve().parents[3]
    artifacts=repo.parent/'JointBuildGS-artifacts'
    cfg=json.loads((repo/'configs/phd/source_candidate_v1/run_v1.json').read_text())
    output=artifacts/'phase-payloads/phd/source_candidate_v1'/args.run_id
    output.parent.mkdir(parents=True,exist_ok=True)
    if args.stage=='method': output.mkdir(exist_ok=False)
    elif not (output/'run/method_seal.json').is_file(): raise ValueError('All-region pre-reference seal required')
    if args.retry:
        if args.stage not in ('evaluation','figures'): raise ValueError('Only incomplete evaluation/figures may be retried')
        completed=(output/'run/evaluation/evaluation_receipt.json' if args.stage=='evaluation'
                   else output/'figures/figure_manifest.json')
        if completed.exists(): raise ValueError('Completed stage cannot be retried')
        archive=output/'failed_attempts'/(args.stage+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        archive.mkdir(parents=True,exist_ok=False)
        paths=[output/(args.stage+'_source'),output/(args.stage+'_launch.json'),output/(args.stage+'_console.log'),
               output/('run/evaluation' if args.stage=='evaluation' else 'figures')]
        for previous in paths:
            if previous.exists():
                target=archive/previous.name
                try: previous.rename(target)
                except PermissionError:
                    # Runtime-created directories are root-owned. Keep the exact
                    # task output mount and use atomic rename, never copy/delete.
                    subprocess.run(['docker','run','--rm','--network','none','--entrypoint','python',
                        '--mount',f'type=bind,src={output},dst=/task',cfg['runtime']['image'],
                        '-c','from pathlib import Path; import sys; Path(sys.argv[1]).rename(sys.argv[2])',
                        '/task/'+str(previous.relative_to(output)),
                        '/task/'+str(target.relative_to(output))],check=True)
        print(json.dumps(dict(archived_incomplete_attempt=str(archive))),flush=True)
    snapshot=output/(args.stage+'_source');snapshot.mkdir(exist_ok=False)
    sources=[]
    for folder in ['src/phd/source_candidate_v1','scripts/phd/source_candidate_v1','configs/phd/source_candidate_v1']:
        sources += [p for p in (repo/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
    sources += list((repo/'tests/phd').glob('test_source_candidate_*.py'))
    sources += [repo/'AGENTS.md',repo/cfg['gravity_manifest']]
    for name in ['src/__init__.py','src/phd/__init__.py','scripts/__init__.py','scripts/phd/__init__.py','tests/__init__.py','tests/phd/__init__.py']:
        if (repo/name).is_file(): sources.append(repo/name)
    manifest={}
    for path in sorted(set(sources)):
        relative=path.relative_to(repo);target=snapshot/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        manifest[str(relative)]=digest(target)
    (snapshot/'SOURCE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    image=cfg['runtime']['image'];head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    prefix=['docker','run','--rm','--name','jbgs-source-candidate-'+args.stage+'-'+args.run_id.lower()[-16:],
            '--network','none','--cpus',str(cfg['runtime']['cpu']),'--memory',cfg['runtime']['memory'],
            '--entrypoint','python','--workdir','/workspace/JointBuildGS',
            '--env','PYTHONDONTWRITEBYTECODE=1','--env','OPENBLAS_NUM_THREADS=1','--env','OMP_NUM_THREADS=2',
            '--env','MPLCONFIGDIR=/tmp/matplotlib',
            '--env','JBGS_SOURCE_GIT_HEAD='+head,'--env','JBGS_CONTAINER_IMAGE_ID='+image]
    mounts=[]
    def mount(host,target,readonly=True):
        if not host.exists(): raise FileNotFoundError(host)
        spec=f'type=bind,src={host},dst={target}'+(',readonly' if readonly else '')
        prefix.extend(['--mount',spec]);mounts.append(dict(source=str(host),target=target,readonly=readonly))
    mount(snapshot,'/workspace/JointBuildGS')
    mount(output,'/output',False)
    for region,spec in cfg['regions'].items():
        for name in ('native.npz','views.json'):
            mount(artifacts/spec['common_root']/name,f'/inputs/{region}/{name}')
    mount(artifacts/cfg['rgb_root'],'/artifacts/JointBuildGS/'+cfg['rgb_root'])
    if args.stage=='evaluation':
        for region in cfg['regions']:
            mount(artifacts/f'phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run/{region}/reference.npz',f'/reference/{region}/reference.npz')
    if args.stage=='method':
        command=prefix+[image,'-u','-m','scripts.phd.source_candidate_v1.run','--config','configs/phd/source_candidate_v1/run_v1.json']
        test_names=['tests.phd.test_source_candidate_geometry','tests.phd.test_source_candidate_photometry','tests.phd.test_source_candidate_decision']
    elif args.stage=='evaluation':
        command=prefix+[image,'-u','-m','scripts.phd.source_candidate_v1.evaluate','--run','/output/run','--config','configs/phd/source_candidate_v1/evaluation_v1.json']
        test_names=['tests.phd.test_source_candidate_evaluation']
    elif args.stage=='figures':
        command=prefix+[image,'-u','-m','scripts.phd.source_candidate_v1.figures','--run','/output/run','--output','/output/figures']
        test_names=[]
    else:
        command=prefix+[image,'-u','-m','scripts.phd.source_candidate_v1.report','--run','/output/run',
            '--output','/output/report','--artifact-host-root',str(output)]
        test_names=[]
    (output/(args.stage+'_launch.json')).write_text(json.dumps(dict(command=command,mounts=mounts,
        source_manifest_sha256=digest(snapshot/'SOURCE_MANIFEST.json'),git_head=head,image=image,
        scientific_verdict=None,created_at=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')
    print(json.dumps(dict(stage=args.stage,output=str(output),snapshot_files=len(manifest))),flush=True)
    with (output/(args.stage+'_console.log')).open('x') as log:
        if test_names:
            test=prefix+[image,'-m','unittest','-v',*test_names]
            result=subprocess.run(test,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            print(result.stdout,flush=True);log.write(result.stdout);log.flush()
            if result.returncode:sys.exit(result.returncode)
        with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1) as process:
            for line in process.stdout:
                print(line,end='',flush=True);log.write(line);log.flush()
            code=process.wait()
    sys.exit(code)


if __name__=='__main__':main()
