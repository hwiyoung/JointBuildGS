# Branch retirement receipt — 2026-07-30

## Result

The repository now has two local branches and two remote branches:

- `main` — default and stable integration branch
- `exp/fusion-w1` — active Fusion W1 workstream

Both branches resolve to `f5189b9cea2ba3701b12d3bbbf8aaef447cae3a5` at this
receipt. GitHub's symbolic `HEAD` resolves to `refs/heads/main`.

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

## Local branches removed

The same obsolete local branches were removed, together with local-only aliases whose
tips were already reachable from `main`:

- `fc/current-baseline-cleanup` (archive-tagged)
- `feature/p0-input-audit`
- `feature/p2-seed-protect`
- all remote branch names listed above

The final local refs are `main` and `exp/fusion-w1`. The final live remote heads are
also `main` and `exp/fusion-w1`.

## Verification evidence

- Remote `HEAD`, `main`, and `exp/fusion-w1` were queried directly with
  `git ls-remote --symref`.
- The archive tags were queried with their dereferenced `^{}` refs and matched the
  preserved commits in the table.
- Ancestor checks used `git merge-base --is-ancestor` against the retained cleanup
  head before any branch deletion.
- The remote branch deletion used one atomic push; local merged branches used safe
  deletion, while only the two archive-tagged unique branches required forced local
  ref deletion.
