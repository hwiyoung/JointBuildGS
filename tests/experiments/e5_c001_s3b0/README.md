# E5 C001 S3B0 tests

Five test modules validate the reusable S3B0 drivers in `scripts/experiments/e5_c001_s3b0/`. From the repository root, run:

```bash
docker compose run --rm dev python -m unittest discover -s tests/experiments/e5_c001_s3b0 -p 'test_*.py' -v
```
