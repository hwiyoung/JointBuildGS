ARG BASE_IMAGE=jointbuildgs:dev
FROM ${BASE_IMAGE}

ARG BASE_IMAGE_ID
ARG GROUNDINGDINO_REVISION=856dde20aee659246248e20734ef9ba5214f5e44
ARG SEGMENT_ANYTHING_REVISION=dca509fe793f601edb92606367a655c15ac00fdf
ARG RUNTIME_REQUIREMENTS_SHA256

ENV P1W_GROUNDEDSAM_ROOT=/opt/jointbuildgs/p1w_groundedsam \
    P1W_GROUNDINGDINO_ROOT=/opt/jointbuildgs/p1w_groundedsam/GroundingDINO \
    P1W_SEGMENT_ANYTHING_ROOT=/opt/jointbuildgs/p1w_groundedsam/segment-anything \
    TORCH_CUDA_ARCH_LIST=8.6 \
    MAX_JOBS=4 \
    SOURCE_DATE_EPOCH=1722384000 \
    PYTHONHASHSEED=0

COPY phases/p2-gsjso/docker/pilot-groundedsam/requirements-runtime.txt \
     /opt/jointbuildgs/p1w_groundedsam/requirements-runtime.txt

RUN python -m pip install --no-cache-dir --no-deps \
        -r /opt/jointbuildgs/p1w_groundedsam/requirements-runtime.txt \
    && python -m pip check

RUN git init -q "${P1W_GROUNDINGDINO_ROOT}" \
    && git -C "${P1W_GROUNDINGDINO_ROOT}" remote add origin \
       https://github.com/IDEA-Research/GroundingDINO.git \
    && git -C "${P1W_GROUNDINGDINO_ROOT}" fetch --quiet --depth=1 origin \
       "${GROUNDINGDINO_REVISION}" \
    && git -C "${P1W_GROUNDINGDINO_ROOT}" checkout --quiet --detach FETCH_HEAD \
    && test "$(git -C "${P1W_GROUNDINGDINO_ROOT}" rev-parse HEAD)" = \
       "${GROUNDINGDINO_REVISION}" \
    && test -z "$(git -C "${P1W_GROUNDINGDINO_ROOT}" status --porcelain --untracked-files=no)"

RUN git init -q "${P1W_SEGMENT_ANYTHING_ROOT}" \
    && git -C "${P1W_SEGMENT_ANYTHING_ROOT}" remote add origin \
       https://github.com/facebookresearch/segment-anything.git \
    && git -C "${P1W_SEGMENT_ANYTHING_ROOT}" fetch --quiet --depth=1 origin \
       "${SEGMENT_ANYTHING_REVISION}" \
    && git -C "${P1W_SEGMENT_ANYTHING_ROOT}" checkout --quiet --detach FETCH_HEAD \
    && test "$(git -C "${P1W_SEGMENT_ANYTHING_ROOT}" rev-parse HEAD)" = \
       "${SEGMENT_ANYTHING_REVISION}" \
    && test -z "$(git -C "${P1W_SEGMENT_ANYTHING_ROOT}" status --porcelain --untracked-files=no)"

# Build only the exact-revision CUDA deformable-attention extension in place.
# The tracked source tree must remain clean; generated build intermediates are
# removed while the final extension remains as a separately receipted byte blob.
RUN cd "${P1W_GROUNDINGDINO_ROOT}" \
    && python setup.py build_ext --inplace \
    && rm -rf build \
    && rm -f groundingdino/version.py \
    && test -z "$(git status --porcelain --untracked-files=no)" \
    && test "$(find groundingdino -maxdepth 1 -type f -name '_C*.so' | wc -l)" -eq 1

ENV PYTHONPATH=/opt/jointbuildgs/p1w_groundedsam/GroundingDINO:/opt/jointbuildgs/p1w_groundedsam/segment-anything:/workspace/JointBuildGS
ENV LD_LIBRARY_PATH=/opt/conda/lib/python3.11/site-packages/torch/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64

RUN python - <<'PY'
import importlib.metadata as metadata
import torch
from groundingdino import _C
from groundingdino.models import build_model
from segment_anything import SamPredictor, sam_model_registry

expected = {
    "transformers": "4.40.2",
    "tokenizers": "0.19.1",
    "huggingface-hub": "0.23.5",
    "safetensors": "0.4.3",
    "timm": "0.9.16",
    "yapf": "0.40.2",
    "regex": "2024.5.15",
    "termcolor": "2.4.0",
    "tomli": "2.0.1",
    "pycocotools": "2.0.8",
}
for distribution, version in expected.items():
    actual = metadata.version(distribution)
    if actual != version:
        raise RuntimeError(f"{distribution}: {actual} != {version}")
print(_C.__file__)
print(build_model, SamPredictor, sorted(sam_model_registry))
PY

WORKDIR /workspace/JointBuildGS

LABEL org.opencontainers.image.title="JointBuildGS P1W pinned GroundedSAM runtime" \
      jointbuildgs.base_image_id="${BASE_IMAGE_ID}" \
      jointbuildgs.groundingdino_revision="${GROUNDINGDINO_REVISION}" \
      jointbuildgs.segment_anything_revision="${SEGMENT_ANYTHING_REVISION}" \
      jointbuildgs.runtime_requirements_sha256="${RUNTIME_REQUIREMENTS_SHA256}" \
      jointbuildgs.learning_runs="0" \
      jointbuildgs.inference_runs="0"
