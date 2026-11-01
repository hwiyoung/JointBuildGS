"""Wait for verified available evidence, prepare comparison figures, never train or publish."""
import json
import subprocess
import time
from run_pilot_r8 import REPO, OUT, CFG, stamp, dump
from readout_resources_r2 import cpu


def ready_r8(iterations):
    for prior in ['ALS', 'LoD2']:
        run = OUT/'r8/runs'/f'tg_B173nb_b10_{prior}_s0_r8'
        for it in iterations:
            checkpoint = run/f'model/point_cloud/iteration_{it}/point_cloud.ply'
            if not checkpoint.exists():
                if (OUT/'r8'/f'STOP_{prior}.json').exists():
                    continue
                return False
            paths = [run/f'report{it}.json', run/f'diagnostics_report{it}.json', run/f'verification_post{it}.json']
            paths += [OUT/f'r8/scoring/r8_{prior}_{it}/{kind}/verification.json' for kind in ['current', 'final']]
            if not all(p.exists() for p in paths):
                return False
    return True


def ready_r7():
    rows = json.loads((CFG/'scoring_continue_r7.r1.json').read_text())['rows']
    for row in rows:
        if row['family'] == 'r7' and row['prior'] == 'ALS' and row['iteration'] > 7000:
            continue
        if not all((OUT/'r7_continue/scoring'/row['key']/kind/'verification.json').exists() for kind in ['current', 'final']):
            return False
    run = OUT/'r7_continue/lod2_retry/runs/tg_B173nb_b10_LoD2_s0_r7'
    return all((run/f'verification_post{it}.json').exists() for it in [15000, 30000])


def ready_7000_references():
    rows = json.loads((CFG/'scoring_continue_r7.r1.json').read_text())['rows']
    return all((OUT/'r7_continue/scoring'/row['key']/kind/'verification.json').exists()
               for row in rows if row['iteration']==7000 for kind in ['current','final'])


def main():
    marker = OUT/'r8/verification/delivery_figures_7000_ready.json'
    while not (ready_r8([7000]) and ready_7000_references()):
        time.sleep(10)
    if not marker.exists():
        for script, args in [('report_axes_r8.py', ['7000']), ('compare_figures_r8.py', ['7000']),
                             ('audit_health_records_r8.py', []), ('audit_readout_bindings_r8.py', [])]:
            cpu('delivery-7000-'+script[:-3].replace('_', '-'), script, args)
        dump(marker, dict(at=stamp(), status='READY_FOR_VISUAL_REVIEW_AND_ARCHIVE', scientific_verdict=None))
        print('R8_7000_READY_FOR_VISUAL_REVIEW_AND_ARCHIVE', flush=True)
    while not (ready_r8([7000, 15000, 30000]) and ready_r7()):
        time.sleep(10)
    for script in ['report_continue_r7.py', 'report_records_continue_r7.py', 'compare_figures_continue_r7.py',
                   'report_detail_continue_r7.py']:
        cpu('delivery-final-'+script[:-3].replace('_', '-'), script,
            ['LoD2'] if script == 'report_detail_continue_r7.py' else [])
    for script, args in [('report_axes_r8.py', ['final']), ('compare_figures_r8.py', ['final']),
                         ('audit_health_records_r8.py', []), ('audit_readout_bindings_r8.py', [])]:
        cpu('delivery-final-'+script[:-3].replace('_', '-'), script, args)
    dump(OUT/'r8/verification/delivery_figures_final_ready.json',
         dict(at=stamp(), status='READY_FOR_VISUAL_REVIEW_AND_ARCHIVE', scientific_verdict=None))
    print('ALL_AVAILABLE_READOUTS_READY_FOR_VISUAL_REVIEW_AND_ARCHIVE', flush=True)


if __name__ == '__main__':
    main()
