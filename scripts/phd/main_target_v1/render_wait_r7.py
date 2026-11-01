"""Read-only baseline render queue; use the other GPU while baseline training runs."""
import json,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[3];O=R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1'
def main():
    for prior in ['ALS','LoD2']:
        receipt=O/'r7/baselines'/f'base7k_B173nb_b10_{prior}_s0/receipt.json'
        while not receipt.exists():time.sleep(5)
        assert json.loads(receipt.read_text())['status']=='COMPLETE_7000'
        subprocess.run([sys.executable,str(Path(__file__).with_name('run_diagnostic_gpu_r7.py')),'1','render_baseline7k_r7.py',prior],check=True)
if __name__=='__main__':main()
