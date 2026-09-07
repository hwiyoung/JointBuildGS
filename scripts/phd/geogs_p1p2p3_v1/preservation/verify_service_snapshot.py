"""Compare current Docker ps identities with the initial task service snapshot."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse(line):
    identifier, name, image, remainder = line.split(maxsplit=3)
    match = re.search(r'(?:\d+\.\d+\.\d+\.\d+:|\[::\]:|\d+/tcp|\d+/udp)', remainder)
    ports = remainder[match.start():] if match else ''
    return dict(id=identifier, name=name, image_descriptor=image,
                running=remainder.startswith('Up '),
                ports=sorted(p.strip() for p in ports.split(',') if p.strip()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--current', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Run the verifier in Docker')
    old = [parse(line) for line in args.baseline.read_text().splitlines() if line]
    current = [parse(line) for line in args.current.read_text().splitlines() if line]
    by_id = {row['id']: row for row in current}
    if len(by_id) != len(current) or len({row['id'] for row in old}) != len(old):
        raise ValueError('Duplicate snapshot container IDs')
    rows = [dict(baseline=row, current=by_id.get(row['id']),
                 pass_identity=row == by_id.get(row['id'])) for row in old]
    passed = bool(rows) and all(row['pass_identity'] for row in rows)
    receipt = dict(schema='GEOGS_SERVICE_SNAPSHOT_IDENTITY_v1',
                   status='PASS' if passed else 'DIFFERENCE_REQUIRES_REVIEW',
                   checked_at_utc=datetime.now(timezone.utc).isoformat(),
                   baseline_sha256=sha(args.baseline), current_sha256=sha(args.current),
                   script_sha256=sha(__file__), baseline_count=len(rows),
                   identity_pass_count=sum(row['pass_identity'] for row in rows),
                   services=rows, scientific_verdict=None,
                   limitation='Point-in-time ID/name/image descriptor/ports/running comparison; no never-restarted, data-byte, or browser health claim.')
    with args.output.open('x') as stream:
        json.dump(receipt, stream, indent=2)
    print(json.dumps({k: receipt[k] for k in ('status', 'baseline_count', 'identity_pass_count')}))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
