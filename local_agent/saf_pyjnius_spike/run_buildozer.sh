#!/usr/bin/env bash
set -euo pipefail
WORK=/root/saf-pyjnius-spike
LOG="${WORK}/build.log"
VENV=/opt/sideband-build-venv
echo "=== buildozer android debug (no deploy) ===" > "${LOG}"
export PATH="${VENV}/bin:${PATH}"
unset LD_LIBRARY_PATH CUDA_HOME || true
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
cd "${WORK}"
set +e
buildozer android debug >> "${LOG}" 2>&1
rc=$?
set -e
echo "=== buildozer exit ${rc} ===" >> "${LOG}"
echo "BUILD_EXIT=${rc}" >> "${LOG}"
exit "${rc}"
