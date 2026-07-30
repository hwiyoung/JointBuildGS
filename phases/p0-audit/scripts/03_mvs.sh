#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."

export P0_UID="${P0_UID:-$(id -u)}"
export P0_GID="${P0_GID:-$(id -g)}"

RUN_ID="${RUN_ID:-t3_mvs_$(date +%Y%m%d_%H%M%S)}"
RUN_DIR="runs/${RUN_ID}"
LOG_DIR="${RUN_DIR}/logs"
WORK_ROOT="data/work/mvs"
IMAGE_ROOT="data/work/images/Images"
SPARSE_IN="data/work/colmap/sparse/0"
RAW_IMAGES="data/raw/uav/Images.zip"
RAW_OPF="data/raw/uav/opf.zip"
DIM_LAZ="${WORK_ROOT}/dim/dim_v1.laz"
SECTION_PNG="docs/figs/dim_v1_als_section.png"
STATS_MD="docs/dim_v1_stats.md"

COLMAP_MAX_IMAGE_SIZE="${COLMAP_MAX_IMAGE_SIZE:-2200}"
COLMAP_MAX_NUM_FEATURES="${COLMAP_MAX_NUM_FEATURES:-4096}"
COLMAP_GPU_INDEX="${COLMAP_GPU_INDEX:--1}"
COLMAP_SEQ_OVERLAP="${COLMAP_SEQ_OVERLAP:-12}"
COLMAP_UNDISTORT_MAX_IMAGE_SIZE="${COLMAP_UNDISTORT_MAX_IMAGE_SIZE:-1400}"
MVS_RESOLUTION_LEVEL="${MVS_RESOLUTION_LEVEL:-4}"
MVS_MAX_RESOLUTION="${MVS_MAX_RESOLUTION:-1400}"
MVS_MIN_RESOLUTION="${MVS_MIN_RESOLUTION:-640}"
MVS_NUMBER_VIEWS="${MVS_NUMBER_VIEWS:-3}"
MVS_NUMBER_VIEWS_FUSE="${MVS_NUMBER_VIEWS_FUSE:-2}"
MVS_MAX_THREADS="${MVS_MAX_THREADS:-24}"
SECTION_BAND_WIDTH="${SECTION_BAND_WIDTH:-8}"
SECTION_MAX_POINTS="${SECTION_MAX_POINTS:-120000}"
FORCE="${FORCE:-0}"
SKIP_BUILD="${SKIP_BUILD:-0}"

COMPOSE=(docker compose -f env/docker-compose.p0.yml)

mkdir -p "$LOG_DIR" docs/figs "${WORK_ROOT}/colmap" "${WORK_ROOT}/triangulated" \
  "${WORK_ROOT}/colmap_dense" "${WORK_ROOT}/openmvs" "${WORK_ROOT}/dim"

if [[ "$FORCE" == "1" ]]; then
  rm -rf "$WORK_ROOT"
  mkdir -p "${WORK_ROOT}/colmap" "${WORK_ROOT}/triangulated" \
    "${WORK_ROOT}/colmap_dense" "${WORK_ROOT}/openmvs" "${WORK_ROOT}/dim"
fi

on_error() {
  local exit_code=$?
  local line_no=${1:-unknown}
  {
    echo
    echo "## T3 DIM Point Cloud"
    echo
    echo "- ${RUN_ID}: failed at line ${line_no} with exit code ${exit_code}. See ${RUN_DIR}/logs/."
  } >> phases/p0-audit/docs/issues.md
  exit "$exit_code"
}
trap 'on_error $LINENO' ERR

require_file() {
  local path=$1
  if [[ ! -f "$path" ]]; then
    echo "Required file missing: $path" >&2
    return 1
  fi
}

run_logged() {
  local name=$1
  shift
  local log="${LOG_DIR}/${name}.log"
  printf '$' | tee "$log"
  printf ' %q' "$@" | tee -a "$log"
  printf '\n' | tee -a "$log"
  "$@" 2>&1 | tee -a "$log"
}

