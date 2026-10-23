"""Resume complete tile/prior jobs only; errors remain visible and stop the chain."""
import json
from pathlib import Path
import subprocess
import sys
import time
from preflight import dump
O=Path('/out');R=O/'holdout/internal';S=Path(__file__).parent
def main():
    start=time.monotonic()
    for t in json.loads((O/'inputs/tiles.json').read_text()):
        tile=t['id']
        for prior in ['LoD2','ALS']:
            for data in ['gt','mvs_a']+(['als'] if prior=='ALS' else []):
                f=R/'work'/(f'gt_{tile}_{prior}.npz' if data=='gt' else f'val_{tile}_{prior}_{data}_R1.5.npz')
                receipt=R/'work'/(f'run_gt_{tile}_{prior}.json' if data=='gt' else f'run_{tile}_{prior}_{data}_1.5.json')
                if f.exists() and receipt.exists():continue
                cmd=[sys.executable,'-B','-u',str(S/'u_worker.py'),tile,prior,data]
                if data!='gt':cmd+=['1.5']
                subprocess.run(cmd+['--workers','32'],check=True)
            subprocess.run([sys.executable,'-B','-u',str(S/'export_values.py'),tile,prior],check=True)
    dump(O/'gates/measurements_complete.json',dict(seconds=time.monotonic()-start,scientific_verdict=None))
if __name__=='__main__':main()
