# Pilot one-wave tests

These 24 modules cover the moved pilot drivers and the reusable Stage 2 implementation they orchestrate. From the repository root, run:

```bash
docker compose run --rm dev python -m unittest discover -s tests/experiments/pilot_1wave -p 'test_*.py' -v
```

Some integration cases require the separately pinned geospatial/reference-asset environment or local immutable run inputs; a missing optional environment asset is reported as an unavailable prerequisite, not repaired by changing source data.
