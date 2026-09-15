"""Start the additive unified viewer without replacing the original R1 service."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[3];root=Path(sys.argv[1]).resolve();cfg=json.loads((root/'config.json').read_text());art=Path(cfg['artifact_root'])
port=8913
assert not subprocess.check_output(['ss','-H','-ltn',f'sport = :{port}']).strip(), 'Viewer port occupied'
source=root/'viewer/source';source.mkdir(parents=True);data=root/'viewer/data';data.mkdir()
(data/'r1legacy').mkdir()
shutil.copytree(repo/'src/apps/r1r5_comparison_v1',source/'app')
for src,dest in [('scripts/phd/r1r5_comparison_v1/publish.py','publish.py'),('scripts/phd/r1_mvs_control_run_v1/publish.py','legacy_publish.py'),
    ('scripts/phd/geogs_mvs_pgsr_v1/viewer/export_geometry.py','export_geometry.py'),('scripts/phd/geogs_mvs_pgsr_v1/viewer/serve.py','serve.py'),
    ('src/apps/gs3d_4way_viewer/build/three.module.min.js','three.module.min.js')]:shutil.copy2(repo/src,source/dest)
(source/'hashes.json').write_text(json.dumps({str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()},indent=2))
image='sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
legacy=art/cfg['r1_run_relative']/'viewer/data';acfg=json.loads((art/cfg['audit_relative']/'result/config.json').read_text())
common=['docker','run','-d','--restart','unless-stopped','--runtime','runc','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user',f'{os.getuid()}:{os.getgid()}',
    '-e','PYTHONDONTWRITEBYTECODE=1','-e','NVIDIA_VISIBLE_DEVICES=void','-e','LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6','-e','OPENBLAS_NUM_THREADS=2','--tmpfs','/tmp:rw,nosuid,size=256m']
for role in ['publisher','viewer']:
    command=common+['--name',f'jbgs-r1r5-{role}-{port}']
    if role=='publisher':
        command+=['--network','none','--cpus','2','--memory','12g'];mounts=[(source,'/driver'),(root,'/run'),(art/cfg['audit_relative']/'result','/audit'),
            (art/acfg['inputs']['fused_mvs_relative'],'/fused.ply'),(legacy,'/r1legacy')]
    else:
        command+=['--cpus','2','--memory','1g','--publish',f'127.0.0.1:{port}:8080'];mounts=[(source/'serve.py','/serve.py'),(source/'app','/app'),
            (source/'three.module.min.js','/vendor/three.module.min.js'),(data,'/data'),(legacy,'/data/r1legacy')]
    for host,target in mounts:command+=['--mount',f'type=bind,source={host},target={target},readonly']
    if role=='publisher':command+=['--mount',f'type=bind,source={data},target=/out']
    command+=['--entrypoint','python',image,'/driver/publish.py' if role=='publisher' else '/serve.py']
    (root/'viewer'/(role+'_command.json')).write_text(json.dumps(command,indent=2));subprocess.run(command,check=True)
print(f'http://127.0.0.1:{port}/')
