#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1: GeoGS initial points of the eight (prior, cell) scenes, at most two at a time (24 workers each), each started when
its scene receipt exists and host MemAvailable >= 35 GB (host side, stdlib).   nohup python3 run_geogs_pcd_chain.py > OUT/logs/geogs_pcd_chain.log 2>&1 &
scientific_verdict: null"""
import subprocess, time
from pathlib import Path
from b151_host import OUT, SCRIPTS, avail_gb, now, progress
todo = [(p, k) for p in ['LoD2', 'ALS'] for k in [0, 1, 2, 3]]
running = {}
while todo or running:
    for key, pr in list(running.items()):
        if pr.poll() is not None:
            progress(f'GeoGS 초기 점 {key[0]} 칸 {key[1]}: 종료 코드 {pr.returncode}')
            del running[key]
    for p, k in list(todo):
        if len(running) >= 2:
            break
        S = OUT / 'scenes' / f'GeoGS_{p}' / f'cell{k}'
        if not (S / 'scene_receipt.json').exists() or avail_gb() < 35:
            continue
        log = open(OUT / 'logs' / f'geogs_pcd_{p}_{k}.log', 'a')
        running[(p, k)] = subprocess.Popen(['bash', str(SCRIPTS / 'run_geogs_cpu.sh'), f'geogs-pcd-{p.lower()}-{k}', '26', '48g', 'b151_geogs_inputs.py', 'pcd', p, str(k),
                                            '--workers', '24'], stdout=log, stderr=subprocess.STDOUT)
        todo.remove((p, k))
        print(now().isoformat(), 'start', p, k, flush=True)
    time.sleep(30)
print(now().isoformat(), 'all done', flush=True)
