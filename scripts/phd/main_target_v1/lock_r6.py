"""Host stdlib: preserve r19 and freeze the user-authorized r6 contract before arithmetic."""
import datetime as dt, hashlib, json, shutil, subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3]; C=R/'configs/phd/main_target_v1'
O=R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def main():
    at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
    order=Path('/home/innopam/.codex/attachments/9ef3568c-c70b-4384-a12d-a7f04c57794a/붙여넣은 텍스트.txt')
    assert not (C/'target_v1.r6.json').exists()
    shutil.copyfile(order,C/'decision_20261101_r6.txt')
    base=R/'src/phd/forks/GeoGS-conf-guided-v1-r19';new=base.with_name('GeoGS-conf-guided-v1-r20')
    shutil.copytree(base,new,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    binding={str(p.relative_to(R)):sha(p) for p in sorted(base.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    put(C/'fork_r20_base.json',dict(at=at,base_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),files=binding,scientific_verdict=None))
    d=json.loads((C/'target_v1.stage1.r4n.json').read_text())
    d['revision']='r6';d['created_at']=at
    d['training'].update(base_candidate=base.name,new_fork=new.name,switch='--jbgs_target on --jbgs_target_rev r6',initial_arm_count=2,deferred_arm_count=6)
    d['stops']['stage1'].pop('target_follow_min')
    d['stops']['stage1'].update(agreement_tau_min={'ALS':.693,'LoD2':.741},no_surface_max='same scorer exact r4n cells 0~3 fraction',both_pilots_required=True)
    d['stage_status'].update(stage1='IMPLEMENTATION_R6_PENDING',stage2='NOT_STARTED')
    d['r6']=dict(authority_sha256=sha(order),previous_config='target_v1.stage1.r4n.json',previous_config_sha256=sha(C/'target_v1.stage1.r4n.json'),
        tags={'background':0,'patch':1,'released':2},immutable_lineage='init_id and initial origin',
        nearest_target=dict(source='r2/targets/<site>_<prior>.npz valid region>=0, entire unit including band; no GT',distance='Euclidean 3D float64',radius_m=.5,ties='lowest original patch index',
            when=['immediately after clone','immediately after split','immediately after prune','every 100 iterations through 30000'],
            eligible_tag='patch only',released_rejoins=False,projection_max_displacement_m=.5,roundoff_tolerance_m=3e-5),
        bound_tags=['patch'],record_only_tags=['background','released'],
        full_state_iterations=[7000,15000,30000],full_state_phase='end of iteration after density/reset and target updates; includes Adam, RNG, camera order/remaining stack, lineage, tags, target index, release counters, n6000',
        scoring_snapshot_phase='before scheduled density/reset at 7000 as r4n; complete resume state saved at end of same iteration',
        no_pause_during_scoring=True,pixel_coverage_is_gate=False,pixel_coverage_reference=.8,
        gates=dict(health='no nonfinite loss; immutable prior-seed lineage opacity median >=0.05; 7000 count <=3*6000 count',floating_max=.05,agreement_tau_min={'ALS':.693,'LoD2':.741},no_surface='<= exact r4n same-score cells 0~3'),
        health_opacity_population='origin==1: all descendants originally seeded from prior patch, including released; current patch-only also reported',
        result_names=['tg_B173nb_b10_ALS_s0_r6','tg_B173nb_b10_LoD2_s0_r6'],
        first_calculation_after_this_lock=True,stage0_and_maps='r2 bytes immutable',source_tag='[이 발주에서 냄]')
    d['amendments'].append(dict(at=at,reason='Direct r6 user order: free background/released, reattach patch to current nearest frozen target, geometry-based gate, complete checkpoints',decision_sha256=sha(order),previous_config_sha256=sha(C/'target_v1.stage1.r4n.json')))
    put(C/'target_v1.r6.json',d)
    put(C/'target_v1.r6.lock.json',dict(at=at,config_sha256=sha(C/'target_v1.r6.json'),decision_sha256=sha(order),base_manifest_sha256=sha(C/'fork_r20_base.json'),scientific_verdict=None))
    (O/'r6/verification').mkdir(parents=True)
    print('LOCKED',at,sha(C/'target_v1.r6.json'))
if __name__=='__main__':main()