write_run_config() {
  cat > "${RUN_DIR}/config.yaml" <<EOF
run_id: ${RUN_ID}
task: T3_DIM_point_cloud
inputs:
  raw_images: ${RAW_IMAGES}
  raw_opf: ${RAW_OPF}
  sparse_colmap: ${SPARSE_IN}
outputs:
  dim_laz: ${DIM_LAZ}
  stats: ${STATS_MD}
  section_png: ${SECTION_PNG}
parameters:
  colmap_max_image_size: ${COLMAP_MAX_IMAGE_SIZE}
  colmap_max_num_features: ${COLMAP_MAX_NUM_FEATURES}
  colmap_gpu_index: ${COLMAP_GPU_INDEX}
  colmap_seq_overlap: ${COLMAP_SEQ_OVERLAP}
  colmap_undistort_max_image_size: ${COLMAP_UNDISTORT_MAX_IMAGE_SIZE}
  mvs_resolution_level: ${MVS_RESOLUTION_LEVEL}
  mvs_max_resolution: ${MVS_MAX_RESOLUTION}
  mvs_min_resolution: ${MVS_MIN_RESOLUTION}
  mvs_number_views: ${MVS_NUMBER_VIEWS}
  mvs_number_views_fuse: ${MVS_NUMBER_VIEWS_FUSE}
  mvs_max_threads: ${MVS_MAX_THREADS}
  section_band_width_m: ${SECTION_BAND_WIDTH}
  section_max_points: ${SECTION_MAX_POINTS}
EOF
}

require_file "$RAW_IMAGES"
require_file "$RAW_OPF"
require_file "${SPARSE_IN}/cameras.txt"
require_file "${SPARSE_IN}/images.txt"
require_file "${SPARSE_IN}/points3D.txt"
write_run_config

if [[ "$SKIP_BUILD" != "1" ]]; then
  run_logged build_tools "${COMPOSE[@]}" build tools
fi

{
  echo "# T3 Tool Versions"
  echo
  echo "- Generated: $(date --iso-8601=seconds)"
  echo "- Run ID: ${RUN_ID}"
  echo "- Repository commit: $(git rev-parse --short HEAD)"
  echo "- Runner: $(id -un) ($(id -u):$(id -g))"
  echo
  echo '```console'
  echo '$ docker compose -f env/docker-compose.p0.yml run --rm colmap bash -lc "nvidia-smi ...; colmap help"'
  "${COMPOSE[@]}" run --rm -T colmap bash -lc \
    'nvidia-smi --query-gpu=name,driver_version --format=csv,noheader; colmap help 2>&1 | head -n 4'
  echo
  echo '$ docker compose -f env/docker-compose.p0.yml run --rm openmvs bash -lc "InterfaceCOLMAP --help; DensifyPointCloud --help"'
  "${COMPOSE[@]}" run --rm -T openmvs bash -lc \
    'command -v InterfaceCOLMAP DensifyPointCloud; InterfaceCOLMAP --help 2>&1 | head -n 8; DensifyPointCloud --help 2>&1 | head -n 8'
  echo
  echo '$ docker compose -f env/docker-compose.p0.yml run --rm tools bash -lc "pdal --version; lasinfo --version; python package versions"'
  "${COMPOSE[@]}" run --rm -T tools bash -lc \
    'pdal --version; lasinfo --version; python3 - <<PY
import importlib.metadata as metadata
import laspy, matplotlib, numpy
print("laspy " + laspy.__version__)
print("matplotlib " + matplotlib.__version__)
print("numpy " + numpy.__version__)
print("pyproj " + metadata.version("pyproj"))
PY'
  echo '```'
} > "${RUN_DIR}/versions.txt" 2>&1

if ! grep -q "## T3 DIM Point Cloud Additions" env/versions.md; then
  {
    echo
    echo "## T3 DIM Point Cloud Additions"
    echo
    echo '```console'
    docker image inspect jointbuildgs-p0-tools:t0 \
      --format='[jointbuildgs-p0-tools:t0] image_id={{.Id}} base_name={{index .Config.Labels "org.opencontainers.image.base.name"}} base_digest={{index .Config.Labels "org.opencontainers.image.base.digest"}}' \
      2>/dev/null || true
    echo
    echo "$ docker compose -f env/docker-compose.p0.yml run --rm tools bash -lc 'lasinfo --version'"
    "${COMPOSE[@]}" run --rm -T tools bash -lc 'lasinfo --version'
    echo '```'
  } >> env/versions.md
