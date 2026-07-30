# Work bootstrap attempt receipt — 2026-07-30

## Attempt 1: not transported

Local commit `58c1dfa685e9cf8e5d1773c7a4ba713594a256a2` created the pending
`work-bootstrap-20260730` offered receipt, but its post-commit inventory gate found
`DOCUMENT_CATALOG.csv` and `DOCUMENT_LINEAGE.csv` stale. The receipt had been added
to the Git index only after inventory generation, so the generator had not treated
it as a tracked input.

That commit was not pushed as `origin/main`, was never fetched or acknowledged by a
Work Host, and is not acceptance or verification evidence. Its immutable receipt
remains `technical_state=pending` and makes no scientific claim.

The recovery sequence is additive: record this failed ordering, regenerate the
catalog with every new input already staged, verify the clean committed state, then
create a replacement offered receipt under a new handoff ID. No receipt or history
is amended, deleted, or rewritten.
