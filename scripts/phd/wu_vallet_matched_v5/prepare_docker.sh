#!/usr/bin/env bash
set -euo pipefail
wv5_mode=${1:?input, acquisition, or trajectory}
wv5_region=${2:?P1, P2, or P3}
wv5_resume=${3:-fresh}
wv5_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
python3 - "$wv5_repo" "$wv5_mode" "$wv5_region" "$wv5_resume" <<'PY'
from pathlib import Path
import hashlib,json,shlex,shutil,subprocess,sys
repo=Path(sys.argv[1]);mode,region,resume=sys.argv[2:]
assert resume in ('fresh','resume')
assert mode in ('input','acquisition','trajectory') and region in ('P1','P2','P3')
assert mode=='input' or region=='P3'
art=repo.parent/'JointBuildGS-artifacts';base=art/'phase-payloads/phd/wu_vallet_matched_v5'
task=f'PHD-WU-VALLET-{region}-INPUT-v5' if mode=='input' else f'PHD-WU-VALLET-P3-{mode.upper()}-ADAPTER-v5'
suffix='_validation_r2' if resume=='resume' else ''
dest=base/task;source=base/(task+'_source'+suffix);base.mkdir(parents=True,exist_ok=True)
if resume=='fresh':dest.mkdir()
else:assert mode!='input' and dest.is_dir() and not (dest/'run/receipt.json').exists()
source.mkdir()
names=subprocess.check_output(['git','-C',str(repo),'ls-files','--cached','--others','--exclude-standard','-z','src','scripts','configs','tests','artifacts/manifests','AGENTS.md','requirements.txt']).decode().split('\0')
hashes={}
for name in sorted(set(names)-{''}):
    path=repo/name
    if not path.is_file():continue
    target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    hashes[name]=hashlib.sha256(target.read_bytes()).hexdigest()
(source/'SOURCE_MANIFEST.json').write_text(json.dumps(hashes,indent=2)+'\n')
cfgname='configs/phd/wu_vallet_matched_v5/regions_v5.json';cfg=json.loads((source/cfgname).read_text());spec=cfg['regions'][region]
mounts=[]
def allow(containerpath):
    prefix='/artifacts/JointBuildGS/'
    assert containerpath.startswith(prefix)
    local=art/containerpath[len(prefix):]
    assert local.exists(),local
    mounts.append((str(local),containerpath))
if mode=='input':
    patch=json.loads((source/spec['patch_config']).read_text());cam=json.loads((source/spec['camera_config']).read_text());src=json.loads((source/cfg['source_config']).read_text())
    allow('/artifacts/JointBuildGS/'+src['inputs']['mvs']['relative_path'])
    als=src['inputs']['existing_als']
    for filename in sorted(als['files']):allow('/artifacts/JointBuildGS/'+als['relative_root']+'/'+filename)
    for sensor in ('als','mvs'):allow('/artifacts/JointBuildGS/'+patch['inputs']['source_relation_relative_root']+'/'+patch['inputs']['partitions'][sensor]['relative_path'])
    allow('/artifacts/JointBuildGS/'+patch['output_relative_root'])
    for filename in ('artifact_manifest.json','evidence_views.json'):allow('/artifacts/JointBuildGS/'+cam['output_relative_root']+'/'+filename)
    camera='/artifacts/JointBuildGS/'+cam['inputs']['current_cameras']['camera_root_relative_path']
    for name in ('sparse','images','stereo/depth_maps'):allow(camera+'/'+name)
    allow(spec['original_native_npz'])
else:
    root=spec[f'original_{mode}_root'];filename='acquisition.npz' if mode=='acquisition' else 'estimated_origins.npz'
    for name in (filename,'receipt.json','config.json'):allow(root+'/'+name)
image='sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774'
args=['docker','run','--rm','--name','jbgs-'+task.lower()+suffix.replace('_','-'),'--network','none','--cpus','4','--memory','12g','--entrypoint','python',
      '--mount',f'type=bind,src={source},dst=/workspace/JointBuildGS,readonly','--mount',f'type=bind,src={dest},dst=/output',
      '--workdir','/workspace/JointBuildGS','--env','PYTHONDONTWRITEBYTECODE=1','--env','OPENBLAS_NUM_THREADS=1','--env','OMP_NUM_THREADS=4',
      '--env',f'JBGS_SOURCE_SNAPSHOT_MANIFEST={source}/SOURCE_MANIFEST.json','--env',f'JBGS_CONTAINER_IMAGE_ID={image}',
      '--env','JBGS_SOURCE_GIT_HEAD='+subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD']).decode().strip()]
for local,remote in sorted(set(mounts)):args+=['--mount',f'type=bind,src={local},dst={remote},readonly']
module='scripts.phd.wu_vallet_matched_v5.prepare_inputs' if mode=='input' else 'scripts.phd.wu_vallet_matched_v5.adapter_recovery'
args+=[image,'-m',module,'--config',cfgname,'--mode',mode,'--region',region,'--output','/output/run']
if resume=='resume':args+=['--resume-adapter']
(dest/f'launch{suffix}.json').write_text(json.dumps({'command':args,'read_only_input_mounts':mounts,'raw_or_cropped_uas_mounted':False,'scientific_verdict':None},indent=2)+'\n')
(dest/f'run{suffix}.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\n'+shlex.join(args)+' 2>&1 | tee '+shlex.quote(str(dest/f'console{suffix}.log'))+'\n')
print(json.dumps({'task':task,'snapshot_files':len(hashes),'input_mount_count':len(mounts),'source_manifest':str(source/'SOURCE_MANIFEST.json')}),flush=True)
result=subprocess.run(['bash',str(dest/f'run{suffix}.sh')]);sys.exit(result.returncode)
PY
