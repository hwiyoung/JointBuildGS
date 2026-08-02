# Codex-to-Work Return ? C1/C2 G2 + C3 first wave v1

- handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-v1`
- task_id: `P2-C1-C2-G2-C3-FIRST-WAVE-v1`
- source_commit: `9a65f54331af31e14da51116a220c0e8fad1c291`
- activation_commit: `70bde7b173b64b9bf9b638c51595b00458b00aa4`
- offered_commit: `0beb5a69297084e411ef189c6fc613ae76c75df3`
- accepted_commit: `6e812af318cb2d02d9052ee92cc6250117f91f7e`
- Return / 200-blocked commit: `SELF`
- proposed technical status: `BLOCKED_PRE_INPUT_CROSS_HOST_PORTABILITY`
- scientific_verdict: `null`

## Answer first

The three authorized first-stage containers each ran once and stopped in preflight.
No scientific or large-artifact processing began. The common cause is a cross-host
portability defect in the new Work-Host implementation, not a data or research-design
failure.

- C1/C2: byte sizes and SHA-256 values were frozen from the Windows CRLF worktree;
  the committed Linux LF blobs therefore failed before any sealed C1/C2 artifact read.
- semantic manifest: the same CRLF-vs-LF error rejected the Git-owned image inventory
  before any RGB read or model download.
- dense seed: Git rejected the read-only repository mount as a dubious ownership
  directory before the producer could bind HEAD; `dim_dense.ply` was not opened.

## Exact execution counters

| operation | count |
|---|---:|
| authorized preflight containers started | 3 |
| C1/C2 artifact reads / hashes | 0 / 0 |
| val3dity invocations | 0 |
| dense source reads / hashes | 0 / 0 |
| RGB reads / hashes | 0 / 0 |
| model downloads / model hashes | 0 / 0 |
| semantic inference images | 0 |
| learning runs / optimizer updates | 0 / 0 |
| validation / held-out access | 0 / 0 |
| R1 / Images.zip / OPF.zip rehash | 0 / 0 / 0 |

Only fresh empty task directories were created. No output PLY, masks, metrics,
checkpoint, result report, or promoted artifact was written.

## Required bounded recovery

A new Work-Host recovery must change only portable Git-blob identity handling and
container Git ownership binding:

1. derive committed-input bytes/SHA from Git blobs or use an explicit EOL-portable
   text identity instead of Windows worktree bytes;
2. set the exact read-only repository as a Git safe directory for the dense producer;
3. add a Linux-container regression that runs against the actual committed blobs;
4. reuse the empty namespace and do not repeat any scientific input/hash work.

The C3 recipe, 199?72 explanation, 51-building comparison roster, dense selection
rule, semantic classes/loss, depth use, and all scientific decisions remain unchanged.
This Return and `200-blocked` are add-once. A direct-child `300-closed` must return
writer ownership to Work Host before the recovery source is edited.

`scientific_verdict` remains `null`.
