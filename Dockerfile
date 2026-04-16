FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TORCH_CUDA_ARCH_LIST="8.6" \
    PATH=/opt/conda/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git wget curl ca-certificates \
        libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
        libgomp1 ninja-build \
        colmap \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q https://repo.anaconda.com/miniconda/Miniconda3-py311_24.3.0-0-Linux-x86_64.sh -O /tmp/mc.sh && \
    bash /tmp/mc.sh -b -p /opt/conda && rm /tmp/mc.sh && \
    conda install -y python=3.11 && conda clean -afy

RUN pip install --no-cache-dir \
        torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu121

RUN pip install --no-cache-dir \
        numpy==1.26.4 scipy==1.13.1 \
        tifffile==2024.8.30 imagecodecs==2024.6.1 \
        Pillow==10.4.0 opencv-python==4.10.0.84 imageio==2.35.1 \
        open3d==0.18.0 trimesh==4.4.9 shapely==2.0.6 \
        lxml==5.3.0 pyyaml==6.0.2 tqdm==4.66.5 einops==0.8.0 \
        tensorboard==2.17.1 \
        scikit-learn==1.5.2 scikit-image==0.24.0 \
        plyfile==1.1 matplotlib==3.9.2

RUN pip install --no-cache-dir gsplat==1.4.0

WORKDIR /workspace/JointBuildGS
ENV PYTHONPATH=/workspace/JointBuildGS:$PYTHONPATH
CMD ["bash"]
