"""Addendum 4 delivery zips (order 8). Host-side, stdlib only (same rule as te_pack.py, but zips and receipts stay inside the addendum4 folders).
usage: a2_pack.py <label> <path> [<path> ...]   paths relative to the repo or to the payload root; dirs recursed; __pycache__ skipped; payload paths are written as payload/; a path listed twice is written once.
Writes PH/.../PHD-MAIN-TRAINERR-v1/addendum4/delivery/PHD-MAIN-TRAINERR-v1_<label>.zip (SHA256SUMS inside) and appends docs addendum4/delivery_receipts.jsonl."""
import hashlib, json, sys, zipfile, datetime as dt
from pathlib import Path
R = Path(__file__).resolve().parents[4]; O = R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_trainerr_v1/PHD-MAIN-TRAINERR-v1'; D = R/'docs/experiments/phd/main_trainerr_v1/addendum4'
STORE = ('.png', '.jpg', '.zip', '.npz')
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): h.update(b)
    return h.hexdigest()
def main(label, *paths):
    out = O/'addendum4/delivery'/f'PHD-MAIN-TRAINERR-v1_{label}.zip'; out.parent.mkdir(parents=True, exist_ok=True); sums = []; seen = set()
    with zipfile.ZipFile(out, 'x') as z:
        for p in paths:
            base = R if (R/p).exists() else O; src = base/p
            files = [src] if src.is_file() else sorted(x for x in src.rglob('*') if x.is_file() and '__pycache__' not in x.parts)
            for f in files:
                arc = ('repo/' if base == R else 'payload/')+str(f.relative_to(base))
                if arc in seen: continue
                seen.add(arc); z.write(f, arc, compress_type=zipfile.ZIP_STORED if f.suffix.lower() in STORE else zipfile.ZIP_DEFLATED); sums.append(f'{sha(f)}  {arc}')
        z.writestr('SHA256SUMS', '\n'.join(sums)+'\n')
    rec = dict(at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), zip=str(out), sha256=sha(out), bytes=out.stat().st_size, files=len(sums), scientific_verdict=None)
    with (D/'delivery_receipts.jsonl').open('a') as f: f.write(json.dumps(rec, ensure_ascii=False)+'\n')
    print(out, rec['bytes'], rec['files'])
if __name__ == '__main__': main(*sys.argv[1:])
