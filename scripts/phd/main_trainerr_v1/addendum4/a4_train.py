"""Host queue for addendum 4 work sa (order 8). Each run starts on a GPU with >= 14 GiB free memory that has no addendum-4 training
(addendum4.json work_sa.gpu_rule); other jobs are never stopped. Waits for every started run, writes receipts.
  python3 a4_train.py queue <run> [<run> ...]
Runs (addendum4.json work_sa):
  sa1_R1_ALS_record6000 : TRAINERR tl_R1_ALS_own command (r28 -> r31) + signed gradients + stop at 6000, record config addendum4_trainlog_sa1.json
  sa2_B0_LoD2_occlmask  : tl_B0_b10_LoD2_s0 command (TRAINLOG case config) + --jbgs_a4_occl_mask_m 10
  sa3_B173_ALS_nojudge  : TRAINLOG tl_B173nb_b10_ALS_s0 command, fork r32, sa-3 inputs (addendum4_sa3.json) + --jbgs_a4_dual_depth on"""
import json, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import a4_launch as A
ARTC = '/art/phase-payloads/phd'
CASE_CFG = '/repo/docs/experiments/phd/main_trainlog_v1/figures_concept_v2/case_B0_b10__LoD2/config/trainlog_v1.json'
RUNS = {'sa1_R1_ALS_record6000': ('R1rep_b10', 'ALS', 'sa1'),
        'sa2_B0_LoD2_occlmask': ('B0_b10', 'LoD2', 'case'),
        'sa3_B173_ALS_nojudge': ('B173nb_b10', 'ALS', 'sa3')}
FORK = {'sa3_B173_ALS_nojudge': 'GeoGS-conf-guided-v1-r32'}

def args_for(run):
    site, prior, kind = RUNS[run]; stem = f'{site}__{prior}'; model = f'/te/addendum4/runs/{site}/{run}/attempt1/model'
    cap = ['6000', '7000', '15000', '30000'] if kind == 'sa1' else ['7000', '15000', '30000']
    a = [site, prior, run, '-s', f'/p/fork_inputs/s61/{site}/scene_{prior}', '-m', model, '--eval', '-r', '1', '--data_device', 'cpu',
         '--lod_depth_path', '/p/fork_none', '--da_depth_path', '/p/fork_none', '--stage_switch_iter', '0', '--lambda_lod_init', '0', '--lambda_lod_anchor', '0', '--lambda_da_depth', '0',
         '--jbgs_judgment', 'off', '--jbgs_target', 'on', '--jbgs_target_rev', 'r8', '--jbgs_finaltrain', 'on',
         '--jbgs_target_dir', f'{ARTC}/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/stage1/{stem}', '--jbgs_target_lambda', '.05', '--jbgs_seed', '0', '--iterations', '30000',
         '--jbgs_capture_iterations', *cap, '--test_iterations', '7000', '15000', '30000', '--save_iterations', '7000', '15000', '30000', '--jbgs_trainlog', 'on']
    if kind == 'sa1':
        a += ['--jbgs_trainlog_region', f'/te/region/{stem}.json', '--jbgs_trainlog_grads', 'on', '--jbgs_a4_grad_signed', 'on', '--jbgs_a4_stop_at', '6000']
        env = ['JBGS_TRAINLOG_CONFIG=/cfg/addendum4_trainlog_sa1.json']
    elif kind == 'sa3':
        new = '/te/addendum4/sa3'; i = a.index('--jbgs_target_dir'); a[i+1] = f'{new}/stage1/{stem}_nojudge'
        a += ['--jbgs_targets', f'{new}/targets/{stem}_nojudge.npz', '--jbgs_a4_dual_depth', 'on']
        env = ['JBGS_TRAINLOG_CONFIG=/repo/configs/phd/main_trainlog_v1/trainlog_v1.json']
    else:
        a += ['--jbgs_a4_occl_mask_m', '10', '--jbgs_a4_mvs_dir', f'/s0/fork_inputs/s61/{site}/maps/mvs']
        env = ['JBGS_TRAINLOG_CONFIG='+CASE_CFG, 'TL_CASE=B0_b10__LoD2']
    return a, env, site

def free_gpus(busy):
    q = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.free', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout.split('\n')
    return [int(i) for i, f in (x.split(', ') for x in q if x.strip()) if int(f) >= 14*1024 and int(i) not in busy]

def queue(runs, prefer=None):
    procs = []
    for run in runs:
        while True:
            busy = {g for g, p, *_ in procs if p.poll() is None}
            g = free_gpus(busy)
            if g: break
            time.sleep(60)
        gpu = prefer if prefer in g else g[0]; args, env, site = args_for(run); root = A.A4O/'runs'/site/run/'attempt1'; root.mkdir(parents=True, exist_ok=False)
        cmd = A.command(f'jbgs-te-a4-{run}', 'addendum4/a4_train_entry.py', args, gpu=gpu, env=env, split_site=site, fork=FORK.get(run, A.FORK))
        A.dump(root/'command.json', cmd); A.dump(root/'launch.json', dict(at=A.now(), gpu=gpu, run=run, rule='>= 14 GiB free, no other addendum-4 training on it', scientific_verdict=None))
        f = (root/'train.log').open('x'); p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT); procs.append((gpu, p, run, root, time.monotonic(), f))
        print('STARTED', run, 'gpu', gpu, A.now(), flush=True); time.sleep(120)
    for gpu, p, run, root, t0, f in procs:
        rc = p.wait(); f.close(); ok = rc == 0 and (root/'TRAINING_COMPLETE.json').exists()
        A.dump(root/'receipt.json', dict(at=A.now(), exit_code=rc, seconds=time.monotonic()-t0, status='COMPLETED' if ok else 'ERROR', scientific_verdict=None))
        print('DONE', run, rc, round(time.monotonic()-t0), flush=True)

if __name__ == '__main__':
    assert sys.argv[1] == 'queue'; queue(sys.argv[2:])
