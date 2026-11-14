"""Host queue for addendum 3 work ba (order 7). Each run starts on a GPU with >= 14 GiB free memory that has no addendum-3 training
(addendum3.json work_ba.gpu_rule); other jobs are never stopped. Waits for every started run, writes receipts.
  python3 a3_train.py queue <run> [<run> ...]
Runs (addendum3.json work_ba.runs):
  ba1_B0_LoD2_nonormal : tl_B0_b10_LoD2_s0 command (TRAINLOG case trainlog config) + --jbgs_a3_normal off
  ba2_B0_LoD2_noreset  : tl_B0_b10_LoD2_s0 command + --jbgs_a3_reset_after 7000
  ba3_B0_ALS_record    : FINALTRAIN ft_ALS_s0 B0 command + TRAINERR record options (trainlog_te.json, annex voxel region, gradients)
  ba2b_B0_LoD2_noreset_nocheck : ba-2 rerun to 30000 (user decision 2026-11-14): ba2 command + --jbgs_a3_count_check off. The inherited FINALTRAIN
                         health stop count_gt_3x_6000 (a no_grad count read) stopped ba2 at 12000; with the switch the row is flagged and training continues."""
import json, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import a3_launch as A
ARTC = '/art/phase-payloads/phd'
CASE_CFG = '/repo/docs/experiments/phd/main_trainlog_v1/figures_concept_v2/case_B0_b10__LoD2/config/trainlog_v1.json'
RUNS = {'ba1_B0_LoD2_nonormal': ('B0_b10', 'LoD2', 'case', ['--jbgs_a3_normal', 'off']),
        'ba2_B0_LoD2_noreset': ('B0_b10', 'LoD2', 'case', ['--jbgs_a3_reset_after', '7000']),
        'ba3_B0_ALS_record': ('B0_b10', 'ALS', 'te', []),
        'ba2b_B0_LoD2_noreset_nocheck': ('B0_b10', 'LoD2', 'case', ['--jbgs_a3_reset_after', '7000', '--jbgs_a3_count_check', 'off'])}

def region_annex():
    """annex box snapped outward to the 0.25 m grid, in the TRAINERR region file layout (single box)."""
    p = A.A3O/'region/B0_b10__ALS_annex.json'
    if p.exists(): return p
    b = json.loads((A.C/'addendum3.json').read_text())['places']['annex_box']; v = .25
    lo = [b['x'][0], b['y'][0], b['z'][0]]; hi = [b['x'][1], b['y'][1], b['z'][1]]; shape = [int(round((h-l)/v)) for l, h in zip(lo, hi)]
    A.dump(p, dict(stem='B0_b10__ALS', box_columns=['xmin', 'xmax', 'ymin', 'ymax', 'zmin', 'zmax', 'points'], boxes=[[lo[0], hi[0], lo[1], hi[1], lo[2], hi[2], 0]],
                   voxel_m=v, grid_origin=lo, grid_shape=shape, occupied_voxels=shape[0]*shape[1]*shape[2], occupied_volume_m3=shape[0]*shape[1]*shape[2]*v**3,
                   rule='addendum3.json places.annex_box; TRAINERR region layout (union of snapped boxes)', scientific_verdict=None))
    return p

def args_for(run):
    site, prior, kind, change = RUNS[run]; stem = f'{site}__{prior}'; model = f'/te/addendum3/runs/{site}/{run}/attempt1/model'
    a = [site, prior, run, '-s', f'/p/fork_inputs/s61/{site}/scene_{prior}', '-m', model, '--eval', '-r', '1', '--data_device', 'cpu',
         '--lod_depth_path', '/p/fork_none', '--da_depth_path', '/p/fork_none', '--stage_switch_iter', '0', '--lambda_lod_init', '0', '--lambda_lod_anchor', '0', '--lambda_da_depth', '0',
         '--jbgs_judgment', 'off', '--jbgs_target', 'on', '--jbgs_target_rev', 'r8', '--jbgs_finaltrain', 'on',
         '--jbgs_target_dir', f'{ARTC}/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/stage1/{stem}', '--jbgs_target_lambda', '.05', '--jbgs_seed', '0', '--iterations', '30000',
         '--jbgs_capture_iterations', '7000', '15000', '30000', '--test_iterations', '7000', '15000', '30000', '--save_iterations', '7000', '15000', '30000', '--jbgs_trainlog', 'on']
    if kind == 'te':
        region_annex(); a += ['--jbgs_trainlog_region', '/te/addendum3/region/B0_b10__ALS_annex.json', '--jbgs_trainlog_grads', 'on']; env = ['JBGS_TRAINLOG_CONFIG=/cfg/trainlog_te.json']
    else: env = ['JBGS_TRAINLOG_CONFIG='+CASE_CFG, 'TL_CASE=B0_b10__LoD2']
    return a+change, env, site

def free_gpus(busy):
    q = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.free', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout.split('\n')
    return [int(i) for i, f in (x.split(', ') for x in q if x.strip()) if int(f) >= 14*1024 and int(i) not in busy]

def queue(runs):
    procs = []
    for run in runs:
        while True:
            busy = {g for g, p, *_ in procs if p.poll() is None}
            g = free_gpus(busy)
            if g: break
            time.sleep(60)
        gpu = g[0]; args, env, site = args_for(run); root = A.A3O/'runs'/site/run/'attempt1'; root.mkdir(parents=True, exist_ok=False)
        cmd = A.command(f'jbgs-te-a3-{run}', 'addendum3/a3_train_entry.py', args, gpu=gpu, env=env, split_site=site)
        A.dump(root/'command.json', cmd); A.dump(root/'launch.json', dict(at=A.now(), gpu=gpu, run=run, rule='>= 14 GiB free, no other addendum-3 training on it', scientific_verdict=None))
        f = (root/'train.log').open('x'); p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT); procs.append((gpu, p, run, root, time.monotonic(), f))
        print('STARTED', run, 'gpu', gpu, A.now(), flush=True); time.sleep(120)
    for gpu, p, run, root, t0, f in procs:
        rc = p.wait(); f.close(); ok = rc == 0 and (root/'TRAINING_COMPLETE.json').exists()
        A.dump(root/'receipt.json', dict(at=A.now(), exit_code=rc, seconds=time.monotonic()-t0, status='COMPLETED_30000' if ok else 'ERROR', scientific_verdict=None))
        print('DONE', run, rc, round(time.monotonic()-t0), flush=True)

if __name__ == '__main__':
    assert sys.argv[1] == 'queue'; queue(sys.argv[2:])
