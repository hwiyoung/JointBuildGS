#!/usr/bin/env python3
"""메모리 예산 일정 관리기 (호스트 python3, 표준 라이브러리만). 11/12 15:05 호스트 OOM 재시작 뒤 만듦.
- 동시에 도는 이 작업 컨테이너의 --mem 합 <= BUDGET (80 GB), 새로 띄울 때 호스트 메모리 사용 <= 78 %.
- 일마다: 이름, --mem, --cpus, 명령, 앞선 일, 끝남 표시 파일, 묶음(묶음마다 동시 개수 상한).
- 실패하면 한 번 다시(_retry), 그래도 실패면 '확인 불가'로 적고 다음으로.
- 광도 점수: 빈 GPU(다른 compute 프로세스 없음)가 있으면 GPU, 두 GPU 가 30분 넘게 차 있으면 CPU.
  python3 sched.py <plan>   plan = stage1 | sens | post"""
import json, os, subprocess, sys, time, datetime as dt
from pathlib import Path
HERE = Path(__file__).resolve().parent; REPO = HERE.parents[2]
ART = (REPO/'..'/'JointBuildGS-artifacts').resolve(); OUT = ART/'phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2'
BUDGET = 80; HOSTMAX = 78
LOG = OUT/'logs/sched.log'
def now(): return dt.datetime.now().strftime('%m-%d %H:%M:%S')
def log(s):
    with LOG.open('a') as f: f.write(f'{now()} {s}\n')
def hostpct():
    t = a = None
    for line in open('/proc/meminfo'):
        if line.startswith('MemTotal'): t = int(line.split()[1])
        if line.startswith('MemAvailable'): a = int(line.split()[1])
    return 100*(t - a)/t
def gpu_free():
    out = []
    for g in [0, 1]:
        r = subprocess.run(['nvidia-smi', '-i', str(g), '--query-compute-apps=pid', '--format=csv,noheader'], capture_output=True, text=True)
        if r.returncode == 0 and not r.stdout.strip(): out.append(g)
    return out
TILES = [t['id'] for t in json.load(open(ART/'phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2/inputs/tiles.json'))]
GEO = [t for t in TILES if (OUT/'geometry_raw'/f'{t}__LoD2.npz').exists() or (OUT/'geometry_raw'/f'{t}__ALS.npz').exists()]
def J(name, mem, cpus, script, args, done, deps=(), group=None, extra=()):
    return dict(name=name, mem=mem, cpus=cpus, script=script, args=list(args), done=done, deps=list(deps), group=group or name, extra=list(extra))
def tsdf_done(t): return (OUT/'truth/mvs_surface'/f'{t}.npz').exists() or (OUT/'truth/mvs_surface'/f'{t}_q3.npz').exists()
def plan_stage1():
    jobs = [J('sight_LoD2', 20, 2, 's2_sight.py', ['LoD2'], lambda: (OUT/'sight/LoD2.complete.json').exists(), group='sight')]
    for t in GEO:
        jobs.append(J(f'prep_{t}', 12, 2, 's3_photo_prepare.py', [t], (lambda t=t: (OUT/'photo_prepared'/f'{t}.json').exists()), group='prep'))
        jobs.append(J(f'score_{t}', 14, 4, 's3_score.py', ['@dev', t], (lambda t=t: (OUT/'photo_scores'/t/'complete.json').exists() or ((OUT/'photo_prepared'/f'{t}.json').exists() and not (OUT/'photo_prepared'/f'{t}.npz').exists())), deps=[f'prep_{t}'], group='score'))
    jobs.append(J('judge_base', 16, 4, 's5_judge.py', ['base'], lambda: (OUT/'judge/base.json').exists(), deps=['sight_LoD2'] + [f'score_{t}' for t in GEO], group='judge'))
    for t in TILES:
        if not tsdf_done(t): jobs.append(J(f'tsdf_{t}', 16, 4, 's1_tsdf_q.py', [t], (lambda t=t: tsdf_done(t)), group='tsdf', extra=['--image', 'jointbuildgs:geogs-conf-guided-v1']))
    for t in GEO:
        d = [f'tsdf_{t}'] if not tsdf_done(t) else []
        jobs.append(J(f'truth_{t}', 20, 8, 's4_truth_rest.py', [t], (lambda t=t: (OUT/'truth/rest'/f'{t}.json').exists()), deps=d, group='truth'))
    for t in GEO: jobs.append(J(f'sens_{t}', 20, 48, 's1_ring.py', ['sens', t], (lambda t=t: (OUT/'ring/sens'/f'{t}.json').exists()), group='ring'))
    for t in GEO: jobs.append(J(f'face_{t}', 20, 48, 's1_ring_face.py', [t], (lambda t=t: (OUT/'ring/face'/f'{t}.json').exists()), deps=[f'sens_{x}' for x in GEO], group='ring'))
    for p in ['LoD2', 'ALS']: jobs.append(J(f'assemble_{p}', 32, 2, 's6_assemble.py', [p], (lambda p=p: (OUT/'analysis'/f'gt_{p}.json').exists()), deps=['judge_base'] + [f'truth_{t}' for t in GEO], group='assemble'))
    for v, dep in [('z_1.645', []), ('z_2.576', []), ('centre_shift', []), ('building_r', []), ('ring_1.0', [f'sens_{t}' for t in GEO]), ('ring_3.0', [f'sens_{t}' for t in GEO]), ('same_face_ring', [f'face_{t}' for t in GEO])]:
        jobs.append(J(f'calib_{v}', 12, 2, 's2_calibrate.py', [v], (lambda v=v: (OUT/'calib'/f'{v}.json').exists()), deps=dep, group='calib'))
        jobs.append(J(f'judgev_{v}', 16, 4, 's5_judge.py', [v], (lambda v=v: (OUT/'judge'/f'{v}.json').exists()), deps=[f'calib_{v}', 'judge_base'], group='judge'))
    return jobs
