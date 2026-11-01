"""Host stdlib progress and explicit implementation issue history."""
import datetime as dt,json
from pathlib import Path
R=Path(__file__).resolve().parents[3];D=R/'docs/experiments/phd/main_target_v1';O=R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1/r6'
at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat();rows=[]
for prior in ['ALS','LoD2']:
 p=O/f'runs/tg_B173nb_b10_{prior}_s0_r6/model/target_monitor/curve.jsonl'
 if p.exists():rows.append((prior,json.loads(p.read_text().splitlines()[-1])))
with (D/'progress.md').open('a') as f:
 f.write('\n## r6 · '+at+'\n\n배경·풀림 묶기 해제와 패치 목표 재연결을 r20에 구현했다. r19 110개 파일과 r2 씨앗·목표·지도 바이트는 보존했다. 설정 잠금 17:46 KST, SHA-256 `1fce3f0a7b9142e37ec3c9c323dec589ba998ad725e73cf23cf49342c9d35593`.\n\n단위 검증: 배경/풀림 위치 보존, 최근접 목표, 복제·분할·삭제, 연속/재시작 100회 모델·Adam·난수·영상 순서 동일 PASS. 동일 목표 지도와 씨앗으로 r4n의 사용자 승인 초기 점검을 계승했다.\n\n')
 for p,r in rows:f.write(f'- {p}: {r["iteration"]:,}회, 현재 가우시안 {r["gaussians"]:,}개.\n')
 f.write('\n두 판 학습과 r4n 메시 재채점 진행 중. 7,000회 이후 CPU 채점 동안 계속 학습하며 새 기준 미달이면 두 판을 멈춘다. 나머지 여섯 판은 점검 통과 전 시작하지 않는다. 예상: 7,000회 모델은 18:10 전후, 채점·진단·점검 ZIP은 자원 상태에 따라 19시 전후(예상, 완료 시각 아님). scientific_verdict: null.\n')
with (D/'issues.md').open('a') as f:f.write('\n## r6 구현 점검 · '+at+'\n\n- 소스 생성기의 단일 치환 가정이 train.py의 두 묶기 호출에 맞지 않아 중단했다. 첫 호출의 Adam 갱신 문맥으로 한정해 수정했다. r19 변경 없음, 학습 전의 생성 오류다.\n- 결정적 GPU 단위 점검 첫 시도는 CuBLAS 결정성 환경 설정 누락으로 실패했다. 첫 로그/폴더를 보존하고 `CUBLAS_WORKSPACE_CONFIG=:4096:8`을 넣어 다시 점검하여 PASS. 실제 실험 학습의 기존 수치 설정은 바꾸지 않았다.\n- 전체 상태는 7,000회 밀도 제어·목표 갱신 뒤, 건강 검사 직전에 저장한다. 채점용 PLY/스냅샷은 r4n과 같은 밀도 제어 직전이다. 두 시점 차이를 기록하며 이어 학습은 전체 상태만 사용한다.\n')
