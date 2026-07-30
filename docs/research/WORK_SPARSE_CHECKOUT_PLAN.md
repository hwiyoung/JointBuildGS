# Work sparse-checkout and partial-clone plan

## Decision

Use a **new control-plane checkout** of the existing repository with both partial clone and cone-mode sparse checkout. Do not convert the current approximately 59 GiB active P2 checkout in place; its staged Fusion work and Docker compatibility mounts should remain undisturbed. The 457.691 GiB figure below refers to the pre-storage-migration baseline.

Partial clone and sparse checkout solve different costs:

- `--filter=blob:none` avoids downloading unneeded Git blobs until accessed.
- sparse checkout limits which tracked paths appear in the working tree.
- neither mechanism removes or manages ignored/untracked data already present in a checkout.

This plan is not executed by the audit.

## Preconditions

1. Preserve the current `JointBuildGS` checkout and linked worktree exactly as they are.
2. Confirm the target branch SHA through `git ls-remote`; the audit baseline is `exp/fusion-w1` at `97f6b3ef3159360b88ba0b25cca4b280c14fdcb8`.
3. Test in a new sibling directory on storage with enough room for on-demand blob fetches.
4. Run the clone from the host or provide the container with a valid remote URL/SSH configuration. The current container cannot resolve the host-only `github-hwiyoung` alias.
5. Do not hydrate C-class research artifacts until their manifests and need are known.

## Profile 1: control plane

The default work profile should include implementation, configs, research instructions, phase scripts/docs, and this audit while excluding bulk run trees and most figure collections.

Suggested cone directories:

```text
src
configs
scripts
tools
tests
docs/catalog
docs/research
docs/experiments
phases/p0-audit/docs
phases/p0-audit/scripts
phases/p2-gsjso/configs
phases/p2-gsjso/docs
phases/p2-gsjso/scripts
```

Cone mode also retains files directly in ancestor directories, so root repository instructions/build files and top-level phase guide files remain available. Verify this explicitly in the pilot clone.

Proposed commands for a new checkout only:

```bash
git clone \
  --filter=blob:none \
  --no-checkout \
  --branch exp/fusion-w1 \
  git@github-hwiyoung:hwiyoung/JointBuildGS.git \
  JointBuildGS-control

cd JointBuildGS-control
git sparse-checkout init --cone
git sparse-checkout set \
  src configs scripts tools tests \
  docs/catalog docs/research docs/experiments \
  phases/p0-audit/docs phases/p0-audit/scripts \
  phases/p2-gsjso/configs phases/p2-gsjso/docs phases/p2-gsjso/scripts
git checkout exp/fusion-w1
```

If the SSH alias is unavailable in the chosen execution environment, use an approved HTTPS URL or an SSH host configured for that environment. Do not copy credentials into the repository.

## Profile 2: evidence review

Start from Profile 1, then add only the curated evidence collection needed for a review. Example:

```bash
git sparse-checkout add \
  docs/evidence
```

Do not add all of `docs/` casually: it currently contains 498.474 MiB, including 351.948 MiB under `docs/figs/`. Add a specific figure directory only when needed:

```bash
git sparse-checkout add docs/figs/<approved-evidence-set>
```

Because this is a partial clone, opening or checking out those paths may fetch their blobs on demand.

## Profile 3: one experiment/run

Add a precise run directory and its corresponding configuration/script directories, not all of `phases/p2-gsjso/runs`:

```bash
git sparse-checkout add phases/p2-gsjso/runs/<run_id>
```

Then resolve external C-class inputs from that run's tracked manifest into an explicit artifact/work volume. Keep the Git checkout and artifact hydration steps separate and auditable.

## Verification gates

Run these read-only checks in the pilot clone:

```bash
git rev-parse HEAD
git rev-parse --is-shallow-repository
git config --get remote.origin.promisor
git config --get remote.origin.partialclonefilter
git config --get core.sparseCheckout
git config --get core.sparseCheckoutCone
git sparse-checkout list
git status --short --branch
git count-objects -vH
```

Required results:

- `HEAD` equals the intended live origin SHA.
- The repository is not shallow; partial clone must preserve history semantics.
- `remote.origin.promisor=true` and the filter is `blob:none` or an explicitly approved equivalent.
- sparse checkout and cone mode are enabled.
- only requested path families are present.
- no original data/results are copied, moved, or modified.
- the checkout can run source/config validation without bulk artifact hydration.

Record clone wall time, network bytes if available, `.git` size, checked-out size, and the first on-demand fetch caused by adding an evidence/run path. Compare these measurements with a normal clone before making this the documented default.

## Artifact hydration contract

Sparse checkout must not be treated as an artifact manager. For a run that needs datasets/checkpoints:

1. read the tracked C-class manifest;
2. verify access and free space;
3. download to the approved external/work volume, not by committing it into the sparse checkout;
4. validate recorded bytes/hash and CRS where applicable;
5. mount or reference it through the existing Docker/config contract;
6. record the resolved artifact ID/URI in the run receipt.

Avoid a command that recursively copies the existing `data/`, `results/`, or phase run trees into the new checkout.

## Operational cautions

- Git commands that inspect blob contents across all history can trigger large on-demand fetches in a partial clone. Prefer metadata-only commands unless content is necessary.
- Sparse checkout does not hide files already present as ignored/untracked; this is why the plan uses a new directory.
- A path added to the sparse set is not automatically scientifically usable; C-class dependencies still need manifest verification.
- Git LFS, if adopted later, is independent of partial clone. Test `GIT_LFS_SKIP_SMUDGE=1` and explicit LFS fetch behavior separately.
- The current repository has a second linked worktree. Do not use it as the sparse-clone pilot or alter its shared Git configuration.

## Rollback

The pilot is disposable because it is a new checkout. If the remote/filter/client combination is unsuitable, stop using the new directory and leave the original checkout untouched. Any later removal of the pilot directory is a separate destructive action requiring explicit scope and approval; it is not part of this plan or audit.

## Reassessment triggers

Reconsider a separate ResearchControl repository only if there is a durable need for different access controls, release cadence, archival ownership, or publication boundaries. Reconsider history cleanup only if measured clean-clone cost remains unacceptable after partial/sparse adoption, or if future commits introduce blobs that violate the proposed gates.
