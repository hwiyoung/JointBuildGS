# Branch retirement receipt — 2026-07-30

## Result

The repository now has two durable local branches and one remote branch:

- `main` — default and stable integration branch
- local `exp/fusion-w1` — upstream-free recovery branch for the preserved dirty WIP

Remote `main` contains technical closeout
`9dd020e1b7fa95aa6ac2f3fd7e68440d8012cf96`; this receipt itself may be a later
documentation-only descendant. Local `exp/fusion-w1` remains at
`c90ef861a50338ef8c57916ef62f74b211912a68`; its staged, unstaged, and untracked
bytes are preserved by the Fusion WIP snapshot. GitHub's symbolic `HEAD` resolves
to `refs/heads/main`.

No commit history was rewritten. No scientific data, experiment result, or
`.gitignore` content was changed by branch retirement.

## Preserved unique tips

Two branch tips were not ancestors of the new `main`, so annotated archive tags were
pushed and dereferenced against their original commits before deleting the branches.

| Retired branch | Archive tag | Preserved commit |
|---|---|---|
| `fc/current-baseline-cleanup` | `archive/fc-current-baseline-cleanup-20260611` | `8b1796c85e9a81f34b6acd826ca89ba952d55aa9` |
| `wip/textureless-signal` | `archive/wip-textureless-signal-20260622` | `21054f48d4c0d36afc0f74fe4b2dc43f1106b633` |

## Remote branches removed

The following remote heads were removed only after the current cleanup head was
atomically pushed to both retained branches and the two unique tips above were tagged:

- `exp/3b-surface-restore`
- `exp/3b-surface-restore-corrected`
- `feat/p2-d6-curved`
- `feat/p2-fidelity`
- `feat/p2-structure-learn`
- `feature/p2-gsjso`
- `feature/p2-prior-full`
- `feature/p2-semantic-seed`
- `wip/textureless-signal`

All removed remote heads except `wip/textureless-signal` were already ancestors of
`f5189b9cea2ba3701b12d3bbbf8aaef447cae3a5`.

## Final Fusion remote retirement

Remote `exp/fusion-w1` was removed in the final Work-readiness closeout after its
`c90ef86` tip was verified as an ancestor of the new `main`, the local dirty WIP
snapshot restored byte-identically, and the 157-test technical handoff passed. The
local recovery branch was deliberately retained without an upstream.

## Local branches removed

The same obsolete local branches were removed, together with local-only aliases whose
tips were already reachable from `main`:

- `fc/current-baseline-cleanup` (archive-tagged)
- `feature/p0-input-audit`
- `feature/p2-seed-protect`
- all remote branch names listed above

The final durable local refs are `main` and the upstream-free recovery branch
`exp/fusion-w1`. The final live remote head is `main` only.

## Verification evidence

- Remote `HEAD` and `main` were queried directly with
  `git ls-remote --symref`.
- The archive tags were queried with their dereferenced `^{}` refs and matched the
  preserved commits in the table.
- Ancestor checks used `git merge-base --is-ancestor` against the retained cleanup
  head before any branch deletion.
- The remote branch deletion used one atomic push; local merged branches used safe
  deletion, while only the two archive-tagged unique branches required forced local
  ref deletion.
- Before deleting remote `exp/fusion-w1`, its `c90ef86` tip was verified as an
  ancestor of the pushed technical handoff. The original dirty checkout was not
  reset or cleaned; only its obsolete upstream configuration was removed.
