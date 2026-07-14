FROM jointbuildgs:dev

ARG MAST3R_COMMIT=f5209afc300cec36239a7ac992263f36847bbba0

USER root
RUN git clone https://github.com/naver/mast3r.git /opt/mast3r \
    && cd /opt/mast3r \
    && git checkout --detach "${MAST3R_COMMIT}" \
    && git submodule update --init --recursive \
    && pip install --no-cache-dir -r /opt/mast3r/dust3r/requirements.txt \
    && pip install --no-cache-dir -r /opt/mast3r/requirements.txt \
    && git -C /opt/mast3r status --short \
    && test "$(git -C /opt/mast3r rev-parse HEAD)" = "${MAST3R_COMMIT}"

ENV PYTHONPATH=/opt/mast3r:/opt/mast3r/dust3r
WORKDIR /workspace/JointBuildGS

LABEL org.opencontainers.image.title="JointBuildGS S3-A-prime MASt3R measurement runtime" \
      org.opencontainers.image.revision="f5209afc300cec36239a7ac992263f36847bbba0" \
      jointbuildgs.learning_runs="0"
