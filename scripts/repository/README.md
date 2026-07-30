# Repository operations

Repository inventory, storage-policy checks, and other maintenance automation.
These utilities must remain read-only unless their command explicitly declares
the generated catalog files it updates.

Agent instructions are governed only by root `AGENTS.md`; root `CLAUDE.md` must be
its byte-identical compatibility mirror, and nested instruction files are forbidden.
Validate this contract in the project container:

```bash
python scripts/repository/validate_agent_instructions.py
python -m unittest tests.repository.test_agent_instruction_sync
```

Cross-host operations also use:

- `validate_work_readiness.py` — Git-only or local-artifact ChatGPT Work readiness;
- `validate_two_host_handoff.py` — exact-commit ancestry, immutable receipt chain,
  scope, role, live artifact rehash, and structured dirty-WIP snapshot gate for
  Work Host/Experiment Host transfer.

Run these through the repository Docker image. Maintenance scripts that mutate
inventories or artifacts require their owning task contract and must not be used as
ad-hoc cleanup commands.
