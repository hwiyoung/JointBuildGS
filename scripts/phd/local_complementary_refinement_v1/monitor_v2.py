"""Read-only compact progress from completed JSONL records and phase receipts."""
import json
from pathlib import Path
from common import read, require_docker


def last_row(path):
    if not path.exists():
        return None
    for line in reversed(path.read_text().splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def main():
    require_docker()
    cfg = read('/config.json')
    rows = []
    for region in cfg['regions']:
        for condition in cfg['conditions']:
            root = Path('/runs')/region/condition['id']
            if not root.exists():
                continue
            result = dict(region=region,condition=condition['id'],phases={})
            for phase in ('train','render','metrics'):
                receipt = root/f'{phase}_receipt.json'
                invocation = root/f'{phase}_invocation.json'
                if receipt.exists():
                    value = read(receipt)
                    result['phases'][phase] = value['status']
                elif invocation.exists():
                    result['phases'][phase] = 'RUNNING_OR_INTERRUPTED'
            trace = last_row(root/'model/local_trace.jsonl')
            if trace:
                result.update(iteration=trace['iteration'],gaussians=trace['gaussians'],
                    lambda_v=trace['lambda_visual'],elapsed_s=round(trace['elapsed_seconds']),
                    peak_alloc_gib=round(trace['peak_cuda_allocated_bytes']/2**30,2),
                    peak_reserved_gib=round(trace['peak_cuda_reserved_bytes']/2**30,2))
            rows.append(result)
    print(json.dumps(dict(runs_present=len(rows),expected=18,rows=rows,scientific_verdict=None)),flush=True)


if __name__ == '__main__':
    main()
