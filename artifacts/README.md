# Artifact resolvers

This directory contains only small, tracked control files. Bulk datasets,
checkpoints, point clouds, meshes, images, logs, caches, and run workspaces are
stored outside the Git working tree.

The current local backend is the sibling directory
`../JointBuildGS-artifacts`. Docker Compose mounts it at
`/artifacts/JointBuildGS` and provides compatibility mounts for historical
runtime paths. Override the host location with `JBGS_ARTIFACT_HOST_ROOT`.

The local backend is an organization boundary, not a backup. Do not remove or
replace payloads from it without a separate retention and recovery decision.
Tracked manifests under `artifacts/manifests/` record every physical move.
