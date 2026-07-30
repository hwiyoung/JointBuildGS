#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd -P)"
IMAGE="jointbuildgs-p0-tools:t0"
EXPECTED_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
CONTAINER_REPO="/workspace/JointBuildGS"
CONTROLLER="phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase3_archive.py"
LOCK="phases/p2-gsjso/configs/e5_c001/e5_c001_s3ap_phase3_archive_lock.json"
CONTROLLER_SHA256="$(sha256sum "${REPO}/${CONTROLLER}" | awk '{print $1}')"

if [[ $# -lt 3 || "$2" != "--wave" || ( "$3" != "base42" && "$3" != "final60" ) ]]; then
  echo "usage: $0 {preflight|archive|verify} --wave {base42|final60} [controller args]" >&2
  exit 64
fi
case "$1" in
  preflight|archive|verify) ;;
  *) echo "invalid command: $1" >&2; exit 64 ;;
esac

ACTUAL_ID="$(docker image inspect "${IMAGE}" --format '{{.Id}}')"
if [[ "${ACTUAL_ID}" != "${EXPECTED_ID}" ]]; then
  echo "tools image ID mismatch: expected=${EXPECTED_ID} actual=${ACTUAL_ID}" >&2
  exit 65
fi

exec docker run --rm -i \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e XDG_CACHE_HOME=/tmp \
  -e "S3AP_ARCHIVE_TOOLS_IMAGE_ID=${ACTUAL_ID}" \
  -e "S3AP_ARCHIVE_CONTROLLER_SHA256=${CONTROLLER_SHA256}" \
  -v "${REPO}:${CONTAINER_REPO}" \
  -w "${CONTAINER_REPO}" \
  "${ACTUAL_ID}" \
  python3 -c 'import hashlib,os,sys; p=sys.argv[1]; b=open(p,"rb").read(); actual=hashlib.sha256(b).hexdigest(); expected=os.environ["S3AP_ARCHIVE_CONTROLLER_SHA256"]; actual == expected or (_ for _ in ()).throw(SystemExit(f"controller SHA mismatch: expected={expected} actual={actual}")); sys.argv=[p,*sys.argv[2:]]; g={"__name__":"__main__","__file__":p,"__package__":None}; exec(compile(b,p,"exec"),g)' \
  "${CONTROLLER}" "$1" --wave "$3" --config "${LOCK}" "${@:4}"
