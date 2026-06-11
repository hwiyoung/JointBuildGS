#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export P0_UID="${P0_UID:-$(id -u)}"
export P0_GID="${P0_GID:-$(id -g)}"

compose=(docker compose -f env/docker-compose.p0.yml)
versions_file="env/versions.md"

"${compose[@]}" build openmvs tools

run_section() {
  local title="$1"
  shift
  {
    printf '\n## %s\n\n' "$title"
    printf '```console\n'
    printf '$'
    printf ' %q' "$@"
    printf '\n'
    "$@" 2>&1
    printf '```\n'
  } >> "$versions_file"
}

image_section() {
  local title="$1"
  shift
  {
    printf '\n## %s\n\n' "$title"
    printf '```console\n'
    for image in "$@"; do
      docker image inspect \
        --format '{{.RepoTags}} repo_digests={{.RepoDigests}} image_id={{.Id}} base_name={{with .Config.Labels}}{{index . "org.opencontainers.image.base.name"}}{{else}}<none>{{end}} base_digest={{with .Config.Labels}}{{index . "org.opencontainers.image.base.digest"}}{{else}}<none>{{end}}' \
        "$image"
    done
    printf '```\n'
  } >> "$versions_file"
}

cat > "$versions_file" <<EOF
# P0 T0 Tool Versions

- Generated: $(date -Iseconds)
- Repository commit before T0 commit: $(git -C .. rev-parse --short HEAD)
- Runner: $(id -un) ($(id -u):$(id -g))
- Note: checked existing conda envs \`gs2ortho\` and \`priorda\`; required CLIs were not present, so P0 uses isolated Docker services.
EOF

image_section "Image Tags And Digests" \
  colmap/colmap@sha256:187ca5ec98e55ed8fbec5f43f9d8f78b7a322b3b7413356634191f7a43c1efcf \
  openmvs/openmvs-ubuntu@sha256:fcb172bd84903d679684e618b45dc6f7a7621de0da87e6dc40f8fb084016e35a \
  3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2 \
  pdal/pdal@sha256:dabc2c1b5de34fb2eff749ddba066cc66a7aa9448eac6e93743c32c7e4aa5051 \
  jointbuildgs-p0-openmvs:t0 \
  jointbuildgs-p0-tools:t0

run_section "COLMAP GPU" \
  "${compose[@]}" run --rm colmap bash -lc 'nvidia-smi --query-gpu=name,driver_version --format=csv,noheader; colmap help 2>&1 | head -n 4'

run_section "OpenMVS" \
  "${compose[@]}" run --rm openmvs bash -lc 'command -v InterfaceCOLMAP DensifyPointCloud; InterfaceCOLMAP --help 2>&1 | head -n 5; DensifyPointCloud --help 2>&1 | head -n 5'

run_section "Roofer" \
  "${compose[@]}" run --rm --entrypoint sh roofer -lc 'command -v roofer; roofer -v'

run_section "PDAL GDAL val3dity citygml-tools laspy" \
  "${compose[@]}" run --rm tools bash -lc 'set -e; pdal --version; gdalinfo --version; val3dity --version 2>&1 || val3dity -h 2>&1 | head -n 5; citygml-tools --version; python3 -c "import laspy; print(\"laspy \" + laspy.__version__)"'

printf 'Wrote %s\n' "$versions_file"