fi

image_count=$(find "$IMAGE_ROOT" -maxdepth 1 -type f 2>/dev/null | wc -l || true)
if [[ "$image_count" -lt 900 ]]; then
  run_logged extract_images "${COMPOSE[@]}" run --rm -T tools bash -lc \
    'set -euo pipefail
     mkdir -p /workspace/data/work/images
     unzip -q -n /workspace/data/raw/uav/Images.zip -d /workspace/data/work/images
     find /workspace/data/work/images/Images -maxdepth 1 -type f | wc -l'
fi

run_logged prepare_inputs "${COMPOSE[@]}" run --rm -T tools bash -lc \
  'python3 <<'"'"'PY'"'"'
from pathlib import Path

root = Path("/workspace")
sparse = root / "data/work/colmap/sparse/0"
images = root / "data/work/images/Images"
work = root / "data/work/mvs"
work.mkdir(parents=True, exist_ok=True)

camera_lines = [
    line.strip()
    for line in (sparse / "cameras.txt").read_text().splitlines()
    if line.strip() and not line.startswith("#")
]
if len(camera_lines) != 1:
    raise SystemExit(f"expected one camera, found {len(camera_lines)}")
camera = camera_lines[0].split()
camera_model = camera[1]
camera_params = ",".join(camera[4:])
if camera_model != "FULL_OPENCV":
    raise SystemExit(f"expected FULL_OPENCV camera, found {camera_model}")

names = []
with (sparse / "images.txt").open("r", encoding="utf-8") as fh:
    for line in fh:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 10:
            continue
        try:
            int(parts[0])
            float(parts[1])
            int(parts[8])
        except ValueError:
            continue
        names.append(" ".join(parts[9:]))
        next(fh, None)

missing = [name for name in names if not (images / name).is_file()]
if missing:
    preview = ", ".join(missing[:8])
    raise SystemExit(f"{len(missing)} model images missing from extracted Images/: {preview}")

