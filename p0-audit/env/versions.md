# P0 T0 Tool Versions

- Generated: 2026-06-11T21:09:58+09:00
- Repository commit before T0 commit: 73092b5
- Runner: innopam (1000:1000)
- Note: checked existing conda envs `gs2ortho` and `priorda`; required CLIs were not present, so P0 uses isolated Docker services.

## Image Tags And Digests

```console
[colmap/colmap:latest] repo_digests=[colmap/colmap@sha256:187ca5ec98e55ed8fbec5f43f9d8f78b7a322b3b7413356634191f7a43c1efcf] image_id=sha256:f3fecec368989ea8d3ba7178416453c07419ff1b310c6df727e1b7efb8a3d4f2 base_name=<no value> base_digest=<no value>
[openmvs/openmvs-ubuntu:latest] repo_digests=[openmvs/openmvs-ubuntu@sha256:fcb172bd84903d679684e618b45dc6f7a7621de0da87e6dc40f8fb084016e35a] image_id=sha256:04a811d0965a8b6ce9b4e4f97dd5d55e654f725ec434ab35ae49da278d35999a base_name=<none> base_digest=<none>
[3dgi/roofer:v1.0.0] repo_digests=[3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2] image_id=sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba base_name=<no value> base_digest=<no value>
[pdal/pdal:latest] repo_digests=[pdal/pdal@sha256:dabc2c1b5de34fb2eff749ddba066cc66a7aa9448eac6e93743c32c7e4aa5051] image_id=sha256:d54e583112b44be3fe7b858a7178c63bb1e302d192f4a046c4de9d24b57dbba9 base_name=<no value> base_digest=<no value>
[jointbuildgs-p0-openmvs:t0] repo_digests=[] image_id=sha256:22f58491f086d39d1cb7a9784abd70a4fb9d04bf0a2c52c49c9537ce94b31f6a base_name=openmvs/openmvs-ubuntu:latest base_digest=sha256:fcb172bd84903d679684e618b45dc6f7a7621de0da87e6dc40f8fb084016e35a
[jointbuildgs-p0-tools:t0] repo_digests=[] image_id=sha256:39a96bd5e6ee65ebc6033a297227fe4332b99754950ea8ab9a14368d90dc66bb base_name=pdal/pdal:latest base_digest=sha256:dabc2c1b5de34fb2eff749ddba066cc66a7aa9448eac6e93743c32c7e4aa5051
```

## COLMAP GPU

```console
$ docker compose -f env/docker-compose.p0.yml run --rm colmap bash -lc nvidia-smi\ --query-gpu=name\,driver_version\ --format=csv\,noheader\;\ colmap\ help\ 2\>\&1\ \|\ head\ -n\ 4

==========
== CUDA ==
==========

CUDA Version 12.9.1

Container image Copyright (c) 2016-2023, NVIDIA CORPORATION & AFFILIATES. All rights reserved.

This container image and its contents are governed by the NVIDIA Deep Learning Container License.
By pulling and using the container, you accept the terms and conditions of this license:
https://developer.nvidia.com/ngc/nvidia-deep-learning-container-license

A copy of this license is made available in this container at /NGC-DL-CONTAINER-LICENSE for your convenience.

NVIDIA GeForce RTX 3090, 580.82.07
NVIDIA GeForce RTX 3090, 580.82.07
COLMAP 4.0.4 -- Structure-from-Motion and Multi-View Stereo
(Commit Unknown on Unknown with CUDA)

Usage:
```

## OpenMVS

```console
$ docker compose -f env/docker-compose.p0.yml run --rm openmvs bash -lc command\ -v\ InterfaceCOLMAP\ DensifyPointCloud\;\ InterfaceCOLMAP\ --help\ 2\>\&1\ \|\ head\ -n\ 5\;\ DensifyPointCloud\ --help\ 2\>\&1\ \|\ head\ -n\ 5
/usr/local/bin/OpenMVS/InterfaceCOLMAP
/usr/local/bin/OpenMVS/DensifyPointCloud
12:10:00 [App     ] Build date: Dec 10 2019, 20:59:37
12:10:00 [App     ] CPU: AMD Ryzen Threadripper 3990X 64-Core Processor  (128 cores)
12:10:00 [App     ] RAM: 125.65GB Physical Memory 2.00GB Virtual Memory
12:10:00 [App     ] OS: Linux 6.8.0-107-generic (x86_64)
12:10:00 [App     ] SSE & AVX compatible CPU & OS detected
12:10:00 [App     ] Build date: Dec 10 2019, 20:59:37
12:10:00 [App     ] CPU: AMD Ryzen Threadripper 3990X 64-Core Processor  (128 cores)
12:10:00 [App     ] RAM: 125.65GB Physical Memory 2.00GB Virtual Memory
12:10:00 [App     ] OS: Linux 6.8.0-107-generic (x86_64)
12:10:00 [App     ] SSE & AVX compatible CPU & OS detected
```

## Roofer

```console
$ docker compose -f env/docker-compose.p0.yml run --rm --entrypoint sh roofer -lc command\ -v\ roofer\;\ roofer\ -v
/opt/roofer/bin/roofer
roofer 1.0.0 (v1.0.0)
```

## PDAL GDAL val3dity citygml-tools laspy

```console
$ docker compose -f env/docker-compose.p0.yml run --rm tools bash -lc set\ -e\;\ pdal\ --version\;\ gdalinfo\ --version\;\ val3dity\ --version\ 2\>\&1\ \|\|\ val3dity\ -h\ 2\>\&1\ \|\ head\ -n\ 5\;\ citygml-tools\ --version\;\ python3\ -c\ \"import\ laspy\;\ print\(\\\"laspy\ \\\"\ +\ laspy.__version__\)\"
--------------------------------------------------------------------------------
pdal 2.10.1 (git-version: 3ef768)
--------------------------------------------------------------------------------

GDAL 3.13.1 "Iowa City", released 2026/06/01

val3dity  version: 2.6.0

citygml-tools 2.5.0
Copyright (C) 2018-2026 Claus Nagel <claus.nagel@gmail.com>

laspy 2.6.1
```
