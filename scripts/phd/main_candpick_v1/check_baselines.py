"""Read all baseline PLY fields in bounded chunks, without rendering/training."""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from plyfile import PlyData
from input_audit import sha


def main():
    inventory_path = Path('/docs/input_audit_v1.json')
    inventory = json.loads(inventory_path.read_text())
    rows = []
    for item in inventory['baselines']:
        p = Path(item['checkpoint']['path'])
        assert sha(p) == item['checkpoint']['sha256'], 'baseline changed after inventory'
        ply = PlyData.read(p, mmap='r')['vertex'].data
        bad = {k: 0 for k in ply.dtype.names}
        invalid_quaternions = 0
        min_quat_norm = float('inf')
        scale_overflow = 0
        for start in range(0, len(ply), 100000):
            block = ply[start:start + 100000]
            for name in bad:
                bad[name] += int((~np.isfinite(block[name])).sum())
            rotation = np.column_stack([block[f'rot_{i}'] for i in range(4)])
            norm = np.linalg.norm(rotation.astype(np.float64), axis=1)
            invalid_quaternions += int((~np.isfinite(norm) | (norm < 1e-12)).sum())
            min_quat_norm = min(min_quat_norm, float(np.nanmin(norm)))
            scale = np.column_stack([block[k] for k in bad if k.startswith('scale_')])
            # Existing model exponentiates float32 log-scales at render time.
            with np.errstate(over='ignore', invalid='ignore'):
                scale_overflow += int((~np.isfinite(np.exp(scale))).sum())
        fail = any(bad.values()) or invalid_quaternions or scale_overflow
        row = dict(site=item['site'], prior=item['prior'], points=len(ply),
                   checkpoint=item['checkpoint'], finite_fields=not any(bad.values()),
                   nonfinite_by_field=bad, invalid_quaternions=invalid_quaternions,
                   minimum_quaternion_norm=min_quat_norm, scale_activation_nonfinite=scale_overflow,
                   status='FAIL' if fail else 'PASS',
                   scope='numeric checkpoint usability only; not rendered scene preflight')
        rows.append(row)
        print(row['site'], row['prior'], row['status'], row['points'], flush=True)
        del ply
    report = dict(task_id='PHD-MAIN-CANDPICK-v1', at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
                  status='PASS' if all(r['status'] == 'PASS' for r in rows) else 'FAIL',
                  inventory_sha256=sha(inventory_path), script_sha256=sha(__file__),
                  docker_image=inventory['docker_image'], rows=rows,
                  optimizer_steps=0, rendered=False, scientific_verdict=None)
    dest = Path('/docs/baseline_numeric_check_v1.json')
    assert not dest.exists(), 'preserve prior validation'
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