(work / "image_list.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
(work / "colmap_camera_model.txt").write_text(camera_model + "\n", encoding="utf-8")
(work / "colmap_camera_params.txt").write_text(camera_params + "\n", encoding="utf-8")
(work / "prepare_summary.txt").write_text(
    f"camera_model={camera_model}\nimage_count={len(names)}\n"
    f"camera_params={camera_params}\n",
    encoding="utf-8",
)
print(f"camera_count=1")
print(f"image_count={len(names)}")
print(f"camera_model={camera_model}")
print(f"camera_params={camera_params}")
PY'

if [[ ! -f "${WORK_ROOT}/.features.done" ]]; then
  run_logged colmap_feature_extractor "${COMPOSE[@]}" run --rm -T colmap bash -lc \
    "set -euo pipefail
     params=\$(cat /workspace/data/work/mvs/colmap_camera_params.txt)
     model=\$(cat /workspace/data/work/mvs/colmap_camera_model.txt)
     rm -f /workspace/data/work/mvs/colmap/database.db
     colmap feature_extractor \
       --database_path /workspace/data/work/mvs/colmap/database.db \
       --image_path /workspace/data/work/images/Images \
       --image_list_path /workspace/data/work/mvs/image_list.txt \
       --ImageReader.single_camera 1 \
       --ImageReader.camera_model \"\${model}\" \
       --ImageReader.camera_params \"\${params}\" \
       --FeatureExtraction.use_gpu 1 \
       --FeatureExtraction.gpu_index \"${COLMAP_GPU_INDEX}\" \
       --FeatureExtraction.max_image_size \"${COLMAP_MAX_IMAGE_SIZE}\" \
       --SiftExtraction.max_num_features \"${COLMAP_MAX_NUM_FEATURES}\"
     touch /workspace/data/work/mvs/.features.done"
fi

if [[ ! -f "${WORK_ROOT}/.matches.done" ]]; then
  run_logged colmap_sequential_matcher "${COMPOSE[@]}" run --rm -T colmap bash -lc \
    "set -euo pipefail
     colmap sequential_matcher \
       --database_path /workspace/data/work/mvs/colmap/database.db \
       --FeatureMatching.use_gpu 1 \
       --FeatureMatching.gpu_index \"${COLMAP_GPU_INDEX}\" \
       --SequentialMatching.overlap \"${COLMAP_SEQ_OVERLAP}\" \
       --SequentialMatching.quadratic_overlap 1 \
       --SequentialMatching.loop_detection 0
     touch /workspace/data/work/mvs/.matches.done"
fi

run_logged prepare_colmap_db_id_model "${COMPOSE[@]}" run --rm -T tools bash -lc \
  'python3 <<'"'"'PY'"'"'
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

root = Path("/workspace")
src = root / "data/work/colmap/sparse/0"
dst = root / "data/work/mvs/colmap_input_db_ids"
db_path = root / "data/work/mvs/colmap/database.db"

if dst.exists():
    shutil.rmtree(dst)
dst.mkdir(parents=True)

with sqlite3.connect(db_path) as conn:
    rows = conn.execute("select image_id, name from images").fetchall()
name_to_db_id = {name: int(image_id) for image_id, name in rows}

shutil.copy2(src / "cameras.txt", dst / "cameras.txt")

image_count = 0
with (src / "images.txt").open("r", encoding="utf-8") as inp, \
    (dst / "images.txt").open("w", encoding="utf-8") as images_out, \
    (dst / "frames.txt").open("w", encoding="utf-8") as frames_out:
    images_out.write("# Image list with two lines of data per image:\n")
    images_out.write("#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n")
    images_out.write("#   POINTS2D[] as (X, Y, POINT3D_ID)\n")
    frames_out.write("# Frame list with one line of data per frame:\n")
    frames_out.write("#   FRAME_ID, RIG_ID, RIG_FROM_WORLD[QW,QX,QY,QZ,TX,TY,TZ], NUM_DATA_IDS, DATA_IDS[] as (SENSOR_TYPE, SENSOR_ID, DATA_ID)\n")

    for line in inp:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 10:
            continue
        try:
            int(parts[0])
            [float(v) for v in parts[1:8]]
            int(parts[8])
        except ValueError:
            continue

        name = " ".join(parts[9:])
        db_id = name_to_db_id.get(name)
        if db_id is None:
            raise SystemExit(f"image not found in COLMAP database: {name}")
        q_t = parts[1:8]
        camera_id = parts[8]
        images_out.write(" ".join([str(db_id), *q_t, camera_id, name]) + "\n\n")
        frames_out.write(" ".join([str(db_id), "1", *q_t, "1", "CAMERA", camera_id, str(db_id)]) + "\n")
        image_count += 1
        next(inp, None)

(dst / "points3D.txt").write_text(
    "# 3D point list with one line of data per point:\n"
    "#   POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[] as (IMAGE_ID, POINT2D_IDX)\n"
    "# Number of points: 0, mean track length: 0\n",
    encoding="utf-8",
)
(dst / "rigs.txt").write_text(
    "# Rig calib list with one line of data per calib:\n"
    "#   RIG_ID, NUM_SENSORS, REF_SENSOR_TYPE, REF_SENSOR_ID, SENSORS[] as (SENSOR_TYPE, SENSOR_ID, HAS_POSE, [QW,QX,QY,QZ,TX,TY,TZ])\n"
    "# Number of rigs: 1\n"
    "1 1 CAMERA 1\n",
    encoding="utf-8",
)

if image_count != len(name_to_db_id):
    raise SystemExit(f"model/database image count mismatch: model {image_count}, database {len(name_to_db_id)}")
print(f"db_id_model_images={image_count}")
print(f"output={dst}")
PY'

if [[ ! -f "${WORK_ROOT}/.triangulated.done" ]]; then
  run_logged colmap_point_triangulator "${COMPOSE[@]}" run --rm -T colmap bash -lc \
    'set -euo pipefail
     rm -rf /workspace/data/work/mvs/triangulated
     mkdir -p /workspace/data/work/mvs/triangulated
     colmap point_triangulator \
       --database_path /workspace/data/work/mvs/colmap/database.db \
       --image_path /workspace/data/work/images/Images \
       --input_path /workspace/data/work/mvs/colmap_input_db_ids \
       --output_path /workspace/data/work/mvs/triangulated \
       --clear_points 1 \
       --refine_intrinsics 0 \
       --Mapper.fix_existing_frames 1 \
       --Mapper.ba_refine_focal_length 0 \
       --Mapper.ba_refine_principal_point 0 \
       --Mapper.ba_refine_extra_params 0 \
       --Mapper.ba_refine_sensor_from_rig 0 \
       --Mapper.ba_global_max_num_iterations 20 \
       --Mapper.ba_local_max_num_iterations 10
     touch /workspace/data/work/mvs/.triangulated.done'
fi

if [[ ! -f "${WORK_ROOT}/.undistorted.done" ]]; then
  run_logged colmap_image_undistorter "${COMPOSE[@]}" run --rm -T colmap bash -lc \
    "set -euo pipefail
     rm -rf /workspace/data/work/mvs/colmap_dense
     mkdir -p /workspace/data/work/mvs/colmap_dense
     colmap image_undistorter \
       --image_path /workspace/data/work/images/Images \
       --input_path /workspace/data/work/mvs/triangulated \
       --output_path /workspace/data/work/mvs/colmap_dense \
       --output_type COLMAP \
       --max_image_size \"${COLMAP_UNDISTORT_MAX_IMAGE_SIZE}\"
     touch /workspace/data/work/mvs/.undistorted.done"
fi

if [[ ! -f "${WORK_ROOT}/.colmap_txt.done" ]]; then
  run_logged colmap_model_converter "${COMPOSE[@]}" run --rm -T colmap bash -lc \
    'set -euo pipefail
     rm -rf /workspace/data/work/mvs/openmvs/colmap_txt
     mkdir -p /workspace/data/work/mvs/openmvs/colmap_txt/sparse
     colmap model_converter \
       --input_path /workspace/data/work/mvs/colmap_dense/sparse \
       --output_path /workspace/data/work/mvs/openmvs/colmap_txt/sparse \
       --output_type TXT
     touch /workspace/data/work/mvs/.colmap_txt.done'
fi

if [[ ! -f "${WORK_ROOT}/.interface_colmap.done" ]]; then
  run_logged openmvs_interface_colmap "${COMPOSE[@]}" run --rm -T openmvs bash -lc \
    'set -euo pipefail
     cd /workspace/data/work/mvs/openmvs
     rm -f scene.mvs
     InterfaceCOLMAP \
       -i /workspace/data/work/mvs/openmvs/colmap_txt \
       -o scene.mvs \
       --image-folder ../../colmap_dense/images
     test -f scene.mvs
     touch /workspace/data/work/mvs/.interface_colmap.done'
fi

if [[ ! -f "${WORK_ROOT}/.densified.done" ]]; then
  run_logged openmvs_densify_point_cloud "${COMPOSE[@]}" run --rm -T openmvs bash -lc \
    "set -euo pipefail
     cd /workspace/data/work/mvs/openmvs
     rm -f dim_dense.ply dim_dense.mvs
     DensifyPointCloud \
       -i scene.mvs \
       -o dim_dense.ply \
       --resolution-level \"${MVS_RESOLUTION_LEVEL}\" \
       --max-resolution \"${MVS_MAX_RESOLUTION}\" \
       --min-resolution \"${MVS_MIN_RESOLUTION}\" \
       --number-views \"${MVS_NUMBER_VIEWS}\" \
       --number-views-fuse \"${MVS_NUMBER_VIEWS_FUSE}\" \
       --estimate-colors 2 \
       --estimate-normals 0 \
       --max-threads \"${MVS_MAX_THREADS}\"
     test -s dim_dense.ply
     touch /workspace/data/work/mvs/.densified.done"
fi

if [[ ! -f "${WORK_ROOT}/.dim_laz.done" ]]; then
  run_logged convert_ply_to_laz "${COMPOSE[@]}" run --rm -T tools bash -lc \
    'python3 <<'"'"'PY'"'"'
import json
from pathlib import Path

root = Path("/workspace")
ref = json.loads((root / "data/work/opf/opf/scene_reference_frame.json").read_text())
shift = ref.get("shift", ref.get("base_to_canonical", {}).get("shift"))
if shift is None:
    raise SystemExit("scene_reference_frame.json does not contain shift/base_to_canonical.shift")
translation = [-float(shift[0]), -float(shift[1]), -float(shift[2])]
pipeline = {
    "pipeline": [
        {"type": "readers.ply", "filename": "/workspace/data/work/mvs/openmvs/dim_dense.ply"},
        {
            "type": "filters.transformation",
            "matrix": (
                f"1 0 0 {translation[0]} "
                f"0 1 0 {translation[1]} "
                f"0 0 1 {translation[2]} "
                "0 0 0 1"
            ),
        },
        {
            "type": "writers.las",
            "filename": "/workspace/data/work/mvs/dim/dim_v1.laz",
            "a_srs": "EPSG:25832",
            "compression": "lazperf",
            "minor_version": 4,
            "dataformat_id": 3,
        },
    ]
}
Path("/workspace/data/work/mvs/dim").mkdir(parents=True, exist_ok=True)
(root / "data/work/mvs/dim/ply_to_laz.json").write_text(json.dumps(pipeline, indent=2), encoding="utf-8")
print(f"translation={translation}")
PY
   pdal pipeline /workspace/data/work/mvs/dim/ply_to_laz.json
   lasinfo /workspace/data/work/mvs/dim/dim_v1.laz
   touch /workspace/data/work/mvs/.dim_laz.done'
fi

if [[ ! -f "${WORK_ROOT}/.stats.done" ]]; then
  run_logged stats_and_section "${COMPOSE[@]}" run --rm -T tools bash -lc \
    "SECTION_BAND_WIDTH='${SECTION_BAND_WIDTH}' SECTION_MAX_POINTS='${SECTION_MAX_POINTS}' python3 <<'PY'
from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path

import laspy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

root = Path('/workspace')
dim_path = root / 'data/work/mvs/dim/dim_v1.laz'
als_paths = sorted((root / 'data/raw/als').glob('*.laz'))
stats_path = root / 'docs/dim_v1_stats.md'
section_png = root / 'docs/figs/dim_v1_als_section.png'
run_versions = Path('/workspace/runs') / '${RUN_ID}' / 'versions.txt'
run_config = Path('/workspace/runs') / '${RUN_ID}' / 'config.yaml'
band_width = float(os.environ['SECTION_BAND_WIDTH'])
max_points = int(os.environ['SECTION_MAX_POINTS'])

if not als_paths:
    raise SystemExit('no ALS LAZ files found under data/raw/als')

with laspy.open(dim_path) as fh:
    dim_header = fh.header
    dim_count = int(dim_header.point_count)
    dim_mins = dim_header.mins
    dim_maxs = dim_header.maxs
    dim_las = fh.read()
    dim_x = np.asarray(dim_las.x)
    dim_y = np.asarray(dim_las.y)
    dim_z = np.asarray(dim_las.z)

if dim_count == 0:
    raise SystemExit('DIM LAZ contains zero points')

pdal_metadata = json.loads(
    subprocess.check_output(
        ['pdal', 'info', '--metadata', str(dim_path)],
        text=True,
    )
)
spatial_ref = pdal_metadata.get('metadata', {}).get('spatialreference', '')
if '25832' not in spatial_ref and 'EPSG:25832' not in spatial_ref:
    raise SystemExit(f'DIM CRS assertion failed: expected EPSG:25832, got {spatial_ref[:240]}')
epsg = 25832

width = float(dim_maxs[0] - dim_mins[0])
depth = float(dim_maxs[1] - dim_mins[1])
area = width * depth
density = dim_count / area if area > 0 else 0.0
center_y = float(np.median(dim_y))
half_band = band_width / 2.0
dim_band = np.abs(dim_y - center_y) <= half_band

als_x_parts = []
als_y_parts = []
als_z_parts = []
als_total_clip = 0
als_total_band = 0
for path in als_paths:
    with laspy.open(path) as fh:
        h = fh.header
        if h.maxs[0] < dim_mins[0] or h.mins[0] > dim_maxs[0] or h.maxs[1] < dim_mins[1] or h.mins[1] > dim_maxs[1]:
            continue
        pts = fh.read()
    x = np.asarray(pts.x)
    y = np.asarray(pts.y)
    z = np.asarray(pts.z)
    clip = (x >= dim_mins[0]) & (x <= dim_maxs[0]) & (y >= dim_mins[1]) & (y <= dim_maxs[1])
    als_total_clip += int(np.count_nonzero(clip))
    band = clip & (np.abs(y - center_y) <= half_band)
    als_total_band += int(np.count_nonzero(band))
    if np.any(band):
        als_x_parts.append(x[band])
        als_y_parts.append(y[band])
        als_z_parts.append(z[band])

if not np.any(dim_band):
    raise SystemExit('no DIM points in requested section band')
if not als_x_parts:
    raise SystemExit('no ALS points overlap the DIM section band')

def sample_xy_z(x: np.ndarray, z: np.ndarray, limit: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    if x.size <= limit:
        return x, z
    rng = np.random.default_rng(seed)
    idx = rng.choice(x.size, size=limit, replace=False)
    return x[idx], z[idx]

dim_sec_x, dim_sec_z = sample_xy_z(dim_x[dim_band], dim_z[dim_band], max_points, 13)
als_x = np.concatenate(als_x_parts)
als_z = np.concatenate(als_z_parts)
als_sec_x, als_sec_z = sample_xy_z(als_x, als_z, max_points, 29)

plt.figure(figsize=(12, 7))
plt.scatter(dim_sec_x, dim_sec_z, s=1.2, c='#d62728', alpha=0.35, label=f'DIM ({dim_sec_x.size:,} sampled)')
plt.scatter(als_sec_x, als_sec_z, s=1.6, c='#1f77b4', alpha=0.45, label=f'ALS ({als_sec_x.size:,} sampled)')
plt.xlabel('EPSG:25832 X (m)')
plt.ylabel('Z (m)')
plt.title(f'ALS vs DIM section, y={center_y:.2f} +/- {half_band:.1f} m')
plt.legend(markerscale=5)
plt.grid(True, linewidth=0.3, alpha=0.4)
plt.tight_layout()
section_png.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(section_png, dpi=180)

with os.popen('lasinfo /workspace/data/work/mvs/dim/dim_v1.laz') as pipe:
    lasinfo_text = pipe.read().strip()
lasinfo_block = '\\n'.join(f'    {line}' for line in lasinfo_text.splitlines())

stats_path.write_text(
    '# DIM v1 Point Cloud Stats\\n\\n'
    f'- Run ID: {os.environ.get(\"RUN_ID\", \"${RUN_ID}\")}\\n'
    f'- Output LAZ: data/work/mvs/dim/dim_v1.laz\\n'
    f'- CRS assertion: EPSG:{epsg}\\n'
    f'- DIM point count: {dim_count:,}\\n'
    f'- DIM XY density: {density:.6f} points/m^2 over {area:.3f} m^2\\n'
    f'- DIM bounds min XYZ: {dim_mins[0]:.3f}, {dim_mins[1]:.3f}, {dim_mins[2]:.3f}\\n'
    f'- DIM bounds max XYZ: {dim_maxs[0]:.3f}, {dim_maxs[1]:.3f}, {dim_maxs[2]:.3f}\\n'
    f'- ALS overlap points in DIM XY bounds: {als_total_clip:,}\\n'
    f'- Section band: y={center_y:.3f} +/- {half_band:.3f} m\\n'
    f'- Section points before sampling: DIM {int(np.count_nonzero(dim_band)):,}, ALS {als_total_band:,}\\n'
    f'- Section comparison PNG: docs/figs/dim_v1_als_section.png\\n'
    f'- Run config: {run_config.relative_to(root)}\\n'
    f'- Run versions: {run_versions.relative_to(root)}\\n\\n'
    '## lasinfo output\\n\\n'
    + lasinfo_block
    + '\\n',
    encoding='utf-8',
)
print(f'dim_point_count={dim_count}')
print(f'dim_density={density:.6f}')
print(f'dim_bounds_min={dim_mins}')
print(f'dim_bounds_max={dim_maxs}')
print(f'als_overlap_points={als_total_clip}')
print(f'section_png={section_png}')
PY"
  touch "${WORK_ROOT}/.stats.done"
fi

echo "T3 complete"
echo "DIM LAZ: ${DIM_LAZ}"
echo "Stats: ${STATS_MD}"
echo "Section PNG: ${SECTION_PNG}"
