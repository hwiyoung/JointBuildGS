"""One serial queue per admitted GPU; all arms follow the same frozen config."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('units', nargs='+'); args = p.parse_args()
    cfg = json.loads(Path('/config/candpick_v1.json').read_text())
    for unit in args.units:
        for item in cfg['arm_order']:
            subprocess.run([sys.executable, '-B', '-u', str(Path(__file__).with_name('train_candidates.py')),
                            unit, item['start'], str(item['sh_degree'])], check=True)
