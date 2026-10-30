"""Refresh task-local progress and completed-arm reports while training runs."""
import json
import subprocess
import sys
import time
from pathlib import Path


def run(name):
    result = subprocess.run([sys.executable, '-B', '-u', str(Path(__file__).with_name(name))],
                            check=True, capture_output=True, text=True)
    if result.stderr:
        print(result.stderr, flush=True)


def main():
    last_completed = None
    last_full_units = set()
    while True:
        run('progress.py')
        progress = json.loads(Path('/docs/progress.json').read_text())
        completed = {r['arm'] for r in progress['rows'] if r['status'] == 'COMPLETE'}
        if completed != last_completed:
            run('score_candidates.py')
            counts = {}
            for arm in completed:
                unit = arm.split('_', 3)[3]
                counts[unit] = counts.get(unit, 0) + 1
            full_units = {unit for unit, count in counts.items() if count == 6}
            if full_units != last_full_units:
                run('plot_results.py')
                last_full_units = full_units
            run('report_results.py')
            print(json.dumps(dict(at=progress['at'], completed=len(completed),
                                  full_units=sorted(full_units))), flush=True)
            last_completed = completed
        failures = [r for r in progress['rows'] if r['status'] == 'ERROR']
        if failures:
            raise RuntimeError('Training error remains visible: ' + json.dumps(failures))
        if len(completed) == 24:
            run('validate_results.py')
            run('verify_frozen_inputs.py')
            run('check_visual_files.py')
            print('24 arms complete; scoring, independent validation, input hashes and figure file checks complete. Visual review and packaging remain.', flush=True)
            return
        time.sleep(30)


if __name__ == '__main__':
    main()
