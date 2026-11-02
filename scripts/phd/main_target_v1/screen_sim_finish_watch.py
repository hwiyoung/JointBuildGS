"""Finish the already-authorized measurement and delivery when its queues finish."""
import os,time,subprocess,json
from r8_screen_prepare import R,O,dump
ROOT=O/'screen_sim'
def cpu(label,script):
 env=dict(os.environ,TARGET_LANE='screen-finish',MEM='8',CPUS='4');cmd=['bash',str(R/'scripts/phd/main_target_v1/run_cpu.sh'),'screen-finish-'+label,script];r=subprocess.run(cmd,env=env);assert r.returncode==0,(label,r.returncode)
def main():
 while len(list((ROOT/'states').glob('*/receipt.json')))<8:time.sleep(15)
 cpu('tables','screen_sim_tables.py');cpu('verify','screen_sim_verify.py');cpu('figures','screen_sim_figure_labels.py')
 while not (ROOT/'cpu_receipt.json').exists():time.sleep(30)
 cpu('finaltables','screen_sim_tables.py');cpu('finalverify','screen_sim_verify.py');cpu('report','screen_sim_report.py')
 p=R/'docs/experiments/phd/main_target_v1/screen_sim/자원과_실행기록.md';p.write_text('''# 실행 자원 기록

학습은 없으며 GPU는 저장 모델의 forward에만 사용했다. 현재 메시 및 AXES71 채점은 CPU Docker에서 실행했다. 큰 메시·채점 작업은 한 번에 하나다.

첫 작업의 CPU quota는 6이었다. 서버 128 논리 CPU와 당시 여유를 확인한 뒤 이 작업의 `jbgs-screen-sim-cpu` 컨테이너에만 quota를 24로 늘렸다. 메모리 상한 32 GiB, OMP_NUM_THREADS=6, 계산 정의와 순서는 그대로다. 각 컨테이너 ID·명령·변경 시각은 cpu_resource_updates.json에 있다. 다른 컨테이너의 자원 설정은 변경하지 않았다.

GeoGS의 첫 두 읽기 시도는 각각 원 실행 sparse_lod 경로 미연결과 ModelParams CLI 인자 미정의로 렌더 전에 실패했다. 원 모델·원 소스는 읽기 전용이었고 변경되지 않았다. 읽기 드라이버 r3가 원 cfg_args의 sparse_lod를 dataset 속성에 전달한다. 실패 로그와 수정 잠금을 모두 남겼다.

scientific_verdict: null
''')
 r=subprocess.run(['python',str(R/'scripts/phd/main_target_v1/screen_sim_package.py')]);assert r.returncode==0,r.returncode;dump(ROOT/'finish_receipt.json',dict(status='PASS',training=False,scientific_verdict=None))
if __name__=='__main__':main()
