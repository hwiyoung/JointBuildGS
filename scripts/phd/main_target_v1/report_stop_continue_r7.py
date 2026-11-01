"""Host receipt of the actual continuation OOM and untouched saved checkpoints."""
import json,re,os,signal
from pathlib import Path
from run_pilot_r7 import REPO,PH,OUT,CFG,stamp,dump
from lock_continue_r7 import sha

def main():
 root=OUT/'r7_continue/attempt2';stop=json.loads((root/'STOP_BOTH.json').read_text());rows=[]
 for prior in ['ALS','LoD2']:
  run=root/'runs'/f'tg_B173nb_b10_{prior}_s0_r7';curve=[json.loads(s) for s in (run/'model/target_monitor/curve.jsonl').read_text().splitlines()];base=json.loads((OUT/'r7/runs'/run.name/'model/target_monitor/health_6000.json').read_text());log=(run/'train.log').read_text();matches=re.findall(r'Training progress:.*?\| (\d+)/23000',log);last=7000+int(matches[-1]) if matches else None
  receipt=json.loads((run/'receipt.json').read_text());row=dict(prior=prior,receipt=receipt,last_progress_iteration=last,last_health=curve[-1],count_at6000=base['gaussians'],count_ratio_to6000=curve[-1]['gaussians']/base['gaussians'],available_new_complete_states=[p.parent.name for p in (run/'model/jbgs_complete').glob('*/receipt.json')],source_complete_iteration=7000,log_sha256=sha(run/'train.log'));rows.append(row)
  tail=log[log.rfind('Traceback'): ] if 'Traceback' in log else log[-2000:];(run/'failure_tail.txt').write_text(tail)
 record=dict(at=stamp(),status='STOPPED_CUDA_OOM',training_retried=False,stop=stop,rows=rows,unavailable_iterations=[15000,30000],unavailable_requested_mesh_rows=8,remaining_available_mesh_rows=16,other_six='NOT_STARTED',count_guard_implementation='Frozen r21 checks count>3*n6000 only at iteration==7000; 14100 ALS count ratio exceeded 3 and was logged but not stopped by this condition. OOM caused the actual stop. No controller rule changed in this continuation.',scientific_verdict=None)
 dump(OUT/'r7_continue/stop_report.json',record);dump(REPO/'docs/experiments/phd/main_target_v1/tables/continue_r7_stop.json',record)
 lines=['# r7 이어 학습 실행 오류 중단 기록','',f'- 기록: {record["at"]}. scientific_verdict: null.','- 항공 LiDAR의 역전파에서 CUDA 메모리 부족이 발생했다. 추가 64 MiB 할당 요청 시 여유 38.19 MiB, PyTorch 할당 22.51 GiB였다.','- 오류는 진행 표시 14,160회 직후다. 오류 반복 자체를 담은 OOM 전용 기록은 설정상 꺼져 있어 정확한 반복 번호는 확인 불가다.','- 공용 중단 제어가 LoD2도 종료했다. 자동 재학습은 하지 않았다.','- 두 판 모두 15,000·30,000회 상태와 메시가 없다. 재개 가능한 완전 저장 상태는 원래 7,000회다.','', '| 판 | 마지막 진행 표시 | 마지막 건강 기록 | 가우시안 수 | 6,000회 대비 | 종료 코드 |','|---|---:|---:|---:|---:|---:|']
 for r in rows:lines.append(f'| {r["prior"]} | {r["last_progress_iteration"]} | {r["last_health"]["iteration"]} | {r["last_health"]["gaussians"]:,} | {r["count_ratio_to6000"]:.4f} | {r["receipt"]["exit_code"]} |')
 lines+=['','## 감시 구현 기록','','- 동결된 r21의 가우시안 수 3배 검사는 `iteration == 7000`에만 실행된다. 항공 LiDAR의 14,100회 수는 6,000회의 3배를 넘었지만 이 조건은 그때 실행되지 않았다. 실제 중단 원인은 이후 CUDA 메모리 부족이다. 이어 학습에서 이 조건을 바꾸지 않았다.','- 이 한계를 건강 검사 통과로 해석하지 않는다. 추가 학습은 사용자 후속 결정 전까지 중단한다.','','## 계속 수행하는 읽기 전용 작업','','- r6·r7·기존 방법의 7,000회와 기존 기준선 30,000회: 8개 저장 모델 × 두 메시 = 16개 메시 채점.','- 도달하지 못한 r7 15,000·30,000회 두 판 × 두 메시 = 8개 줄은 결과 없음으로 기록.','- 기존 기준선 재채점과 항공 LiDAR 설정·계보·뜬 면 진단, 확인 가능한 자료의 전달 묶음을 마무리한다.','- 나머지 여섯 판은 시작하지 않았다. 결론과 해석은 쓰지 않는다.','']
 dest=REPO/'docs/experiments/phd/main_target_v1/이어학습_r7_중단기록.md';dest.write_text('\n'.join(lines));print(dest,flush=True)
 # Only our two waiting diagnostic coordinators, with no child inference yet.
 for pid,prior in [(2071596,'ALS'),(2071597,'LoD2')]:
  p=Path('/proc')/str(pid)/'cmdline'
  if p.exists() and ('queue_diagnostics_continue_r7.py' in p.read_text()) and prior in p.read_text():os.kill(pid,signal.SIGTERM)
if __name__=='__main__':main()
