"""Bundle (host python, stdlib). usage: python3 df_zip.py <kind>   kind = 학습전셈 | 중간1 | 중간2 | 전체
Contents: docs/experiments/phd/main_depthfix_v1 (all), configs/phd/main_depthfix_v1, scripts/phd/main_depthfix_v1 (*.py, *.sh), payload checks/ and
receipts (families/targets_receipt, maps/base/*receipt*), and for result bundles points/ and figures; SHA256SUMS inside."""
import datetime as dt, hashlib, sys, zipfile
from pathlib import Path
R = Path(__file__).resolve().parents[3]; O = R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_depthfix_v1/PHD-MAIN-DEPTHFIX-v1'
kind = sys.argv[1]; stamp = dt.datetime.now().strftime('%m%d-%H%M'); out = O/'zips'/f'PHD-MAIN-DEPTHFIX-v1_{kind}_{stamp}.zip'; out.parent.mkdir(exist_ok=True)
files = []
for base in [R/'docs/experiments/phd/main_depthfix_v1', R/'configs/phd/main_depthfix_v1']: files += [p for p in base.rglob('*') if p.is_file()]
files += sorted(p for p in (R/'scripts/phd/main_depthfix_v1').glob('*') if p.suffix in ('.py', '.sh'))
pay = [O/'checks', O/'families/targets_receipt'] + sorted((O/'points').glob('pts_*.npz')) + ([O/'points_out'] if kind != '학습전셈' else [])
for b in pay:
    if b.is_file(): files.append(b)
    elif b.exists(): files += [p for p in b.rglob('*') if p.is_file()]
files += sorted((O/'maps/base').glob('*receipt*.json'))
for p in (O/'runs').rglob('receipt.json') if kind != '학습전셈' else []:
    if p.parent.parent.parent == O/'runs': files.append(p)
sums = []
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in files:
        a = ('payload/'+str(p.relative_to(O))) if O in p.parents else str(p.relative_to(R))
        z.write(p, 'PHD-MAIN-DEPTHFIX-v1/'+a); sums.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {a}')
    z.writestr('PHD-MAIN-DEPTHFIX-v1/SHA256SUMS', '\n'.join(sums)+'\n')
print(out, out.stat().st_size, hashlib.sha256(out.read_bytes()).hexdigest())