LIMIT = dict(sight=1, prep=2, score=3, judge=1, tsdf=2, truth=2, ring=1, assemble=1, calib=1)
def main(plan):
    jobs = {j['name']: j for j in plan_stage1()}; state = {n: ('done' if j['done']() else 'wait') for n, j in jobs.items()}; procs = {}; tries = {}
    busy_since = None; log(f'START plan={plan} jobs={len(jobs)} todo={sum(s == "wait" for s in state.values())}')
    while True:
        for n, (p, mem, gpu) in list(procs.items()):
            rc = p.poll()
            if rc is None: continue
            del procs[n]; ok = rc == 0 and jobs[n]['done']()
            if ok: state[n] = 'done'; log(f'DONE {n}')
            elif tries.get(n, 0) < 2: state[n] = 'wait'; log(f'RETRY {n} rc={rc}')
            else: state[n] = 'fail'; log(f'FAIL {n} rc={rc} (확인 불가)')
        waiting = [n for n, s in state.items() if s == 'wait']
        if not waiting and not procs: break
        used = sum(m for _, m, _ in procs.values()); groups = {}
        for n in procs: groups[jobs[n]['group']] = groups.get(jobs[n]['group'], 0) + 1
        for n in waiting:
            j = jobs[n]
            if any(state.get(d, 'done') in ('wait', 'run') for d in j['deps']): continue
            if any(state.get(d) == 'fail' for d in j['deps']) and j['group'] != 'judge': pass
            if groups.get(j['group'], 0) >= LIMIT.get(j['group'], 1): continue
            if used + j['mem'] > BUDGET or hostpct() > HOSTMAX: continue
            if j['done'](): state[n] = 'done'; log(f'ALREADY {n}'); continue
            args = list(j['args']); gpu = None; extra = list(j['extra']); cpus = j['cpus']
            if '@dev' in args:
                free = [g for g in gpu_free() if g not in [x[2] for x in procs.values() if x[2] is not None]]
                if free: gpu = free[0]; args[args.index('@dev')] = 'cuda'; extra += ['--gpu', str(gpu)]; busy_since = None
                else:
                    busy_since = busy_since or time.time()
                    if time.time() - busy_since < 1800 and not any(x[2] is not None for x in procs.values()):
                        continue
                    if any(x[2] is not None for x in procs.values()): continue
                    args[args.index('@dev')] = 'cpu'
            tries[n] = tries.get(n, 0) + 1; tag = n + ('' if tries[n] == 1 else '_retry')
            cmd = ['bash', str(HERE/'run.sh'), tag, '--cpus', str(cpus), '--mem', str(j['mem'])] + extra + [j['script']] + args
            p = subprocess.Popen(cmd, cwd=str(REPO), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            procs[n] = (p, j['mem'], gpu); state[n] = 'run'; used += j['mem']; groups[j['group']] = groups.get(j['group'], 0) + 1
            log(f'LAUNCH {n} mem={j["mem"]} cpus={cpus} dev={"gpu" + str(gpu) if gpu is not None else ("cpu" if "cpu" in args else "-")} used={used} host={hostpct():.0f}%')
        time.sleep(20)
    log(f'END plan={plan} done={sum(s == "done" for s in state.values())} fail={[n for n, s in state.items() if s == "fail"]}')
if __name__ == '__main__': main(sys.argv[1] if len(sys.argv) > 1 else 'stage1')
