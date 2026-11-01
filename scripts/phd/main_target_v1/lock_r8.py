"""Lock the direct r8 amendment before deriving seeds, maps or measurements."""
import datetime as dt, hashlib, json, shutil, subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'configs/phd/main_target_v1';O=R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def main():
    at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
    assert not (C/'target_v1.r8.json').exists()
    base=R/'src/phd/forks/GeoGS-conf-guided-v1-r21';new=base.with_name('GeoGS-conf-guided-v1-r22')
    shutil.copytree(base,new,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    put(C/'fork_r22_base.json',dict(at=at,base_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),files={str(p.relative_to(R)):sha(p) for p in sorted(base.rglob('*')) if p.is_file() and '__pycache__' not in p.parts},scientific_verdict=None))
    d=json.loads((C/'target_v1.r7.json').read_text());d['revision']='r8';d['created_at']=at
    d['training'].update(base_candidate=base.name,new_fork=new.name,switch='--jbgs_target on --jbgs_target_rev r8')
    d['r8']=dict(authority_sha256=sha(C/'decision_20261101_r8.md'),parent_config_sha256=sha(C/'target_v1.r7.json'),
        stage0='reuse exact r7 targets and labels; no recomputation',
        background=dict(source='baseline input points3D.ply, original origin==0 (SfM) in original order',
            provenance='compare entire baseline model/input.ply coordinates and colors with scene source; origin.npy binds source order',
            exclusion='same exclude_cylinders_r2.cpp and exact r2 cylinders; roof half length10m, wall5m; no extra voxel thinning of baseline SfM points',
            initialization='baseline colors, opacity0.1, retained original baseline random rotation; same distCUDA2 scale rule on combined target+SfM cloud, no cap',
            diagnostic_anchor='own initial SfM position',diagnostic_normal='baseline initial Gaussian rotation z axis; no background bound',
            diagnostic_sigma='inherited same-unit/prior background target-map sigma, marked substituted; diagnostics only, no background bound or seed-sigma loss',
            weight='1 at owner<0 with finite positive MVS target; invalid pixels retain0',
            patch_pixels='copy exact r7 depth, sigma, owner and weight arrays; sigma_ref unchanged all-target median'),
        unit=['byte-identical patch seed fields','byte-identical full depth/sigma/owner maps','byte-identical patch weight','all valid background weights1','r7 candidate/reattach/loss and optimizer unchanged','count guard at every1000 from7000','complete state roundtrip'],
        monitor=dict(count_and_gpu_interval=1000,count_reference=6000,growth_max=3,check_from=7000,independent_stops=True,opacity_grace='unchanged r7'),
        geometry_gates='same prior base7k floating+0.02, agreement-0.02, missing+0.01; record only, do not stop',
        checkpoints=[7000,15000,30000],r7_LoD2='continue reference',r7_ALS='do not resume',other_six='NOT_STARTED',
        result_names=['tg_B173nb_b10_ALS_s0_r8','tg_B173nb_b10_LoD2_s0_r8'],scientific_verdict=None)
    d['amendments'].append(dict(at=at,previous_config_sha256=sha(C/'target_v1.r7.json'),reason='direct r8 decision: background initialization and pixel weights, periodic count/memory monitoring and independent health stops; r8 overrides historical sections'))
    put(C/'target_v1.r8.json',d)
    put(C/'target_v1.r8.lock.json',dict(at=at,config_sha256=sha(C/'target_v1.r8.json'),authority_sha256=sha(C/'decision_20261101_r8.md'),base_manifest_sha256=sha(C/'fork_r22_base.json'),first_calculation_after_lock=True,scientific_verdict=None))
    for p in ['r8/verification','r8/targets','r8/stage1','r8/diagnostics','r8/runs']:(O/p).mkdir(parents=True,exist_ok=True)
    print('R8_LOCKED',at,sha(C/'target_v1.r8.json'))
if __name__=='__main__':main()
