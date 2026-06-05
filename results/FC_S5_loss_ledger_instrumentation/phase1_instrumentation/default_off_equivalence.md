# Default-Off Equivalence

Status: PASS

Checks performed:
- `python -m py_compile src/stage2/loss/mutual.py src/stage2/train.py` passed.
- Direct tensor equivalence test compared the new `l_mutual()` defaults against the legacy formula for total, wall verticality, roof non-wall, terrain normal, and combined height. All compared tensors were exactly equal.
- With all new FC-S5 config flags omitted or set to their defaults, `mutual_schedule=constant`, terrain controls enabled, relation placeholders disabled, and audit logging disabled, the existing trainer loss path remains the same as the pre-FC-S5 mutual path.

Notes:
- Split height logs are diagnostic only. The active combined height loss preserves the legacy reduction exactly when default controls are enabled.
- The two-iteration smoke config shortens `mutual_warmup` to 0 only to force audit tags to appear; that smoke is not used as an equivalence claim.

Git commit at smoke time: `5576101`
