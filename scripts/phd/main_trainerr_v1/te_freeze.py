"""Write and sha-lock the r28 training-log configs derived from the locked trainerr_v1.json record_runs section (stage 0/1)."""
from common import *
def main():
    c = cfg(); tl = json.loads((R/'configs/phd/main_trainlog_v1/trainlog_v1.json').read_text())
    grav = PH.parent/'p0-audit/data/work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/checkpoints/030-dense_mvs_and_gravity.json'
    up = np.array(json.loads(grav.read_text())['payload']['gravity']['up'], float); up /= np.linalg.norm(up)
    coords = dict(crs='EPSG:25832', local_to_world_translation=c['coordinates']['shift_to_EPSG25832_m'], up=up.tolist(), gravity_source=str(grav), gravity_sha256=sha(grav))
    keys = [str(k) for k in c['record_runs']['key_iterations']] + ['3000_pre_reset']
    rec = dict(training_log=dict(save_iterations=tl['training_log']['save_iterations'], save_rule=tl['training_log']['save_rule'], scene_dump=keys,
               flush_every=500, curve_every=100), coordinates=coords, note='TRAINLOG 2.2 schedule; scene dump only at TRAINERR key iterations (+3000_pre_reset); range = --jbgs_trainlog_region', scientific_verdict=None)
    probe = dict(training_log=dict(save_iterations=list(range(0, 301, 50)), scene_dump=True, flush_every=100, curve_every=100), coordinates=coords,
                 note='unit-check schedule only (small example, 300 iterations)', scientific_verdict=None)
    out = {}
    for name, v in [('trainlog_te.json', rec), ('trainlog_probe.json', probe)]:
        p = C/name; assert not p.exists(); dump(p, v); out[name] = sha(p)
    dump(C/'trainlog_te.lock.json', dict(at=now(), files=out, base_config_sha256=sha(C/'trainerr_v1.json'), scientific_verdict=None)); print(out)
if __name__ == '__main__': main()
