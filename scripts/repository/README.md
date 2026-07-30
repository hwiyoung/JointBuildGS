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
