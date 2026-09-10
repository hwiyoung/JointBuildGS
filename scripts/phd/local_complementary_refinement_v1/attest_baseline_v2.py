"""Copy only technical reuse status/digests into the training contract."""
from common import read, record, require_docker, sha, write_new


def main():
    require_docker()
    receipt = read('/preflight/receipt.json')
    cfg = record('/contracts/experiment_v2.json')
    if (receipt['status'] != 'PASS_BASELINE_REUSE' or receipt['cache_count'] != 42
        or receipt['expected_cache_count'] != 42 or receipt['scientific_verdict'] is not None
        or not any(r['sha256'] == cfg['sha256'] for r in receipt['inputs'])):
        raise ValueError('Actual baseline evaluation identity not verified for main specification')
    write_new('/contracts/baseline_validation.json', dict(schema='JBGS_BASELINE_REUSE_ATTESTATION_v2',
        status='PASS_BASELINE_REUSE', scientific_verdict=None, config=cfg, verified_cache_count=42,
        source_receipt_sha256=sha('/preflight/receipt.json'), producer=record(__file__),
        scope='technical identity attestation only; no reference geometry, scores or labels'))


if __name__ == '__main__':
    main()
